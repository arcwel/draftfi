#!/bin/bash
# fullstack-agent bootstrap — recreates Tony's Jarvis setup on this machine.
#
# Built in a Claude Code cloud session on 2026-08-22. The cloud container had
# no mic/webcam/display, so this script replays the finished setup locally:
#   ~/my-agent  — the agent's home (boot config + the four tool repos)
#   ~/HQ        — the memory vault (plain markdown, opened with Obsidian)
#
# Safe to re-run: it never overwrites anything that already exists.

set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
AGENT="$HOME/my-agent"
VAULT="$HOME/HQ"

echo "== fullstack-agent bootstrap =="

# 1. The four tool repos + the installer toolbox, cloned as siblings.
mkdir -p "$AGENT"
for r in fullstack-agent ai-memory-vault backtalk ai-visualizer barehands; do
  if [ -d "$AGENT/$r" ]; then
    echo "  keep : $AGENT/$r (already there, untouched)"
  else
    echo "  clone: $AGENT/$r"
    git clone "https://github.com/jaredrhod/$r" "$AGENT/$r"
  fi
done

# 2. The agent's brain (boot config).
if [ -e "$AGENT/CLAUDE.md" ]; then
  echo "  keep : $AGENT/CLAUDE.md exists — NOT overwriting. Compare with $HERE/my-agent/CLAUDE.md yourself."
else
  cp "$HERE/my-agent/CLAUDE.md" "$AGENT/CLAUDE.md"
  echo "  write: $AGENT/CLAUDE.md"
fi

# 3. The wired configs (each lives untracked inside its repo, so updates never touch it).
for pair in "backtalk.json backtalk" "ai-visualizer.json ai-visualizer" "barehands.json barehands"; do
  set -- $pair
  if [ -e "$AGENT/$2/$1" ]; then
    echo "  keep : $AGENT/$2/$1 exists — NOT overwriting."
  else
    cp "$HERE/my-agent/$1" "$AGENT/$2/$1"
    echo "  write: $AGENT/$2/$1"
  fi
done

# 4. The memory vault.
if [ -d "$VAULT" ]; then
  echo "  keep : $VAULT exists — NOT overwriting. New copy left at $HERE/HQ for manual merge."
else
  cp -R "$HERE/HQ" "$VAULT"
  echo "  write: $VAULT (the vault — open it in Obsidian)"
fi

# 5. barehands ring hooks for Claude Code (~/.claude/settings.json), merged, never clobbered.
python3 - "$AGENT/barehands" <<'PY'
import json, os, sys
repo = sys.argv[1]
path = os.path.expanduser("~/.claude/settings.json")
os.makedirs(os.path.dirname(path), exist_ok=True)
cfg = {}
if os.path.exists(path):
    with open(path) as f:
        try:
            cfg = json.load(f)
        except Exception:
            print(f"  skip : {path} is not valid JSON — merge the barehands hooks by hand (see barehands.md Phase 4a).")
            sys.exit(0)
hooks = cfg.setdefault("hooks", {})
def add(event, cmd):
    entries = hooks.setdefault(event, [])
    if any(cmd in json.dumps(e) for e in entries):
        return False
    entries.append({"hooks": [{"type": "command", "command": cmd}]})
    return True
changed = add("UserPromptSubmit", f"printf thinking > {repo}/state/state")
changed = add("Stop", f"printf idle > {repo}/state/state") or changed
if changed:
    with open(path, "w") as f:
        json.dump(cfg, f, indent=2)
    print(f"  write: {path} (barehands ring hooks merged in)")
else:
    print(f"  keep : {path} already has the barehands hooks")
PY

echo
echo "== Done. What's left needs this machine's hardware: =="
echo "  1. Obsidian (the window into the vault):  open Claude Code in $AGENT and say"
echo "     'read ai-memory-vault/ai-memory-vault.md Part 1 and finish my Obsidian setup for the vault at ~/HQ'"
echo "     (it installs Obsidian and registers the vault so first launch opens straight into it)"
echo "  2. The voice: cd $AGENT/backtalk && ./install.sh   (~1GB of local speech models, first run only)"
echo "     Then decide the voice engine by ear — built-in bm_lewis is configured; ElevenLabs is the upgrade."
echo "  3. First hello: cd $AGENT && ./fullstack-agent/start.sh"
echo "  4. Desktop shortcuts: ask your agent — 'read fullstack-agent/fullstack-agent.md Phase 6 and make my launchers'."
echo
echo "Daily habit: open Claude Code in $AGENT — that's where Jarvis lives."
