# Configuration for the ASL3 appliance fallback-AP watchdog.
# Sourced by systemd via EnvironmentFile= — plain KEY=VALUE, no shell expansion.

# SSID broadcast by the fallback AP
AP_SSID_PREFIX="AllStarLink_"

# WPA2-PSK passphrase (8-63 chars). Leave empty for an open (unencrypted) network.
AP_PSK="AllStarLinkSetup"

# IPv4 address/prefix assigned to the AP interface (DHCP served via
# NetworkManager's shared method, scoped to this connection's lifecycle).
# Deliberately the RFC 2544 benchmarking block (198.18.0.0/15) rather than
# RFC 1918 space: most operators here aren't networking-savvy, so avoiding
# a collision with their real LAN matters more than avoiding a block that
# only a networking-literate user would already have claimed for something
# else. APIPA (169.254.0.0/16) and RFC 6598 CGNAT space (100.64.0.0/10)
# were each tried and dropped first — iOS refuses to fully join a network
# whose DHCP lease falls in the APIPA block at all, and CGNAT space is
# exactly the kind of range a networking-literate operator's own network
# may already use. Must stay within 198.18.0.0/15 — Apache's reverse proxy
# to Cockpit (src/apache2/000-default.conf) is scoped to that whole block,
# not templated to this specific address.
AP_IPV4_CIDR="198.18.252.1/24"

# IPv6 is intentionally not offered on the fallback AP — see the module
# docstring in fallback-ap-watchdog.py for why a ULA doesn't help here.

# 802.11 band: bg (2.4GHz) or a (5GHz), depending on adapter support
AP_BAND="bg"

# WiFi Channel - has to match a channel in AP_BAND
AP_CHANNEL="11"

# Name of the NetworkManager connection profile the watchdog manages
AP_CONN_NAME="asl-fallback-ap"