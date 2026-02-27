import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import yaml

CONFIG_DIR = Path.home() / ".config" / "hpc-submit"
CONFIG_PATH = CONFIG_DIR / "config.yaml"


@dataclass
class Config:
    remote_host: str = ""  # SSH target: alias like "hpc" or "user@host"
    remote_base_path: str = ""
    remote_host_env: str = ""  # deprecated: env var name, kept for backwards compat


def load_config() -> Config:
    try:
        raw = yaml.safe_load(CONFIG_PATH.read_text())
    except yaml.YAMLError:
        print(f"Error: config file is not valid YAML: {CONFIG_PATH}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(raw, dict):
        print(f"Error: config file must be a YAML mapping: {CONFIG_PATH}", file=sys.stderr)
        sys.exit(1)

    if "remote_base_path" not in raw or not raw["remote_base_path"]:
        print("Error: config is missing required field 'remote_base_path'", file=sys.stderr)
        sys.exit(1)

    has_host = bool(raw.get("remote_host"))
    has_env = bool(raw.get("remote_host_env"))
    if not has_host and not has_env:
        print(
            "Error: config needs 'remote_host' (SSH target) or 'remote_host_env' (env var name).\n"
            "  Run: hpc-submit --init",
            file=sys.stderr,
        )
        sys.exit(1)

    return Config(
        remote_host=str(raw.get("remote_host", "")),
        remote_base_path=str(raw["remote_base_path"]),
        remote_host_env=str(raw.get("remote_host_env", "")),
    )


def save_config(config: Config) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    data: dict = {}
    if config.remote_host:
        data["remote_host"] = config.remote_host
    data["remote_base_path"] = config.remote_base_path
    if config.remote_host_env:
        data["remote_host_env"] = config.remote_host_env
    CONFIG_PATH.write_text(yaml.safe_dump(data, default_flow_style=False))


def resolve_remote_host(config: Config) -> str:
    # Prefer direct remote_host value
    if config.remote_host:
        return config.remote_host

    # Fall back to env var lookup (backwards compat)
    var = config.remote_host_env
    if not var:
        print(
            "Error: no SSH target configured.\n"
            "  Run: hpc-submit --init",
            file=sys.stderr,
        )
        sys.exit(1)

    value = os.environ.get(var)
    if value is None:
        print(
            f"Error: environment variable '{var}' is not set.\n"
            f"  Set it, e.g.: export {var}=user@cluster.example.com\n"
            f"  Or run: hpc-submit --init   to set a direct SSH target instead.",
            file=sys.stderr,
        )
        sys.exit(1)
    if not value.strip():
        print(f"Error: environment variable '{var}' is set but empty", file=sys.stderr)
        sys.exit(1)
    return value.strip()


# ---------------------------------------------------------------------------
# SSH diagnostics
# ---------------------------------------------------------------------------

def test_ssh_connection(host: str) -> tuple[bool, str]:
    """Test SSH connectivity in batch mode.

    Returns (success, message) with actionable guidance on failure.
    All diagnosis comes from ssh's exit code and stderr — no .ssh files are read.
    """
    try:
        result = subprocess.run(
            [
                "ssh",
                "-o", "BatchMode=yes",
                "-o", "ConnectTimeout=10",
                host,
                "echo __hpc_submit_ok__",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except subprocess.TimeoutExpired:
        return (False,
            "SSH connection timed out after 15 seconds.\n"
            "  - The hostname may be wrong or the server unreachable\n"
            "  - A firewall or VPN may be blocking the connection")
    except FileNotFoundError:
        return (False, "ssh command not found. Is OpenSSH installed?")

    if result.returncode == 0 and "__hpc_submit_ok__" in result.stdout:
        return (True, f"Connected to '{host}'.")

    stderr = result.stderr.strip().lower()

    if "could not resolve hostname" in stderr:
        return (False,
            f"Hostname not found: '{host}'\n"
            "  - Check for typos in the hostname\n"
            "  - If using an SSH alias, ensure it is defined in ~/.ssh/config")

    if "connection refused" in stderr:
        return (False,
            f"Connection refused by '{host}'\n"
            "  - The SSH port may be wrong (default: 22)\n"
            "  - The server may be down or decommissioned\n"
            "  - Try a different login node if available")

    if "host key verification failed" in stderr:
        return (False,
            f"Host key verification failed for '{host}'\n"
            "  Your ~/.ssh/known_hosts has a stale entry for this server\n"
            "  (common after a cluster reinstall).\n"
            "  Fix: ssh-keygen -R <hostname>   then connect manually once\n"
            "  to accept the new host key.")

    if "permission denied" in stderr and "keyboard-interactive" in stderr:
        return (False,
            f"Authentication to '{host}' requires 2FA (keyboard-interactive).\n"
            "  Batch SSH calls cannot prompt for a 2FA code.\n"
            "  Fix: set up SSH ControlMaster multiplexing.\n"
            "\n"
            "  1. Add to ~/.ssh/config:\n"
            "\n"
            f"     Host {host}\n"
            "         HostName <cluster-login-node>\n"
            "         User <your-username>\n"
            "         ControlMaster auto\n"
            "         ControlPath ~/.ssh/sockets/%r@%h-%p\n"
            "         ControlPersist 4h\n"
            "\n"
            "  2. Create the socket directory:\n"
            "         mkdir -p ~/.ssh/sockets\n"
            "\n"
            "  3. Connect once interactively:\n"
            f"         ssh {host}\n"
            "\n"
            "  After authenticating, all subsequent ssh/rsync/hpc-submit calls\n"
            "  reuse the authenticated connection for 4 hours.")

    if "permission denied" in stderr and "publickey" in stderr:
        return (False,
            f"Public key authentication failed for '{host}'\n"
            "  - Check that your key is loaded: ssh-add -l\n"
            "  - Check that IdentityFile is set correctly in ~/.ssh/config\n"
            "  - Verify the public key is in authorized_keys on the server")

    if "permission denied" in stderr:
        return (False,
            f"Permission denied connecting to '{host}'\n"
            f"  SSH error: {result.stderr.strip()}")

    return (False,
        f"SSH connection to '{host}' failed (exit code {result.returncode}).\n"
        f"  SSH error: {result.stderr.strip()}\n"
        f"  Try connecting manually: ssh {host}")


def test_remote_path(host: str, path: str) -> tuple[bool, str]:
    """Test that a remote path exists (or can be created) and is writable."""
    try:
        result = subprocess.run(
            [
                "ssh",
                "-o", "BatchMode=yes",
                "-o", "ConnectTimeout=10",
                host,
                f"mkdir -p {path} && test -w {path} && echo __path_ok__",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return (False, "Could not test remote path (SSH failed).")

    if result.returncode == 0 and "__path_ok__" in result.stdout:
        return (True, f"Remote path '{path}' is accessible and writable.")

    return (False,
        f"Remote path '{path}' is not writable or could not be created.\n"
        f"  SSH error: {result.stderr.strip()}\n"
        "  Ensure the directory exists and you have write permissions.")


# ---------------------------------------------------------------------------
# Setup and connectivity check
# ---------------------------------------------------------------------------

def interactive_setup() -> Config:
    print("hpc-submit: configuration setup")
    print("=" * 40)
    print()
    print("SSH target — this is what gets passed to ssh and rsync.")
    print("  You can use:")
    print("    - An SSH config alias, e.g.: hpc")
    print("    - A full user@host, e.g.: user@cluster.example.com")
    print()
    print("  Tip: an SSH config alias is preferred because it carries")
    print("  IdentityFile, ControlMaster, ProxyJump, etc. settings.")
    print()

    host = input("SSH target [hpc]: ").strip()
    if not host:
        host = "hpc"

    # Test the connection immediately
    print(f"\nTesting SSH connection to '{host}'...")
    ok, msg = test_ssh_connection(host)
    print()
    if ok:
        print(f"  OK: {msg}")
    else:
        print("  FAILED:\n")
        for line in msg.splitlines():
            print(f"    {line}")
        print()
        print("  You can fix this now and re-run: hpc-submit --init")
        print("  Or save this config anyway and fix SSH later.")
        choice = input("  Save config with this SSH target anyway? [y/N]: ").strip().lower()
        if choice != "y":
            print("Setup aborted.")
            sys.exit(1)

    print()
    base_path = input("Remote base path for job directories [~/jobs]: ").strip()
    if not base_path:
        base_path = "~/jobs"

    # Test remote path if SSH succeeded
    if ok:
        print(f"\nTesting remote path '{base_path}'...")
        path_ok, path_msg = test_remote_path(host, base_path)
        if path_ok:
            print(f"  OK: {path_msg}")
        else:
            print(f"  Warning: {path_msg}")
            print("  The path will be created when you submit your first job.")

    config = Config(remote_host=host, remote_base_path=base_path)
    save_config(config)
    print(f"\nConfig written to {CONFIG_PATH}")

    if ok:
        print("Ready to use: hpc-submit <script.sh>")
    else:
        print("Fix your SSH connection, then verify with: hpc-submit --check")

    return config


def check_connectivity(config: Config) -> bool:
    """Run SSH and remote path diagnostics. Returns True if all pass."""
    host = resolve_remote_host(config)

    print(f"Checking SSH connection to '{host}'...")
    ok, msg = test_ssh_connection(host)

    if ok:
        print(f"  [PASS] {msg}")
    else:
        print("  [FAIL]")
        for line in msg.splitlines():
            print(f"    {line}")
        return False

    print(f"Checking remote path '{config.remote_base_path}'...")
    path_ok, path_msg = test_remote_path(host, config.remote_base_path)
    if path_ok:
        print(f"  [PASS] {path_msg}")
    else:
        print("  [FAIL]")
        for line in path_msg.splitlines():
            print(f"    {line}")
        return False

    print("\nAll checks passed. Ready to submit jobs.")
    return True


def ensure_config() -> Config:
    if CONFIG_PATH.exists():
        return load_config()
    return interactive_setup()
