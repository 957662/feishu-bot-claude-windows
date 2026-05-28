"""zellij process wrapper: real + fake implementations.

Windows-native replacement for the macOS tmux backend. The interface is the
same `SessionMux` shape the orchestrator/inbound consume — only the binary
and the command shapes differ.

zellij CLI cheatsheet (verified against 0.40):
  list-sessions                         → one session per line on stdout
  --session NAME                        → create or attach (CLI use)
  --session NAME action write-chars S   → send literal text to the focused pane
  --session NAME action write 13        → send ASCII key code (13 = Enter)
  delete-session NAME --force           → kill a session
"""

from __future__ import annotations

import os
import subprocess
import sys
from abc import ABC, abstractmethod


class SessionMux(ABC):
    """Interface for terminal session multiplexer (tmux on Unix, zellij on Windows)."""

    @abstractmethod
    def has_session(self, name: str) -> bool: ...

    @abstractmethod
    def new_session(self, name: str, cwd: str, command: str, attach_if_exists: bool = False) -> None: ...

    @abstractmethod
    def send_keys(self, session: str, keys: str) -> None: ...

    @abstractmethod
    def send_special(self, session: str, key: str) -> None: ...

    @abstractmethod
    def kill_session(self, name: str) -> None: ...


# Backward-compat alias so handlers/orchestrator imports of `Tmux` keep working.
Tmux = SessionMux


class FakeZellij(SessionMux):
    """In-memory fake — records all calls, lets tests configure session existence."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self._sessions: set[str] = set()

    def set_session(self, name: str, exists: bool) -> None:
        if exists:
            self._sessions.add(name)
        else:
            self._sessions.discard(name)

    def has_session(self, name: str) -> bool:
        self.calls.append(("has_session", {"name": name}))
        return name in self._sessions

    def new_session(self, name: str, cwd: str, command: str, attach_if_exists: bool = False) -> None:
        if name in self._sessions:
            if attach_if_exists:
                self.calls.append(("attach_session", {"name": name}))
                return
            raise ValueError(f"session {name!r} already exists")
        self.calls.append(("new_session", {"name": name, "cwd": cwd, "command": command}))
        self._sessions.add(name)

    def send_keys(self, session: str, keys: str) -> None:
        if session not in self._sessions:
            raise RuntimeError(f"no session: {session!r}")
        self.calls.append(("send_keys", {"session": session, "keys": keys}))

    def send_special(self, session: str, key: str) -> None:
        if session not in self._sessions:
            raise RuntimeError(f"no session: {session!r}")
        self.calls.append(("send_special", {"session": session, "key": key}))

    def kill_session(self, name: str) -> None:
        self.calls.append(("kill_session", {"name": name}))
        self._sessions.discard(name)


# Test alias so the Mac project's `FakeTmux` import sites translate cleanly.
FakeTmux = FakeZellij


class RealZellij(SessionMux):
    """Real zellij backend — shells out to `zellij.exe`."""

    def __init__(self, binary: str = "zellij") -> None:
        self._binary = binary

    def has_session(self, name: str) -> bool:
        result = subprocess.run(
            [self._binary, "list-sessions", "--short"],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            # zellij returns 1 when no sessions exist at all. Treat as "no session".
            return False
        for line in result.stdout.splitlines():
            if line.strip() == name:
                return True
        return False

    def new_session(self, name: str, cwd: str, command: str, attach_if_exists: bool = False) -> None:
        """Spawn a detached zellij session in a new console window.

        On Windows we open a new console so the user can see the TUI; on
        Unix-like dev hosts (where this code may run for testing) we just spawn
        in the background.
        """
        if self.has_session(name):
            if attach_if_exists:
                return
            raise ValueError(f"session {name!r} already exists")

        if sys.platform == "win32":
            # CREATE_NEW_CONSOLE = 0x00000010 — gives Claude TUI its own window.
            CREATE_NEW_CONSOLE = 0x00000010
            subprocess.Popen(
                [self._binary, "--session", name, "--", "cmd", "/c", command],
                cwd=cwd,
                creationflags=CREATE_NEW_CONSOLE,
                close_fds=True,
            )
        else:
            # Background spawn — used for tests / dev only.
            subprocess.Popen(
                [self._binary, "--session", name, "--", "sh", "-c", command],
                cwd=cwd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )

    def send_keys(self, session: str, keys: str) -> None:
        """Send `keys` (literal) to the focused pane of `session`.

        Trailing newline → press Enter via `action write 13` (ASCII).
        Internal newlines are NOT translated; they go through as part of the
        chars buffer. Use the explicit Enter sequence when you need a newline
        to actually submit input.
        """
        stripped = keys
        needs_enter = stripped.endswith("\n")
        if needs_enter:
            stripped = stripped.rstrip("\n")

        if stripped:
            result = subprocess.run(
                [self._binary, "--session", session, "action", "write-chars", stripped],
                capture_output=True, text=True,
            )
            if result.returncode != 0:
                msg = (result.stderr + result.stdout).strip()
                if self._looks_like_no_session(msg):
                    raise RuntimeError(f"no session: {session!r}")
                raise RuntimeError(f"zellij write-chars failed: {msg}")

        if needs_enter:
            result = subprocess.run(
                [self._binary, "--session", session, "action", "write", "13"],
                capture_output=True, text=True,
            )
            if result.returncode != 0:
                msg = (result.stderr + result.stdout).strip()
                if self._looks_like_no_session(msg):
                    raise RuntimeError(f"no session: {session!r}")
                raise RuntimeError(f"zellij write Enter failed: {msg}")

    # Map symbolic key names → list of ASCII byte codes that produce the same
    # behavior in a typical terminal. zellij's `action write` takes raw byte
    # codes, so terminal escape sequences (Up = ESC[A, etc.) must be encoded
    # as 3 numbers.
    _SPECIAL_KEY_BYTES = {
        "Escape": [27],
        "Enter":  [13],
        "Tab":    [9],
        "BSpace": [127],
        "Up":     [27, 91, 65],
        "Down":   [27, 91, 66],
        "Right":  [27, 91, 67],
        "Left":   [27, 91, 68],
        "M-Enter": [27, 13],     # Alt+Enter → soft newline in Claude/Codex input
        "C-c":    [3],
        "C-d":    [4],
        "C-l":    [12],
        "C-u":    [21],
    }

    def send_special(self, session: str, key: str) -> None:
        codes = self._SPECIAL_KEY_BYTES.get(key)
        if codes is None:
            raise ValueError(f"unknown special key: {key!r}")
        result = subprocess.run(
            [self._binary, "--session", session, "action", "write", *map(str, codes)],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            msg = (result.stderr + result.stdout).strip()
            if self._looks_like_no_session(msg):
                raise RuntimeError(f"no session: {session!r}")
            raise RuntimeError(f"zellij action write {key!r} failed: {msg}")

    def kill_session(self, name: str) -> None:
        result = subprocess.run(
            [self._binary, "delete-session", name, "--force"],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            msg = (result.stderr + result.stdout).strip()
            if not self._looks_like_no_session(msg):
                raise RuntimeError(f"zellij delete-session failed: {msg}")

    @staticmethod
    def _looks_like_no_session(msg: str) -> bool:
        lower = msg.lower()
        return any(
            needle in lower
            for needle in (
                "no active sessions",
                "no such session",
                "session does not exist",
                "session not found",
            )
        )
