# Experiment Verification Report

## State Contract

- Required input state: `SMOKE_READY`
- Observed input state: `SMOKE_READY`
- Output state: remains `SMOKE_READY`

No full experiment was submitted in this verification pass.

## Dry-Run Completeness

Verified planned job counts:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 scripts/submit_full.py --dry-run
```

Result:

```json
{"backend": "tmux", "jobs": 552, "dry_run": true}
```

Single-method dry-runs:

- `--method BC`: 138 jobs
- `--method SAA-BC`: 138 jobs

This matches `138 instances * 4 methods = 552 method-instance runs`.

## CLI Smoke Runs

Created a temporary tiny instance under `/tmp` and ran:

```bash
source scripts/activate_env.sh && PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python scripts/run_single.py --run-id tiny_cli_bc --instance-json /tmp/alv_tiny_cli.json --method BC --raw-result-path /tmp/alv_tiny_cli_bc_result.json --time-limit 30
```

Result file:

- Status: `2`
- Objective: `3.0`
- Best bound: `3.0`
- Objective decomposition: travel `3.0`, consistency `0.0`, skipping `0.0`, total `3.0`
- Decomposition residual: `0.0`

Ran the same tiny CLI smoke for `BD`:

- Status: `2`
- Objective: `3.0`
- Best bound: `3.0`
- Method status at this early smoke pass: `BD-like`

That early smoke result predates the later exact branch-and-check implementation and is not used for final reproduction completeness. Current BD raw results are required to include the paper-equivalent run marker before `scripts/check_result_completeness.py` counts them.

These are smoke checks only and are not reported as paper reproduction results.

## Result Completeness Gate

Added:

- `scripts/check_result_completeness.py`
- `tests/test_result_completeness.py`

The completeness gate expects:

- 138 canonical instances
- 4 target methods: `BC`, `BD`, `SAA-BC`, `SAA-BD`
- 552 raw method-instance results

Current completeness result:

- `complete`: `false`
- `total_raw_results`: `0`
- each method missing 138 instances

This is intentional because the full experiment has not been submitted.

## 2026-05-19 Full Queue Update

After fixing BC/BD/SAA paper-equivalence blockers, the full queue was restarted from clean raw results. A later DebugAgent audit found two execution issues before final completion:

- Fixed-y scenario subproblems inherited full-model SBCs; raw results from before that correction were archived.
- Long Gurobi child processes launched directly by the Python queue worker could disappear without raw files in this environment.

The current queue implementation starts each running job in an independent tmux session when tmux is available. This keeps long Gurobi jobs alive even if the manager needs to be restarted. Stale `running` records whose pid/session is gone and whose raw file is missing are treated as `pending` for safe resume.

Current verified queue status after the tmux-child fix:

```json
{"total": 552, "done": 2, "running": 1, "pending": 549, "failed": 0, "timeout": 0}
```

The queue is intentionally running with concurrency `1` for local process stability. This does not alter the paper protocol for each optimization run: every model still uses `Threads=1`, `MIPGap=1e-5`, 10 hours for standalone BC/BD, and 30 minutes per SAA sample problem.

## Current PDF-Exactness Guard

No subset result or early smoke output is acceptable for final reporting. The final report remains blocked until:

- `results/processed/result_completeness.json` reports `complete=true`.
- `total_raw_results` is exactly `552`.
- All five alignment tables are regenerated from paper-equivalent raw results and contain no `not_run` or implementation-deviation status.
- `scripts/final_report_guard.py` exits with `can_claim_full_reproduction=true`.
