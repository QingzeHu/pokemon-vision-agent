# Build a vision-only Pokémon-playing agent harness

Build a small, clean Python project: an agent that plays a Game Boy Pokémon game
**purely from screenshots**, using the Anthropic API. This deliberately mirrors
the design philosophy of Anthropic's own "Claude Plays Pokémon" benchmark in its
most stripped-down (vision-only) form: minimal scaffolding, no cheating, the
model controls the game by looking at the screen and pressing buttons.

## Design philosophy (read this first — it constrains every decision)

- **Vision only.** The agent gets the raw screenshot and nothing else. Do NOT
  read the emulator's RAM. Do NOT inject coordinates, map tiles, money, badges,
  party stats, or any structured game state. The model must infer everything
  from the image.
- **One game-interaction tool: button presses.** No "navigator", no pathfinding,
  no movement helpers. The model presses A/B/Start/Select/D-pad, gets the next
  screenshot, repeats.
- **Keep the harness thin.** The goal is to benchmark/observe the *model's*
  ability, not to engineer a program that beats the game. Resist adding
  cleverness. When in doubt, do less.
- **One non-visual mechanism is allowed and required: memory management.** The
  context window will overflow over thousands of turns, so we need (a) an
  accordion-style periodic summarization that compresses + resets history, and
  (b) a lightweight free-form notes scratchpad the model fully controls. That is
  the *only* persistent memory. Nothing structured beyond that.
- **The system prompt's core rule:** the model must NOT trust its own memorized
  Pokémon knowledge (maps, menus, locations may differ from what it remembers);
  it should trust only the current screenshot and its own notes. This directly
  counters the known failure mode where the model hallucinates routes.

## Tech stack

- Python 3.11+
- mGBA dev build (`/Applications/mGBA-dev.app`) as the emulator — accurate
  GB/GBC/GBA rendering, native window and sound, game runs in real time. It
  autoruns `bridge.lua` (configured once in mGBA settings), which serves
  button presses and screenshots over a local TCP socket (port 8888).
- `anthropic` (official SDK, tool use / `messages.create`)
- `pillow`
- No web framework, no DB. Keep it runnable from the CLI.
- (History: the original build used `pyboy`, but its CGB emulation corrupts
  the Chinese Crystal translation's dialog tiles — a timing-level emulation
  divergence, not fixable here. Swapped to mGBA 2026-07.)

## Project structure

```
pokemon-vision-agent/
  README.md
  requirements.txt
  config.py            # all tunables in one place
  bridge.lua           # runs inside mGBA: TCP server for press/screenshot
  emulator.py          # mGBA bridge client: press buttons, capture screenshot
  agent.py             # the main agent loop + memory compression
  tools.py             # tool schemas (press_buttons, update_notes)
  prompts.py           # system prompt text
  main.py              # CLI entrypoint (argparse: --rom, optional overrides)
```

## Component requirements

### config.py
Centralize: `MODEL` (default to a cheap model like
`claude-haiku-4-5-20251001` for loop debugging, with comments noting
`claude-sonnet-5` and `claude-fable-5` as alternatives), `SUMMARY_EVERY`
(default 30), `FRAMES_PER_ACTION` (default ~24), `UPSCALE` (default 3),
`MAX_TOKENS`, the frame-stability settle tunables, and the mGBA bridge
settings (binary path, port, screenshot path, launch timeout).

### emulator.py
A client driving one mGBA instance through the `bridge.lua` TCP protocol
(`press <btn> <frames>` / `shot <path>` / `ping`):
- constructor takes `rom_path`; attaches to a running mGBA (ping handshake) or
  launches one. The game runs continuously in real time — picture and sound
  never pause while the model thinks.
- `press(buttons: list[str])`: for each valid button, send a timed press
  (held `BUTTON_HOLD_FRAMES`), pace by `FRAMES_PER_ACTION`, then wait for the
  screen to settle (pixel-diff stability with blank-frame rejection and a
  hard frame cap) so screenshots never catch mid-transition frames. Returns
  (pressed, frames_waited). Ignore invalid buttons.
