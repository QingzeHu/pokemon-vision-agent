"""Main agent loop, accordion-style memory compression, and crash-safe state."""

import base64
import io
import json
import os
import time
from datetime import datetime

import anthropic

import config
from emulator import Emulator
from prompts import SYSTEM_PROMPT
from tools import TOOLS

# cache_control on the system prompt enables prompt caching across turns.
SYSTEM = [
    {
        "type": "text",
        "text": SYSTEM_PROMPT,
        "cache_control": {"type": "ephemeral"},
    }
]


def log(message: str) -> None:
    """Print and mirror to the run log — hours-long runs outlive terminal scrollback."""
    print(message)
    with open(config.LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now():%m-%d %H:%M:%S} {message}\n")


class Agent:
    """Plays the game in a screenshot -> model -> button press loop."""

    def __init__(
        self,
        emulator: Emulator,
        model: str = config.MODEL,
        summary_every: int = config.SUMMARY_EVERY,
        fresh: bool = False,
    ) -> None:
        self.client = anthropic.Anthropic()
        self.emulator = emulator
        self.model = model
        self.summary_every = summary_every
        self.history: list[dict] = []
        self.notes: str = "(no notes yet)"
        self.summary: str = ""
        self.turns_since_summary = 0
        self.total_actions = 0
        self.turns_sent = 0
        self.usage_totals = {
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
            "cost_usd": 0.0,
        }
        os.makedirs(config.DEBUG_FRAMES_DIR, exist_ok=True)
        if fresh and os.path.exists(config.STATE_FILE):
            os.remove(config.STATE_FILE)
            log("[state]  --fresh: previous state discarded")
        else:
            self._restore_state()

    def run(self, max_actions: int | None = None) -> None:
        """Run the agent loop for up to max_actions presses in THIS session
        (forever if None; Ctrl-C to stop). total_actions persists across
        restarts, so the cap must be relative to where this session starts."""
        session_start = self.total_actions
        while max_actions is None or self.total_actions - session_start < max_actions:
            self._turn()
            # Count turns, not presses: every turn adds a screenshot to the
            # history (notes-only turns included), and images are what
            # overflow the context.
            self.turns_since_summary += 1
            if self.turns_since_summary >= self.summary_every:
                self._compress_memory()

    def _call_model(self, messages: list[dict], use_tools: bool = True, **kwargs) -> anthropic.types.Message:
        """messages.create with retries; transient failures must not end the run.

        use_tools=False omits the tools param entirely rather than sending
        tool_choice="none" - some providers behind translation proxies (e.g.
        GPT-5.6's Responses API via litellm) mistranslate that tool_choice
        value into an invalid request. No tools param means nothing to
        choose, which every backend handles correctly.
        """
        delay = config.API_RETRY_DELAY
        for attempt in range(config.API_RETRIES):
            try:
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=config.MAX_TOKENS,
                    system=SYSTEM,
                    messages=self._cache_anchored(messages),
                    **({"tools": TOOLS} if use_tools else {}),
                    **kwargs,
                )
                self._record_usage(response.usage)
                return response
            except (anthropic.APIConnectionError, anthropic.APIStatusError) as e:
                # Client errors other than rate limiting won't fix themselves.
                if isinstance(e, anthropic.APIStatusError) and e.status_code < 500 and e.status_code != 429:
                    raise
                if attempt == config.API_RETRIES - 1:
                    raise
                log(f"[api]    {type(e).__name__}: retry {attempt + 1}/{config.API_RETRIES} in {delay:.0f}s")
                time.sleep(delay)
                delay = min(delay * 2, 120.0)
        raise RuntimeError("unreachable")

    def _cache_anchored(self, messages: list[dict]) -> list[dict]:
        """Copy of messages with cache_control on the last and third-to-last
        user messages, so each request's prefix hits the cache written one
        turn earlier and the whole history bills at the cache-read rate.
        Without these anchors only the system prompt is cached and every
        history image re-bills at full price each turn. Two anchors, not one,
        because the no-tool-call re-ask rewrites the final user message — the
        older anchor still matches then. Anchors go on copies: history itself
        is never mutated, so markers can't pile up past the API's 4-breakpoint
        limit. Non-Anthropic backends ignore the field (cache reads show 0).
        """
        user_idx = [i for i, m in enumerate(messages) if m["role"] == "user"]
        out = list(messages)
        for i in {user_idx[-1], user_idx[max(len(user_idx) - 3, 0)]}:
            content = messages[i]["content"]
            blocks = [{"type": "text", "text": content}] if isinstance(content, str) else list(content)
            blocks[-1] = {**blocks[-1], "cache_control": {"type": "ephemeral"}}
            out[i] = {**messages[i], "content": blocks}
        return out

    def _record_usage(self, usage) -> None:
        """Log this call's tokens/cost and fold it into the session totals.

        Cost is an estimate (list price, not the account's actual billing
        tier) so a run can be compared across models without leaving the
        harness — see config.PRICING. Persisted immediately: usage is the
        kind of thing you want intact even if the process dies mid-turn.
        """
        cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0
        cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
        pricing = config.PRICING.get(self.model)
        cost = None
        if pricing:
            in_price, out_price = pricing
            cost = (
                usage.input_tokens * in_price
                + cache_write * in_price * config.CACHE_WRITE_MULTIPLIER
                + cache_read * in_price * config.CACHE_READ_MULTIPLIER
            ) / 1_000_000 + usage.output_tokens * out_price / 1_000_000

        self.usage_totals["input_tokens"] += usage.input_tokens
        self.usage_totals["output_tokens"] += usage.output_tokens
        self.usage_totals["cache_creation_input_tokens"] += cache_write
        self.usage_totals["cache_read_input_tokens"] += cache_read
        if cost is not None:
            self.usage_totals["cost_usd"] += cost

        cost_note = f"  (${cost:.4f}, session ${self.usage_totals['cost_usd']:.2f})" if cost is not None else ""
        log(
            f"[usage]  in={usage.input_tokens} out={usage.output_tokens} "
            f"cache_write={cache_write} cache_read={cache_read}{cost_note}"
        )
        self._save_state()

    def log_usage_summary(self) -> None:
        """Print/save the running session totals — call once when a run ends."""
        u = self.usage_totals
        cost_str = f"${u['cost_usd']:.2f}" if self.model in config.PRICING else "unknown (no price entry for this model)"
        log(
            f"[usage]  SESSION TOTAL — in={u['input_tokens']} out={u['output_tokens']} "
            f"cache_write={u['cache_creation_input_tokens']} cache_read={u['cache_read_input_tokens']} "
            f"cost={cost_str}"
        )

    def _turn(self) -> None:
        """One turn: screenshot -> model call -> execute tool calls.

        The user message joins the history only after the call succeeds, so a
        retried/failed call never leaves a half-appended turn behind.
        """
        message = self._user_message()
        response = self._call_model(self.history + [message])

        # A reply with no tool call presses nothing. Discard it and re-ask
        # (with a nudge appended to the SAME screenshot) instead of letting the
        # narrated pseudo-call into history, where it would become a format
        # example that drags weaker models into narrating instead of acting.
        for _ in range(config.TOOLLESS_RETRIES):
            if any(block.type == "tool_use" for block in response.content):
                break
            log("[warn]   reply contained no tool call - discarding and re-asking")
            nudge = {
                "role": "user",
                "content": message["content"][:-1]
                + [
                    {
                        "type": "text",
                        "text": (
                            message["content"][-1]["text"]
                            + "\n\nIMPORTANT: your previous reply was discarded "
                            "because it did not invoke any tool. Writing "
                            "press_buttons(...) as plain text does NOT press "
                            "buttons. You must CALL the press_buttons tool."
                        ),
                    }
                ],
            }
            response = self._call_model(self.history + [nudge])

        self.history.append(message)
        self.history.append({"role": "assistant", "content": response.content})

        tool_results = []
        for block in response.content:
            if block.type == "text":
                log(f"\n[{self.model}] {block.text}")
            elif block.type == "tool_use":
                tool_results.append(self._handle_tool(block))
        if tool_results:
            self.history.append({"role": "user", "content": tool_results})

    def _user_message(self) -> dict:
        """Current screenshot + notes. This is everything the model gets to see."""
        frame = self.emulator.screenshot()
        self.turns_sent += 1
        frame.save(os.path.join(config.DEBUG_FRAMES_DIR, f"turn_{self.turns_sent:05d}.png"))
        buf = io.BytesIO()
        frame.save(buf, format="PNG")
        content = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": base64.b64encode(buf.getvalue()).decode("ascii"),
                },
            },
            {
                "type": "text",
                "text": (
                    f"Your notes:\n{self.notes}\n\n"
                    "This is the current screen. What do you do next?"
                ),
            },
        ]
        # Invariant #1: the model sees the screenshot and its notes — nothing else.
        assert [block["type"] for block in content] == ["image", "text"]
        return {"role": "user", "content": content}

    def _handle_tool(self, block) -> dict:
        """Execute one tool_use block and return its tool_result."""
        if block.name == "press_buttons":
            pressed, waited = self.emulator.press(block.input.get("buttons", []))
            log(f"[press]  {' '.join(pressed) if pressed else '(wait)'}  [settled in {waited} frames]")
            self.total_actions += 1
            result = (
                "Buttons pressed. See next screenshot."
                if pressed
                else "Waited while the game ran. See next screenshot."
            )
        elif block.name == "update_notes":
            self.notes = block.input.get("notes", "")
            log(f"[notes]  {self.notes}")
            self._save_state()
            result = "Notes saved."
        else:
            result = f"Unknown tool: {block.name}"
        return {"type": "tool_result", "tool_use_id": block.id, "content": result}

    def _compress_memory(self) -> None:
        """Ask the model for a progress summary, then reset history to just that summary.

        Notes live outside the history and are re-injected each turn, so they
        survive compression untouched.
        """
        log("\n[memory] compressing history...")
        request = {
            "role": "user",
            "content": (
                "Pause for a moment. Write a concise progress summary: where you "
                "are, what you were doing, what worked and what didn't, and your "
                "immediate next objective. Reply with the summary text only."
            ),
        }
        response = self._call_model(self.history + [request], use_tools=False)
        self.summary = "".join(b.text for b in response.content if b.type == "text")
        log(f"[memory] {self.summary}")
        self.history = [self._summary_message()]
        self.turns_since_summary = 0
        self._save_state()

    def _summary_message(self) -> dict:
        # The reminder matters: compression deletes every past tool_use block,
        # and without those format anchors weaker models start narrating
        # button presses as text instead of calling the tool.
        return {
            "role": "user",
            "content": (
                f"[Summary of progress so far]\n{self.summary}\n\n"
                "Continue playing. Act only by invoking the press_buttons tool "
                "(and update_notes for memory) - text alone presses nothing."
            ),
        }

    def _save_state(self) -> None:
        """Persist the agent's mind (notes + summary) atomically after every change."""
        state = {
            "notes": self.notes,
            "summary": self.summary,
            "total_actions": self.total_actions,
            "turns_sent": self.turns_sent,
            "usage_totals": self.usage_totals,
        }
        tmp = config.STATE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        os.replace(tmp, config.STATE_FILE)

    def _restore_state(self) -> None:
        """Resume from a previous run: notes come back, history restarts from
        the last summary — the same shape a compression would have left."""
        if not os.path.exists(config.STATE_FILE):
            return
        with open(config.STATE_FILE, encoding="utf-8") as f:
            state = json.load(f)
        self.notes = state.get("notes", self.notes)
        self.summary = state.get("summary", "")
        self.total_actions = state.get("total_actions", 0)
        self.turns_sent = state.get("turns_sent", 0)
        self.usage_totals.update(state.get("usage_totals", {}))
        if self.summary:
            self.history = [self._summary_message()]
        log(f"[state]  resumed: {self.total_actions} actions so far, notes {len(self.notes)} chars")
