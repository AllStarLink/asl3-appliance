# SPDX-License-Identifier: GPL-2.0-or-later

"""Minimal synchronous client for the Arduino Router MessagePack RPC API."""

from __future__ import annotations

import socket
from typing import Any

import msgpack


class BridgeError(RuntimeError):
    """An Arduino Bridge request failed."""


class BridgeClient:
    """Make synchronous RPC calls through the UNO Q Arduino Router."""

    def __init__(self, path: str = "/run/arduino-router.sock", timeout: float = 5.0):
        self.path = path
        self.timeout = timeout
        self._next_message_id = 0
        self._connection: socket.socket | None = None
        self._unpacker = msgpack.Unpacker(raw=False)

    def connect(self) -> None:
        if self._connection is not None:
            return
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        connection.settimeout(self.timeout)
        connection.connect(self.path)
        self._connection = connection

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def __enter__(self) -> "BridgeClient":
        self.connect()
        return self

    def __exit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
        self.close()

    def call(self, method: str, *params: Any) -> Any:
        self._next_message_id = (self._next_message_id + 1) % (2**32)
        message_id = self._next_message_id
        request = [0, message_id, method, params]

        self.connect()
        assert self._connection is not None
        self._connection.sendall(msgpack.packb(request, use_bin_type=True))

        while True:
            data = self._connection.recv(4096)
            if not data:
                self.close()
                raise BridgeError("Arduino Router closed the connection")
            self._unpacker.feed(data)
            for response in self._unpacker:
                if not isinstance(response, list) or len(response) != 4:
                    continue
                message_type, response_id, error, result = response
                if message_type != 1 or response_id != message_id:
                    continue
                if error is not None:
                    raise BridgeError(f"Bridge method {method!r} failed: {error}")
                return result
