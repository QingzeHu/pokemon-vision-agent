"""Asserts on the request body the agent builds, without calling the API.

Two classes of bug are invisible at runtime and only show up on the bill or in
a post-mortem, which is why they get a test instead of a code comment:

  * A leaked-state regression. Invariant #1 says the model sees the screenshot
    and its notes, nothing else. A stray content block would still run fine.

  * A cache regression. Prompt caching is a prefix match over
    tools -> system -> messages, so anything that varies the tools or rewrites
    history silently re-bills the whole conversation at the cache-WRITE rate.
    That is exactly how the summary turn used to cost 24% of a run.

Run it with `make test` (or `python test_request_shape.py`). No pytest needed,
though the names are compatible with it.
"""

import json
import os
import sys
import tempfile

os.environ.setdefault("POKEMON_RUN_DIR", tempfile.mkdtemp(prefix="pokemon-test-"))

import anthropic
from PIL import Image

import config

THINKING_MODEL = next(iter(config.THINKING_MODELS))
PLAIN_MODEL = "claude-haiku-4-5-20251001"


class FakeBlock:
    """A content block, duck-typed like the SDK's."""

    def __init__(self, **fields) -> None:
        self.__dict__.update(fields)


class FakeResponse:
    def __init__(self, content: list[FakeBlock]) -> None:
        self.content = content
        self.usage = FakeBlock(
            input_tokens=1,
            output_tokens=1,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=0,
        )


class FakeClient:
    """Records every request body instead of sending it.

    summary_calls_tool simulates the one failure mode the fix introduces: tools
    now stay on the summary turn (for the cache), so the model *can* call one
    there instead of writing text.
    """

    requests: list[dict] = []
    summary_calls_tool = False

    def __init__(self, *args, **kwargs) -> None:
        self.messages = self

    def create(self, **kwargs) -> FakeResponse:
        FakeClient.requests.append(kwargs)
        last = kwargs["messages"][-1]["content"]
        text = last[-1]["text"] if isinstance(last, list) else last

        if "progress summary" in text:
            if FakeClient.summary_calls_tool:
                return FakeResponse([FakeBlock(type="tool_use", id="s", name="press_buttons", input={"buttons": ["a"]})])
            return FakeResponse([FakeBlock(type="text", text="Summary: on Route 29.")])

        return FakeResponse([
            FakeBlock(type="thinking", thinking="Reasoning happens here."),
            FakeBlock(type="tool_use", id="n", name="update_notes", input={"notes": "Ledges are one-way."}),
            FakeBlock(type="tool_use", id="p", name="press_buttons", input={"buttons": ["down"]}),
        ])


class FakeEmulator:
    def __init__(self) -> None:
        self.presses: list[list[str]] = []

    def screenshot(self) -> Image.Image:
        return Image.new("RGB", (320, 288), "green")

    def press(self, buttons: list[str]) -> tuple[list[str], int]:
        self.presses.append(list(buttons))
        return list(buttons), 24


anthropic.Anthropic = FakeClient

import agent as agent_module

agent_module.log = lambda message: None  # keep the test output readable

SUMMARY_EVERY = 3  # small enough that a short run compresses


def capture(model: str = PLAIN_MODEL, actions: int = 4):
    """Run the loop against fakes; return (requests, agent, emulator)."""
    FakeClient.requests = []
    emulator = FakeEmulator()
    agent = agent_module.Agent(emulator, model=model, summary_every=SUMMARY_EVERY, fresh=True)
    agent.run(max_actions=actions)
    return FakeClient.requests, agent, emulator


def summary_requests(requests: list[dict]) -> list[dict]:
    return [r for r in requests if "progress summary" in str(r["messages"][-1]["content"])]


def content_only(message: dict) -> str:
    """A message's content, minus cache_control.

    cache_control marks a breakpoint; it is not part of the cached bytes, and
    it legitimately moves forward every turn. Comparing prefixes with the
    markers left in would report a mismatch where the cache actually hits.
    """
    def strip(block):
        # Assistant turns carry SDK block objects, not dicts - they have no
        # cache_control and serialize via default=str below.
        if not isinstance(block, dict):
            return block
        return {k: v for k, v in block.items() if k != "cache_control"}

    content = message["content"]
    if isinstance(content, list):
        content = [strip(block) for block in content]
    return json.dumps({"role": message["role"], "content": content}, sort_keys=True, default=str)


