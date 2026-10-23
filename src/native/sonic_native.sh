#!/bin/sh
set -eu
cd /mnt/UDISK/falcon_native_usb
SERVICE=/etc/init.d/falcon_a1_bridge
R4=/etc/falcon_a1/bridge_r3.py
[ "$(id -u)" = 0 ] || exit 1
[ -x "$SERVICE" ] || { echo 'Original bridge service missing'; exit 1; }
[ "$(sha256sum "$R4" | awk '{print $1}')" = bedd02fe96aaa438ec15926f9876fe33b777049087768c1907fe8e75686a146f ] || { echo 'Unexpected original bridge; nothing stopped'; exit 1; }
python3 -c 'import ast; ast.parse(open("sonic_serial_relay.py").read())'
CHILD=
cleanup() {
    trap - EXIT HUP INT TERM
    if [ -n "$CHILD" ]; then
        kill "$CHILD" 2>/dev/null || true
        wait "$CHILD" 2>/dev/null || true
    fi
    "$SERVICE" start
}
"$SERVICE" stop
trap cleanup EXIT HUP INT TERM
python3 sonic_serial_relay.py --instance "${1:-}" &
CHILD=$!
wait "$CHILD"
CHILD=
