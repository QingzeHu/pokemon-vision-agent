"""CLI entrypoint: python main.py --rom <path-to-rom>"""

import argparse
import os
import sys
import traceback

import config
from agent import Agent, log
from emulator import Emulator


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Vision-only Pokemon-playing agent (Anthropic API + mGBA)"
    )
    parser.add_argument("--rom", required=True, help="Path to a legally-obtained ROM (.gb/.gbc/.gba)")
    parser.add_argument("--model", default=config.MODEL, help=f"Anthropic model id (default: {config.MODEL})")
    parser.add_argument("--summary-every", type=int, default=config.SUMMARY_EVERY, help=f"Compress memory every N turns (default: {config.SUMMARY_EVERY})")
    parser.add_argument("--max-actions", type=int, default=None, help="Stop after N actions (default: run forever)")
    parser.add_argument("--fresh", action="store_true", help="Discard saved notes/summary and start over (also start a new game save)")
    args = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("Error: ANTHROPIC_API_KEY is not set. Export it and try again.")

    if not args.rom.lower().endswith((".gb", ".gbc", ".gba")):
        sys.exit(f"Error: {args.rom!r} is not a Game Boy ROM (.gb/.gbc/.gba).")

    emulator = Emulator(args.rom)
    emulator.tick(config.BOOT_FRAMES)  # let the boot/intro splash play out

    agent = Agent(emulator, model=args.model, summary_every=args.summary_every, fresh=args.fresh)
    try:
        agent.run(max_actions=args.max_actions)
    except KeyboardInterrupt:
        print("\nStopped by user.")
    except Exception:
        # Unattended runs must leave a trace even when nobody's watching the
        # terminal - an uncaught exception otherwise only prints to a
        # scrollback that may already be gone by the time someone looks.
        log("[fatal]  " + traceback.format_exc())
        raise
    finally:
        agent.log_usage_summary()
        emulator.stop()


if __name__ == "__main__":
    main()
