# ExperimentAgent Script Report

## State Contract

- Required input state: `SMOKE_READY`
- Observed input state: `SMOKE_READY`
- Output state: no full-experiment transition performed in this session

The full experiment was not submitted automatically. The scripts required for asynchronous submission and management are now present.

## Scripts Created

- `scripts/submit_full.sh`
- `scripts/submit_full.py`
- `scripts/poll_runs.py`
- `scripts/kill_run.py`
- `scripts/resume_missing.py`
- `scripts/run_single.py`

## Execution Modes

`scripts/submit_full.py` supports:

1. Slurm when `sbatch` is available.
2. tmux when `tmux` is available.
3. nohup-style background processes as fallback.

The dry-run check selected `tmux` on this machine.

## Run Registry

Registry path:

`state/run_registry.jsonl`

Each submitted run records:

- `run_id`
- `instance_id`
- `instance_path`
- `method`
- `config_hash`
- `status`
- `submit_time`
- `start_time`
- `end_time`
- `raw_result_path`
- `log_path`
- `pid` or `slurm_job_id`
- `command`

## Verification

Dry-run submission:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 scripts/submit_full.py --dry-run --limit 2
```

Result:

```json
{"backend": "tmux", "jobs": 2, "dry_run": true}
```

Polling with empty registry:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/poll_runs.py
```

Result:

```json
{
  "done": 0,
  "failed": 0,
  "missing_raw_result_files": [],
  "pending": 0,
  "running": 0,
  "timeout": 0,
  "total": 0
}
```

## Submission Command

To submit the full experiment asynchronously:

```bash
scripts/submit_full.sh
```

Useful safer checks:

```bash
scripts/submit_full.sh --dry-run
scripts/submit_full.sh --dry-run --method BC --limit 2
```

