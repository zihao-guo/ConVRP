# BendersAgent Report

## State Contract

- Required input state: `MODEL_CORE_READY`
- Observed input state: `MODEL_CORE_READY`
- State file modified: yes, after verification
- Method status: `paper_equivalent`

## Implementation

Implemented `src/alv/benders.py` with a decomposition driver around the existing data/model semantics:

- Master problem contains first-stage `y[i,k]`, `s[k]`, `lambda[i]`, and one continuous `theta[omega]` per scenario.
- Master includes first-stage consistency, assignment, activation, and vehicle symmetry constraints.
- Master starts with the prompt-specified lower-bound cuts `theta[omega] >= L_omega`, where `L_omega = sum_{i in C_omega} min{b_i, min incident edge cost in N_omega}`.
- Scenario subproblem is solved for every master candidate `y`, even when earlier scenarios already require cuts.
- Scenario subproblem uses fixed `y` values and solves the PDF Section 3.2.2 recourse problem (21)-(30) directly. It does not reuse the full extensive form and therefore does not include first-stage consistency, assignment activation, valid inequalities, or the full-model vehicle-order SBC.
- Integer optimality cuts use:

```text
theta_omega >= Q_omega(y_hat)
  - Q_omega(y_hat) * (
      sum_{(i,k): y_hat[i,k]=1} (1 - y[i,k])
      + sum_{(i,k): y_hat[i,k]=0} y[i,k]
    )
```

The helper `integer_cut_rhs_value` is included so the formula can be tested directly on binary points.

## Exactness Status

The current implementation is paper-style branch-and-check. The master is solved once with `LazyConstraints=1`; each feasible incumbent `(y, theta)` at `GRB.Callback.MIPSOL` triggers all scenario subproblems; violated integer optimality cuts are added with `cbLazy` inside the master branch-and-bound tree.

## PDF Subproblem Correction

DebugAgent found a blocker after comparing the fixed-y scenario subproblem against PDF formulas (21)-(30): the previous implementation built a one-scenario full extensive form and fixed `y`, which inherited the full-model reference-scenario vehicle-order SBC. That constraint is not part of the BD subproblem and can overestimate recourse for fixed assignments where a higher-index vehicle is the only eligible vehicle for a present customer.

The issue is recorded as `BUG-METHOD-FIXED-Y-SUBPROBLEM-SBC` and fixed in `src/alv/subproblem.py`. The new shared subproblem builder creates only:

- `z[i,k]` for present customers in the scenario.
- `x[i,j,k]` for scenario edges.
- Visit-once, degree, depot-degree, linking to fixed `y`, capacity, and dynamic SEC constraints.
- Travel plus skipping objective.

The same fixed-y subproblem is used by BD callback evaluation, SAA full-Omega evaluation, and the BC primal heuristic.

The older iterative outer-loop implementation remains available only as `solve_benders_iterative(...)` and is not used by `solve_benders_like(...)`, `run_single.py`, or SAA-BD.

## SBC/VI Interpretation

The PDF states after the BD lower-bound cut that the BD method also uses the BC method's SBCs and VIs. In the current implementation this is interpreted in the only way that preserves the PDF master/subproblem definitions:

- VI (18), `sum_k y_ik >= 1`, is included in the BD master.
- SBC (17), `s_k <= s_{k-1}`, is included in the BD master.
- SBC (16), the depot-degree vehicle ordering constraint on `x`, is not included in the BD master because the master has no `x` variables in PDF formulation (19)-(20).
- SBC (16) is also not included in fixed-y scenario subproblems because PDF formulas (21)-(30) do not contain it. Adding it after fixing `y` can change the true recourse value `theta_omega(y)`, since vehicle labels can no longer be permuted in the subproblem without changing the fixed assignment.

This was verified by the regression test `test_scenario_subproblem_does_not_apply_full_model_vehicle_order_sbc`, where adding the full-model vehicle-order SBC to a fixed-y scenario subproblem raises the recourse objective from the PDF value `2.0` to `6.0`.

## Tests

RED phase:

```bash
source scripts/activate_env.sh && PYTHONPATH=src python -m unittest tests.test_benders -v
```

failed because `alv.benders` did not exist.

GREEN verification:

```bash
source scripts/activate_env.sh && PYTHONPATH=src python -m unittest tests.test_benders -v
```

passed with Gurobi WLS access.

Regression verification after formula tightening:

```bash
source scripts/activate_env.sh && PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python -m unittest tests.test_data_loader tests.test_model_core tests.test_branch_cut tests.test_benders -v
```

passed:

- `tests.test_data_loader`: 2 tests
- `tests.test_model_core`: 2 tests
- `tests.test_branch_cut`: 2 tests
- `tests.test_benders`: 3 tests

Regression verification after the fixed-y subproblem correction:

```bash
source scripts/activate_env.sh && PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. python -m unittest tests.test_benders tests.test_branch_cut tests.test_saa -v
```

passed, including `test_scenario_subproblem_does_not_apply_full_model_vehicle_order_sbc`.

## Changed Files

- `src/alv/benders.py`
- `tests/test_benders.py`
- `reports/subagents/06_benders.md`
- `diff.txt`
