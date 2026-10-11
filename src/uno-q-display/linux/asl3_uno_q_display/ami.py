# SPDX-License-Identifier: GPL-2.0-or-later

"""Small AMI client and Asterisk manager.conf credential reader."""

from __future__ import annotations

from dataclasses import dataclass
import glob
from pathlib import Path
import re
import socket
from typing import BinaryIO


class AMIError(RuntimeError):
    """An Asterisk Manager Interface operation failed."""


@dataclass(frozen=True)
class AMIConfig:
    username: str
    secret: str
    host: str = "127.0.0.1"
    port: int = 5038


_INCLUDE_RE = re.compile(r'^#(?:try)?include\s+["<]?([^">]+)[">]?\s*$')


def _read_asterisk_config(path: Path, seen: set[Path]) -> list[tuple[str, dict[str, str]]]:
    path = path.resolve()
    if path in seen or not path.is_file():
        return []
    seen.add(path)

    sections: list[tuple[str, dict[str, str]]] = []
    current: dict[str, str] | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith(";"):
            continue

        include = _INCLUDE_RE.match(line)
        if include:
            pattern = include.group(1)
            if not pattern.startswith("/"):
                pattern = str(path.parent / pattern)
            for included in sorted(glob.glob(pattern)):
                sections.extend(_read_asterisk_config(Path(included), seen))
            continue

        if line.startswith("[") and "]" in line:
            name = line[1 : line.index("]")].strip()
            current = {}
            sections.append((name, current))
            continue

        if current is not None and "=" in line:
            key, value = line.split("=", 1)
            current[key.strip().lower()] = value.split(";", 1)[0].strip()

    return sections


def load_ami_config(path: str = "/etc/asterisk/manager.conf") -> AMIConfig:
    """Select usable AMI credentials without copying the secret elsewhere."""
    sections = _read_asterisk_config(Path(path), set())
    general = next((values for name, values in sections if name.lower() == "general"), {})
    accounts = [(name, values) for name, values in sections if name.lower() != "general"]

    def usable(account: tuple[str, dict[str, str]]) -> bool:
        _name, values = account
        permissions = {item.strip().lower() for item in values.get("read", "").split(",")}
        return bool(values.get("secret")) and bool({"all", "call"} & permissions)

    candidates = [account for account in accounts if usable(account)]
    if not candidates:
        raise AMIError(f"no AMI account with call event access found in {path}")

    preferred_names = ("asl3-uno-q-display", "admin")
    selected = next(
        (account for preferred in preferred_names for account in candidates if account[0].lower() == preferred),
        candidates[0],
    )
    username, values = selected

    try:
        port = int(general.get("port", "5038"))
    except ValueError as error:
        raise AMIError("invalid AMI port in manager.conf") from error

    return AMIConfig(username=username, secret=values["secret"], port=port)


class AMIClient:
    """Synchronous client for AMI actions and events."""

    def __init__(self, config: AMIConfig, timeout: float = 5.0):
        self.config = config
        self.timeout = timeout
        self._socket: socket.socket | None = None
        self._stream: BinaryIO | None = None
        self.greeting = ""
        self._next_action_id = 0

    def connect(self, events: bool = True) -> None:
        self._socket = socket.create_connection((self.config.host, self.config.port), self.timeout)
        self._socket.settimeout(self.timeout)
        self._stream = self._socket.makefile("rb")
        self.greeting = self._readline()
        self.send_action(
            {
                "Action": "Login",
                "Username": self.config.username,
                "Secret": self.config.secret,
                "Events": "on" if events else "off",
            }
        )
        response = self.read_message()
        if response.get("Response", "").lower() != "success":
            self.close()
            raise AMIError(response.get("Message", "AMI login failed"))

    def close(self) -> None:
        if self._socket is not None:
            try:
                self._socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        if self._stream is not None:
            try:
                self._stream.close()
            except OSError:
                pass
            self._stream = None
        if self._socket is not None:
            self._socket.close()
            self._socket = None

    def set_timeout(self, timeout: float | None) -> None:
        """Set the socket timeout; ``None`` enables blocking event reads."""
        if self._socket is None:
            raise AMIError("AMI is not connected")
        self._socket.settimeout(timeout)

    def __enter__(self) -> "AMIClient":
        self.connect()
        return self

    def __exit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
        self.close()

    def _readline(self) -> str:
        if self._stream is None:
            raise AMIError("AMI is not connected")
        line = self._stream.readline()
        if not line:
            raise AMIError("AMI closed the connection")
        return line.decode("utf-8", errors="replace").rstrip("\r\n")

    def read_message(self) -> dict[str, str]:
        message: dict[str, str] = {}
        while True:
            line = self._readline()
            if not line:
                return message
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            message[key.strip()] = value.strip()

    def send_action(self, headers: dict[str, str]) -> None:
        if self._socket is None:
            raise AMIError("AMI is not connected")
        payload = "".join(f"{key}: {value}\r\n" for key, value in headers.items()) + "\r\n"
        self._socket.sendall(payload.encode("utf-8"))

    def action(self, action: str, **headers: str) -> dict[str, str]:
        """Send an AMI action and wait for its matching response."""
        self._next_action_id += 1
        action_id = f"asl3-uno-q-{self._next_action_id}"
        request = {"Action": action, "ActionID": action_id, **headers}
        self.send_action(request)
        while True:
            response = self.read_message()
            if response.get("ActionID") == action_id:
                return response
