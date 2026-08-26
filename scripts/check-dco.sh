#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
#
# check-dco.sh — verify every non-merge commit in a range carries a
# Developer Certificate of Origin sign-off trailer:
#
#     Signed-off-by: Full Name <email@example.com>
#
# Usage:
#     scripts/check-dco.sh [<range>]        # default: origin/main..HEAD
#
# Exit status is 1 when any commit lacks a valid trailer. Used by
# .github/workflows/dco.yml and usable locally before pushing.

set -euo pipefail

RANGE="${1:-origin/main..HEAD}"

# A trailer is only valid when git itself parses it as one (so a mention in
# the body text does not count) and it carries a "Name <email>" shape.
TRAILER_RE='^Signed-off-by: .+ <[^<>@[:space:]]+@[^<>@[:space:]]+>$'

commits="$(git rev-list --no-merges "${RANGE}")"
if [[ -z "${commits}" ]]; then
  echo "No commits in range ${RANGE}; nothing to check."
  exit 0
fi

failed=0
checked=0
while IFS= read -r sha; do
  [[ -z "${sha}" ]] && continue
  checked=$((checked + 1))
  subject="$(git log -1 --format='%s' "${sha}")"
  trailers="$(git log -1 --format='%(trailers:key=Signed-off-by,valueonly=false)' "${sha}")"
  if grep -Eq "${TRAILER_RE}" <<<"${trailers}"; then
    echo "ok       ${sha:0:10}  ${subject}"
  else
    echo "MISSING  ${sha:0:10}  ${subject}"
    failed=$((failed + 1))
  fi
done <<<"${commits}"

echo
if [[ "${failed}" -ne 0 ]]; then
  cat <<EOF
${failed} of ${checked} commit(s) lack a Developer Certificate of Origin sign-off.

Every commit must carry a trailer of the form:
    Signed-off-by: Full Name <email@example.com>

Add it to new commits with:        git commit -s
Add it to the last commit with:    git commit --amend -s --no-edit
Add it to a whole branch with:     git rebase --signoff <base>
then push again (a rewritten branch needs --force-with-lease).

By signing off you certify the DCO 1.1 (https://developercertificate.org/);
see documentation/contributing/CONTRIBUTING.md.
EOF
  exit 1
fi

echo "All ${checked} commit(s) carry a DCO sign-off."
