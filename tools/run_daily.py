#!/usr/bin/env python3
"""Deterministic orchestrator for the Practical Rewards daily blog pipeline."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from common import ROOT, STATE, read_json


STEPS = ("ingest", "plan", "draft", "build", "verify")
SCRIPT_NAMES = {
    "ingest": "ingest.py",
    "plan": "plan.py",
    "draft": "draft.py",
    "build": "build_post.py",
    "verify": "verify_post.py",
}
PUBLISH_STATE_FILES = (
    "seen.json", "inbox.json", "todays-brief.json", "draft.json",
    "verify-report.json", "published.json",
)
STATIC_PUBLISH_PATHS = ("blog/index.html", "blog/feed.xml", "sitemap.xml")


@dataclass
class Snapshot:
    path: Path
    existed: bool
    data: bytes | None
    tracked: bool


class StepFailure(RuntimeError):
    def __init__(self, step: str, returncode: int) -> None:
        super().__init__(f"{step} exited with status {returncode}")
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

    def log(self, message: str) -> None:
        stamp = dt.datetime.now().astimezone().isoformat(timespec="seconds")
        line = f"[{stamp}] {message}"
        print(line)
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def run_step(self, step: str) -> int:
        self.current_step = step
        command = [sys.executable, str(ROOT / "tools" / SCRIPT_NAMES[step])]
        self.log(f"START {step}: {' '.join(command)}")
        result = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        for stream_name, value in (("stdout", result.stdout), ("stderr", result.stderr)):
            if value:
                for line in value.rstrip().splitlines():
                    self.log(f"{step} {stream_name}: {line}")
        self.log(f"END {step}: exit {result.returncode}")
        return result.returncode

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
        paths.extend(f"tools/state/{name}" for name in PUBLISH_STATE_FILES)
        return paths

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
        if status.returncode != 0:
            raise RuntimeError("could not inspect publish targets")
        if status.stdout.strip():
            raise RuntimeError(
                "publish target has pre-existing work; aborting before ingest: "
                + " | ".join(status.stdout.strip().splitlines())
            )
        self.publish_base_head = local.stdout.strip()
        mode = "Review" if self.review else "Publish"
        self.log(f"{mode} preflight passed at {self.publish_base_head}")

    def capture_pipeline_state(self) -> None:
        paths = [STATE / name for name in PUBLISH_STATE_FILES]
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
        self.snapshots = [
            Snapshot(path, path.exists(), path.read_bytes() if path.exists() else None, self.is_tracked(path))
            for path in paths
        ]
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
        self.log("Restored all build-touched paths to their exact pre-run state")

    def notify(self, message: str) -> None:
        safe = message.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
        script = f'display notification "{safe}" with title "Practical Rewards"'
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                timeout=15,
                check=False,
            )
            if result.returncode != 0:
                self.log(f"WARNING notification failed: {result.stderr.strip()}")
        except Exception as error:
            self.log(f"WARNING notification failed: {error}")

    def hold_failed_post(self) -> str:
        report = read_json(STATE / "verify-report.json", {})
        failures = report.get("failures", []) if isinstance(report, dict) else []
        first_reason = str(failures[0]) if failures else "verification failed"
        draft = read_json(STATE / "draft.json", {})
        slug = str(draft.get("slug", "post")) if isinstance(draft, dict) else "post"
        held = STATE / "held" / self.today
        held.mkdir(parents=True, exist_ok=True)
        for path in (STATE / "draft.json", STATE / "verify-report.json", ROOT / "blog" / f"{slug}.html"):
            if path.exists():
                destination = held / path.name
                if destination.exists():
                    destination.unlink()
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
        except Exception:
            rollback_failures = restore_prepared_local_state()
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
        except Exception as error:
            rollback_failures = restore_prepared_local_state()
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

    def run_full(self) -> int:
        try:
            if not self.dry_run:
                self.current_step = "publish-preflight"
                self.preflight_publish()
                self.capture_pipeline_state()
            for step in ("ingest", "plan", "draft"):
                code = self.run_step(step)
                if code:
                    raise StepFailure(step, code)
            self.capture_build_state()
            code = self.run_step("build")
            if code:
                raise StepFailure("build", code)
            verify_code = self.run_step("verify")
            report = read_json(STATE / "verify-report.json", {})
            passed = verify_code == 0 and isinstance(report, dict) and report.get("passed") is True
            if not passed:
                failures = report.get("failures", []) if isinstance(report, dict) else []
                reason = str(failures[0]) if failures else f"verify exited with status {verify_code}"
                if self.dry_run:
                    self.log(f"DRY RUN: post failed verification; leaving all changes for inspection: {reason}")
                else:
                    reason = self.hold_failed_post()
                    self.restore_build_state()
                    self.restore_pipeline_state()
                    self.notify(f"today's post was held — {reason}")
                return 1
            draft = read_json(STATE / "draft.json", {})
            if self.dry_run:
                self.log(
                    f"DRY RUN PASS: built and verified {draft.get('title', 'post')}; no commit or push; changes left for inspection"
                )
                return 0
            self.current_step = "git-publish"
            title, slug = self.git_publish()
            if self.review:
                self.notify(
                    f"Post ready for review: {title} — preview: "
                    f"http://carters-mac-mini.tailb1c452.ts.net:8000/blog/{slug}.html"
                )
            return 0
        except Exception as error:
            self.log(f"ERROR during {self.current_step}: {type(error).__name__}: {error}")
            if not self.dry_run:
                try:
                    self.restore_build_state()
                except Exception as restore_error:
                    self.log(f"ERROR while restoring tree: {restore_error}")
                try:
                    self.restore_pipeline_state()
                except Exception as restore_error:
                    self.log(f"ERROR while restoring pipeline state: {restore_error}")
                self.notify(f"pipeline failed during {self.current_step} — {error}")
            else:
                self.log("DRY RUN: leaving the working tree unchanged for inspection")
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
    runner = DailyRunner(dry_run=args.dry_run, review=args.review)
    if args.step:
        return runner.run_step(args.step)
    return runner.run_full()


if __name__ == "__main__":
    raise SystemExit(main())
