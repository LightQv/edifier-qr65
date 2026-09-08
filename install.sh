#!/bin/bash

set -euo pipefail

force=0
if [[ ${1:-} == "--force" ]]; then
  force=1
  shift
fi
if (( $# > 0 )); then
  echo "Usage: ./install.sh [--force]" >&2
  exit 2
fi

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
data_home=${XDG_DATA_HOME:-"$HOME/.local/share"}
config_home=${XDG_CONFIG_HOME:-"$HOME/.config"}
state_home=${XDG_STATE_HOME:-"$HOME/.local/state"}
if [[ $config_home != "$HOME/.config" || $state_home != "$HOME/.local/state" ]]; then
  echo "error: custom XDG_CONFIG_HOME and XDG_STATE_HOME are not supported by the systemd sandbox" >&2
  exit 1
fi
runtime_dir="$data_home/edifier-qr65"
venv="$runtime_dir/venv"
marker="$runtime_dir/install-state"
launcher="$HOME/.local/bin/edifier-qr65"
service="$config_home/systemd/user/edifier-qr65.service"
hook="$config_home/omarchy/hooks/theme-set.d/qr65-theme-sync"

for command in python omarchy systemctl sha256sum; do
  command -v "$command" >/dev/null || {
    echo "error: required command not found: $command" >&2
    exit 1
  }
done

python -c 'import bleak' >/dev/null 2>&1 || {
  echo "error: python-bleak is required; install it with: omarchy pkg add python-bleak" >&2
  exit 1
}

if [[ -f $marker ]] && ! grep -qx 'owner=lightqv.edifier-qr65' "$marker"; then
  if (( ! force )); then
    echo "error: refusing invalid ownership marker $marker; inspect it or rerun with --force" >&2
    exit 1
  fi
elif [[ -e $venv && ! -f $marker && $force -eq 0 ]]; then
  echo "error: refusing to use unmanaged directory $runtime_dir; inspect it or rerun with --force" >&2
  exit 1
fi

state_value() {
  local wanted=$1 key value
  [[ -f $marker ]] || return 1
  while IFS='=' read -r key value; do
    if [[ $key == "$wanted" ]]; then
      printf '%s\n' "$value"
      return 0
    fi
  done < "$marker"
  return 1
}

check_file() {
  local key=$1 destination=$2 source=$3 previous current
  if [[ ! -e $destination && ! -L $destination ]]; then
    return 0
  fi
  previous=$(state_value "$key" || true)
  current=$(sha256sum -- "$destination" 2>/dev/null | cut -d' ' -f1 || true)
  if [[ -n $previous && $current == "$previous" ]] || cmp -s -- "$destination" "$source"; then
    return 0
  fi
  if (( ! force )); then
    echo "error: refusing to replace $destination; inspect it or rerun with --force" >&2
    exit 1
  fi
  return 0
}

if [[ -e $launcher || -L $launcher ]]; then
  if [[ -L $launcher && $(readlink -f -- "$launcher") == "$venv/bin/edifier-qr65" ]]; then
    :
  elif (( force )); then
    :
  else
    echo "error: refusing to replace $launcher; inspect it or rerun with --force" >&2
    exit 1
  fi
fi
check_file service "$service" "$root/systemd/edifier-qr65.service"
check_file hook "$hook" "$root/hooks/qr65-theme-sync"

install -d -m 0700 "$runtime_dir" "$config_home/edifier-qr65" \
  "$state_home/edifier-qr65"
install -d "$HOME/.local/bin" "$config_home/systemd/user" \
  "$config_home/omarchy/hooks/theme-set.d"
temporary_dir=$(mktemp -d "$runtime_dir/.install.XXXXXX")
fresh_venv=0
[[ -e $venv ]] || fresh_venv=1
cleanup() {
  local result=$?
  trap - EXIT
  rm -rf -- "$temporary_dir"
  if (( result != 0 && fresh_venv )) && [[ ! -f $marker ]]; then
    rm -rf -- "$venv"
  fi
  exit "$result"
}
trap cleanup EXIT

python -m venv --system-site-packages "$temporary_dir/build-venv"
"$temporary_dir/build-venv/bin/pip" wheel --disable-pip-version-check \
  --no-deps --no-build-isolation --wheel-dir "$temporary_dir/wheels" "$root"
wheel=("$temporary_dir"/wheels/edifier_qr65-*.whl)
[[ -f ${wheel[0]} ]] || {
  echo "error: backend wheel was not created" >&2
  exit 1
}
python -m venv --system-site-packages "$venv"
"$venv/bin/pip" install --disable-pip-version-check --no-deps --force-reinstall \
  "${wheel[0]}"

rm -f -- "$launcher"
ln -s "$venv/bin/edifier-qr65" "$launcher"

rm -f -- "$service"
install -m 0644 "$root/systemd/edifier-qr65.service" "$service"
rm -f -- "$hook"
install -m 0755 "$root/hooks/qr65-theme-sync" "$hook"

temporary_marker="$temporary_dir/install-state"
{
  printf 'owner=lightqv.edifier-qr65\n'
  printf 'version=0.1.0\n'
  printf 'service=%s\n' "$(sha256sum -- "$service" | cut -d' ' -f1)"
  printf 'hook=%s\n' "$(sha256sum -- "$hook" | cut -d' ' -f1)"
} > "$temporary_marker"
mv -- "$temporary_marker" "$marker"

systemctl --user daemon-reload
omarchy plugin enable lightqv.edifier-qr65 --section right --before omarchy.bluetooth
systemctl --user enable edifier-qr65.service
systemctl --user restart edifier-qr65.service

echo "Installed Edifier QR65 backend and enabled lightqv.edifier-qr65."
echo "Optional shortcut: SUPER+CTRL+G -> omarchy-shell shell toggle lightqv.edifier-qr65"
