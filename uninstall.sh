#!/bin/bash

set -euo pipefail

data_home=${XDG_DATA_HOME:-"$HOME/.local/share"}
config_home=${XDG_CONFIG_HOME:-"$HOME/.config"}
runtime_dir="$data_home/edifier-qr65"
venv="$runtime_dir/venv"
marker="$runtime_dir/install-state"
launcher="$HOME/.local/bin/edifier-qr65"
service="$config_home/systemd/user/edifier-qr65.service"
hook="$config_home/omarchy/hooks/theme-set.d/qr65-theme-sync"

if [[ ! -f $marker ]] || ! grep -qx 'owner=lightqv.edifier-qr65' "$marker"; then
  echo "error: installation ownership marker is missing or invalid: $marker" >&2
  exit 1
fi

state_value() {
  local wanted=$1 key value
  while IFS='=' read -r key value; do
    if [[ $key == "$wanted" ]]; then
      printf '%s\n' "$value"
      return 0
    fi
  done < "$marker"
  return 1
}

verify_owned_file() {
  local key=$1 path=$2 expected current
  if [[ ! -e $path && ! -L $path ]]; then
    return 0
  fi
  expected=$(state_value "$key" || true)
  current=$(sha256sum -- "$path" 2>/dev/null | cut -d' ' -f1 || true)
  if [[ -z $expected || $current != "$expected" ]]; then
    echo "error: refusing to remove modified or unrecognized file: $path" >&2
    exit 1
  fi
}

verify_owned_file service "$service"
verify_owned_file hook "$hook"
if [[ -e $launcher || -L $launcher ]]; then
  if [[ ! -L $launcher || $(readlink -f -- "$launcher") != "$venv/bin/edifier-qr65" ]]; then
    echo "error: refusing to remove modified or unrecognized file: $launcher" >&2
    exit 1
  fi
fi

systemctl --user disable --now edifier-qr65.service 2>/dev/null || true
rm -f -- "$service" "$hook" "$launcher"
rm -rf -- "$venv"
rm -- "$marker"
rmdir --ignore-fail-on-non-empty "$runtime_dir"
systemctl --user daemon-reload

echo "Removed the QR65 backend, service, and theme hook."
echo "Settings and runtime state were preserved."
echo "Remove the shell plugin separately with: omarchy plugin remove lightqv.edifier-qr65"
