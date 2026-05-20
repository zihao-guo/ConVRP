# ConVRP Reproduction

This repository contains a reproduction workflow for:

Alvarez, A., Cordeau, J.-F., and Jans, R. (2024). *The consistent vehicle routing problem with stochastic customers and demands*. Transportation Research Part B: Methodological, 186, 102968.

The intended solver difference is explicit:

- Paper: CPLEX 22.1
- This reproduction: Gurobi from `$CONDA_ROOT/envs/p3-cvrpsd`

The project is guarded against claiming a full reproduction before all required runs are complete. A final report may claim full reproduction only when all 138 instances and all four methods (`BC`, `BD`, `SAA-BC`, `SAA-BD`) have completed, all paper-alignment tables have been regenerated, and the final guard passes.

## Required Local Paths

The scripts expect the same local paths used during development:

```bash
CONDA_ROOT=/path/to/miniconda3
CONDA_ENV=$CONDA_ROOT/envs/p3-cvrpsd
DATA_ROOT=/mnt/e/currentWORK/AAA_Project/P3/data
ROOT=/home/zeio99/Alv
```

`scripts/activate_env.sh` auto-detects conda from `CONDA_ROOT`, the current `CONDA_EXE`, `$HOME/miniconda3`, `$HOME/anaconda3`, or `/opt/conda`.

The canonical optimization inputs are the 138 processed JSON instances under:

```text
/mnt/e/currentWORK/AAA_Project/P3/data/processed/omega100
/mnt/e/currentWORK/AAA_Project/P3/data/processed/omega500
```

Do not use legacy `processed/instances/**` files as optimization inputs.

## Environment

Python dependencies and the from-scratch conda bootstrap are documented in `requirements.txt`.

Create the required environment, install dependencies, and activate it:

```bash
source scripts/activate_env.sh
```

Check Gurobi and the license:

```bash
PYTHONPATH=src:. python3 scripts/check_environment.py
```

The reproduction uses `Threads=1` and `MIPGap=1e-5` to match the paper's single-thread protocol as closely as possible.

## Data Audit

Validate the locked data format and regenerate data summaries:

```bash
PYTHONPATH=src:. python3 scripts/audit_data.py
```

The parser rules are documented in `DATA_FORMAT.md`.

## Tests

Run the lighter non-solver checks:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. python -m unittest \
  tests.test_table_alignment \
  tests.test_result_completeness \
  tests.test_final_report_guard \
  tests.test_experiment_protocol \
  tests.test_full_experiment_queue -v
```

Run the model and solver-focused tests when Gurobi is available:

```bash
source scripts/activate_env.sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. python -m unittest \
  tests.test_data_loader \
  tests.test_model_core \
  tests.test_branch_cut \
  tests.test_benders \
  tests.test_saa -v
```

## Single Run

Run one method-instance pair:

```bash
source scripts/activate_env.sh
PYTHONPATH=src:. python scripts/run_single.py \
  --run-id demo_bc \
  --instance-json /mnt/e/currentWORK/AAA_Project/P3/data/processed/omega100/A/convrp_10_test_1__omega100__alpha20.json \
  --method BC \
  --raw-result-path results/raw/BC/demo_bc.json \
  --time-limit 36000 \
  --seed 0
```

Supported methods:

```text
BC
BD
SAA-BC
SAA-BD
```

## Full Experiment

Check the full job count before submitting:

```bash
source scripts/activate_env.sh
PYTHONPATH=src:. python scripts/submit_full.py --dry-run
```

Expected output includes:

```json
{"jobs": 552, "dry_run": true}
```

Submit the full asynchronous queue:

```bash
source scripts/activate_env.sh
PYTHONPATH=src:. python scripts/submit_full_queue.py --submit --concurrency 1 --seed 0 --poll-interval 30
```

Monitor progress:

```bash
source scripts/activate_env.sh
PYTHONPATH=src:. python scripts/poll_runs.py
```

The paper time protocol is:

- Standalone `BC` and `BD`: full Omega, 10 hours per instance.
- `SAA-BC`: `M=20`, `|N|=5`, 30 minutes per sample problem.
- `SAA-BD`: `M=20`, `|N|=15`, 30 minutes per sample problem.
- SAA full-Omega evaluation time is additional, as in the paper.

## Tables

Readable PDF baseline tables are generated under `results/tables/`, especially:

```text
results/tables/PAPER_TABLES.md
results/tables/paper_table_1_method_comparison.csv
results/tables/paper_table_2_gap_by_omega_and_set.csv
results/tables/paper_table_3_saa_bc_solution_attributes.csv
results/tables/paper_appendix_b11_saa_bc.csv
results/tables/paper_appendix_b12_saa_bd.csv
```

After the full experiment completes, regenerate alignment tables:

```bash
source scripts/activate_env.sh
PYTHONPATH=src:. python scripts/generate_alignment_tables.py
```

The alignment generator intentionally leaves reproduction values blank with `status=not_run` until all 552 paper-equivalent raw results exist.

## Final Guard

Check whether a final report is allowed to claim full reproduction:

```bash
source scripts/activate_env.sh
PYTHONPATH=src:. python scripts/check_result_completeness.py
PYTHONPATH=src:. python scripts/final_report_guard.py
```

The final guard must output:

```json
{"can_claim_full_reproduction": true}
```

If it does not, `REPRODUCTION_REPORT.md` must not claim full reproduction. Current blockers and deviations are tracked in `diff.txt` and `state/bug_queue.jsonl`.
