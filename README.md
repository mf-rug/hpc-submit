# hpc-submit

A small command-line tool for submitting SLURM jobs to a remote HPC cluster. It handles file transfer, remote directory setup, and job submission in a single command — no need to manually `scp`, `ssh`, and `sbatch` separately.

## How it works

1. Reads the job name from your script's `#SBATCH --job-name=` directive
2. Creates a dedicated directory on the remote cluster
3. Transfers the **entire directory** containing the job script via `rsync`
   (excluding any existing `output/` to avoid re-uploading large result files)
4. Transfers any `--files` extras additively
5. Runs `sbatch` on the remote and prints the job ID

## Requirements

- Python 3.10+
- SSH access to the cluster (key-based or 2FA with ControlMaster — see below)
- `rsync` installed locally

## Installation

```bash
pip install -e .
```

This makes the `hpc-submit` command available in your shell.

## First-time setup

Run `hpc-submit --init` (or it runs automatically on first use):

```
hpc-submit: configuration setup
========================================

SSH target — this is what gets passed to ssh and rsync.
  You can use:
    - An SSH config alias, e.g.: hpc
    - A full user@host, e.g.: user@cluster.example.com

SSH target [hpc]:
Remote base path for job directories [~/jobs]:
```

The setup wizard **tests the SSH connection** and provides specific diagnostics
if it fails. An SSH config alias is recommended because it carries IdentityFile,
ControlMaster, ProxyJump, and other settings.

The config is saved to `~/.config/hpc-submit/config.yaml` and can be re-run
anytime with `--init`.

## SSH setup for 2FA clusters

If your cluster requires two-factor authentication (keyboard-interactive),
batch SSH calls will fail because they cannot prompt for a code.

The fix is **SSH ControlMaster multiplexing**. Add this to `~/.ssh/config`:

```
Host hpc
    HostName login.cluster.example.com
    User your-username
    IdentityFile ~/.ssh/your-key
    ControlMaster auto
    ControlPath ~/.ssh/sockets/%r@%h-%p
    ControlPersist 4h
```

Then:
```bash
mkdir -p ~/.ssh/sockets
ssh hpc   # log in once manually with your 2FA code
```

All subsequent ssh/rsync/hpc-submit calls will reuse the authenticated
connection for 4 hours. Use the alias `hpc` as your SSH target in
`hpc-submit --init`.

## Usage

### Submit a job

```bash
hpc-submit my_job.sh
```

Transfers the entire directory containing `my_job.sh` to the cluster and submits it.
The remote directory name is taken from `#SBATCH --job-name=` in the script.

### Submit with additional files

```bash
hpc-submit my_job.sh --files extra_data.csv
```

The job directory is always transferred in full. `--files` is additive — use it for
files that live outside the job directory.

### Override the job name

```bash
hpc-submit my_job.sh --jobname custom_name
```

Uses `custom_name` as the remote directory name instead of parsing it from the script.

### Check job status

```bash
hpc-submit --status 12345678
```

Queries `squeue` (running) or `sacct` (completed/failed) on the cluster and prints the result.

### Cancel a job

```bash
hpc-submit --cancel 12345678
```

Runs `scancel` on the remote cluster.

### Check SSH connectivity

```bash
hpc-submit --check
```

Tests the SSH connection and verifies the remote base path is accessible.
Provides specific diagnostics if anything fails — useful as a first debugging step.

### Overwrite an existing remote directory

```bash
hpc-submit my_job.sh --overwrite
```

Skips the overwrite/new-directory prompt. Useful for scripted re-runs.

### Re-run configuration

```bash
hpc-submit --init
```

## Directory conflict resolution

If the remote directory already exists, you are prompted to either overwrite it or
create a numbered variant (`_1`, `_2`, etc.). Use `--overwrite` to skip the prompt.

## Example

```
$ hpc-submit myjob/job.sh

Transferring contents of /path/to/myjob/ ...
Submitting job...

----------------------------------------
Job submitted successfully.
  Job ID:          12345678
  Remote directory: ~/jobs/myjob
  Host:            hpc

  To cancel:       hpc-submit --cancel 12345678
----------------------------------------
```
