# fullstack-agent bootstrap (Windows) — recreates Tony's Jarvis setup on this machine.
# Safe to re-run: it never overwrites anything that already exists.

$ErrorActionPreference = "Stop"
$Here  = Split-Path -Parent $MyInvocation.MyCommand.Path
$Agent = Join-Path $HOME "my-agent"
$Vault = Join-Path $HOME "HQ"

Write-Output "== fullstack-agent bootstrap (Windows) =="

# 0. git (a fresh terminal may not see a just-installed git; use the full path then)
$Git = "git"
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Output "  git is missing - installing it via winget..."
    winget install --id Git.Git -e --source winget --silent --accept-package-agreements --accept-source-agreements
    $Git = "C:\Program Files\Git\cmd\git.exe"
}

# 1. The four tool repos + the installer toolbox, cloned as siblings.
New-Item -ItemType Directory -Force -Path $Agent | Out-Null
foreach ($r in @("fullstack-agent","ai-memory-vault","backtalk","ai-visualizer","barehands")) {
    $dest = Join-Path $Agent $r
    if (Test-Path $dest) {
        Write-Output "  keep : $dest (already there, untouched)"
    } else {
        Write-Output "  clone: $dest"
        & $Git clone "https://github.com/jaredrhod/$r" $dest
    }
}

# 2. The agent's brain (boot config).
$claudeMd = Join-Path $Agent "CLAUDE.md"
if (Test-Path $claudeMd) {
    Write-Output "  keep : $claudeMd exists - NOT overwriting. Compare with $Here\my-agent\CLAUDE.md yourself."
} else {
    Copy-Item (Join-Path $Here "my-agent\CLAUDE.md") $claudeMd
    Write-Output "  write: $claudeMd"
}

# 3. The wired configs (each lives untracked inside its repo, so updates never touch it).
foreach ($pair in @(@("backtalk.json","backtalk"), @("ai-visualizer.json","ai-visualizer"), @("barehands.json","barehands"))) {
    $dest = Join-Path (Join-Path $Agent $pair[1]) $pair[0]
    if (Test-Path $dest) {
        Write-Output "  keep : $dest exists - NOT overwriting."
    } else {
        Copy-Item (Join-Path $Here ("my-agent\" + $pair[0])) $dest
        Write-Output "  write: $dest"
    }
}

# 4. The memory vault.
if (Test-Path $Vault) {
    Write-Output "  keep : $Vault exists - NOT overwriting. New copy left at $Here\HQ for manual merge."
} else {
    Copy-Item -Recurse (Join-Path $Here "HQ") $Vault
    Write-Output "  write: $Vault (the vault - open it in Obsidian)"
}

# 5. barehands ring hooks for Claude Code (~/.claude/settings.json) - only written when absent;
#    an existing file is never touched (ask your agent to merge the hooks instead).
$settingsDir  = Join-Path $HOME ".claude"
$settingsPath = Join-Path $settingsDir "settings.json"
$stateFile    = Join-Path (Join-Path $Agent "barehands") "state\state"
if (Test-Path $settingsPath) {
    Write-Output "  keep : $settingsPath exists - ask your agent to merge the barehands hooks (barehands.md Phase 4a)."
} else {
    New-Item -ItemType Directory -Force -Path $settingsDir | Out-Null
    $hooks = @{
        hooks = @{
            UserPromptSubmit = @(@{ hooks = @(@{ type = "command"; command = "cmd /c echo thinking> $stateFile" }) })
            Stop             = @(@{ hooks = @(@{ type = "command"; command = "cmd /c echo idle> $stateFile" }) })
        }
    }
    $hooks | ConvertTo-Json -Depth 10 | Set-Content $settingsPath
    Write-Output "  write: $settingsPath (barehands ring hooks)"
}

Write-Output ""
Write-Output "== Done. What's left needs this machine's hardware: =="
Write-Output "  1. Obsidian (the window into the vault): open Claude Code in $Agent and say"
Write-Output "     'read ai-memory-vault/ai-memory-vault.md Part 1 and finish my Obsidian setup for the vault at ~/HQ'"
Write-Output "  2. The voice: open Claude Code in $Agent and say"
Write-Output "     'read backtalk/backtalk.md and finish the Windows install (Phase 1 step 3)'"
Write-Output "     (uv, espeak-ng, ~1GB of local speech models - your agent does it, not you)"
Write-Output "  3. First hello: run  $Agent\fullstack-agent\start.bat"
Write-Output "  4. Desktop shortcuts: ask your agent - 'read fullstack-agent/fullstack-agent.md Phase 6 and make my launchers'."
Write-Output ""
Write-Output "Daily habit: open Claude Code in $Agent - that's where Jarvis lives."
