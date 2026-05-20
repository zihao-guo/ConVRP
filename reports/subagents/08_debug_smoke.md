# DebugAgent Smoke Report

## State Contract

- Required input state: any state after `MODEL_CORE_READY`
- Observed input state: `SAA_READY`
- Transition performed: `SAA_READY -> SMOKE_READY`

## Bug Queue

Checked `state/bug_queue.jsonl`.

- Total tickets: 1
- Open or in-progress tickets: 0
- Fixed tickets: `BUG-ENV-GUROBI`

## Smoke Checks

Data audit:

```bash
PYTHONPATH=src python3 scripts/audit_data.py
```

Result:

```json
{"valid": true, "total_instances": 138}
```

Integrated unit/smoke suite:

```bash
source scripts/activate_env.sh && PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python -m unittest tests.test_data_loader tests.test_model_core tests.test_branch_cut tests.test_benders tests.test_saa -v
```

Result: 13 tests passed.

## Residual Risks

- This historical smoke section is superseded by the 2026-05-19 PDF-equivalence checks below.

## 2026-05-19 PDF-Equivalence Debug Update

DebugAgent found and reproduced `BUG-METHOD-FIXED-Y-SUBPROBLEM-SBC`: fixed-y scenario subproblems reused the full extensive form and inherited the full-model reference-scenario vehicle-order SBC, which is not present in PDF Section 3.2.2 formulas (21)-(30). The RED test returned objective `6.0` where the paper subproblem objective is `2.0`.

Fix verified:

```bash
source scripts/activate_env.sh && PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. python -m unittest tests.test_benders.BendersTests.test_scenario_subproblem_does_not_apply_full_model_vehicle_order_sbc tests.test_benders tests.test_branch_cut tests.test_saa -v
```

Result: 18 tests passed.

Full regression:

```bash
source scripts/activate_env.sh && PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. python -m unittest tests.test_data_loader tests.test_model_core tests.test_branch_cut tests.test_benders tests.test_saa tests.test_result_completeness tests.test_final_report_guard tests.test_table_alignment tests.test_experiment_protocol tests.test_full_experiment_queue -v
```

Result: 34 tests passed.

Pre-fix raw results and the registry were archived to `results/archive_pdf_exact_subproblem_fix/20260519_190000/`. The workflow is back at `SMOKE_READY`; full experiments must be restarted from clean raw results.
