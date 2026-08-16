#!/bin/bash
# Times of Palestine — session-start hook (owner order 2026-08-16).
#
# Fixes the environment-provisioned stop hook's squash-merge false positive
# (issue #286): it counts "unpushed" commits against origin/<branch>, which
# is stale history after every squash-merge + branch reset in this repo's
# workflow. A commit reachable from ANY remote ref is pushed — the same
# rationale the hook's own signing block already documents. The environment
# re-provisions ~/.claude on each session, so the repo re-applies the patch
# at session start. Idempotent; exits quietly when the hook is absent or
# already patched; never blocks the session.
set -uo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

HOOK="$HOME/.claude/stop-hook-git-check.sh"
OLD='unpushed=$(git rev-list "$upstream..HEAD" --count 2>/dev/null) || unpushed=0'
NEW='unpushed=$(git rev-list HEAD --not --remotes --count 2>/dev/null) || unpushed=0'

if [ -f "$HOOK" ] && grep -qF "$OLD" "$HOOK"; then
  python3 - "$HOOK" << 'PYEOF'
import sys
p = sys.argv[1]
s = open(p).read()
old = 'unpushed=$(git rev-list "$upstream..HEAD" --count 2>/dev/null) || unpushed=0'
new = ('# Squash-merge aware (TimesofPalestine#286): a commit reachable from\n'
       '  # ANY remote ref is pushed.\n'
       '  unpushed=$(git rev-list HEAD --not --remotes --count 2>/dev/null) || unpushed=0')
open(p, 'w').write(s.replace('  ' + old, '  ' + new))
PYEOF
  echo "stop-hook: squash-merge patch applied"
else
  echo "stop-hook: absent or already patched — nothing to do"
fi
exit 0
