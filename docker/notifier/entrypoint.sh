#!/bin/sh
set -e

INTERVAL="${NOTIFIER_INTERVAL:-300}"

while true; do
  python /opt/radicale-notifier/notify.py || true
  sleep "$INTERVAL"
done
