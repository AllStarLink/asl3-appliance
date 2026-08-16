#!/usr/bin/env python3
"""
fallback-ap-watchdog.py — bring up a NetworkManager AP profile if the
host has no usable connectivity, so Cockpit stays reachable for
bootstrapping. Bootstrap-only: no static gateway is configured by this
script itself; IPv4 addressing and DHCP for the fallback subnet are
provided by NetworkManager's own "shared" method, which is fully tied
to this connection's activation lifecycle (starts on activation, torn
down automatically on deactivation).

IPv4-only, deliberately: the subnet is pinned to the RFC 2544
benchmarking block (198.18.0.0/15) rather than RFC 1918 space, so it
can never collide with a real network the client is also attached to.
Most operators here aren't networking-savvy, so avoiding RFC 1918 is
the priority; anyone actually running RFC 2544 benchmark gear or
Fake-IP VPN/proxy tooling (e.g. Clash, sing-box) that claims this block
is, definitionally, someone who knows how to override AP_IPV4_CIDR.

Two other ranges were tried and rejected first: APIPA (169.254.0.0/16)
— iOS refuses to fully join a network whose DHCP-assigned address
falls in that block at all, treating a lease there the same as "no
DHCP server responded" regardless of who issued it — and RFC 6598
Carrier-Grade NAT space (100.64.0.0/10), which is exactly the kind of
range a networking-literate operator (or their upstream ISP) may
already have in active use, the same problem this is meant to avoid.
198.18.0.0/15 has no client-OS self-assignment special-casing like
APIPA does — it's just an ordinary, if obscure, reserved block.

IPv6 is disabled outright rather than paired with a ULA — a ULA prefix
is not a global unicast address, and Windows' NCSI explicitly downgrades
an interface without one to "local" connectivity without ever running
the active probe that would otherwise trigger captive-portal detection,
so a ULA-only AP interface would carry that liability for no benefit.

Configuration is read from environment variables, normally supplied by
systemd via EnvironmentFile=/etc/default/asl3-fallback-ap.
"""

import ipaddress
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("fallback-ap")

STATE_FILE = Path("/run/fallback-ap-watchdog/suppressed-connections.json")

# NM reads this directory's *.conf snippets into the dnsmasq instance it
# spawns for any "shared"-method connection (see nm-settings(5), ipv4.method
# = shared). Used here to blackhole DNS on the AP subnet so every hostname a
# client looks up resolves to the gateway — which is what actually trips a
# client OS's captive-portal detection.
DNSMASQ_SHARED_DIR = Path("/etc/NetworkManager/dnsmasq-shared.d")
DNSMASQ_SHARED_CONF = DNSMASQ_SHARED_DIR / "asl-fallback-ap.conf"

# The full RFC 2544 benchmarking block. Used to scope Apache's reverse
# proxy to fallback-AP clients regardless of which address inside it
# AP_IPV4_CIDR picks — see src/apache2/000-default.conf.
BENCHMARK_NETWORK = ipaddress.IPv4Network("198.18.0.0/15")


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

def load_config() -> dict:
    cfg = {
        "ssid_prefix": os.environ.get("AP_SSID_PREFIX", "AllStarLink_"),
        "psk": os.environ.get("AP_PSK", ""),
        "ipv4_cidr": os.environ.get("AP_IPV4_CIDR", "198.18.252.1/24"),
        "band": os.environ.get("AP_BAND", "bg"),
        "channel": os.environ.get("AP_CHANNEL", "11 "),
        "conn_name": os.environ.get("AP_CONN_NAME", "asl-fallback-ap"),
    }
    validate_benchmark_cidr(cfg["ipv4_cidr"])
    return cfg


def validate_benchmark_cidr(cidr: str) -> None:
    """Confirm AP_IPV4_CIDR is a well-formed address within RFC 2544
    benchmarking space (198.18.0.0/15).

    Apache's reverse proxy to Cockpit (see src/apache2/000-default.conf) is
    scoped to the whole 198.18.0.0/15 block rather than templated to this
    specific address, so straying outside it silently breaks that proxy.
    """
    if not cidr or "/" not in cidr:
        log.error("AP_IPV4_CIDR must be in address/prefix form, e.g. 198.18.252.1/24")
        sys.exit(1)
    try:
        addr = ipaddress.IPv4Interface(cidr)
    except ValueError as e:
        log.error("AP_IPV4_CIDR '%s' is not valid: %s", cidr, e)
        sys.exit(1)

    if addr.ip not in BENCHMARK_NETWORK:
        log.error(
            "AP_IPV4_CIDR '%s' is not within RFC 2544 benchmarking space "
            "(198.18.0.0/15). This range is used deliberately so the "
            "fallback AP's subnet can never collide with a real network — "
            "see the module docstring.",
            cidr,
        )
        sys.exit(1)


