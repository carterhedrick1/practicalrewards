#!/usr/bin/env python3
"""Deterministic orchestrator for the Practical Rewards daily blog pipeline."""

from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from common import ROOT, STATE, read_json, slugify_brand_name


STEPS = ("ingest", "plan", "draft", "build", "verify", "social")
SCRIPT_NAMES = {
    "ingest": "ingest.py",
    "plan": "plan.py",
    "draft": "draft.py",
    "build": "build_post.py",
    "verify": "verify_post.py",
    "social": "social.py",
}
DURABLE_STATE_FILES = ("seen.json", "published.json")
SCRATCH_STATE_FILES = (
    "inbox.json", "todays-brief.json", "draft.json", "verify-report.json",
    "articles.json",
)
PIPELINE_STATE_FILES = DURABLE_STATE_FILES + SCRATCH_STATE_FILES
STATIC_PUBLISH_PATHS = ("blog/index.html", "blog/feed.xml", "sitemap.xml")
INSTAGRAM_PREVIEW_URL = "http://carters-mac-mini.tailb1c452.ts.net:8000/preview/instagram/"


@dataclass
class Snapshot:
    path: Path
    existed: bool
    data: bytes | None
    tracked: bool


class StepFailure(RuntimeError):
    def __init__(self, step: str, returncode: int, detail: str | None = None) -> None:
        super().__init__(detail or f"{step} exited with status {returncode}")
        self.step = step
        self.returncode = returncode


