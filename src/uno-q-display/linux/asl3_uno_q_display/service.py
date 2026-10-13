# SPDX-License-Identifier: GPL-2.0-or-later

"""Long-running ASL3 display controller."""

from dataclasses import dataclass, field
import logging
import re
import signal
import socket
import threading
import time

from .ami import AMIClient, AMIError, load_ami_config
from .bridge import BridgeClient, BridgeError
from .frames import idle_sequence, receive, transmit, unavailable_sequence

LOG = logging.getLogger("asl3-uno-q-display")


@dataclass
class NodeState:
    primary: str
    links: list[str]
    rx: bool = False
    tx: bool = False
    etx: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock)

    def snapshot(self) -> tuple[str, tuple[str, ...], bool, bool]:
        with self.lock:
            return self.primary, tuple(self.links), self.rx, self.tx or self.etx

    def update(self, event: dict[str, str]) -> None:
        if event.get("Node") != self.primary:
            return
        name, value = event.get("Event", ""), event.get("EventValue", "")
        with self.lock:
            if name == "RPT_RXKEYED":
                self.rx = value == "1"
            elif name == "RPT_TXKEYED":
                self.tx = value == "1"
            elif name == "RPT_ETXKEYED":
                self.etx = value == "1"
            elif name == "RPT_LINKS":
                self.links = [digits for item in value.split(",")[1:] if (digits := "".join(re.findall(r"\d", item)))]


def initialize(client: AMIClient) -> NodeState:
    response = client.action("RptStatus", Command="RptStat")
    nodes = [item.strip() for item in response.get("Nodes", "").split(",") if item.strip()]
    if not nodes:
        raise AMIError("RptStat returned no local nodes")
    response = client.action("RptStatus", Command="XStat", Node=nodes[0])
    if response.get("Response", "").lower() != "success":
        raise AMIError(response.get("Message", "XStat failed"))
    return NodeState(nodes[0], re.findall(r"\d+", response.get("LinkedNodes", "")))


def show_unavailable(stop: threading.Event, started: float, duration: float = 3.0) -> None:
    """Animate the unavailable state until it is time to retry AMI."""
    deadline = time.monotonic() + duration
    last_frame = None
    try:
        with BridgeClient() as bridge:
            while not stop.is_set() and time.monotonic() < deadline:
                frame = unavailable_sequence(time.monotonic() - started)
                if frame != last_frame:
                    bridge.call("draw", frame)
                    last_frame = frame
                stop.wait(0.05)
    except (BridgeError, ConnectionError, OSError):
        stop.wait(min(duration, max(0.0, deadline - time.monotonic())))


def run_session(stop: threading.Event, on_connected=None) -> None:
    ami = AMIClient(load_ami_config(), timeout=5)
    ami.connect(events=True)
    state = initialize(ami)
    if on_connected is not None:
        on_connected()
    ami.set_timeout(None)
    disconnected = threading.Event()

    def read_events() -> None:
        try:
            while not stop.is_set():
                state.update(ami.read_message())
        except (AMIError, OSError):
            if not stop.is_set():
                disconnected.set()

    reader = threading.Thread(target=read_events, name="ami-events", daemon=True)
    reader.start()
    LOG.info("displaying primary node %s", state.primary)
    idle_started = time.monotonic()
    previous_active = False
    previous_content = state.snapshot()[:2]
    last_frame = None
    try:
        with BridgeClient() as bridge:
            while not stop.is_set() and not disconnected.is_set():
                primary, links, rx, tx = state.snapshot()
                active = rx or tx
                content = primary, links
                now = time.monotonic()
                if (previous_active and not active) or content != previous_content:
                    idle_started = now
                previous_active = active
                previous_content = content
                if rx:
                    frame = receive()
                elif tx:
                    frame = transmit()
                else:
                    frame = idle_sequence(primary, links, now - idle_started)
                if frame != last_frame:
                    bridge.call("draw", frame)
                    last_frame = frame
                stop.wait(0.05)
    finally:
        ami.close()
        reader.join(timeout=2)
    if disconnected.is_set():
        raise AMIError("AMI connection lost")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda _signum, _frame: stop.set())
    signal.signal(signal.SIGINT, lambda _signum, _frame: stop.set())
    unavailable_since = time.monotonic()
    ami_unavailable = False

    def connected() -> None:
        nonlocal ami_unavailable
        if ami_unavailable:
            LOG.info("AMI connectivity restored")
            ami_unavailable = False

    while not stop.is_set():
        try:
            run_session(stop, connected)
        except (AMIError, BridgeError, ConnectionError, OSError, ValueError) as error:
            if not ami_unavailable:
                LOG.warning("AMI unavailable: %s; retrying silently", error)
                ami_unavailable = True
                unavailable_since = time.monotonic()
            show_unavailable(stop, unavailable_since)


if __name__ == "__main__":
    main()
