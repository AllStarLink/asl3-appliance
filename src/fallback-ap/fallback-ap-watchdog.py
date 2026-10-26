#!/usr/bin/env python3
"""
fallback-ap-watchdog.py — bring up a NetworkManager AP profile if the
host has no usable connectivity, so Cockpit stays reachable for
bootstrapping. Bootstrap-only: no static gateway is configured by this
script itself; IPv4 addressing and DHCP for the fallback subnet are
provided by NetworkManager's own "shared" method, which is fully tied
to this connection's activation lifecycle (starts on activation, torn
down automatically on deactivation).

IPv4-only, deliberately: the subnet is a fixed, narrow RFC 1918 window
(192.168.187.64/29 — 6 usable addresses, plenty for one bootstrapping
client at a time) rather than a global reserved block. Three reserved
ranges were tried before this and each failed in real-world testing:
APIPA (169.254.0.0/16) — iOS refuses to fully join a network whose
DHCP-assigned address falls in that block at all, treating a lease
there the same as "no DHCP server responded" regardless of who issued
it; RFC 6598 Carrier-Grade NAT space (100.64.0.0/10) — exactly the
kind of range a networking-literate operator's own environment may
already use; and the RFC 2544 benchmarking block (198.18.0.0/15),
which also didn't work in practice on real hardware/clients (root
cause not conclusively isolated — possibly the same class of issue,
possibly unrelated AP-mode reliability problems). Given that track
record, a small, obscure corner of RFC 1918 space that a home/office
router would be very unlikely to already be using is the pragmatic
choice — the residual collision risk this was meant to avoid entirely
is accepted as unavoidable rather than chased further.

IPv6 is disabled outright rather than paired with a ULA — a ULA prefix
is not a global unicast address, and Windows' NCSI explicitly downgrades
an interface without one to "local" connectivity without ever running
the active probe that would otherwise trigger captive-portal detection,
so a ULA-only AP interface would carry that liability for no benefit.

Configuration is read from environment variables, normally supplied by
systemd via EnvironmentFile=/etc/default/asl3-fallback-ap.

Run with --scan (fallback-ap-scan.timer) to check whether a saved Wi-Fi
network has come back while the AP is up. The radio can't join another
network while it's in AP mode, so without this the node would stay on the
AP until some other interface brought connectivity back.
"""

import fcntl
import ipaddress
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("fallback-ap")

# NM reads this directory's *.conf snippets into the dnsmasq instance it
# spawns for any "shared"-method connection (see nm-settings(5), ipv4.method
# = shared). Used here to blackhole DNS on the AP subnet so every hostname a
# client looks up resolves to the gateway — which is what actually trips a
# client OS's captive-portal detection.
DNSMASQ_SHARED_DIR = Path("/etc/NetworkManager/dnsmasq-shared.d")
DNSMASQ_SHARED_CONF = DNSMASQ_SHARED_DIR / "asl-fallback-ap.conf"

# The fixed, narrow window the fallback AP's subnet lives in. Used to scope
# Apache's reverse proxy to fallback-AP clients regardless of which address
# inside it AP_IPV4_CIDR picks — see src/apache2/000-default.conf.
AP_NETWORK = ipaddress.IPv4Network("192.168.187.64/29")

# Held for the whole run so the watchdog can't bring the AP back up while a
# --scan run has it down on purpose.
LOCK_FILE = Path("/run/fallback-ap-watchdog.lock")

DEGRADED_STATES = ("none", "limited")

# How long a --scan run waits for a saved network to show up in the scan
# before putting the AP back early, instead of waiting out AP_SCAN_TIMEOUT.
SCAN_SETTLE_SECONDS = 15

# NMDeviceState values between "prepare" and "activated": NM is joining.
DEVICE_ACTIVATING = range(40, 100)
DEVICE_ACTIVATED = 100


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

def load_config() -> dict:
    cfg = {
        "ssid_prefix": os.environ.get("AP_SSID_PREFIX", "AllStarLink_"),
        "psk": os.environ.get("AP_PSK", ""),
        "ipv4_cidr": os.environ.get("AP_IPV4_CIDR", "192.168.187.65/29"),
        "band": os.environ.get("AP_BAND", "bg"),
        "channel": os.environ.get("AP_CHANNEL", "11 "),
        "conn_name": os.environ.get("AP_CONN_NAME", "asl-fallback-ap"),
    }
    validate_ap_cidr(cfg["ipv4_cidr"])
    try:
        cfg["scan_timeout"] = int(os.environ.get("AP_SCAN_TIMEOUT", "60"))
    except ValueError:
        log.error("AP_SCAN_TIMEOUT must be a whole number of seconds")
        sys.exit(1)
    return cfg