- `screenshot() -> PIL.Image`: fetch the native frame, upscale by `UPSCALE`
  with nearest-neighbor (keep pixels crisp).
- `tick(n)` (real-time wait) and `stop()` (detach; quit mGBA only if we
  launched it).
- Valid buttons: a, b, start, select, up, down, left, right.

### tools.py
Two Anthropic tool definitions:
- `press_buttons`: input `{ buttons: string[] }` (enum-constrained to the 8
  valid buttons). Description should tell the model to use SHORT sequences (1–5)
  so it can observe results.
- `update_notes`: input `{ notes: string }`. Description: overwrite the whole
  notes blob each time; keep it compact (location, current objective, team
  status, key learnings). This is the only long-term memory.

### prompts.py
The system prompt. Must include, clearly:
1. You play Pokémon on a Game Boy purely by looking at screenshots and pressing
   buttons.
2. DO NOT rely on memorized Pokémon knowledge — maps/menus/layouts may differ;
   trust only the screenshot and your notes.
3. Read all on-screen text every turn; identify character, NPCs, walls, doors,
   menu state.
4. After acting you get a new screenshot — compare to what you expected; if
   nothing changed, your input did something unintended, so reconsider.
5. Keep reasoning short: what you see → what you intend → call the tool.
6. Use update_notes to maintain compact running memory.
7. Be methodical; avoid repeating the same failed action; after a few failures
   try a genuinely different approach.

### agent.py — the main loop
Each turn:
1. Capture screenshot; build a user message = `[image_block, text_block]` where
   the text includes the current notes and asks "what do you do next?".
2. Append to history; call `client.messages.create(...)` with `system` (wrapped
   with `cache_control: ephemeral` for prompt caching), `tools`, and `messages`.
3. Append the assistant response to history.
4. Iterate the response content blocks:
   - `text` → print as the model's reasoning.
   - `tool_use` `press_buttons` → execute on emulator, push a `tool_result`
     ("Buttons pressed. See next screenshot."), increment action counter.
   - `tool_use` `update_notes` → replace notes var, push a `tool_result`
     ("Notes saved.").
5. Append the tool_results as the next user message.
6. Every `SUMMARY_EVERY` actions, run memory compression.

Memory compression function:
- Append a user message asking the model to write a concise progress summary
  (where it is, what it was doing, what worked/didn't, immediate next objective).
- Call the model once for the summary.
- Return a fresh history containing only one user message: the summary framed as
  "[Summary of progress so far] ... Continue playing." (Notes persist
  separately and are re-injected each turn, so they survive compression.)

Handle `KeyboardInterrupt` gracefully and always `stop()` the emulator.

### main.py
argparse with `--rom` (required) and optional flags to override model /
summary interval. Check `ANTHROPIC_API_KEY` is set; exit with a clear message if
not.

### README.md
Install steps, the three run commands, an explicit note that the user must
supply their own legally-obtained ROM (the project ships none), a short cost
warning (vision tokens × thousands of turns adds up; debug on Haiku, use prompt
caching, scope to small goals first), and a one-paragraph explanation of the
vision-only design philosophy.

### requirements.txt
`anthropic`, `pillow` (pin reasonable recent versions). The emulator is an
external app, not a Python dependency.

## Acceptance criteria

- `python main.py --rom <rom>` boots the emulator, skips the intro by ticking a
  few hundred frames, and enters the loop.
- The console streams the model's reasoning, each button press, and notes
  updates.
- Memory compresses every N actions without crashing; notes survive compression.
- No RAM reads, no coordinate/state injection anywhere — verify the model only
  ever receives the screenshot image + its own notes text.
- Code is clean, typed where reasonable, with short docstrings. No dead code,
  no over-engineering.

## Out of scope (do NOT add)

- Navigator / pathfinding / tile-graph BFS.
- RAM-based overlays or any structured game-state extraction.
- A second "critic" model. (Could be a later extension; not now.)
- Any GUI beyond the optional emulator window.

Build it, then give me the run command and tell me roughly what to expect on the
first ~50 actions.
