#!/bin/sh
# run.sh <profile.sb|-none> <argv...>  -> prints rc + first lines of stdout/stderr
S=/private/tmp/claude-501/-Volumes-4TB-BAD-Halbert/1c4f8f70-ff55-451a-86d5-eab129e684c5/scratchpad/sb
prof="$1"; shift
if [ "$prof" = "-none" ]; then
  "$@" > "$S/.o" 2> "$S/.e"; rc=$?
else
  /usr/bin/sandbox-exec -f "$S/$prof" "$@" > "$S/.o" 2> "$S/.e"; rc=$?
fi
echo "rc=$rc stdout_lines=$(wc -l < "$S/.o" | tr -d ' ')"
head -3 "$S/.o"
if [ -s "$S/.e" ]; then echo "STDERR:"; head -3 "$S/.e"; fi