def validate_ap_cidr(cidr: str) -> None:
    """Confirm AP_IPV4_CIDR is a well-formed address within the fallback
    AP's fixed window (192.168.187.64/29).

    Apache's reverse proxy to Cockpit (see src/apache2/000-default.conf) is
    scoped to that whole /29 rather than templated to this specific
    address, so straying outside it silently breaks that proxy.
    """
    if not cidr or "/" not in cidr:
        log.error("AP_IPV4_CIDR must be in address/prefix form, e.g. 192.168.187.65/29")
        sys.exit(1)
    try:
        addr = ipaddress.IPv4Interface(cidr)
    except ValueError as e:
        log.error("AP_IPV4_CIDR '%s' is not valid: %s", cidr, e)
        sys.exit(1)

    if addr.ip not in AP_NETWORK:
        log.error(
            "AP_IPV4_CIDR '%s' is not within the fallback AP's fixed window "
            "(192.168.187.64/29). This range is used deliberately so the "
            "fallback AP's subnet stays out of common RFC 1918 territory — "
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


def nmcli_unescape(value: str) -> str:
    """Undo nmcli's terse-mode escaping of ':' and '\\'."""
    return value.replace("\\:", ":").replace("\\\\", "\\")


def saved_wifi_profiles(conn_name: str) -> list[str]:
    """Names of the autoconnect Wi-Fi profiles other than the AP."""
    result = nmcli("-t", "-f", "TYPE,AUTOCONNECT,NAME", "connection", "show")
    profiles = []
    for line in result.stdout.splitlines():
        ctype, autoconnect, name = line.split(":", 2)
        name = nmcli_unescape(name)
        if ctype == "802-11-wireless" and autoconnect == "yes" and name != conn_name:
            profiles.append(name)
    return profiles


def saved_ssids(profiles: list[str]) -> tuple[set[str], bool]:
    """SSIDs of the given profiles, and whether any of them is hidden."""
    ssids, hidden = set(), False
    for name in profiles:
        result = nmcli("-g", "802-11-wireless.ssid,802-11-wireless.hidden",
                       "connection", "show", name)
        lines = result.stdout.splitlines()
        if lines:
            ssids.add(nmcli_unescape(lines[0]))
        if len(lines) > 1 and lines[1] == "yes":
            hidden = True
    return ssids, hidden


def visible_ssids(ifname: str) -> set[str]:
    """SSIDs in NM's current scan results, without starting a new scan."""
    result = nmcli("-t", "-f", "SSID", "device", "wifi", "list",
                   "ifname", ifname, "--rescan", "no")
    return {nmcli_unescape(line) for line in result.stdout.splitlines() if line}


def device_state(ifname: str) -> int:
    result = nmcli("-g", "GENERAL.STATE", "device", "show", ifname)
    try:
        return int(result.stdout.split()[0])
    except (IndexError, ValueError):
        return 0


def ap_station_count(ifname: str) -> int | None:
    """Number of clients associated with the AP, or None if it can't be told."""
    try:
        result = subprocess.run(
            ["iw", "dev", ifname, "station", "dump"],
            capture_output=True, text=True, check=False
        )
    except FileNotFoundError:
        log.error("iw is not installed; can't tell whether clients are on the AP")
        return None
    if result.returncode != 0:
        log.error("iw station dump failed: %s", result.stderr.strip())
        return None
    return sum(1 for line in result.stdout.splitlines() if line.startswith("Station "))


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

def ap_ssid(ifname: str, cfg: dict) -> str:
    return f"{cfg['ssid_prefix']}{get_interface_mac(ifname)}"


def ensure_ap_profile(ifname: str, cfg: dict) -> None:
    """Create the fallback AP profile bound to the given interface if missing."""
    if len(cfg["ssid"]) > 32:
        log.warning(
            "Generated SSID '%s' exceeds 32 bytes and will be truncated by "
            "the driver — shorten AP_SSID_PREFIX", cfg["ssid"]
        )

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
# Activate / deactivate
# --------------------------------------------------------------------------

def activate_ap(ifname: str, cfg: dict) -> bool:
    # Other profiles on this radio are left with autoconnect as-is: NM never
    # autoconnects onto a device with an active connection, so they can't
    # preempt the AP, and they need to stay eligible to rejoin as soon as
    # the AP is torn down.
    #
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


def scan_for_networks(ifname: str, cfg: dict) -> bool:
    """If the AP is up with no clients, take it down and give NM a chance to
    autoconnect to a saved Wi-Fi profile; put the AP back if that fails."""
    if not ap_is_active(cfg["conn_name"]):
        return True

    # Unknown counts as "someone might be using it" — leave it alone.
    stations = ap_station_count(ifname)
    if stations is None:
        return True
    if stations:
        log.info("%d client(s) on the AP; not scanning", stations)
        return True

    profiles = saved_wifi_profiles(cfg["conn_name"])
    if not profiles:
        log.info("No saved Wi-Fi profiles to try; leaving the AP up")
        return True
    ssids, hidden = saved_ssids(profiles)

    log.info("No clients on the AP — taking it down to look for saved networks")
    nmcli("connection", "down", cfg["conn_name"])
    # The `device disconnect` in activate_ap() blocks autoconnect on the
    # device. NM clears that again on the AP's `connection up`, but make
    # sure — if it stuck, NM wouldn't try any saved profile.
    nmcli("device", "set", ifname, "autoconnect", "yes")
    # Best effort — NM also scans on its own once the device is free.
    nmcli("device", "wifi", "rescan", "ifname", ifname)

    # Waiting out the whole timeout only helps if NM has something to join.
    # A hidden network never shows up by name in a scan, so with one saved
    # there's no telling — wait the whole timeout then.
    start = time.monotonic()
    deadline = start + cfg["scan_timeout"]
    while time.monotonic() < deadline:
        time.sleep(5)
        state = device_state(ifname)
        if state == DEVICE_ACTIVATED and get_connectivity_state() not in DEGRADED_STATES:
            log.info("Joined a saved network; leaving the AP down")
            return True
        if (not hidden and state not in DEVICE_ACTIVATING
                and time.monotonic() - start >= SCAN_SETTLE_SECONDS
                and not ssids & visible_ssids(ifname)):
            log.info("No saved network in range after %ds; restoring the AP",
                     SCAN_SETTLE_SECONDS)
            return activate_ap(ifname, cfg)

    log.info("No usable network found within %ds; restoring the AP", cfg["scan_timeout"])
    return activate_ap(ifname, cfg)


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main() -> int:
    scan = "--scan" in sys.argv[1:]
    cfg = load_config()

    lock = open(LOCK_FILE, "w")
    fcntl.flock(lock, fcntl.LOCK_EX)

    wireless_ifaces = get_wireless_interfaces()
    if not wireless_ifaces:
        log.warning("No wireless interfaces found; nothing to do")
        return 0

    ifname = wireless_ifaces[0]
    if len(wireless_ifaces) > 1:
        log.info("Multiple wireless interfaces found (%s); using %s",
                  ", ".join(wireless_ifaces), ifname)

    write_dns_blackhole(cfg)

    # Needed on every run (activate_ap logs it), not just when the profile
    # is first created.
    cfg["ssid"] = ap_ssid(ifname, cfg)

    if not ap_profile_exists(cfg["conn_name"]):
        ensure_ap_profile(ifname, cfg)
    else:
        # Self-heal profiles created before connection.zone was pinned
        # (see ensure_ap_profile) so they don't silently fall back to NM's
        # nm-shared firewalld zone.
        nmcli("connection", "modify", cfg["conn_name"], "connection.zone", "allstarlink")

    if scan:
        return 0 if scan_for_networks(ifname, cfg) else 1

    state = get_connectivity_state()
    log.info("Connectivity state: %s", state)
    degraded = state in DEGRADED_STATES

    currently_active = ap_is_active(cfg["conn_name"])

    if degraded and not currently_active:
        if not activate_ap(ifname, cfg):
            return 1
    elif not degraded and currently_active:
        deactivate_ap(cfg)

    return 0


if __name__ == "__main__":
    sys.exit(main())