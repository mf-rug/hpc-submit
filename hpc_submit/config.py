import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import yaml

CONFIG_DIR = Path.home() / ".config" / "hpc-submit"
CONFIG_PATH = CONFIG_DIR / "config.yaml"


@dataclass
class Config:
    remote_host_env: str
    remote_base_path: str


def load_config() -> Config:
    try:
        raw = yaml.safe_load(CONFIG_PATH.read_text())
    except yaml.YAMLError:
        print(f"Error: config file is not valid YAML: {CONFIG_PATH}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(raw, dict):
        print(f"Error: config file must be a YAML mapping: {CONFIG_PATH}", file=sys.stderr)
        sys.exit(1)

    for field in ("remote_host_env", "remote_base_path"):
        if field not in raw or not raw[field]:
            print(f"Error: config is missing required field '{field}'", file=sys.stderr)
            sys.exit(1)

    return Config(
        remote_host_env=str(raw["remote_host_env"]),
        remote_base_path=str(raw["remote_base_path"]),
    )


def save_config(config: Config) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(yaml.safe_dump(asdict(config), default_flow_style=False))


def interactive_setup() -> Config:
    print("hpc-submit: configuration setup")
    print("-" * 35)

    host_env = input("Environment variable holding user@host [HPC]: ").strip()
    if not host_env:
        host_env = "HPC"

    base_path = input("Remote base path for job directories [~/jobs]: ").strip()
    if not base_path:
        base_path = "~/jobs"

    config = Config(remote_host_env=host_env, remote_base_path=base_path)
    save_config(config)
    print(f"\nConfig written to {CONFIG_PATH}")
    return config


def ensure_config() -> Config:
    if CONFIG_PATH.exists():
        return load_config()
    return interactive_setup()


def resolve_remote_host(config: Config) -> str:
    var = config.remote_host_env
    value = os.environ.get(var)
    if value is None:
        print(
            f"Error: environment variable '{var}' is not set.\n"
            f"  Set it to user@host, e.g.: export {var}=user@cluster.example.com",
            file=sys.stderr,
        )
        sys.exit(1)
    if not value.strip():
        print(f"Error: environment variable '{var}' is set but empty", file=sys.stderr)
        sys.exit(1)
    return value.strip()
