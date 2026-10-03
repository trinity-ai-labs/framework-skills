#!/usr/bin/env bash
# The content checks CI runs, runnable locally: bash scripts/check.sh
# Takes no arguments; needs only bash and Python 3. Runs the checks in order and
# exits non-zero at the first one that fails, after printing all of its failures.
# The version-bump rule is not here: it needs a base ref, so it stays a CI step.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

# Frontmatter Claude Code needs: every skill dir has a SKILL.md whose name and
# description are set, and whose name matches the directory.
check_frontmatter() {
  local fail=0 dir slug file fm key declared
  for dir in skills/*/; do
    slug="$(basename "$dir")"; file="$dir/SKILL.md"
    [ -f "$file" ] || { echo "::error::$dir has no SKILL.md"; fail=1; continue; }
    fm="$(awk '/^---$/{n++; next} n==1' "$file")"
    for key in name description; do
      grep -qE "^$key:" <<<"$fm" || { echo "::error::$slug: missing '$key'"; fail=1; }
    done
    declared="$(grep -E '^name:' <<<"$fm" | head -1 | sed 's/^name:[[:space:]]*//' || true)"
    [ "$declared" = "$slug" ] || { echo "::error::$slug: frontmatter name is '$declared'"; fail=1; }
  done
  return $fail
}

# These skills are public and generic on purpose; a re-introduced product name
# or an author's home-directory path is the regression to catch.
check_sweep() {
  if grep -rniE 'trinity|/Users/[a-z]|/home/[a-z]' skills --include='*.md' \
     | grep -vE '/users/\$|/users/:|`/users/' ; then
    echo "::error::identifier or local path found in skills/"
    return 1
  fi
  echo "clean"
}

# Every '## Contents' link points at a real heading.
check_toc() {
  python3 - <<'PY'
import pathlib, re, sys
def slug(h):
    s = re.sub(r'`|\*|\[|\]|\(|\)', '', h.strip().lower())
    s = re.sub(r'[^\w\s-]', '', s)
    return re.sub(r'\s+', '-', s).strip('-')
bad = 0
for r in sorted(pathlib.Path("skills").rglob("reference/*.md")):
    txt = r.read_text()
    if "## Contents" not in txt: continue
    valid = {slug(l[3:]) for l in txt.splitlines() if l.startswith("## ")} | \
            {slug(l[4:]) for l in txt.splitlines() if l.startswith("### ")}
    for m in re.finditer(r'^- \[.+?\]\(#([\w-]+)\)$', txt, re.M):
        if m.group(1) not in valid:
            print(f"::error::{r}: broken TOC link #{m.group(1)}"); bad += 1
sys.exit(1 if bad else 0)
PY
}

run() {
  echo "== $1"
  if ! "$2"; then
    echo "check failed: $1" >&2
    exit 1
  fi
}

run "skill frontmatter and directory names" check_frontmatter
run "no product name or local paths" check_sweep
run "reference TOC links resolve" check_toc
echo "all checks passed"
