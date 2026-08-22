# agent-setup — Jarvis, built and boxed

This folder is the output of a [fullstack-agent](https://github.com/jaredrhod/fullstack-agent)
setup run performed in a Claude Code **cloud** session on 2026-08-22. The cloud
machine is ephemeral and has no microphone, webcam, or display, so the finished
personal layer was committed here to survive, ready to be replayed onto a real
computer.

**This folder is unrelated to the DraftFi app itself** — it lives on the
`claude/fullstack-agent-setup-uheiau` branch only, as a carrying case. Don't
merge it into `main` unless you actually want it there.

## What's inside

- `my-agent/CLAUDE.md` — the agent's boot config: the shipped **Jarvis**
  identity (door A, as-is), the barehands board block, and the mechanic section.
- `my-agent/backtalk.json` — voice config: push-to-talk on the `home` key,
  ask-mode permissions, built-in `bm_lewis` voice, greeting
  "Hello Tony, what are we working on today?", vault in `extra_dirs`,
  barehands state wired.
- `my-agent/ai-visualizer.json` — face config: JARVIS on the **board** (living
  circuit board), bus pointed at backtalk.
- `my-agent/barehands.json` — hands config: JARVIS ring, the HQ vault as a
  notes orb.
- `HQ/` — the memory vault: VAULT-INDEX, Active Priorities, folder structure
  with indexes (DraftFi seeded as the active project), daily-note template,
  and the first daily note logging this build.
- `bootstrap.sh` — replays all of it onto the machine it runs on. Safe to
  re-run; it never overwrites anything that already exists.

## Set up your machine (Mac/Linux)

```
git clone -b claude/fullstack-agent-setup-uheiau https://github.com/arcwel/draftfi /tmp/agent-carrier
bash /tmp/agent-carrier/agent-setup/bootstrap.sh
```

Then follow the four "what's left" steps the script prints (Obsidian, the
voice models, the first hello, the Desktop shortcuts) — each is one sentence
said to Claude Code in `~/my-agent`.

## What was verified in the cloud session

- ai-visualizer server: starts, serves the gallery and faces (HTTP 200).
- barehands server: starts, serves the stage, reports the JARVIS config with
  the HQ orb, and accepts board commands from the agent (`board.sh` → 204).
- The vault and boot config: complete, no placeholders.

Not run in the cloud (needs your hardware): backtalk's `install.sh`
(~1GB speech models), Obsidian, the spoken hello, camera/mic permissions.
