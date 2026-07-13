"""mGBA wrapper: press buttons, wait for a stable frame, capture screenshots.

The game runs in a real mGBA process (accurate rendering, native window and
sound, never pauses while the model thinks). This module talks to it over the
TCP bridge served by bridge.lua, which mGBA autoruns on launch (configured
once in mGBA's settings). If an mGBA with the bridge is already running, we
attach to it; otherwise we launch one with the requested ROM.
"""

import os
import socket
import subprocess
import time

from PIL import Image, ImageChops

import config

VALID_BUTTONS = frozenset({"a", "b", "start", "select", "up", "down", "left", "right"})


class Emulator:
    """Drives one mGBA instance through the Lua bridge."""

    def __init__(self, rom_path: str) -> None:
        self._shot_path = os.path.abspath(config.BRIDGE_SHOT_PATH)
        os.makedirs(os.path.dirname(self._shot_path), exist_ok=True)
        self.process: subprocess.Popen | None = None
        if not self._bridge_up():
            self.process = subprocess.Popen(
                [config.MGBA_BINARY, os.path.abspath(rom_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env={**os.environ, "POKEMON_BRIDGE_PORT": str(config.BRIDGE_PORT)},
            )
            self._wait_for_bridge()
        self.sock = socket.create_connection(("localhost", config.BRIDGE_PORT), timeout=10)
        self._recv_buffer = b""
        if self._command("ping") != "pong":
            raise RuntimeError("mGBA bridge did not answer ping")

    def _bridge_up(self) -> bool:
        """Probe with a full ping/pong handshake — a bare connect-and-close
        looks like a port scan and adds no information."""
        try:
            probe = socket.create_connection(("localhost", config.BRIDGE_PORT), timeout=0.5)
            probe.settimeout(2)
            probe.sendall(b"ping\n")
            data = probe.recv(16)
            probe.close()
            return data.startswith(b"pong")
        except OSError:
            return False

    def _wait_for_bridge(self) -> None:
        deadline = time.monotonic() + config.MGBA_LAUNCH_TIMEOUT
        while time.monotonic() < deadline:
            if self._bridge_up():
                return
            if self.process and self.process.poll() is not None:
                raise RuntimeError("mGBA exited before the bridge came up")
            time.sleep(0.3)
        raise RuntimeError(
            "mGBA bridge not reachable. Is bridge.lua configured as an autorun "
            "script in mGBA's settings? (Settings > Scripting > Edit autorun scripts)"
        )

    def _command(self, line: str) -> str:
        """Send one bridge command, return its one-line reply."""
        self.sock.sendall(line.encode("ascii") + b"\n")
        while b"\n" not in self._recv_buffer:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise RuntimeError("mGBA bridge closed the connection")
            self._recv_buffer += chunk
        reply, self._recv_buffer = self._recv_buffer.split(b"\n", 1)
        return reply.decode("ascii").strip()

    def press(self, buttons: list[str]) -> tuple[list[str], int]:
        """Press each valid button in order, then wait for the screen to settle.

        Returns (buttons actually pressed, frames waited to settle). An empty
        (or all-invalid) list is the "wait" action: no input, just the settle
        wait, which lets cutscenes, animations, and text play out.
        """
        pressed: list[str] = []
        for button in buttons:
            button = button.lower().strip()
            if button not in VALID_BUTTONS:
                continue
            # The bridge replies "ok" after holding for BUTTON_HOLD_FRAMES.
            if self._command(f"press {button} {config.BUTTON_HOLD_FRAMES}") == "ok":
                pressed.append(button)
            time.sleep((config.FRAMES_PER_ACTION - config.BUTTON_HOLD_FRAMES) / 60)
        return pressed, self._settle()

    def _grab(self) -> Image.Image:
        """Fetch the current native frame from mGBA."""
        if self._command(f"shot {self._shot_path}") != "ok":
            raise RuntimeError("mGBA bridge failed to take a screenshot")
        with Image.open(self._shot_path) as img:
            return img.convert("RGB")

    def _settle(self) -> int:
        """Wait until the screen stops changing, so the screenshot is a stable
        frame a human would act on — not mid-scroll text or a half-drawn map.

        "Stable" tolerates a small pixel diff because idle animations never
        fully stop; near-uniform (blank) frames never count, so mid-fade
        black/white screens are waited out; MAX_SETTLE_FRAMES caps the wait so
        looping animations can't stall a turn. The game runs in real time, so
        waiting means sleeping wall-clock time between samples.
        """
        prev = self._grab().convert("L")
        pixels = prev.width * prev.height
        waited = 0
        stable = 0
        while waited < config.MAX_SETTLE_FRAMES:
            time.sleep(config.STABLE_CHECK_INTERVAL / 60)
            waited += config.STABLE_CHECK_INTERVAL
            cur = self._grab().convert("L")
            changed = sum(ImageChops.difference(prev, cur).histogram()[1:])
            blank = max(cur.histogram()) >= config.BLANK_SCREEN_FRACTION * pixels
            prev = cur
            if not blank and changed <= config.STABLE_DIFF_THRESHOLD * pixels:
                stable += 1
                if stable >= config.STABLE_CHECKS:
                    break
            else:
                stable = 0
        return waited

    def screenshot(self) -> Image.Image:
        """Capture the screen, upscaled with nearest-neighbor (crisp pixels)."""
        img = self._grab()
        return img.resize(
            (img.width * config.UPSCALE, img.height * config.UPSCALE),
            Image.NEAREST,
        )

    def tick(self, n: int) -> None:
        """Let the game run for n frames (it runs in real time on its own)."""
        time.sleep(n / 60)

    def stop(self) -> None:
        """Detach from mGBA; quit it only if we launched it."""
        try:
            self.sock.close()
        except OSError:
            pass
        if self.process is not None:
            self.process.terminate()
