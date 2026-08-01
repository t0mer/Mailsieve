#!/usr/bin/env bash
# Compute the next date-based release version: YYYY.M.PATCH (no leading zero on
# the month). Finds the latest tag for the current YYYY.M and increments PATCH;
# starts at .0 when there is no tag for this month yet.
set -euo pipefail
TODAY="$(date +%Y.%-m)"          # %-m = month, no leading zero
LATEST="$(git tag --list "${TODAY}.*" 2>/dev/null | sort -V | tail -1)"
if [ -z "$LATEST" ]; then echo "${TODAY}.0";
else PATCH="${LATEST##*.}"; echo "${TODAY}.$((PATCH + 1))"; fi
