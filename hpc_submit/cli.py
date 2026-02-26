import argparse
import sys
from pathlib import Path

from .config import ensure_config, interactive_setup, resolve_remote_host
from .submit import cancel_job, check_job_status, submit


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hpc-submit",
        description="Submit SLURM job scripts to a remote HPC cluster via SSH.",
    )
    parser.add_argument(
        "job_script",
        nargs="?",
        type=Path,
        help="Path to the .sh job script to submit.",
    )
    parser.add_argument(
        "--files",
        nargs="+",
        type=Path,
        default=[],
        metavar="PATH",
        help="Additional files or directories to transfer alongside the job script.",
    )
    parser.add_argument(
        "--jobname",
        type=str,
        default=None,
        help="Override the remote directory name. Defaults to #SBATCH --job-name from the script.",
    )
    parser.add_argument(
        "--cancel",
        type=int,
        metavar="JOB_ID",
        help="Cancel a running job by its SLURM job ID.",
    )
    parser.add_argument(
        "--status",
        type=int,
        metavar="JOB_ID",
        help="Check the status of a running or completed job.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite the remote directory if it already exists (no prompt).",
    )
    parser.add_argument(
        "--init",
        action="store_true",
        help="Run (or re-run) interactive configuration setup.",
    )
    return parser


def validate_args(args: argparse.Namespace) -> None:
    if not args.job_script.exists():
        print(f"Error: job script not found: {args.job_script}", file=sys.stderr)
        sys.exit(1)
    if args.job_script.suffix != ".sh":
        print(f"Error: job script must be a .sh file, got: {args.job_script}", file=sys.stderr)
        sys.exit(1)
    for f in args.files:
        if not f.exists():
            print(f"Error: file not found: {f}", file=sys.stderr)
            sys.exit(1)


def main() -> None:
    try:
        parser = build_parser()
        args = parser.parse_args()

        if args.cancel is not None:
            config = ensure_config()
            remote_host = resolve_remote_host(config)
            cancel_job(remote_host, args.cancel)
            sys.exit(0)

        if args.status is not None:
            config = ensure_config()
            remote_host = resolve_remote_host(config)
            check_job_status(remote_host, args.status)
            sys.exit(0)

        if args.init:
            interactive_setup()
            if args.job_script is None:
                print("Configuration saved. You can now run: hpc-submit <script.sh>")
                sys.exit(0)

        if args.job_script is None:
            parser.error("the following arguments are required: job_script")

        validate_args(args)

        config = ensure_config()
        remote_host = resolve_remote_host(config)

        submit(
            job_script=args.job_script,
            remote_host=remote_host,
            remote_base_path=config.remote_base_path,
            name=args.jobname,
            extra_files=args.files,
            overwrite=args.overwrite,
        )
    except KeyboardInterrupt:
        print("\nAborted.", file=sys.stderr)
        sys.exit(130)
