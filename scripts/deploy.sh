#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
#
# Deploy the marketing site (sites/marketing) to production.
#
# The contract: `git push origin main` ONLY syncs code. Production
# deploys ONLY happen through this script — never as a side effect of a
# code push. It works by moving a dedicated `deploy/main` ref to the
# commit you want live; Netlify watches that ref (not main), so a plain
# push can never trigger a deployment.
#
# Usage:
#   scripts/deploy.sh            # deploy local main
#   scripts/deploy.sh <commit>   # deploy that commit (must be pushed)
#   scripts/deploy.sh --status   # show local/remote deploy ref state
#
# Requirements (checked before anything is touched):
#   - the commit to deploy is on origin/main (Netlify builds from the
#     remote; an unpushed commit would deploy something invisible)
#   - a clean working tree (an accidental deploy of half-finished work
#     is worse than a refused deploy)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEPLOY_REF="refs/heads/deploy/main"
REMOTE_DEPLOY="origin/deploy/main"

die() { echo "deploy: $*" >&2; exit 1; }

status() {
  local target
  target="$(git -C "$REPO_ROOT" rev-parse --verify --quiet refs/remotes/origin/main | cut -c1-12 || true)"
  echo "origin/main:    ${target:-<none>}"
  target="$(git -C "$REPO_ROOT" rev-parse --verify --quiet "$DEPLOY_REF" | cut -c1-12 || true)"
  echo "local deploy:   ${target:-<none>}"
  target="$(git -C "$REPO_ROOT" rev-parse --verify --quiet "refs/remotes/$REMOTE_DEPLOY" | cut -c1-12 || true)"
  echo "remote deploy:  ${target:-<none>}  (what production was last built from)"
}

[ $# -ge 1 ] && [ "$1" = "--status" ] && { status; exit 0; }

COMMIT="${1:-main}"

# Resolve first so the checks talk about a concrete commit.
REV="$(git -C "$REPO_ROOT" rev-parse --verify --quiet "$COMMIT^{commit}" \
  || die "cannot resolve '$COMMIT' to a commit")"
SHORT="$(echo "$REV" | cut -c1-12)"

# Clean tree — uncommitted work must not ride along with a deploy.
if [ -n "$(git -C "$REPO_ROOT" status --porcelain -- sites docs scripts netlify.toml)" ]; then
  die "working tree has uncommitted changes; commit or stash before deploying."
fi

# The commit must be public: Netlify builds the remote, and an unpushed
# commit would silently deploy the wrong thing (or nothing).
if ! git -C "$REPO_ROOT" merge-base --is-ancestor "$REV" refs/remotes/origin/main 2>/dev/null; then
  git -C "$REPO_ROOT" fetch origin main --quiet 2>/dev/null || true
  git -C "$REPO_ROOT" merge-base --is-ancestor "$REV" refs/remotes/origin/main 2>/dev/null \
    || die "$SHORT is not on origin/main — push it first: git push origin main"
fi

echo "Deploying $SHORT → $DEPLOY_REF"
git -C "$REPO_ROOT" update-ref "$DEPLOY_REF" "$REV"
git -C "$REPO_ROOT" push origin "$DEPLOY_REF:$DEPLOY_REF"

echo
echo "Deploy ref moved to $SHORT. Netlify is now building:"
echo "  https://app.netlify.com  (Halbert site → Production deploys)"
echo "Production URL:            https://halbert.computer"
status