#!/usr/bin/env bash
set -euo pipefail

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This script only supports macOS." >&2
  exit 1
fi

INTERFACE="Wi-Fi"
SHOW_REPORT=1

usage() {
  cat <<'EOF'
Usage:
  scripts/reset-macos-dns.sh [options]

Options:
  -i, --interface <name>  Network interface name for DNS report (default: Wi-Fi)
  --no-report             Skip resolver/report output
  -h, --help              Show this help

Examples:
  scripts/reset-macos-dns.sh
  scripts/reset-macos-dns.sh --interface "USB 10/100/1000 LAN"
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -i|--interface)
      INTERFACE="${2:-}"
      shift 2
      ;;
    --no-report)
      SHOW_REPORT=0
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 2
      ;;
  esac
done

echo "Resetting macOS DNS caches..."
sudo dscacheutil -flushcache
sudo killall -HUP mDNSResponder
echo "DNS cache reset complete."

if [[ "$SHOW_REPORT" -eq 1 ]]; then
  echo ""
  echo "DNS servers for interface: ${INTERFACE}"
  if networksetup -listallnetworkservices | grep -Fxq "${INTERFACE}"; then
    networksetup -getdnsservers "${INTERFACE}" || true
  else
    echo "Interface not found: ${INTERFACE}"
  fi

  echo ""
  echo "Active resolver nameservers (scutil):"
  scutil --dns | grep -A2 'nameserver\[[0-9]\]' || true
fi
