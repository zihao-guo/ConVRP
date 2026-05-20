# BranchCutAgent Report

## Input State

- Read `state/workflow_state.json`.
- Confirmed required input state: `MODEL_CORE_READY`.
- Did not modify `state/workflow_state.json`.

## Scope

- Added `src/alv/branch_cut.py`.
- Added `tests/test_branch_cut.py`.
- Reused `src/alv/data.py` and `src/alv/model.py`.

## Implementation

- Implemented `solve_branch_and_cut(instance, ...)` as a Gurobi wrapper around `build_extensive_form(..., lazy_constraints=True)`.
- The wrapper leaves the core model construction in `src/alv/model.py` and optimizes with `branch_and_cut_callback`.
- The callback acts at `GRB.Callback.MIPNODE` for root-node fractional SEC separation and at `GRB.Callback.MIPSOL` for integer incumbent SEC separation, matching the paper's root-node and integer-solution separation protocol.
- At `MIPSOL`, the callback reads incumbent values with `model.cbGetSolution(built.x)` and `model.cbGetSolution(built.z)`.
- At `MIPSOL`, the callback adds violated integer subtour elimination constraints with `model.cbLazy(lhs <= rhs)`.
- At root `MIPNODE`, the callback reads the relaxation with `model.cbGetNodeRel(...)` and adds violated fractional SECs with `model.cbCut(...)`.
- For the paper's Base BC primal heuristic, the callback fixes the current first-stage `y`, solves the paper scenario subproblems (PDF formulas (21)-(30)) as independent Gurobi models, and submits the resulting full candidate solution through `cbSetSolution`. It never calls `optimize()` on the active callback model.

## SEC Separation

Implemented root-node fractional SEC separation and integer incumbent SEC separation.

For each vehicle and scenario, the separator:

1. Reads visited customers from integer incumbent `z`.
2. Builds the support graph from incumbent `x` values.
3. Finds connected components not containing the depot.
4. Adds one lazy SEC per customer-only component:

`sum_{i,j in S} x[i,j,k,w] <= sum_{i in S} z[i,k,w] - 1`

For the root-node fractional relaxation, the callback acts at `GRB.Callback.MIPNODE` when the node count is zero and the node relaxation is optimal. It retrieves fractional values with `cbGetNodeRel`, solves exact undirected minimum `s-t` cut problems using an internal Edmonds-Karp max-flow routine, and adds user cuts with `cbCut`. Edmonds-Karp is used only as the exact min-cut implementation in place of Concorde; it does not change the mathematical SEC family.

## Tests

- Wrote the isolated callback/SEC test before implementation.
- Initial RED result: `ModuleNotFoundError: No module named 'alv.branch_cut'`.
- Verified with required conda environment and WLS network access:

`bash -lc 'source scripts/activate_env.sh && PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python -m unittest tests.test_branch_cut tests.test_model_core -v'`

Result: 4 tests passed.

## PDF Alignment Status Update

The paper's Section 3.2.1 separates SECs with exact minimum `s-t` cuts at the root node and every time an integer solution is found, using Concorde. Current code implements exact root-node min-cut separation with an internal Edmonds-Karp max-flow routine and integer incumbent lazy SEC separation via the Gurobi `MIPSOL` callback. The solver library differs, but the separated SECs are mathematically the same cut family.

The paper's Base BC also includes a primal heuristic: at every integer solution, fix the current first-stage `y`, solve all scenario subproblems, and inject the resulting feasible original-problem solution if it improves the incumbent. Current `src/alv/branch_cut.py` implements this heuristic and submits the constructed candidate with `cbSetSolution`.

The fixed-y scenario subproblems used by this heuristic now call `src/alv/subproblem.py`, which implements only PDF recourse formulas (21)-(30). This avoids inheriting full-model first-stage valid inequalities or vehicle-order SBCs that are not part of the paper's scenario subproblem.

`BUG-METHOD-BC-SEC` and `BUG-METHOD-BC-PRIMAL-HEURISTIC` are fixed; `state/workflow_state.json` marks `method_status.BC=paper_equivalent`.

No extra valid inequalities, routing constraints, or heuristic constraints beyond the paper-described BC method are added to the optimization model. The only implementation substitution is the exact min-cut routine used to separate the same SECs.
