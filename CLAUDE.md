# CLAUDE.md

Persistent working agreement for this repository. Read this at the start of every
session. `SPEC.md` describes *what to build once*; this file describes *how we
work here ongoing*. When the two conflict, ask.

## What this project is

A deliberately minimal agent that plays a Game Boy Pokémon game **purely from
screenshots**, via the Anthropic API. It mirrors the philosophy of Anthropic's
own "Claude Plays Pokémon" benchmark in its most stripped-down, vision-only form.
The point is to observe the *model's* raw capability, not to engineer a program
that wins. Thinness is a feature, not a limitation.

## Invariants — never violate these

These are the identity of the project. Breaking any of them changes what the
project *is*, so treat them as hard constraints, not preferences.

1. **Vision only.** The model receives the screenshot image and its own notes
   text — nothing else. Never read emulator RAM. Never inject coordinates, map
   tiles, money, badges, party stats, item counts, or any structured game state.
2. **One game-interaction tool.** Button presses only. No navigator, no
   pathfinding, no tile-graph BFS, no movement shortcuts.
3. **Memory is the only allowed non-visual mechanism.** Accordion summarization
   + a free-form notes scratchpad the model controls. Nothing more structured.
4. **The "don't trust your own knowledge" rule stays in the system prompt.** It
   is load-bearing against the hallucinated-route failure mode. Don't soften it.

If a change would touch any invariant, stop and surface it to me first with the
tradeoff spelled out. Do not quietly add scaffolding to "help it play better" —
that is the opposite of this project's goal.

## Cost discipline

API spend is real and this loop runs thousands of turns with image inputs.

- **Default to the cheapest model** (`claude-haiku-4-5-20251001`) for anything
  involving the live loop, including all debugging.
- **Never switch to `claude-fable-5` or run a long session without asking me
  first.** A full run can cost thousands of dollars; that decision is mine.
- Keep prompt caching (`cache_control: ephemeral`) on the system prompt and tool
  definitions. If you change the system prompt or tools, confirm caching still
  applies.
- When testing, scope to a tiny goal (e.g. "leave the starting house") and a low
  action cap. Don't burn tokens proving the loop works.
- If you add a feature that increases per-turn token cost, call it out explicitly
  in your summary.

## Code conventions

- Python 3.11+. Standard library first; only the two declared Python deps
  (`anthropic`, `pillow`). The emulator is external: an mGBA dev build
  (`/Applications/mGBA-dev.app`) autoruns `bridge.lua`, and `emulator.py`
  drives it over a local TCP socket (stdlib only).
- Type hints on public functions. Short docstrings explaining *why*, not *what*.
- Keep the file layout from SPEC.md (config / emulator / agent / tools / prompts
  / main). One responsibility per module.
- All tunables live in `config.py`. No magic numbers scattered through the loop.
- No dead code, no speculative abstraction, no "just in case" config. If it isn't
  used now, don't add it.
- Prefer clarity over cleverness. This is a reference implementation people read
  to understand the design — readability is part of the deliverable.

## When changing the agent loop

- Preserve the turn shape: screenshot+notes in → reasoning+tool_use out →
  tool_result back. Don't reorder so that state leaks in.
- Notes must survive memory compression (they're re-injected each turn, stored
  separately from history). Verify this after any change to compression.
- Print the model's reasoning, each button press, and notes updates to the
  console — observability is the main way I evaluate runs.

## Testing & verification

- After any change, do a short dry run (cheap model, ~10–20 actions) and confirm:
  loop runs, no crash, memory compresses, notes persist.
- Add a quick check (test or assertion) that the user message sent to the API
  contains only the image block + notes text — no injected game state. This
  guards invariant #1 against regressions.
- The emulator should boot, skip the intro, and enter the loop without manual
  intervention. (One-time prerequisite: `bridge.lua` registered as an autorun
  script in mGBA's settings; the agent then attaches to a running mGBA or
  launches one itself.)

## Commits & PRs

- Conventional-commit style: `feat:`, `fix:`, `refactor:`, `docs:`, `chore:`.
- One logical change per commit. Don't bundle a refactor with a behavior change.
- In the PR/summary, always note: did this touch any invariant? did it change
  per-turn cost? what did the dry run show?

## Communication style with me

- Lead with what you changed and why, then details.
- Flag assumptions explicitly rather than guessing silently.
- If something is ambiguous or risks an invariant, ask before doing — I'd rather
  answer a question than unwind a wrong direction.
