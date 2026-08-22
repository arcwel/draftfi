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

## Set up your machine

**Mac / Linux** — paste into Terminal:

```
git clone -b claude/fullstack-agent-setup-uheiau https://github.com/arcwel/draftfi /tmp/agent-carrier && bash /tmp/agent-carrier/agent-setup/bootstrap.sh && cd ~/my-agent && claude "You are Jarvis and your bootstrap just ran. Finish the hardware half of my setup: Obsidian + vault registration for ~/HQ (ai-memory-vault.md Part 1), backtalk's install.sh, the voice-engine audition, the Desktop shortcuts (fullstack-agent.md Phase 6), then the first hello with ./fullstack-agent/start.sh."
```

**Windows** — paste into PowerShell:

```
git clone -b claude/fullstack-agent-setup-uheiau https://github.com/arcwel/draftfi $env:TEMP\agent-carrier; & $env:TEMP\agent-carrier\agent-setup\bootstrap.ps1; cd $HOME\my-agent; claude "You are Jarvis and your bootstrap just ran. Finish the hardware half of my setup: Obsidian + vault registration for ~/HQ (ai-memory-vault.md Part 1), the backtalk Windows install (backtalk.md Phase 1 step 3), the voice-engine audition, the Desktop shortcuts (fullstack-agent.md Phase 6), then the first hello with fullstack-agent\start.bat."
```

Either way: the bootstrap replays the finished setup (never overwriting
anything that exists), then Claude Code opens **as Jarvis** in its home
folder and does the remaining hardware steps itself — Obsidian, the voice
models, the shortcuts, the first hello. You just answer its questions.

## What was verified in the cloud session

- ai-visualizer server: starts, serves the gallery and faces (HTTP 200).
- barehands server: starts, serves the stage, reports the JARVIS config with
  the HQ orb, and accepts board commands from the agent (`board.sh` → 204).
- The vault and boot config: complete, no placeholders.

Not run in the cloud (needs your hardware): backtalk's `install.sh`
(~1GB speech models), Obsidian, the spoken hello, camera/mic permissions.
