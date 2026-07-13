# The game runs in mGBA (dev build, /Applications/mGBA-dev.app) with
# bridge.lua configured as an autorun script — the agent attaches to it, or
# launches it automatically. The game window and sound are always on and the
# game never pauses while the model thinks.
#
# Every target below plays on its OWN copy of the ROM inside runs/<label>/,
# with its own save file, agent_state.json, run.log, and debug_frames/ — so
# `make local` and `make opus` (or any combination) can run at the same time
# without their notes, logs, or game progress touching each other.
#
# Usage (local model, free):
#   make dry                    quick 10-action sanity run
#   make local                  play until Ctrl-C (qwen3.6)
#   make local-gemma            same, on Gemma 4 31B dense
#   make local MAX_ACTIONS=200  bounded run
#   make stop                   unload the local model / stop LM Studio server
#
# Usage (cloud models, real money — see CLAUDE.md cost discipline):
#   make claude                 Haiku,  capped at 1000 actions, fresh mind
#   make opus                   Opus 4.8
#   make fable5                 Fable 5
#   make gpt                    GPT-5.6 Sol, via a local litellm proxy
#   make grok                   Grok 4.5,    via a local litellm proxy
#   make claude MAX_ACTIONS=20  quick try of any of the above
#   make claude FRESH=0         resume that model's saved notes instead
#   make reset LABEL=opus       wipe one model's run dir (mind + save)
#   make stop-cloud             stop the litellm proxy
#
# Keys live in secrets/ (gitignored): $ANTHROPIC_API_KEY or
# secrets/anthropic_api_key (Claude); $OPENAI_API_KEY or
# secrets/openai_api_key (GPT); $XAI_API_KEY or secrets/xai_api_key (Grok).

MODEL ?= qwen/qwen3.6-35b-a3b
ROM ?= roms/shuijing.gbc
RUNS_DIR ?= runs
# 64K: SUMMARY_EVERY=20 turns × ~2K tokens/turn (one screenshot each) needs
# headroom; LM Studio 500s on overflow because images can't be truncated.
CONTEXT ?= 65536
LOCAL_URL ?= http://localhost:1234
CLOUD_PROXY_PORT ?= 4000

# Switch any of these deliberately — a long run on a big model costs real
# money: make opus MAX_ACTIONS=20, make gpt GPT_MODEL=openai/gpt-5.6-luna
CLAUDE_MODEL ?= claude-haiku-4-5-20251001
GPT_MODEL ?= openai/gpt-5.6-sol
GROK_MODEL ?= xai/grok-4.5

claude claude-dry: MODEL = $(CLAUDE_MODEL)
opus:   MODEL = claude-opus-4-8
fable5: MODEL = claude-fable-5
gpt:    MODEL = $(GPT_MODEL)
grok:   MODEL = $(GROK_MODEL)

# MAX_ACTIONS unset = run forever (Ctrl-C to stop).
claude opus fable5 gpt grok: MAX_ACTIONS ?= 1000
# These are "try it out" runs: start with a blank mind each time (FRESH=0 to
# resume that model's saved notes instead). `local` is the long-haul run and
# resumes by default — that asymmetry is intentional.
claude opus fable5 gpt grok: FRESH ?= 1

# Per-model isolation: a dedicated run dir, ROM copy, and bridge port, so
# nothing collides if several of these run at once.
local:      RUN_LABEL = local
local-gemma: RUN_LABEL = local-gemma
dry:        RUN_LABEL = dry
claude:     RUN_LABEL = claude
claude-dry: RUN_LABEL = claude-dry
opus:       RUN_LABEL = opus
fable5:     RUN_LABEL = fable5
gpt:        RUN_LABEL = gpt
grok:       RUN_LABEL = grok
local:      PORT = 8888
local-gemma: PORT = 8895
dry:        PORT = 8898
claude:     PORT = 8889
claude-dry: PORT = 8899
opus:       PORT = 8890
fable5:     PORT = 8891
gpt:        PORT = 8892
grok:       PORT = 8893

RUN_DIR = $(RUNS_DIR)/$(RUN_LABEL)
RUN_ROM = $(RUN_DIR)/$(notdir $(ROM))
# Copy the ROM in once per label, then leave it (and the .sav mGBA grows next
# to it) alone on every later run. Test-then-copy, not `cp -n`: BSD cp (macOS)
# exits 1 when the destination already exists, unlike GNU cp's silent no-op —
# `-n` alone would fail this every run after the first.
ISOLATE = mkdir -p $(RUN_DIR) && { [ -f $(RUN_ROM) ] || cp $(ROM) $(RUN_ROM); }
RUN_ENV = POKEMON_RUN_DIR=$(RUN_DIR) POKEMON_BRIDGE_PORT=$(PORT)

AGENT_FLAGS = --rom $(RUN_ROM) --model "$(MODEL)" \
	$(if $(MAX_ACTIONS),--max-actions $(MAX_ACTIONS)) \
	$(if $(filter 1,$(FRESH)),--fresh)

LOCAL_ENV = ANTHROPIC_API_KEY=lmstudio ANTHROPIC_BASE_URL=$(LOCAL_URL)
# tr strips stray whitespace/newlines around the key in the file.
CLAUDE_ENV = ANTHROPIC_API_KEY="$${ANTHROPIC_API_KEY:-$$(cat secrets/anthropic_api_key 2>/dev/null | tr -d '[:space:]')}"
# GPT/Grok aren't Anthropic models: litellm (started by serve-cloud) sits in
# between and translates /v1/messages to each provider's own API. The key
# here is a dummy — auth happens inside the proxy with the real provider key.
CLOUD_ENV = ANTHROPIC_API_KEY=sk-local ANTHROPIC_BASE_URL=http://localhost:$(CLOUD_PROXY_PORT)

