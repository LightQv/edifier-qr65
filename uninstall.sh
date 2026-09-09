#!/bin/bash

set -euo pipefail

data_home=${XDG_DATA_HOME:-"$HOME/.local/share"}
config_home=${XDG_CONFIG_HOME:-"$HOME/.config"}
if [[ $data_home != "$HOME/.local/share" || $config_home != "$HOME/.config" ]]; then
  echo "error: custom XDG data and config locations are not supported" >&2
  exit 1
fi
runtime_dir="$data_home/edifier-qr65"
releases="$runtime_dir/releases"
current="$runtime_dir/current"
marker="$runtime_dir/install-state"
launcher="$HOME/.local/bin/edifier-qr65"
service="$config_home/systemd/user/edifier-qr65.service"

if [[ -L $runtime_dir ]]; then
  echo "error: refusing symlinked runtime directory $runtime_dir" >&2
  exit 1
fi
if [[ -L $marker || (-e $marker && ! -f $marker) ]]; then
  echo "error: refusing non-regular ownership marker $marker" >&2
  exit 1
fi
if [[ -L $releases || (-e $releases && ! -d $releases) ]]; then
  echo "error: refusing non-directory releases path $releases" >&2
  exit 1
fi
if [[ ! -L $current ]]; then
  echo "error: current daemon release is missing or invalid: $current" >&2
  exit 1
fi
if [[ $(readlink -f -- "$current") != "$releases/"* ]]; then
  echo "error: current daemon release is outside $releases" >&2
  exit 1
fi
if [[ ! -f $marker ]] || ! grep -qx 'owner=edifier-qr65' "$marker"; then
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
if [[ -e $launcher || -L $launcher ]]; then
  if [[ ! -L $launcher || $(readlink -f -- "$launcher") != "$(readlink -f -- "$current/bin/edifier-qr65")" ]]; then
    echo "error: refusing to remove modified or unrecognized file: $launcher" >&2
    exit 1
  fi
fi

systemctl --user disable --now edifier-qr65.service 2>/dev/null || true
rm -f -- "$service" "$launcher"
rm -f -- "$current"
rm -rf -- "$releases"
rm -- "$marker"
rmdir --ignore-fail-on-non-empty "$runtime_dir"
systemctl --user daemon-reload

echo "Removed the Edifier QR65 daemon."
echo "Settings and runtime state were preserved."
