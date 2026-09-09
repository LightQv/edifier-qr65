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
if [[ $data_home != "$HOME/.local/share" || $config_home != "$HOME/.config" \
    || $state_home != "$HOME/.local/state" ]]; then
  echo "error: custom XDG data, config, and state locations are not supported by the systemd unit" >&2
  exit 1
fi
runtime_dir="$data_home/edifier-qr65"
legacy_venv="$runtime_dir/venv"
releases="$runtime_dir/releases"
current="$runtime_dir/current"
marker="$runtime_dir/install-state"
launcher="$HOME/.local/bin/edifier-qr65"
service="$config_home/systemd/user/edifier-qr65.service"
legacy_hook="$config_home/omarchy/hooks/theme-set.d/qr65-theme-sync"
legacy_install=0

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
if [[ -e $current && ! -L $current ]]; then
  echo "error: refusing non-symlink current release $current" >&2
  exit 1
fi

for command in python systemctl sha256sum; do
  command -v "$command" >/dev/null || {
    echo "error: required command not found: $command" >&2
    exit 1
  }
done

python -c 'from importlib.metadata import version; parts=version("bleak").split("."); major_minor=tuple(map(int, parts[:2])); raise SystemExit(not ((3, 0) <= major_minor < (4, 0)))' \
  >/dev/null 2>&1 || {
  echo "error: python-bleak >=3.0,<4 is required; install it with your system package manager" >&2
  exit 1
}

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

verify_recorded_file() {
  local key=$1 path=$2 expected current
  [[ -e $path || -L $path ]] || return 0
  expected=$(state_value "$key" || true)
  current=$(sha256sum -- "$path" 2>/dev/null | cut -d' ' -f1 || true)
  if [[ -z $expected || $current != "$expected" ]]; then
    if (( ! force )); then
      echo "error: refusing modified or unrecognized legacy file $path; inspect it or rerun with --force" >&2
      exit 1
    fi
  fi
}

if [[ -f $marker ]]; then
  owner=$(state_value owner || true)
  case "$owner" in
    edifier-qr65)
      if [[ ! -L $current || $(readlink -f -- "$current") != "$releases/"* ]]; then
        echo "error: current daemon release is missing or outside $releases" >&2
        exit 1
      fi
      ;;
    lightqv.edifier-qr65)
      legacy_install=1
      verify_recorded_file service "$service"
      verify_recorded_file hook "$legacy_hook"
      ;;
    *)
      if (( ! force )); then
        echo "error: refusing invalid ownership marker $marker; inspect it or rerun with --force" >&2
        exit 1
      fi
      ;;
  esac
elif [[ (-e $legacy_venv || -e $releases || -e $current) && $force -eq 0 ]]; then
  echo "error: refusing to use unmanaged directory $runtime_dir; inspect it or rerun with --force" >&2
  exit 1
fi

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
}

if [[ -e $launcher || -L $launcher ]]; then
  expected_launcher="$current/bin/edifier-qr65"
  if (( legacy_install )); then
    expected_launcher="$legacy_venv/bin/edifier-qr65"
  fi
  if [[ -L $launcher && $(readlink -f -- "$launcher") == "$(readlink -f -- "$expected_launcher")" ]]; then
    :
  elif (( ! force )); then
    echo "error: refusing to replace $launcher; inspect it or rerun with --force" >&2
    exit 1
  fi
fi
check_file service "$service" "$root/systemd/edifier-qr65.service"

install -d -m 0700 "$runtime_dir" "$config_home/edifier-qr65" \
  "$state_home/edifier-qr65"
install -d "$HOME/.local/bin" "$config_home/systemd/user" "$releases"
temporary_dir=$(mktemp -d "$runtime_dir/.install.XXXXXX")
release_dir=$(mktemp -d "$releases/0.1.0.XXXXXX")
previous_release=""
previous_launcher=""
service_existed=0
switched=0
committed=0
if [[ -L $current ]]; then
  previous_release=$(readlink -f -- "$current")
fi
if [[ -L $launcher ]]; then
  previous_launcher=$(readlink -- "$launcher")
fi
if [[ -f $service ]]; then
  service_existed=1
  cp -- "$service" "$temporary_dir/previous.service"
fi
cleanup() {
  local result=$?
  trap - EXIT
  if (( result != 0 && ! committed )); then
    if (( switched )); then
      rm -f -- "$current" "$launcher"
      if [[ -n $previous_release ]]; then
        ln -s "$previous_release" "$current"
      fi
      if [[ -n $previous_launcher ]]; then
        ln -s "$previous_launcher" "$launcher"
      fi
      if (( service_existed )); then
        install -m 0644 "$temporary_dir/previous.service" "$service"
      else
        rm -f -- "$service"
      fi
      systemctl --user daemon-reload >/dev/null 2>&1 || true
      if [[ -n $previous_release || $legacy_install -eq 1 ]]; then
        systemctl --user restart edifier-qr65.service >/dev/null 2>&1 || true
      else
        systemctl --user disable edifier-qr65.service >/dev/null 2>&1 || true
      fi
    fi
    rm -rf -- "$release_dir"
  fi
  rm -rf -- "$temporary_dir"
  exit "$result"
}
trap cleanup EXIT

python -m venv --system-site-packages "$temporary_dir/build-venv"
"$temporary_dir/build-venv/bin/pip" wheel --disable-pip-version-check \
  --no-deps --wheel-dir "$temporary_dir/wheels" "$root"
wheel=("$temporary_dir"/wheels/edifier_qr65-*.whl)
[[ -f ${wheel[0]} ]] || {
  echo "error: daemon wheel was not created" >&2
  exit 1
}
python -m venv --system-site-packages "$release_dir"
"$release_dir/bin/pip" install --disable-pip-version-check --no-deps --force-reinstall \
  "${wheel[0]}"
[[ -x $release_dir/bin/edifier-qr65 ]] || {
  echo "error: installed daemon command is not executable" >&2
  exit 1
}

ln -s "$release_dir" "$temporary_dir/current"
mv -Tf -- "$temporary_dir/current" "$current"
switched=1
rm -f -- "$launcher"
ln -s "$current/bin/edifier-qr65" "$launcher"
rm -f -- "$service"
install -m 0644 "$root/systemd/edifier-qr65.service" "$service"

systemctl --user daemon-reload
systemctl --user enable edifier-qr65.service
systemctl --user restart edifier-qr65.service

temporary_marker="$temporary_dir/install-state"
{
  printf 'owner=edifier-qr65\n'
  printf 'version=0.1.0\n'
  printf 'release=%s\n' "$(basename -- "$release_dir")"
  printf 'service=%s\n' "$(sha256sum -- "$service" | cut -d' ' -f1)"
} > "$temporary_marker"
chmod 0600 "$temporary_marker"
mv -- "$temporary_marker" "$marker"
committed=1

if (( legacy_install )); then
  rm -f -- "$legacy_hook" || echo "warning: could not remove legacy theme hook $legacy_hook" >&2
  rm -rf -- "$legacy_venv" || echo "warning: could not remove legacy environment $legacy_venv" >&2
fi
if [[ -n $previous_release && $previous_release != "$release_dir"
    && $previous_release == "$releases/"* ]]; then
  rm -rf -- "$previous_release" || echo "warning: could not remove previous release $previous_release" >&2
fi

echo "Installed and started the Edifier QR65 daemon."
if (( legacy_install )); then
  echo "Adopted the legacy combined installation and removed its theme hook."
fi
