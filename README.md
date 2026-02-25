# hpc-submit

A small command-line tool for submitting SLURM jobs to a remote HPC cluster. It handles file transfer, remote directory setup, and job submission in a single command — no need to manually `scp`, `ssh`, and `sbatch` separately.

## How it works

1. Reads the job name from your script's `#SBATCH --job-name=` directive
2. Creates a dedicated directory on the remote cluster
3. Transfers the job script (and any extra files) via `rsync`
4. Runs `sbatch` on the remote and prints the job ID

## Requirements

- Python 3.10+
- SSH access to the cluster with key-based authentication
- `rsync` installed locally

## Installation

```bash
pip install -e .
```

This makes the `hpc-submit` command available in your shell.

## First-time setup

On first run, `hpc-submit` will interactively ask for your configuration:

```
hpc-submit: configuration setup
-----------------------------------
Environment variable holding user@host [HPC]:
Remote base path for job directories [~/jobs]:
```

- **Environment variable**: The name of the env var that holds your `user@host` login (e.g. `HPC`). You should have something like `export HPC=user@cluster.example.com` in your shell profile.
- **Remote base path**: Where job directories are created on the cluster.

The config is saved to `~/.config/hpc-submit/config.yaml` and can be re-run anytime with `--init`.

## Usage

### Submit a job

```bash
hpc-submit my_job.sh
```

The remote directory name is taken from `#SBATCH --job-name=` in the script. For a script containing `#SBATCH --job-name=protein_fold`, the files are placed in `~/jobs/protein_fold/` on the remote.

### Submit with additional files

```bash
hpc-submit my_job.sh --files input_data/ params.csv
```

All specified files and directories are transferred alongside the job script into the same remote directory.

### Override the job name

```bash
hpc-submit my_job.sh --jobname custom_name
```

Uses `custom_name` as the remote directory name instead of parsing it from the script.

### Cancel a job

```bash
hpc-submit --cancel 12345678
```

Runs `scancel` on the remote cluster. The exact command is printed after every successful submission for easy copy-pasting.

### Re-run configuration

```bash
hpc-submit --init
```

## Smart directory handling

**Output directory detection**: If your script has an `#SBATCH --output=` directive with a directory path (e.g. `--output=/scratch/logs/job_%j.out`), `hpc-submit` will ask whether to use that directory (`/scratch/logs/`) instead of the configured base path.

**Conflict resolution**: If the remote directory already exists, you're prompted to either overwrite it or create a numbered variant (`_1`, `_2`, etc.).

## Example

```
$ hpc-submit fold_protein.sh --files sequences.fasta

Creating remote directory: ~/jobs/protein_fold
Transferring files...
Submitting job...

----------------------------------------
Job submitted successfully.
  Job ID:          12345678
  Remote directory: ~/jobs/protein_fold
  Host:            user@cluster.example.com

  To cancel:       hpc-submit --cancel 12345678
----------------------------------------
```
