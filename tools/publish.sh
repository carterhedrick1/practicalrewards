#!/usr/bin/env bash

set -u

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/.." && pwd)"
cd -- "$repo_root" || {
    printf '%s\n' "FAILURE: could not enter repository root: $repo_root" >&2
    exit 1
}

scratch_exclusions=(
    ':(exclude)tools/state/inbox.json'
    ':(exclude)tools/state/todays-brief.json'
    ':(exclude)tools/state/draft.json'
    ':(exclude)tools/state/verify-report.json'
    ':(exclude)tools/state/articles.json'
)

if ! tracked_changes="$(
    git status --porcelain=v1 --untracked-files=no -- . "${scratch_exclusions[@]}"
)"; then
    printf '%s\n' 'FAILURE: could not inspect the repository working tree.' >&2
    exit 1
fi

if [[ -n "$tracked_changes" ]]; then
    printf '%s\n' 'FAILURE: refusing to push; tracked files have uncommitted changes:' >&2
    printf '%s\n' "$tracked_changes" >&2
    exit 1
fi

if ! git fetch origin main; then
    printf '%s\n' 'FAILURE: could not fetch origin/main before push.' >&2
    exit 1
fi

git merge-base --is-ancestor origin/main main
ancestor_status=$?
if [[ $ancestor_status -ne 0 ]]; then
    printf '%s\n' 'FAILURE: local main has diverged from or is behind origin/main; refusing to push.' >&2
    exit 1
fi

if git push origin main; then
    printf '%s\n' 'SUCCESS: pushed local main to origin/main.'
    exit 0
fi

printf '%s\n' 'Plain git push failed; retrying with GitHub CLI credentials.' >&2
if git -c 'credential.helper=!gh auth git-credential' push origin main; then
    printf '%s\n' 'SUCCESS: pushed local main to origin/main with GitHub CLI credentials.'
    exit 0
fi

printf '%s\n' 'FAILURE: could not push local main to origin/main.' >&2
exit 1
