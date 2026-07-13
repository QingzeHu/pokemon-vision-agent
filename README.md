# pokemon-vision-agent

A minimal agent that plays a Game Boy Pokémon game **purely from screenshots**,
using the Anthropic API and the mGBA emulator. No RAM reads, no pathfinding, no
injected game state — the model looks at the screen, presses buttons, and keeps
its own notes. The game runs in a real mGBA window at real-time speed with
sound; it never pauses while the model thinks.

## Design philosophy

This deliberately mirrors the vision-only form of Anthropic's "Claude Plays
Pokémon" benchmark: the harness is kept as thin as possible so that what you
observe is the *model's* ability, not the scaffolding's. The model receives
exactly two inputs — the current screenshot and its own free-form notes — and
has exactly one way to affect the game: pressing buttons. The only non-visual
mechanism is memory management (periodic history compression plus the notes
scratchpad), which exists solely because the context window cannot hold
thousands of turns. The system prompt explicitly tells the model not to trust
its memorized Pokémon knowledge, only the screen and its notes.

## Install

1. Python side:

   ```sh
   cd pokemon-vision-agent
   uv venv
   uv pip install -r requirements.txt
   export ANTHROPIC_API_KEY=sk-ant-...   # or put the key in secrets/anthropic_api_key
   ```

2. Emulator (one-time): install an mGBA **development build** (0.11-dev+,
   the stable 0.10.x lacks autorun scripts) to `/Applications/mGBA-dev.app`
   — download from <https://mgba.io/downloads.html>. Open it once and
   register `bridge.lua` (repo root) as an autorun script:
   **Settings → Scripting → Edit autorun scripts → Add**. From then on every
   mGBA launch starts the TCP bridge automatically and the agent can attach.

## Run

```sh
# Quick sanity run / full run on a local LM Studio model (free)
make dry
make local

# Claude API (Haiku by default, 100-action cap)
make claude-dry
make claude

# Or call the entrypoint directly
uv run python main.py --rom roms/shuijing.gbc --model claude-sonnet-4-6 --summary-every 50
```

The agent attaches to a running mGBA, or launches one itself. Stop with
`Ctrl-C` — mGBA is only quit if the agent launched it.

## ROM

This project ships **no ROM**. You must supply your own legally-obtained ROM
file (e.g. dumped from a cartridge you own). mGBA emulates the Game Boy,
Game Boy Color, and Game Boy Advance, so `.gb`, `.gbc`, and `.gba` all work.

## Cost warning

Every turn sends a screenshot (vision tokens) plus the conversation history,
and a real playthrough takes thousands of turns — costs add up quickly. Debug
the loop on Haiku (`claude-haiku-4-5-20251001`, the default) before switching
to `claude-sonnet-4-6` or `claude-fable-5`. The system prompt is sent with
`cache_control` for prompt caching, but the screenshots themselves are new
tokens each turn. Scope early runs to small goals (e.g. "get out of the first
room") rather than letting it run unattended.
