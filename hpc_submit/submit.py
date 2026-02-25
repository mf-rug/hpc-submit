import re
import subprocess
import sys
from pathlib import Path


def parse_sbatch_directive(job_script: Path, directive: str) -> str | None:
    for line in job_script.read_text().splitlines():
        match = re.match(rf"^#SBATCH\s+--{directive}=(.+)", line)
        if match:
            return match.group(1).strip()
    return None


def sanitize_dir_name(name: str) -> str:
    sanitized = re.sub(r"\s+", "_", name)
    sanitized = re.sub(r"[^a-zA-Z0-9_\-]", "", sanitized)
    return sanitized if sanitized else "job"


def remote_dir_exists(remote_host: str, remote_path: str) -> bool:
    cmd = ["ssh", remote_host, f"test -d {remote_path}"]
    result = subprocess.run(cmd, capture_output=True)
    return result.returncode == 0


def resolve_remote_path(remote_host: str, remote_path: str) -> str:
    if not remote_dir_exists(remote_host, remote_path):
        return remote_path

    print(f"Remote directory already exists: {remote_path}")
    choice = input("  [o]verwrite or [n]ew numbered directory? [o/n]: ").strip().lower()

    if choice == "o":
        return remote_path

    # Find next available _N suffix
    n = 1
    while True:
        candidate = f"{remote_path}_{n}"
        if not remote_dir_exists(remote_host, candidate):
            print(f"  Using: {candidate}")
            return candidate
        n += 1


def create_remote_dir(remote_host: str, remote_path: str) -> None:
    cmd = ["ssh", remote_host, f"mkdir -p {remote_path}"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error: failed to create remote directory {remote_path}", file=sys.stderr)
        print(f"  ssh stderr: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)


def transfer_files(
    remote_host: str,
    remote_path: str,
    job_script: Path,
    extra_files: list[Path],
) -> None:
    sources = [str(job_script)]
    for f in extra_files:
        sources.append(str(f))

    destination = f"{remote_host}:{remote_path}/"
    cmd = ["rsync", "-avz", "--progress", *sources, destination]

    result = subprocess.run(cmd)
    if result.returncode != 0:
        print(f"Error: rsync transfer failed (exit code {result.returncode})", file=sys.stderr)
        sys.exit(1)


def run_sbatch(
    remote_host: str,
    remote_path: str,
    script_name: str,
) -> int:
    cmd = ["ssh", remote_host, f"cd {remote_path} && sbatch {script_name}"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("Error: sbatch failed", file=sys.stderr)
        if result.stdout.strip():
            print(f"  stdout: {result.stdout.strip()}", file=sys.stderr)
        if result.stderr.strip():
            print(f"  stderr: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)

    stdout = result.stdout.strip()
    try:
        job_id = int(stdout.split()[-1])
    except (ValueError, IndexError):
        print(f"Error: could not parse job ID from sbatch output: {stdout!r}", file=sys.stderr)
        sys.exit(1)

    return job_id


def cancel_job(remote_host: str, job_id: int) -> None:
    cmd = ["ssh", remote_host, f"scancel {job_id}"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("Error: scancel failed", file=sys.stderr)
        if result.stderr.strip():
            print(f"  stderr: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    print(f"Job {job_id} cancelled.")


def check_output_dir(job_script: Path) -> str | None:
    output = parse_sbatch_directive(job_script, "output")
    if output is None:
        return None
    output_dir = str(Path(output).parent)
    if output_dir in (".", ""):
        return None
    return output_dir


def submit(
    job_script: Path,
    remote_host: str,
    remote_base_path: str,
    name: str | None,
    extra_files: list[Path],
) -> None:
    if name is None:
        name = parse_sbatch_directive(job_script, "job-name")
        if name is None:
            print(
                "Error: no #SBATCH --job-name= found in script and no --jobname given",
                file=sys.stderr,
            )
            sys.exit(1)

    # Check if --output defines a directory we should use directly
    output_dir = check_output_dir(job_script)
    if output_dir is not None:
        default_path = f"{remote_base_path}/{sanitize_dir_name(name)}"
        print(f"Found #SBATCH --output directory: {output_dir}")
        choice = input(f"  Use this instead of {default_path}? [y/n]: ").strip().lower()
        if choice == "y":
            remote_path = resolve_remote_path(remote_host, output_dir)
        else:
            remote_path = resolve_remote_path(remote_host, default_path)
    else:
        remote_path = resolve_remote_path(remote_host, f"{remote_base_path}/{sanitize_dir_name(name)}")

    print(f"Creating remote directory: {remote_path}")
    create_remote_dir(remote_host, remote_path)

    print("Transferring files...")
    transfer_files(remote_host, remote_path, job_script, extra_files)

    print("Submitting job...")
    job_id = run_sbatch(remote_host, remote_path, job_script.name)

    print()
    print("-" * 40)
    print("Job submitted successfully.")
    print(f"  Job ID:          {job_id}")
    print(f"  Remote directory: {remote_path}")
    print(f"  Host:            {remote_host}")
    print()
    print(f"  To cancel:       hpc-submit --cancel {job_id}")
    print("-" * 40)