# --------------------------------------------------------------------------
# Interface discovery
# --------------------------------------------------------------------------

def get_wireless_interfaces() -> list[str]:
    """Return names of interfaces with a wireless/ subdir in sysfs."""
    net_root = Path("/sys/class/net")
    if not net_root.exists():
        return []
    return sorted(
        iface.name for iface in net_root.iterdir()
        if (iface / "wireless").exists()
    )


# --------------------------------------------------------------------------
# nmcli helpers
# --------------------------------------------------------------------------

def nmcli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["nmcli", *args],
        capture_output=True, text=True, check=False
    )


def get_connectivity_state() -> str:
    result = nmcli("-t", "-f", "CONNECTIVITY", "general", "status")
    return result.stdout.strip().lower()


def connection_names() -> list[str]:
    result = nmcli("-t", "-f", "NAME", "connection", "show")
    return result.stdout.splitlines()


def active_connection_names() -> list[str]:
    result = nmcli("-t", "-f", "NAME", "connection", "show", "--active")
    return result.stdout.splitlines()


def ap_profile_exists(conn_name: str) -> bool:
    return conn_name in connection_names()


def ap_is_active(conn_name: str) -> bool:
    return conn_name in active_connection_names()


def get_ifname_for_connection(conn_name: str) -> str | None:
    result = nmcli("-t", "-f", "connection.interface-name", "connection", "show", conn_name)
    line = result.stdout.strip()
    if ":" in line:
        val = line.split(":", 1)[1].strip()
        return val or None
    return None

def get_interface_mac(ifname: str) -> str:
    """Read the interface's MAC address from sysfs and format it for SSID use
    (colons stripped, uppercase) — e.g. AA:BB:CC:DD:EE:FF -> AABBCCDDEEFF."""
    mac_path = Path(f"/sys/class/net/{ifname}/address")
    try:
        mac = mac_path.read_text().strip()
    except OSError as e:
        log.error("Could not read MAC address for %s: %s", ifname, e)
        sys.exit(1)
    return mac.replace(":", "").upper()

# --------------------------------------------------------------------------
# AP profile management
# --------------------------------------------------------------------------

def ensure_ap_profile(ifname: str, cfg: dict) -> None:
    """Create the fallback AP profile bound to the given interface if missing."""
    mac = get_interface_mac(ifname)
    ssid = f"{cfg['ssid_prefix']}{mac}"

    if len(ssid) > 32:
        log.warning(
            "Generated SSID '%s' exceeds 32 bytes and will be truncated by "
            "the driver — shorten AP_SSID_PREFIX", ssid
        )

    cfg["ssid"] = ssid
    log.info("Creating missing AP profile '%s' on %s", cfg["conn_name"], ifname)

    args = [
        "connection", "add", "type", "wifi", "ifname", ifname,
        "con-name", cfg["conn_name"], "autoconnect", "no",
        "ssid", cfg["ssid"],
        "802-11-wireless.mode", "ap",
        "802-11-wireless.band", cfg["band"],
        "802-11-wireless.channel", cfg["channel"],
        # shared = NM-managed scoped dnsmasq instance for DHCP, fully tied
        # to this connection's lifecycle. No process for us to manage.
        "ipv4.method", "shared",
        "ipv4.addresses", cfg["ipv4_cidr"],
        "ipv6.method", "disabled",
        "connection.autoconnect-priority", "-999",
        # Without an explicit zone, NM binds "shared" connections to its own
        # built-in nm-shared firewalld zone (dhcp/dns/ssh only) instead of
        # this system's default zone, silently blocking Cockpit/http/https
        # and the other allstarlink.xml services on the AP interface.
        "connection.zone", "allstarlink",
    ]

    if cfg["psk"]:
        args += ["wifi-sec.key-mgmt", "wpa-psk", "wifi-sec.psk", cfg["psk"]]
    else:
        log.warning("AP_PSK is empty — creating an OPEN (unencrypted) hotspot")
        args += ["wifi-sec.key-mgmt", "none"]

    result = nmcli(*args)
    if result.returncode != 0:
        log.error("Failed to create AP profile: %s", result.stderr.strip())
        sys.exit(1)


