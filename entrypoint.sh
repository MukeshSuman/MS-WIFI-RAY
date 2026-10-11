#!/bin/sh
# Root se data folder likhne layak banao, phir scanner user pe chodo.
set -e
mkdir -p /data
if [ ! -s /data/known_devices.json ] && [ -s /seed/known_devices.json ]; then
  cp /seed/known_devices.json /data/known_devices.json
fi
if [ ! -s /data/vendor_cache.json ] && [ -s /seed/vendor_cache.json ]; then
  cp /seed/vendor_cache.json /data/vendor_cache.json
fi
chown -R scanner:scanner /data
exec setpriv --reuid=scanner --regid=scanner --init-groups -- python -u /app/wifi_web.py
