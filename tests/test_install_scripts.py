import os
import hashlib
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
    _write_command(
        fake_bin / "systemctl",
        "#!/bin/bash\n"
        "if [[ ${FAIL_RESTART:-0} == 1 && $1 == --user && $2 == restart ]]; then exit 1; fi\n"
        "exit 0\n",
    )
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

    runtime = home / ".local/share/edifier-qr65"
    assert (runtime / "install-state").is_file()
    assert (runtime / "current").is_symlink()
    assert (runtime / "current/bin/edifier-qr65").is_file()
    assert (home / ".local/bin/edifier-qr65").is_symlink()
    assert (home / ".config/systemd/user/edifier-qr65.service").is_file()

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


def test_installer_adopts_legacy_combined_installation(tmp_path) -> None:
    environment, home = _environment(tmp_path)
    runtime = home / ".local/share/edifier-qr65"
    venv_bin = runtime / "venv/bin"
    service = home / ".config/systemd/user/edifier-qr65.service"
    hook = home / ".config/omarchy/hooks/theme-set.d/qr65-theme-sync"
    launcher = home / ".local/bin/edifier-qr65"
    venv_bin.mkdir(parents=True)
    service.parent.mkdir(parents=True)
    hook.parent.mkdir(parents=True)
    launcher.parent.mkdir(parents=True)
    service.write_bytes((PROJECT / "systemd/edifier-qr65.service").read_bytes())
    hook.write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")
    _write_command(venv_bin / "edifier-qr65", "#!/bin/bash\nexit 0\n")
    launcher.symlink_to(venv_bin / "edifier-qr65")

    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    (runtime / "install-state").write_text(
        "owner=lightqv.edifier-qr65\n"
        "version=0.1.0\n"
        f"service={digest(service)}\n"
        f"hook={digest(hook)}\n",
        encoding="utf-8",
    )

    _run_install(environment)

    marker = (runtime / "install-state").read_text(encoding="utf-8")
    assert "owner=edifier-qr65\n" in marker
    assert not hook.exists()
    assert service.is_file()
    assert "/releases/0.1.0." in str(launcher.resolve())


def test_failed_restart_rolls_back_current_release(tmp_path) -> None:
    environment, home = _environment(tmp_path)
    _run_install(environment)
    runtime = home / ".local/share/edifier-qr65"
    current = runtime / "current"
    previous = current.resolve()
    marker = (runtime / "install-state").read_text(encoding="utf-8")

    result = subprocess.run(
        [PROJECT / "install.sh"],
        check=False,
        cwd=PROJECT,
        env=environment | {"FAIL_RESTART": "1"},
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert current.resolve() == previous
    assert (runtime / "install-state").read_text(encoding="utf-8") == marker
    assert list((runtime / "releases").iterdir()) == [previous]


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
    assert (home / ".local/share/edifier-qr65/current").is_symlink()


def test_installer_refuses_symlinked_runtime_directory(tmp_path) -> None:
    environment, home = _environment(tmp_path)
    target = tmp_path / "outside"
    target.mkdir()
    data_home = home / ".local/share"
    data_home.mkdir(parents=True)
    (data_home / "edifier-qr65").symlink_to(target, target_is_directory=True)

    result = subprocess.run(
        [PROJECT / "install.sh"],
        check=False,
        cwd=PROJECT,
        env=environment,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "refusing symlinked runtime directory" in result.stderr
    assert not list(target.iterdir())
