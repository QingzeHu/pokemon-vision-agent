"""Anthropic tool definitions for the agent."""

BUTTONS = ["a", "b", "start", "select", "up", "down", "left", "right"]

TOOLS = [
    {
        "name": "press_buttons",
        "description": (
            "Press a sequence of Game Boy buttons. Use SHORT sequences (1-5 presses) "
            "so you can observe the result on the next screenshot before deciding "
            "what to do next. Pass an EMPTY list to wait: the game runs for a moment "
            "without input. Use this during intros, cutscenes, and animations that "
            "cannot be skipped with buttons."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "buttons": {
                    "type": "array",
                    "items": {"type": "string", "enum": BUTTONS},
                    "description": "Buttons to press, in order.",
                }
            },
            "required": ["buttons"],
        },
    },
    {
        "name": "update_notes",
        "description": (
            "Overwrite your entire notes scratchpad with new text. This is your ONLY "
            "long-term memory: older conversation history is periodically discarded, "
            "but notes survive. Keep them compact: current location, current objective, "
            "team status, and key learnings (what worked, what failed)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "notes": {
                    "type": "string",
                    "description": "The full new contents of your notes.",
                }
            },
            "required": ["notes"],
        },
    },
]
