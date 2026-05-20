# Experiment Monitor Status

## State Contract

- Agent: ExperimentAgent / ReproductionLeadAgent
- Required input state for full experiment submission: `SMOKE_READY`
- Observed workflow state: `BLOCKED`
- Output transition: remains `BLOCKED`

## Current Registry Status

Full queue submission has been started after the user explicitly required a full experiment. The registry contains all 552 method-instance jobs.

Latest observed `scripts/poll_runs.py` report:

- total: 552
- pending: 0
- running: queue-managed, changes as jobs complete
- done: at least 6 at the first monitor checks
- failed: 0
- timeout: 0

`scripts/check_result_completeness.py` reports:

- expected instances: 138
- expected methods: `BC`, `BD`, `SAA-BC`, `SAA-BD`
- expected total method-instance raw results: 552
- current total raw results: increasing as the queue completes jobs
- complete: false

## Submission Decision

The full experiment is now submitted as a controlled queue, not as a subset and not as 552 simultaneous solver processes. The queue uses all 138 instances and all four target methods:

- `BC`
- `BD`
- `SAA-BC`
- `SAA-BD`

Command used:

```bash
source scripts/activate_env.sh
PYTHONPATH=src:. python scripts/submit_full_queue.py --submit --concurrency 2 --poll-interval 30
```

The full experiment is still methodologically blocked for any final "complete reproduction" claim by non-solver paper-alignment issues:

- `BUG-METHOD-BC-SEC`
- `BUG-METHOD-BC-PRIMAL-HEURISTIC`
- `BUG-METHOD-BD-EXACT`
- `BUG-SAA-STATS`

The results being generated must therefore be treated as full-run results for the current implementation until these method blockers are fixed or explicitly marked in table alignment.

## Monitoring Commands

The live monitor has been started in `tmux:alv_full_experiment_monitor`. It records snapshots every 300 seconds to:

- `results/metadata/full_experiment_monitor.jsonl`
- `results/logs/full_experiment_monitor.log`

Manual monitor command:

```bash
source scripts/activate_env.sh
PYTHONPATH=src:. python scripts/poll_runs.py --watch --interval 300
```

Check completeness with:

```bash
PYTHONPATH=src:. python scripts/check_result_completeness.py
```

The final report guard must remain nonzero until all 552 raw results exist, all alignment statuses are acceptable, and BC/BD/SAA method statuses are paper-equivalent.