def write_dns_blackhole(cfg: dict) -> None:
    """Make the AP's dnsmasq answer every hostname with the gateway's own
    address, so a client's captive-portal probe (which expects a specific
    real-internet response) instead gets redirected to the appliance —
    that mismatch is what triggers the OS's captive-portal browser popup.

    Applies to every NM "shared" connection on this host, not just this
    one, since dnsmasq-shared.d is a single global directory — harmless
    here since the fallback AP is the only shared connection in use.
    """
    gateway = ipaddress.IPv4Interface(cfg["ipv4_cidr"]).ip
    DNSMASQ_SHARED_DIR.mkdir(parents=True, exist_ok=True)
    DNSMASQ_SHARED_CONF.write_text(f"address=/#/{gateway}\n")


# --------------------------------------------------------------------------
# Conflict handling — evict/restore other profiles bound to the same radio
# --------------------------------------------------------------------------

def find_conflicting_connections(ifname: str, ap_conn_name: str) -> list[str]:
    """Other autoconnect-enabled profiles bound to the same wireless interface."""
    conflicts = []
    for name in connection_names():
        if name == ap_conn_name:
            continue
        if get_ifname_for_connection(name) != ifname:
            continue
        autoconn = nmcli("-t", "-f", "connection.autoconnect", "connection", "show", name)
        val = autoconn.stdout.strip().split(":", 1)[-1].strip().lower()
        if val in ("yes", "true", "1"):
            conflicts.append(name)
    return conflicts


def suppress_conflicts(ifname: str, ap_conn_name: str) -> None:
    conflicts = find_conflicting_connections(ifname, ap_conn_name)
    if not conflicts:
        return
    log.info("Suppressing autoconnect on conflicting profiles: %s", ", ".join(conflicts))
    for name in conflicts:
        nmcli("connection", "modify", name, "connection.autoconnect", "no")

    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(conflicts))


def restore_conflicts() -> None:
    if not STATE_FILE.exists():
        return
    try:
        conflicts = json.loads(STATE_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        conflicts = []

    for name in conflicts:
        log.info("Restoring autoconnect on %s", name)
        nmcli("connection", "modify", name, "connection.autoconnect", "yes")

    STATE_FILE.unlink(missing_ok=True)


# --------------------------------------------------------------------------
# Activate / deactivate
# --------------------------------------------------------------------------

def activate_ap(ifname: str, cfg: dict) -> bool:
    suppress_conflicts(ifname, cfg["conn_name"])

    # Force the radio free of whatever's currently using it — an explicit
    # `connection up` below is authoritative regardless of autoconnect
    # priority, but disconnecting first avoids relying on NM to evict
    # cleanly on its own.
    nmcli("device", "disconnect", ifname)

    result = nmcli("connection", "up", cfg["conn_name"])
    if result.returncode != 0:
        log.error("Failed to bring up AP: %s", result.stderr.strip())
        return False

    log.info("AP '%s' active on %s", cfg["ssid"], ifname)
    return True


def deactivate_ap(cfg: dict) -> None:
    log.info("Connectivity restored — tearing down %s", cfg["conn_name"])
    nmcli("connection", "down", cfg["conn_name"])
    restore_conflicts()


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main() -> int:
    cfg = load_config()

    wireless_ifaces = get_wireless_interfaces()
    if not wireless_ifaces:
        log.warning("No wireless interfaces found; nothing to do")
        return 0

    ifname = wireless_ifaces[0]
    if len(wireless_ifaces) > 1:
        log.info("Multiple wireless interfaces found (%s); using %s",
                  ", ".join(wireless_ifaces), ifname)

    write_dns_blackhole(cfg)

    if not ap_profile_exists(cfg["conn_name"]):
        ensure_ap_profile(ifname, cfg)
    else:
        # Self-heal profiles created before connection.zone was pinned
        # (see ensure_ap_profile) so they don't silently fall back to NM's
        # nm-shared firewalld zone.
        nmcli("connection", "modify", cfg["conn_name"], "connection.zone", "allstarlink")

    state = get_connectivity_state()
    log.info("Connectivity state: %s", state)
    degraded = state in ("none", "limited")

    currently_active = ap_is_active(cfg["conn_name"])

    if degraded and not currently_active:
        if not activate_ap(ifname, cfg):
            return 1
    elif not degraded and currently_active:
        deactivate_ap(cfg)

    return 0


if __name__ == "__main__":
    sys.exit(main())