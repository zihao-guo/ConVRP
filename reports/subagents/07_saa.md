# SAAAgent Report

## State Contract

- Required input states: `BC_READY` and `BD_READY`
- Observed state support: `state/workflow_state.json` has `completed_states` containing both `BC_READY` and `BD_READY`
- Transition performed: `BD_READY -> SAA_READY`

## Implementation

Implemented `src/alv/saa.py` with the paper protocol defaults:

- SAA-BC: `M=20`, `|N|=5`, sample time limit `30 minutes`
- SAA-BD: `M=20`, `|N|=15`, sample time limit `30 minutes`

Implemented functions for:

- deterministic sample membership generation
- identical sample memberships for equal sample size and seed
- sample-instance construction with reweighted scenario probabilities
- first-stage `y` evaluation on full Omega
- SAA run loop for `SAA-BC` and `SAA-BD`

The run loop stores sample memberships and evaluates each candidate first-stage solution on the full scenario set. It does not start full experiments; ExperimentAgent must submit long-running jobs asynchronously.

## Solver Method Notes

- `SAA-BC` uses `solve_branch_and_cut`.
- `SAA-BD` uses the corrected paper-equivalent BD branch-and-check method.
- Full-Omega first-stage evaluation uses the Benders scenario evaluator, which now solves fixed-y single-scenario routing subproblems with the lazy SEC callback enabled.

## PDF Alignment Deviation

Section 3.1 of the paper requires the SAA statistical lower-bound estimate, variance of that estimate, incumbent full-Omega variance, SAA gap, and SAA gap variance. Appendix B also reports `Opt gap (%)` and `Sample gap (%)` for each SAA configuration.

The current implementation now computes the paper SAA lower-bound estimate, lower-bound variance, incumbent full-Omega variance, SAA gap, SAA gap variance, `Opt gap (%)`, and average `Sample gap (%)` in `compute_saa_statistics`. `scripts/run_single.py` writes those statistics into raw SAA result JSON.

Raw SAA results now also serialize the best full-Omega evaluation decomposition and solution attributes required by Table 3: travel cost, consistency penalty, skipping cost, skipped-customer percentage, number of clusters, and violation level.

`BUG-SAA-STATS` is fixed and `state/workflow_state.json` marks `method_status.SAA=paper_equivalent`. Full reproduction still depends on the corrected 552-job experiment queue finishing and TableAlignmentAgent regenerating all alignment tables from the completed raw results.

## Tests

RED phase:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m unittest tests.test_saa -v
```

failed because `alv.saa` did not exist.

GREEN verification:

```bash
source scripts/activate_env.sh && PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python -m unittest tests.test_benders tests.test_saa -v
```

passed: 7 tests.

## Changed Files

- `src/alv/saa.py`
- `tests/test_saa.py`
- `reports/subagents/07_saa.md`
