#!/usr/bin/env bash
#
# push.sh — create the GitHub repo and push the local history.
# Run once, from inside this folder, on a machine where:
#   - git is installed
#   - the GitHub CLI (gh) is installed and authenticated (`gh auth login`)
#
# Usage:
#   ./push.sh                # public repo, default name "shopify-csm-agent"
#   REPO_NAME=foo ./push.sh  # custom repo name
#   VISIBILITY=private ./push.sh
#
# Idempotent-ish: if the repo already exists on your account, gh will
# return an error and stop. In that case, push manually with:
#   git remote add origin git@github.com:<you>/<repo>.git
#   git push -u origin main

set -euo pipefail

REPO_NAME="${REPO_NAME:-shopify-csm-agent}"
VISIBILITY="${VISIBILITY:-public}"

if ! command -v gh >/dev/null 2>&1; then
    echo "error: gh CLI not found. Install: https://cli.github.com/" >&2
    exit 1
fi

if ! gh auth status >/dev/null 2>&1; then
    echo "error: gh is not authenticated. Run: gh auth login" >&2
    exit 1
fi

if [ ! -d .git ]; then
    echo "error: this folder is not a git repo. Did the local init run?" >&2
    exit 1
fi

echo "▶ creating $VISIBILITY repo '$REPO_NAME' and pushing main..."
gh repo create "$REPO_NAME" \
    --"$VISIBILITY" \
    --source=. \
    --push \
    --remote=origin

echo
echo "✓ done. URL:"
gh repo view --json url -q .url
