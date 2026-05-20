# ModelSpecAgent Report

## State Contract

- Required input state: `FORMAT_LOCKED`
- Observed input state: `FORMAT_LOCKED`
- Transition performed: `FORMAT_LOCKED -> MODEL_CORE_READY`

## Implementation

Implemented the core two-stage stochastic ConVRP extensive-form model in `src/alv/model.py`.

Variable blocks:

- `y[i,k]` binary
- `s[k]` binary
- `lambda[i]` continuous nonnegative
- `z[i,k,omega]` binary
- `x[i,j,k,omega]` on undirected edges `i<j`
  - depot edges `x[0,j,k,omega]` are integer with upper bound 2
  - customer-customer edges are binary

Constraints implemented:

- Consistency: `sum_k y[i,k] <= D + lambda[i]`
- Visit at most once: `sum_k z[i,k,omega] <= 1`
- Degree: incident edge degree equals `2 z[i,k,omega]`
- Depot degree: depot incident degree is at most 2
- Linking: `z[i,k,omega] <= y[i,k]`
- Capacity
- Assignment activation
- Valid inequality: `sum_k y[i,k] >= 1`
- Symmetry on `s[k]`
- Reference-scenario depot-degree symmetry

Objective accounting implemented with:

- `total_cost`
- `travel_cost`
- `consistency_penalty`
- `skipping_cost`

The invariant is covered by tests:

`abs(total_cost - travel_cost - consistency_penalty - skipping_cost) <= 1e-5`

## SEC Status

Subtour elimination constraints are not implemented in this module. This is intentional: SEC lazy separation belongs to `BranchCutAgent`, per the workflow. The model builder supports `lazy_constraints=True` so BranchCutAgent can enable Gurobi lazy callbacks.

## Tests

RED phase:

```bash
PYTHONPATH=src python3 -m unittest tests.test_model_core -v
```

failed because `alv.model` did not exist.

GREEN verification:

```bash
bash -lc 'source scripts/activate_env.sh && PYTHONPATH=src python -m unittest tests.test_model_core -v'
```

The sandboxed run failed because WLS could not resolve `token.gurobi.com`. The same command with network approval passed:

- `test_builds_expected_variable_blocks`: ok
- `test_solves_tiny_instance_and_accounts_objective`: ok

## Changed Files

- `src/alv/model.py`
- `tests/test_model_core.py`
- `reports/subagents/04_model_spec.md`

