import os
import subprocess
from pathlib import Path


PROJECT = Path(__file__).parents[1]


def _write_command(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _environment(tmp_path: Path) -> tuple[dict[str, str], Path]:
    home = tmp_path / "home"
    fake_bin = tmp_path / "bin"
    home.mkdir()
    fake_bin.mkdir()
    _write_command(
        fake_bin / "python",
        """#!/bin/bash
set -e
if [[ $1 == -c ]]; then exit 0; fi
venv=${@: -1}
mkdir -p "$venv/bin"
cat > "$venv/bin/pip" <<'PIP'
#!/bin/bash
set -e
if [[ $1 == wheel ]]; then
  while (( $# )); do
    if [[ $1 == --wheel-dir ]]; then
      mkdir -p "$2"
      : > "$2/edifier_qr65-0.1.0-py3-none-any.whl"
      exit 0
    fi
    shift
  done
  exit 1
fi
launcher=$(dirname "$0")/edifier-qr65
printf '#!/bin/bash\n' > "$launcher"
chmod 755 "$launcher"
PIP
chmod 755 "$venv/bin/pip"
""",
    )
    _write_command(fake_bin / "omarchy", "#!/bin/bash\nexit 0\n")
    _write_command(fake_bin / "systemctl", "#!/bin/bash\nexit 0\n")
    environment = os.environ | {
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(home / ".config"),
        "XDG_DATA_HOME": str(home / ".local/share"),
        "XDG_STATE_HOME": str(home / ".local/state"),
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
    }
    return environment, home


def _run_install(environment: dict[str, str]) -> None:
    result = subprocess.run(
        [PROJECT / "install.sh"],
        check=False,
        cwd=PROJECT,
        env=environment,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_installer_is_idempotent_and_uninstaller_removes_owned_files(tmp_path) -> None:
    environment, home = _environment(tmp_path)

    for _attempt in range(2):
        _run_install(environment)

    assert (home / ".local/share/edifier-qr65/install-state").is_file()
    assert (home / ".local/bin/edifier-qr65").is_symlink()
    assert (home / ".config/systemd/user/edifier-qr65.service").is_file()
    assert (home / ".config/omarchy/hooks/theme-set.d/qr65-theme-sync").is_file()

    subprocess.run(
        [PROJECT / "uninstall.sh"],
        check=True,
        cwd=PROJECT,
        env=environment,
        capture_output=True,
        text=True,
    )

    assert not (home / ".local/share/edifier-qr65").exists()
    assert not (home / ".local/bin/edifier-qr65").exists()
    assert not (home / ".config/systemd/user/edifier-qr65.service").exists()


def test_uninstaller_refuses_modified_owned_file(tmp_path) -> None:
    environment, home = _environment(tmp_path)
    _run_install(environment)
    service = home / ".config/systemd/user/edifier-qr65.service"
    service.write_text("unrelated service\n", encoding="utf-8")

    result = subprocess.run(
        [PROJECT / "uninstall.sh"],
        check=False,
        cwd=PROJECT,
        env=environment,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "refusing to remove modified or unrecognized file" in result.stderr
    assert service.read_text(encoding="utf-8") == "unrelated service\n"
    assert (home / ".local/share/edifier-qr65/venv").is_dir()
