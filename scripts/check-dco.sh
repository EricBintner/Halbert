#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
#
# check-dco.sh — verify every commit in a range carries a Developer Certificate
# of Origin sign-off trailer that matches the commit's author or committer:
#
#     Signed-off-by: Full Name <email@example.com>
#
# Usage:
#     scripts/check-dco.sh                    # merge-base(origin/main, HEAD)..HEAD
#     scripts/check-dco.sh <base> [<head>]    # merge-base(<base>, <head>)..<head>
#     scripts/check-dco.sh <a>..<b>           # literal range
#
# Mirrors the rules of the probot DCO GitHub App: merge commits and commits
# authored by GitHub bot accounts (dependabot[bot], …) are skipped, and the
# sign-off name/email must match the author or the committer (case-insensitive).
# Exit status is 1 when any commit fails. Used by .github/workflows/dco.yml.

set -euo pipefail

if [[ $# -ge 1 && "$1" == *..* ]]; then
  RANGE="$1"
else
  BASE="${1:-origin/main}"
  HEAD_REF="${2:-HEAD}"
  if ! MB="$(git merge-base "${BASE}" "${HEAD_REF}" 2>/dev/null)"; then
    echo "error: cannot find merge-base of ${BASE} and ${HEAD_REF} (is the history fetched? try fetch-depth: 0)" >&2
    exit 2
  fi
  RANGE="${MB}..${HEAD_REF}"
fi

TRAILER_RE='^Signed-off-by: (.+) <([^<>@[:space:]]+@[^<>@[:space:]]+)>$'

lower() { printf '%s' "$1" | tr '[:upper:]' '[:lower:]'; }

commits="$(git rev-list --no-merges "${RANGE}")"
if [[ -z "${commits}" ]]; then
  echo "No commits in range ${RANGE}; nothing to check."
  exit 0
fi

failed=0
checked=0
skipped=0
while IFS= read -r sha; do
  [[ -z "${sha}" ]] && continue
  subject="$(git log -1 --format='%s' "${sha}")"
  an="$(git log -1 --format='%an' "${sha}")"; ae="$(git log -1 --format='%ae' "${sha}")"
  cn="$(git log -1 --format='%cn' "${sha}")"; ce="$(git log -1 --format='%ce' "${sha}")"

  # GitHub bot accounts commit as "name[bot] <id+name[bot]@users.noreply.github.com>".
  if [[ "${an}" == *"[bot]" || "${ae}" == *"[bot]@users.noreply.github.com" ]]; then
    echo "skip     ${sha:0:10}  ${subject}  (bot author: ${an})"
    skipped=$((skipped + 1))
    continue
  fi

  checked=$((checked + 1))
  ok=0
  while IFS= read -r trailer; do
    [[ -z "${trailer}" ]] && continue
    if [[ "${trailer}" =~ ${TRAILER_RE} ]]; then
      name="$(lower "${BASH_REMATCH[1]}")"; email="$(lower "${BASH_REMATCH[2]}")"
      if { [[ "${name}" == "$(lower "${an}")" && "${email}" == "$(lower "${ae}")" ]] \
        || [[ "${name}" == "$(lower "${cn}")" && "${email}" == "$(lower "${ce}")" ]]; }; then
        ok=1; break
      fi
    fi
  done < <(git log -1 --format='%(trailers:key=Signed-off-by,valueonly=false)' "${sha}")

  if [[ "${ok}" -eq 1 ]]; then
    echo "ok       ${sha:0:10}  ${subject}"
  else
    echo "MISSING  ${sha:0:10}  ${subject}  (author: ${an} <${ae}>)"
    failed=$((failed + 1))
  fi
done <<<"${commits}"

echo
if [[ "${failed}" -ne 0 ]]; then
  cat <<EOF
${failed} of ${checked} commit(s) lack a Developer Certificate of Origin sign-off
matching the commit author or committer.

Every commit must carry a trailer of the form:
    Signed-off-by: Full Name <email@example.com>
where the name and email are those of the commit's author (git config user.name / user.email).

Add it to new commits with:        git commit -s
Add it to the last commit with:    git commit --amend -s --no-edit
Add it to a whole branch with:     git rebase --signoff <base>
then push again (a rewritten branch needs --force-with-lease).

By signing off you certify the DCO 1.1 (https://developercertificate.org/);
see documentation/contributing/CONTRIBUTING.md.
EOF
  exit 1
fi

echo "All ${checked} commit(s) carry a matching DCO sign-off (${skipped} bot commit(s) skipped)."