def breakpoints(request: dict) -> int:
    count = sum(1 for block in request["system"] if "cache_control" in block)
    for message in request["messages"]:
        if isinstance(message["content"], list):
            count += sum(1 for b in message["content"] if isinstance(b, dict) and "cache_control" in b)
    return count


# --- Invariants -------------------------------------------------------------

def test_user_message_is_screenshot_and_notes_only() -> None:
    """Invariant #1: no game state may ride along with the screenshot."""
    requests, _, _ = capture()
    turns = [
        r["messages"][-1]["content"]
        for r in requests
        if isinstance(r["messages"][-1]["content"], list)
        and any(b.get("type") == "image" for b in r["messages"][-1]["content"])
    ]
    assert turns, "no screenshot turn was captured"
    for content in turns:
        # Report the block types, not the blocks - one of them is a base64 PNG.
        types = [block["type"] for block in content]
        assert types == ["image", "text"], f"extra content in the user turn: {types}"


def test_notes_survive_compression() -> None:
    """Invariant #3: notes live outside history, so compression must not drop them."""
    requests, agent, _ = capture()
    assert summary_requests(requests), "the run never compressed"
    assert "one-way" in agent.notes, agent.notes
    # Compression throws the turns away and restarts history from the summary.
    assert "[Summary of progress so far]" in agent.history[0]["content"]


# --- Prompt caching ---------------------------------------------------------

def test_every_call_sends_identical_tools_and_system() -> None:
    """The cached prefix is tools -> system -> messages; vary either and the
    whole history re-bills at the write rate."""
    requests, _, _ = capture()
    assert summary_requests(requests), "the run never compressed"
    assert all("tools" in r for r in requests), "a call omitted tools"
    assert len({json.dumps(r["tools"], sort_keys=True) for r in requests}) == 1
    assert len({json.dumps(r["system"], sort_keys=True) for r in requests}) == 1


def test_compression_appends_to_the_cached_prefix() -> None:
    """The summary turn must reuse the previous call's messages verbatim and
    only append, or it reads nothing from cache."""
    requests, _, _ = capture()
    summary = summary_requests(requests)[0]
    previous = requests[requests.index(summary) - 1]

    before = [content_only(m) for m in previous["messages"]]
    after = [content_only(m) for m in summary["messages"]]
    assert after[: len(before)] == before, "the summary turn rewrote history"
    assert len(after) > len(before), "the summary turn appended nothing"


def test_cache_breakpoints_stay_within_the_api_limit() -> None:
    requests, _, _ = capture()
    for request in requests:
        assert breakpoints(request) <= 4, f"{breakpoints(request)} breakpoints, API allows 4"


# --- Reasoning visibility ---------------------------------------------------

def test_thinking_is_sent_only_to_models_that_already_think() -> None:
    """Sending it elsewhere either enables thinking (a cost change) or 400s."""
    plain, _, _ = capture(PLAIN_MODEL)
    assert all("thinking" not in r for r in plain)

    thinking, _, _ = capture(THINKING_MODEL)
    assert all(r.get("thinking") == config.THINKING for r in thinking)


# --- The failure mode the cache fix introduces -------------------------------

def test_summary_turn_that_calls_a_tool_keeps_the_previous_summary() -> None:
    """Tools stay on the summary turn for the cache, so the model may call one
    instead of writing text. Blanking the summary would wipe the run's only
    long-term memory; pressing its buttons would be worse."""
    FakeClient.summary_calls_tool = True
    try:
        _, agent, emulator = capture()
    finally:
        FakeClient.summary_calls_tool = False

    assert agent.summary == "", "a tool-calling summary turn must not overwrite the summary"
    assert ["a"] not in emulator.presses, "the summary turn's tool call must never reach the emulator"


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for test in tests:
        try:
            test()
            print(f"  pass  {test.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {test.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