.PHONY: serve local local-gemma dry claude claude-dry opus fable5 gpt grok \
        serve-cloud stop-cloud check-key check-openai-key check-xai-key reset stop

# Start the LM Studio server and load the vision model. Idempotent, keyed on
# model name AND context length: a GUI/JIT load leaves the model up at the
# 8192 default, where the agent's first screenshot request overflows and LM
# Studio 500s — so a name-only check would happily reuse the wrong instance.
# Reload (unload first: a second bare `lms load` would duplicate the model
# and double the RAM use) whenever the loaded context differs.
serve:
	lms server start
	@lms ps | grep "$(MODEL)" | grep -q "$(CONTEXT)" || { \
		(lms ps | grep -q "$(MODEL)" && lms unload "$(MODEL)") || true; \
		lms load "$(MODEL)" --context-length $(CONTEXT) --yes; \
	}

local: serve
	@$(ISOLATE)
	$(RUN_ENV) $(LOCAL_ENV) uv run python main.py $(AGENT_FLAGS)

# Gemma 4 31B is DENSE — every token runs all 31B params, ~10x the active
# compute of the A3B-class models. The next probe of the capability floor.
local-gemma: MODEL = google/gemma-4-31b
local-gemma: serve
	@$(ISOLATE)
	$(RUN_ENV) $(LOCAL_ENV) uv run python main.py $(AGENT_FLAGS)

dry: serve
	@$(ISOLATE)
	$(RUN_ENV) $(LOCAL_ENV) uv run python main.py $(AGENT_FLAGS) --max-actions 10 --summary-every 5

claude: check-key
	@$(ISOLATE)
	$(RUN_ENV) $(CLAUDE_ENV) uv run python main.py $(AGENT_FLAGS)

claude-dry: check-key
	@$(ISOLATE)
	$(RUN_ENV) $(CLAUDE_ENV) uv run python main.py $(AGENT_FLAGS) --max-actions 10 --summary-every 5

opus: check-key
	@$(ISOLATE)
	$(RUN_ENV) $(CLAUDE_ENV) uv run python main.py $(AGENT_FLAGS)

fable5: check-key
	@$(ISOLATE)
	$(RUN_ENV) $(CLAUDE_ENV) uv run python main.py $(AGENT_FLAGS)

gpt: check-openai-key serve-cloud
	@$(ISOLATE)
	$(RUN_ENV) $(CLOUD_ENV) uv run python main.py $(AGENT_FLAGS)

grok: check-xai-key serve-cloud
	@$(ISOLATE)
	$(RUN_ENV) $(CLOUD_ENV) uv run python main.py $(AGENT_FLAGS)

check-key:
	@[ -n "$${ANTHROPIC_API_KEY:-$$(cat secrets/anthropic_api_key 2>/dev/null | tr -d '[:space:]')}" ] || \
		{ echo "Error: no API key. Export ANTHROPIC_API_KEY or put your key in secrets/anthropic_api_key"; exit 1; }

check-openai-key:
	@[ -n "$${OPENAI_API_KEY:-$$(cat secrets/openai_api_key 2>/dev/null | tr -d '[:space:]')}" ] || \
		{ echo "Error: no OpenAI API key. Export OPENAI_API_KEY or put it in secrets/openai_api_key"; exit 1; }

check-xai-key:
	@[ -n "$${XAI_API_KEY:-$$(cat secrets/xai_api_key 2>/dev/null | tr -d '[:space:]')}" ] || \
		{ echo "Error: no xAI API key. Export XAI_API_KEY or put it in secrets/xai_api_key"; exit 1; }

# litellm translates Anthropic-format requests to OpenAI/xAI's own APIs, so
# GPT and Grok work through the same anthropic-SDK code path as every Claude
# model. Idempotent (skips if already listening); run via uvx so litellm
# stays an external tool, not a project dependency. Pinned to --python 3.12:
# litellm's Rust extension doesn't build yet on the 3.14 default.
serve-cloud:
	@nc -z localhost $(CLOUD_PROXY_PORT) 2>/dev/null || { \
		echo "[cloud] starting litellm proxy on :$(CLOUD_PROXY_PORT)..."; \
		OPENAI_API_KEY="$${OPENAI_API_KEY:-$$(cat secrets/openai_api_key 2>/dev/null | tr -d '[:space:]')}" \
		XAI_API_KEY="$${XAI_API_KEY:-$$(cat secrets/xai_api_key 2>/dev/null | tr -d '[:space:]')}" \
		nohup uvx --python 3.12 --from 'litellm[proxy]' litellm \
			--config litellm_config.yaml --port $(CLOUD_PROXY_PORT) \
			> litellm.log 2>&1 & echo $$! > .litellm.pid; \
		until nc -z localhost $(CLOUD_PROXY_PORT) 2>/dev/null; do sleep 1; done; \
	}

stop-cloud:
	@[ -f .litellm.pid ] && kill "$$(cat .litellm.pid)" 2>/dev/null && rm -f .litellm.pid && echo "[cloud] stopped" || echo "[cloud] not running"

# Wipe one model's mind AND game save for a true from-scratch run, e.g.
# `make reset LABEL=opus`. run.log and debug_frames are kept for analysis.
reset:
	@[ -n "$(LABEL)" ] || { echo "Usage: make reset LABEL=<local|claude|opus|fable5|gpt|grok>"; exit 1; }
	rm -f $(RUNS_DIR)/$(LABEL)/agent_state.json $(RUNS_DIR)/$(LABEL)/*.sav

stop:
	lms unload --all
	lms server stop