class DailyRunner:
    def __init__(self, dry_run: bool, review: bool = False) -> None:
        self.dry_run = dry_run
        self.review = review
        self.today = dt.date.today().isoformat()
        self.log_path = STATE / "logs" / f"{self.today}.log"
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.snapshots: list[Snapshot] = []
        self.state_snapshots: list[Snapshot] = []
        self.publish_base_head: str | None = None
        self.current_step = "startup"
        self.last_step_stderr = ""
        self.started_at = dt.datetime.now().astimezone()
        self.social_dir: Path | None = None
        self.social_note = ""
        self.social_ready = False

    def log(self, message: str) -> None:
        stamp = dt.datetime.now().astimezone().isoformat(timespec="seconds")
        line = f"[{stamp}] {message}"
        print(line)
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def run_step(self, step: str, env: dict[str, str] | None = None, args: list[str] | None = None) -> int:
        self.current_step = step
        command = [sys.executable, str(ROOT / "tools" / SCRIPT_NAMES[step]), *(args or [])]
        self.log(f"START {step}: {' '.join(command)}")
        step_env = os.environ.copy()
        if env:
            step_env.update(env)
        try:
            result = subprocess.run(
                command,
                cwd=ROOT,
                env=step_env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=1800,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            stdout = error.stdout or ""
            stderr = error.stderr or ""
            if isinstance(stdout, bytes):
                stdout = stdout.decode(errors="replace")
            if isinstance(stderr, bytes):
                stderr = stderr.decode(errors="replace")
            self.last_step_stderr = stderr
            for stream_name, value in (("stdout", stdout), ("stderr", stderr)):
                for line in value.rstrip().splitlines():
                    self.log(f"{step} {stream_name}: {line}")
            message = f"{step} timed out after 1800 seconds"
            self.log(f"END {step}: {message}")
            raise StepFailure(step, -1, message) from error
        self.last_step_stderr = result.stderr
        for stream_name, value in (("stdout", result.stdout), ("stderr", result.stderr)):
            if value:
                for line in value.rstrip().splitlines():
                    self.log(f"{step} {stream_name}: {line}")
        self.log(f"END {step}: exit {result.returncode}")
        return result.returncode

    def verify_env(self) -> dict[str, str]:
        review_mode = self.review and not self.dry_run
        return {"VERIFY_MODE": "review" if review_mode else "auto"}

    @staticmethod
    def verifier_notes(report: Any) -> list[str]:
        if not isinstance(report, dict):
            return []
        notes = report.get("soft_failures", [])
        return [str(note) for note in notes] if isinstance(notes, list) else []

    @staticmethod
    def verifier_note_lines(notes: list[str]) -> list[str]:
        if not notes:
            return []
        return [
            f"{len(notes)} verifier notes",
            *(
                note if len(note) <= 140 else note[:137].rstrip() + "..."
                for note in notes[:3]
            ),
        ]

    def log_verifier_notes(self, notes: list[str]) -> None:
        for note in notes:
            self.log(f"verifier note: {note}")

    def is_tracked(self, path: Path) -> bool:
        relative = str(path.relative_to(ROOT))
        result = subprocess.run(
            ["git", "ls-files", "--error-unmatch", "--", relative],
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return result.returncode == 0

    def run_git(
        self,
        command: list[str],
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            command,
            cwd=ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        output = (result.stdout + result.stderr).strip()
        if output:
            for line in output.splitlines():
                self.log(f"git: {line}")
        return result

    def publish_paths(self, slug: str | None = None) -> list[str]:
        paths = list(STATIC_PUBLISH_PATHS)
        if slug:
            paths.append(f"blog/{slug}.html")
            paths.extend(self.referenced_brand_paths(slug))
            paths.extend(self.social_asset_paths(slug))
        paths.extend(f"tools/state/{name}" for name in DURABLE_STATE_FILES)
        return paths

    def social_asset_paths(self, slug: str) -> list[str]:
        """Return the generated Instagram/share assets for this slug, if any."""
        social_dir = ROOT / "social" / slug
        if not social_dir.is_dir():
            return []
        return sorted(
            str(path.relative_to(ROOT))
            for path in social_dir.iterdir()
            if path.is_file() and not path.name.startswith(".")
        )

    def strip_share_image_tags(self, slug: str) -> None:
        """Remove og:image/twitter:image tags when no share image was generated."""
        post_path = ROOT / "blog" / f"{slug}.html"
        if not post_path.is_file():
            return
        lines = post_path.read_text(encoding="utf-8").splitlines(keepends=True)
        kept = [
            line for line in lines
            if not re.search(r'(?:property="og:image(?::width|:height)?"|name="twitter:(?:card|image)")', line)
        ]
        post_path.write_text("".join(kept), encoding="utf-8")

    def referenced_brand_paths(self, slug: str) -> list[str]:
        """Return only local brand assets referenced by this run's built page."""
        post_path = ROOT / "blog" / f"{slug}.html"
        if not post_path.is_file():
            return []
        value = post_path.read_text(encoding="utf-8")
        paths: set[str] = set()
        for reference in re.findall(
            r"\b(?:href|src)\s*=\s*['\"]([^'\"]+)['\"]",
            value,
            flags=re.IGNORECASE,
        ):
            relative = urllib.parse.unquote(urllib.parse.urlsplit(reference).path).lstrip("/")
            if not relative.startswith("images/brands/"):
                continue
            filename = relative.removeprefix("images/brands/")
            if filename and Path(filename).name == filename:
                paths.add(f"images/brands/{filename}")
        return sorted(paths)

    def preflight_publish(self) -> None:
        if not self.review:
            fetch = self.run_git(["git", "fetch", "origin", "main"])
            if fetch.returncode != 0:
                raise RuntimeError("could not fetch origin/main for publish preflight")
        branch = self.run_git(["git", "branch", "--show-current"])
        if branch.returncode != 0 or branch.stdout.strip() != "main":
            raise RuntimeError("publishing requires the checked-out branch to be main")
        local = self.run_git(["git", "rev-parse", "HEAD"])
        if local.returncode != 0:
            raise RuntimeError("could not resolve the local main commit")
        if not self.review:
            upstream = self.run_git(["git", "rev-parse", "refs/remotes/origin/main"])
            if upstream.returncode != 0:
                raise RuntimeError("could not resolve origin/main commit")
            if local.stdout.strip() != upstream.stdout.strip():
                raise RuntimeError("publishing requires HEAD to exactly match origin/main")
        status = self.run_git([
            "git", "status", "--porcelain=v1", "--", *self.publish_paths(),
        ])
        brand_status = self.run_git([
            "git", "status", "--porcelain=v1", "--untracked-files=no", "--",
            "images/brands/",
        ])
        if status.returncode != 0 or brand_status.returncode != 0:
            raise RuntimeError("could not inspect publish targets")
        dirty_targets = status.stdout.strip().splitlines()
        dirty_targets.extend(brand_status.stdout.strip().splitlines())
        if dirty_targets:
            raise RuntimeError(
                "publish target has pre-existing work; aborting before ingest: "
                + " | ".join(dirty_targets)
            )
        self.publish_base_head = local.stdout.strip()
        mode = "Review" if self.review else "Publish"
        self.log(f"{mode} preflight passed at {self.publish_base_head}")

    def capture_pipeline_state(self) -> None:
        paths = [STATE / name for name in PIPELINE_STATE_FILES]
        self.state_snapshots = [
            Snapshot(path, path.exists(), path.read_bytes() if path.exists() else None, self.is_tracked(path))
            for path in paths
        ]

    def restore_pipeline_state(self) -> None:
        for snapshot in self.state_snapshots:
            if snapshot.existed:
                snapshot.path.parent.mkdir(parents=True, exist_ok=True)
                snapshot.path.write_bytes(snapshot.data or b"")
            elif snapshot.path.exists():
                snapshot.path.unlink()
        if self.state_snapshots:
            self.log("Restored pipeline state to its exact pre-ingest contents")

    def capture_build_state(self) -> None:
        draft = read_json(STATE / "draft.json", {})
        slug = str(draft.get("slug", "")) if isinstance(draft, dict) else ""
        if not slug:
            raise ValueError("cannot snapshot build state without a draft slug")
        paths = [
            ROOT / "blog" / "index.html",
            ROOT / "blog" / "feed.xml",
            ROOT / "blog" / f"{slug}.html",
            ROOT / "sitemap.xml",
            STATE / "published.json",
        ]
        hero = draft.get("hero") if isinstance(draft, dict) else None
        art = hero.get("art") if isinstance(hero, dict) else None
        brand_name = art.get("brand_name") if isinstance(art, dict) else None
        brand_slug = slugify_brand_name(brand_name) if isinstance(brand_name, str) else ""
        if brand_slug:
            paths.append(ROOT / "images" / "brands" / f"{brand_slug}.png")
        self.snapshots = [
            Snapshot(path, path.exists(), path.read_bytes() if path.exists() else None, self.is_tracked(path))
            for path in paths
        ]
        social_dir = ROOT / "social" / slug
        self.social_dir = None if social_dir.exists() else social_dir
        self.log(f"Captured pre-build state for {len(paths)} paths")

    def restore_build_state(self) -> None:
        if not self.snapshots:
            return
        tracked_site_paths = [
            str(snapshot.path.relative_to(ROOT))
            for snapshot in self.snapshots
            if snapshot.tracked and (snapshot.path.parent == ROOT / "blog" or snapshot.path == ROOT / "sitemap.xml")
        ]
        if tracked_site_paths:
            result = subprocess.run(
                ["git", "checkout", "--", *tracked_site_paths],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            if result.returncode != 0:
                self.log(f"WARNING git checkout restore failed: {(result.stderr or result.stdout).strip()}")
        # Reapply exact pre-run bytes so separately approved local modifications survive restoration.
        for snapshot in self.snapshots:
            if snapshot.existed:
                snapshot.path.parent.mkdir(parents=True, exist_ok=True)
                snapshot.path.write_bytes(snapshot.data or b"")
            elif snapshot.path.exists():
                snapshot.path.unlink()
        if self.social_dir is not None and self.social_dir.exists():
            shutil.rmtree(self.social_dir, ignore_errors=True)
        self.log("Restored all build-touched paths to their exact pre-run state")

    def notify(
        self,
        title: str,
        message: str,
        link: str | None = None,
        actions: list[tuple[str, str]] | None = None,
    ) -> None:
        """Send an ntfy push (with optional tap buttons) and a macOS notification."""
        def log_notification(message: str) -> None:
            try:
                self.log(message)
            except Exception:
                pass

        try:
            config_path = Path("~/.config/practicalrewards/notify.json").expanduser()
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            config = None
        except Exception:
            log_notification("WARNING ntfy: failed")
            config = None

        topic = config.get("ntfy_topic") if isinstance(config, dict) else None
        if isinstance(topic, str) and topic.strip():
            try:
                priority_word = "high" if "held" in title.casefold() or "fail" in title.casefold() else "default"
                priority_int = 4 if priority_word == "high" else 3
                payload = {
                    "topic": topic.strip(),
                    "title": title,
                    "message": message,
                    "priority": priority_int,
                }
                if link is not None:
                    payload["click"] = link
                if actions:
                    payload["actions"] = [
                        {"action": "view", "label": label, "url": url, "clear": True}
                        for label, url in actions[:3]
                    ]
                request = urllib.request.Request(
                    "https://ntfy.sh",
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                for attempt in range(2):
                    try:
                        with urllib.request.urlopen(request, timeout=10):
                            pass
                        log_notification("ntfy: sent")
                        break
                    except Exception:
                        if attempt < 1:
                            time.sleep(2)
                        else:
                            raise
            except Exception:
                log_notification("WARNING ntfy: failed")

        def osascript_safe(value: str) -> str:
            return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")

        try:
            script = (
                f'display notification "{osascript_safe(message)}" '
                f'with title "{osascript_safe(title)}"'
            )
            result = subprocess.run(
                ["osascript", "-e", script],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                timeout=15,
                check=False,
            )
            if result.returncode != 0:
                log_notification("WARNING osascript: failed")
        except Exception:
            log_notification("WARNING osascript: failed")

    def hold_failed_post(self) -> str:
        report = read_json(STATE / "verify-report.json", {})
        failures = report.get("failures", []) if isinstance(report, dict) else []
        first_reason = str(failures[0]) if failures else "verification failed"
        draft = read_json(STATE / "draft.json", {})
        slug = str(draft.get("slug", "post")) if isinstance(draft, dict) else "post"
        held_at = self.started_at
        held = STATE / "held" / held_at.strftime("%Y-%m-%d-%H%M%S")
        while held.exists():
            held_at += dt.timedelta(seconds=1)
            held = STATE / "held" / held_at.strftime("%Y-%m-%d-%H%M%S")
        held.mkdir(parents=True, exist_ok=True)
        for path in (STATE / "draft.json", STATE / "verify-report.json", ROOT / "blog" / f"{slug}.html"):
            if path.exists():
                destination = held / path.name
                shutil.move(str(path), str(destination))
        self.log(f"Held failed post artifacts in {held}")
        return first_reason

    def git_publish(self) -> tuple[str, str]:
        draft = read_json(STATE / "draft.json", {})
        title = str(draft.get("title", "Untitled")) if isinstance(draft, dict) else "Untitled"
        slug = str(draft.get("slug", "")) if isinstance(draft, dict) else ""
        if not slug:
            raise ValueError("cannot publish without a draft slug")
        paths = self.publish_paths(slug)
        if not self.publish_base_head:
            raise RuntimeError("publish preflight was not completed")
        branch = self.run_git(["git", "branch", "--show-current"])
        current = self.run_git(["git", "rev-parse", "HEAD"])
        if branch.stdout.strip() != "main":
            raise RuntimeError("branch changed after preflight; refusing to publish")
        if any(result.returncode != 0 for result in (branch, current)):
            raise RuntimeError("could not re-check publish base")
        if current.stdout.strip() != self.publish_base_head:
            raise RuntimeError("HEAD changed after preflight; refusing to publish")
        if not self.review:
            upstream = self.run_git(["git", "rev-parse", "refs/remotes/origin/main"])
            if upstream.returncode != 0:
                raise RuntimeError("could not re-check origin/main")
            if upstream.stdout.strip() != self.publish_base_head:
                raise RuntimeError("origin/main changed after preflight; refusing to publish")

        descriptor, temporary_name = tempfile.mkstemp(prefix="practical-rewards-index-", suffix=".gitindex")
        os.close(descriptor)
        temporary_index = Path(temporary_name)
        temporary_index.unlink()
        isolated_env = os.environ.copy()
        isolated_env["GIT_INDEX_FILE"] = str(temporary_index)
        new_entries: dict[str, tuple[str, str]] = {}
        old_entries: dict[str, tuple[str, str] | None] = {}
        try:
            for command in (["git", "read-tree", self.publish_base_head], ["git", "add", "--", *paths]):
                result = self.run_git(command, env=isolated_env)
                if result.returncode != 0:
                    raise RuntimeError(f"command failed ({' '.join(command)}), exit {result.returncode}")
            tree_result = self.run_git(["git", "write-tree"], env=isolated_env)
            if tree_result.returncode != 0:
                raise RuntimeError("could not write isolated publish tree")
            commit_result = self.run_git([
                "git", "commit-tree", tree_result.stdout.strip(),
                "-p", self.publish_base_head, "-m", f"Post: {title}",
            ])
            if commit_result.returncode != 0:
                raise RuntimeError("could not create isolated publish commit")
            new_head = commit_result.stdout.strip()
            for path in paths:
                entry = self.run_git(["git", "ls-tree", new_head, "--", path])
                if entry.returncode != 0 or not entry.stdout.strip():
                    raise RuntimeError(f"published commit is missing expected path: {path}")
                metadata, listed_path = entry.stdout.rstrip("\n").split("\t", 1)
                mode, object_type, object_id = metadata.split()
                if object_type != "blob" or listed_path != path:
                    raise RuntimeError(f"unexpected tree entry for publish path: {path}")
                new_entries[path] = (mode, object_id)
                old_entry = self.run_git(["git", "ls-files", "--stage", "--", path])
                if old_entry.returncode != 0:
                    raise RuntimeError(f"could not snapshot index entry for {path}")
                if not old_entry.stdout.strip():
                    old_entries[path] = None
                else:
                    lines = old_entry.stdout.rstrip("\n").splitlines()
                    if len(lines) != 1:
                        raise RuntimeError(f"publish target has an unmerged index entry: {path}")
                    metadata, listed_path = lines[0].split("\t", 1)
                    old_mode, old_object_id, stage = metadata.split()
                    if stage != "0" or listed_path != path:
                        raise RuntimeError(f"unexpected index entry for publish path: {path}")
                    old_entries[path] = (old_mode, old_object_id)
        finally:
            temporary_index.unlink(missing_ok=True)
            Path(str(temporary_index) + ".lock").unlink(missing_ok=True)

        index_changed = False
        ref_changed = False

        def restore_prepared_local_state() -> list[str]:
            rollback_failures: list[str] = []
            if ref_changed:
                restored_ref = self.run_git([
                    "git", "update-ref", "-m", "rollback failed Practical Rewards publish",
                    "refs/heads/main", self.publish_base_head, new_head,
                ])
                if restored_ref.returncode != 0:
                    rollback_failures.append("local main ref")
            if index_changed:
                for rollback_path, old_metadata in old_entries.items():
                    if old_metadata is None:
                        restored_index = self.run_git([
                            "git", "update-index", "--force-remove", "--", rollback_path,
                        ])
                    else:
                        old_mode, old_object_id = old_metadata
                        restored_index = self.run_git([
                            "git", "update-index", "--add", "--cacheinfo",
                            f"{old_mode},{old_object_id},{rollback_path}",
                        ])
                    if restored_index.returncode != 0:
                        rollback_failures.append(f"index entry {rollback_path}")
            return rollback_failures

        try:
            # Prepare the real index and local ref first. Every target was clean at
            # preflight, and exact old index entries are retained for rollback.
            for path, (mode, object_id) in new_entries.items():
                sync = self.run_git([
                    "git", "update-index", "--add", "--cacheinfo",
                    f"{mode},{object_id},{path}",
                ])
                if sync.returncode != 0:
                    raise RuntimeError(f"index preparation failed for {path}")
                index_changed = True
            ref_update = self.run_git([
                "git", "update-ref", "-m", "publish Practical Rewards post",
                "refs/heads/main", new_head, self.publish_base_head,
            ])
            if ref_update.returncode != 0:
                raise RuntimeError("local main could not be prepared for publish")
            ref_changed = True
        except BaseException as error:
            rollback_failures = restore_prepared_local_state()
            if isinstance(error, (KeyboardInterrupt, SystemExit)):
                raise
            if rollback_failures:
                raise RuntimeError(
                    "publish preparation failed and rollback also failed for: "
                    + ", ".join(rollback_failures)
                )
            raise

        if self.review:
            self.log(f"Review commit prepared locally at {new_head}; git push skipped")
            return title, slug

        # This push is deliberately the final operation on the success path: no
        # local synchronization remains that could fail after origin/main moves.
        try:
            push_result = subprocess.run(
                ["git", "push", "origin", f"{new_head}:refs/heads/main"],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
        except BaseException as error:
            rollback_failures = restore_prepared_local_state()
            if isinstance(error, (KeyboardInterrupt, SystemExit)):
                raise
            message = f"git push could not run: {type(error).__name__}: {error}"
            if rollback_failures:
                message += "; rollback also failed for: " + ", ".join(rollback_failures)
            raise RuntimeError(message) from error
        if push_result.returncode != 0:
            rollback_failures = restore_prepared_local_state()
            detail = (push_result.stderr or push_result.stdout).strip()
            message = f"git push failed with exit {push_result.returncode}"
            if detail:
                message += f": {detail}"
            if rollback_failures:
                message += "; rollback also failed for: " + ", ".join(rollback_failures)
            raise RuntimeError(message)
        return title, slug

    def run_social_step(self, slug: str) -> None:
        """Generate Instagram slides and the share image; never blocks the post."""
        try:
            code = self.run_step("social", args=[slug, "--force"] if slug else None)
        except StepFailure as error:
            code = error.returncode
        if code == 0:
            record = read_json(ROOT / "social" / slug / "post.json", {}) if slug else {}
            count = len(record.get("images", [])) if isinstance(record, dict) else 0
            self.social_note = (
                f"Instagram {record.get('format', 'post')} ready ({count} image{'s' if count != 1 else ''})"
            )
            self.social_ready = True
            self.log(self.social_note + f": {INSTAGRAM_PREVIEW_URL}")
            return
        self.log("WARNING social step failed; publishing the post without share images")
        self.social_note = "Instagram assets FAILED (post still ready)"
        if slug:
            shutil.rmtree(ROOT / "social" / slug, ignore_errors=True)
            self.strip_share_image_tags(slug)

    def run_full(self) -> int:
        try:
            if not self.dry_run:
                self.current_step = "publish-preflight"
                self.preflight_publish()
                self.capture_pipeline_state()
            for step in ("ingest", "plan"):
                code = self.run_step(step)
                if code:
                    raise StepFailure(step, code)
            draft_code = self.run_step("draft")
            if draft_code and "DRAFT_SOURCES_UNAVAILABLE" in self.last_step_stderr:
                self.log("Draft sources unavailable; forcing the evergreen fallback once")
                plan_code = self.run_step("plan", {"PLAN_FORCE_EVERGREEN": "1"})
                if plan_code:
                    raise StepFailure("plan", plan_code)
                draft_code = self.run_step("draft")
            if draft_code:
                raise StepFailure("draft", draft_code)
            self.capture_build_state()
            code = self.run_step("build")
            if code:
                raise StepFailure("build", code)
            verify_code = self.run_step("verify", self.verify_env())
            report = read_json(STATE / "verify-report.json", {})
            passed = verify_code == 0 and isinstance(report, dict) and report.get("passed") is True
            if not passed:
                failures = report.get("failures", []) if isinstance(report, dict) else []
                reason = str(failures[0]) if failures else f"verify exited with status {verify_code}"
                if self.dry_run:
                    self.log(f"DRY RUN: post failed verification; leaving all changes for inspection: {reason}")
                    return 1
                for revision_round in range(1, 3):
                    self.log(
                        f"Verification failed ({reason}); requesting draft revision {revision_round}/2"
                    )
                    failed_draft = read_json(STATE / "draft.json", {})
                    failed_slug = (
                        str(failed_draft.get("slug", ""))
                        if isinstance(failed_draft, dict)
                        else ""
                    )
                    failed_html_path = ROOT / "blog" / f"{failed_slug}.html"
                    failed_html = (
                        failed_html_path.read_bytes()
                        if failed_slug and failed_html_path.is_file()
                        else None
                    )
                    self.restore_build_state()
                    revision_code = self.run_step("draft", {"DRAFT_REVISE": "1"})
                    if revision_code:
                        if failed_html is not None:
                            failed_html_path.parent.mkdir(parents=True, exist_ok=True)
                            failed_html_path.write_bytes(failed_html)
                        self.log(
                            f"Draft revision {revision_round}/2 failed with status {revision_code}; holding post"
                        )
                        break
                    self.capture_build_state()
                    build_code = self.run_step("build")
                    if build_code:
                        raise StepFailure("build", build_code)
                    verify_code = self.run_step("verify", self.verify_env())
                    report = read_json(STATE / "verify-report.json", {})
                    passed = (
                        verify_code == 0
                        and isinstance(report, dict)
                        and report.get("passed") is True
                    )
                    failures = report.get("failures", []) if isinstance(report, dict) else []
                    reason = (
                        str(failures[0])
                        if failures
                        else f"verify exited with status {verify_code}"
                    )
                    if passed:
                        self.log(f"Verification passed after revision {revision_round}")
                        break
                if not passed:
                    verifier_notes = self.verifier_notes(report) if self.review else []
                    reason = self.hold_failed_post()
                    self.restore_build_state()
                    self.restore_pipeline_state()
                    held_message = f"Today's post was held — {reason}"
                    if self.review:
                        self.log_verifier_notes(verifier_notes)
                        held_message = f"Today's post was held for a HARD reason — {reason}"
                        note_lines = self.verifier_note_lines(verifier_notes)
                        if note_lines:
                            held_message += "\n" + "\n".join(note_lines)
                    self.notify("Post held", held_message)
                    return 1
            draft = read_json(STATE / "draft.json", {})
            self.run_social_step(str(draft.get("slug", "")) if isinstance(draft, dict) else "")
            if self.dry_run:
                self.log(
                    f"DRY RUN PASS: built and verified {draft.get('title', 'post')}; no commit or push; changes left for inspection"
                )
                return 0
            self.current_step = "git-publish"
            title, slug = self.git_publish()
            if self.review:
                preview_link = f"http://carters-mac-mini.tailb1c452.ts.net:8000/blog/{slug}.html"
                verifier_notes = self.verifier_notes(report)
                self.log_verifier_notes(verifier_notes)
                notification_lines = [
                    self.social_note or "Post ready for review",
                    f"Blog: {preview_link}",
                    *self.verifier_note_lines(verifier_notes),
                ]
                actions = [("Blog preview", preview_link)]
                if self.social_ready:
                    actions.append(("Instagram preview", INSTAGRAM_PREVIEW_URL))
                self.notify(
                    title,
                    "\n".join(notification_lines),
                    link=preview_link,
                    actions=actions,
                )
            return 0
        except BaseException as error:
            self.log(f"ERROR during {self.current_step}: {type(error).__name__}: {error}")
            if not self.dry_run:
                try:
                    self.restore_build_state()
                except BaseException as restore_error:
                    self.log(f"ERROR while restoring tree: {restore_error}")
                try:
                    self.restore_pipeline_state()
                except BaseException as restore_error:
                    self.log(f"ERROR while restoring pipeline state: {restore_error}")
                self.notify(
                    "Pipeline failed",
                    f"Pipeline failed during {self.current_step} — {error}",
                )
            else:
                self.log("DRY RUN: leaving the working tree unchanged for inspection")
            if isinstance(error, (KeyboardInterrupt, SystemExit)):
                raise
            return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Practical Rewards daily content pipeline.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="run the full pipeline without commit, push, hold, or restore; leave outputs for inspection (also overrides --review)",
    )
    parser.add_argument(
        "--review",
        action="store_true",
        help="commit a verified post locally on main for review, skip the origin/main match and push, and send a preview notification",
    )
    parser.add_argument(
        "--step",
        choices=STEPS,
        help="run only one pipeline step (no commit, push, hold, or restore)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    lock_path = STATE / ".run.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_handle = lock_path.open("a+")
    try:
        fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        runner = DailyRunner(dry_run=args.dry_run, review=args.review)
        message = "another run is in progress"
        runner.log(f"ERROR: {message}")
        runner.notify("Pipeline failed", message)
        lock_handle.close()
        return 1
    runner = DailyRunner(dry_run=args.dry_run, review=args.review)
    try:
        if args.step:
            env = runner.verify_env() if args.step == "verify" else None
            return runner.run_step(args.step, env)
        return runner.run_full()
    finally:
        lock_handle.close()


if __name__ == "__main__":
    raise SystemExit(main())
