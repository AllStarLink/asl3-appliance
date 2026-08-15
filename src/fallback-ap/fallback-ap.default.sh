# Configuration for the ASL3 appliance fallback-AP watchdog.
# Sourced by systemd via EnvironmentFile= — plain KEY=VALUE, no shell expansion.

# SSID broadcast by the fallback AP
AP_SSID_PREFIX="AllStarLink_"

# WPA2-PSK passphrase (8-63 chars). Leave empty for an open (unencrypted) network.
AP_PSK="AllStarLinkSetup"

# IPv4 address/prefix assigned to the AP interface (DHCP served via
# NetworkManager's shared method, scoped to this connection's lifecycle)
AP_IPV4_CIDR="192.168.252.1/24"

# IPv6 Unique Local Address (ULA) prefix/address for the AP interface,
# also via ipv6.method=shared. Must fall within fc00::/7 (fd00::/8 in
# practice). Generate a proper random ULA prefix once per deployment/image:
#   python3 -c "import secrets;print('fd'+secrets.token_hex(5))"
# and bake it into the image rather than leaving every appliance on the
# same guessable default.
AP_IPV6_CIDR="fd75:9d2a:4e3c::1/64"

# 802.11 band: bg (2.4GHz) or a (5GHz), depending on adapter support
AP_BAND="bg"

# Name of the NetworkManager connection profile the watchdog manages
AP_CONN_NAME="asl-fallback-ap"