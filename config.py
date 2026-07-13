"""All tunables in one place."""

import os

# Everything one run produces (state, log, frames) lives under this directory,
# and the bridge port is per-run too — so two agents (e.g. local model vs
# Claude) can run side by side without polluting each other. Defaults keep
# single-instance behavior unchanged.
RUN_DIR = os.environ.get("POKEMON_RUN_DIR", ".")
BRIDGE_PORT = int(os.environ.get("POKEMON_BRIDGE_PORT", "8888"))

# Model used for the agent loop. Haiku is cheap/fast for debugging the harness.
# Stronger alternatives once the loop works:
#   MODEL = "claude-sonnet-4-6"
#   MODEL = "claude-fable-5"
MODEL = "claude-haiku-4-5-20251001"

# Max output tokens per API call. Set far above any real reasoning chain —
# a truncated reply loses its tool call and wastes the whole (full-price)
# call, which costs more than long output ever does. Observed needs: Fable 5
# reasoning ~1-2K, qwen thinking chains ~2K+. Not unlimited: the cap is the
# circuit breaker against degenerate repetition loops (junk tokens at output
# price, minutes of decode per turn).
MAX_TOKENS = 8192

# Replies with no tool call are discarded and re-asked this many times before
# being accepted into history. Keeping the narrated pseudo-calls OUT of the
# history matters: once one gets in, it becomes a format example and weaker
# models spiral into narrating instead of acting.
TOOLLESS_RETRIES = 2

# Compress conversation history every N turns. Every turn adds one screenshot
# (~1.5-2K tokens), so N=20 keeps the history near 40K — safely inside a 64K
# context. Raise only together with the model's loaded context length.
SUMMARY_EVERY = 20

# Frames the emulator advances after each button press (~60 fps; 16 ~= 0.27s).
FRAMES_PER_ACTION = 16

# Frames a button is held down (must be < FRAMES_PER_ACTION to release in time).
BUTTON_HOLD_FRAMES = 10

# --- Frame-stability settle ---
# After each action the emulator ticks until the screen stops changing, so
# screenshots never catch mid-transition frames (scrolling text, fades,
# half-loaded maps). Pixel comparison only — no RAM is read.

# Frames between stability comparisons. Wide enough that scrolling text
# changes many pixels per check and keeps the wait alive until it finishes.
STABLE_CHECK_INTERVAL = 12

# A check counts as stable if at most this fraction of pixels changed.
# Nonzero because idle animations (water, flowers, blinking cursors) never
# fully stop; low enough that text still printing never counts as stable.
STABLE_DIFF_THRESHOLD = 0.01

# Consecutive stable checks required before taking the screenshot.
STABLE_CHECKS = 2

# A frame where one gray value covers at least this fraction of pixels is
# "blank" (mid-fade black/white) and never counts as stable — keep waiting.
BLANK_SCREEN_FRACTION = 0.99

# Hard cap on the settle wait, so looping animations can't stall a turn.
MAX_SETTLE_FRAMES = 300

# Every screenshot sent to the model is also saved here (observability).
DEBUG_FRAMES_DIR = os.path.join(RUN_DIR, "debug_frames")

# Scratch file the bridge writes each screenshot to before Python reads it.
BRIDGE_SHOT_PATH = os.path.join(DEBUG_FRAMES_DIR, "live_shot.png")

# --- Long-run resilience ---
# Transient API failures (LM Studio restart, network blips) must not kill an
# hours-long run: retry with doubling delay, capped, before giving up.
API_RETRIES = 8
API_RETRY_DELAY = 5.0  # seconds; doubles each attempt, capped at 120

# Notes + latest summary + action count, saved after every change so a crash
# or restart never loses the agent's "mind". Delete it (or run --fresh) to
# start over. The game itself persists separately via mGBA's battery save.
STATE_FILE = os.path.join(RUN_DIR, "agent_state.json")

# Console output is mirrored here with timestamps (append; survives restarts).
LOG_FILE = os.path.join(RUN_DIR, "run.log")

# --- Cost tracking ---
# Per-million-token USD price (input, output), used only to estimate spend in
# logs — not authoritative billing. A model absent from this table still gets
# its token counts logged, just without a $ estimate, rather than guessing.
#
# No provider exposes a pricing API (checked 2026-07-12: Anthropic's
# models.retrieve() returns capabilities but no price field; the "OpenAI
# pricing API" that shows up in search results is an unofficial third-party
# wrapper) — these numbers only go stale by hand, so check them by hand.
# Official pricing pages, for whenever this table needs a refresh:
#   Anthropic — https://platform.claude.com/docs/en/pricing
#   OpenAI    — https://developers.openai.com/api/docs/pricing
#   xAI       — https://x.ai/api  (or https://docs.x.ai/docs/api-reference)
PRICING = {
    # Claude — api.anthropic.com list price.
    "claude-haiku-4-5-20251001": (1.00, 5.00),
    "claude-sonnet-5": (3.00, 15.00),
    "claude-opus-4-8": (5.00, 25.00),
    "claude-fable-5": (10.00, 50.00),
    # Non-Claude, via the litellm proxy — third-party list price, not eligible
    # for Anthropic-style prompt-cache discounting (cache fields read as 0).
    "openai/gpt-5.6-sol": (5.00, 30.00),
    "openai/gpt-5.6-terra": (2.50, 15.00),
    "openai/gpt-5.6-luna": (1.00, 6.00),
    "xai/grok-4.5": (2.00, 6.00),
}
# Cache write/read multipliers on the input price (Anthropic prompt caching).
CACHE_WRITE_MULTIPLIER = 1.25
CACHE_READ_MULTIPLIER = 0.1

# Nearest-neighbor upscale factor for screenshots sent to the model.
# 2x halves vision prefill time vs 3x; measured OCR quality is unchanged
# (Chinese dialog text reads correctly even at 1x).
UPSCALE = 2

# Frames ticked once at boot to get past the BIOS/intro splash.
BOOT_FRAMES = 600

# --- mGBA bridge ---
# The game runs in a real mGBA (dev build with autorun scripts); bridge.lua
# serves button/screenshot commands over TCP. BRIDGE_PORT is defined above
# (per-run, from the environment).
MGBA_BINARY = "/Applications/mGBA-dev.app/Contents/MacOS/mGBA"
MGBA_LAUNCH_TIMEOUT = 20  # seconds to wait for the autorun bridge after launch
