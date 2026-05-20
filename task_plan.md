# Alvarez ConVRP Reproduction Task Plan

Goal: reproduce Alvarez, Cordeau, Jans, "The Consistent Vehicle Routing Problem with Stochastic Customers and Demands" table-by-table using the provided data and Gurobi in `/home/zeio99/miniconda3/envs/p3-cvrpsd`, with only the solver difference from CPLEX 22.1 documented.

Current workflow state: BLOCKED

## Phases

- [x] Phase 0: Initialize persistent planning and state directories
- [x] Phase 1: DeploymentAgent environment and Gurobi license check
- [x] Phase 2: DataAuditAgent format locking and parser validation
- [x] Phase 3: PaperBaselineAgent baseline extraction into config
- [x] Phase 4: ModelSpecAgent core two-stage formulation implementation
- [x] Phase 5: BranchCutAgent callback SEC implementation and tests
- [x] Phase 6: BendersAgent branch-and-check implementation and tests: implemented as `BD-like`, not exact branch-and-check
- [x] Phase 7: SAAAgent sampling, evaluation, and reproducibility layer
- [x] Phase 8: DebugAgent smoke tests and bug verification
- [ ] Phase 9: ExperimentAgent async full experiment scripts: scripts ready, full experiment not submitted
- [x] Phase 9a: Experiment dry-run and completeness-gate verification
- [x] Phase 9b: PDF alignment audit pass: blockers documented, not resolved
- [ ] Phase 10: TableAlignmentAgent full table comparison
- [ ] Phase 11: ReproductionLeadAgent final report
- [ ] Phase 12: Clear final-report blockers before any full reproduction claim

## State Machine

Valid states are INIT, ENV_CHECK, DATA_AUDIT, FORMAT_LOCKED, MODEL_CORE_READY, CALLBACK_TESTED, BC_READY, BD_READY, SAA_READY, SMOKE_READY, FULL_EXPERIMENT_SUBMITTED, FULL_EXPERIMENT_RUNNING, FULL_EXPERIMENT_DONE, TABLES_DONE, FINAL_REPORT_DONE, BLOCKED.

## Errors Encountered

| Error | Attempt | Resolution |
| --- | --- | --- |
| `unzip` command not found | 1 | Use Python standard `zipfile` for ZIP inspection and sample extraction. |
| Gurobi cannot open `/mnt/d/P3/gurobi.lic` | 2 | User provided `/mnt/c/Users/User/Downloads/gurobi.lic`; updated activation wrapper; verified tiny MIP; `BUG-ENV-GUROBI` fixed. |
| `pytest` not installed in base Python | 1 | Used standard-library `unittest` for data loader tests. |
| Manifest `out` paths include leading `data/` prefix | 1 | Documented in `DATA_FORMAT.md`; validator normalizes prefix before comparison. |
| Gurobi model tests fail in sandbox due WLS DNS | 1 | Reran the same test command with network approval; tests passed. |
| BendersAgent initial implementation used `0.0` lower bounds and strengthened integer cuts | 1 | Tightened tests to prompt formulas; implemented scenario lower-bound cut and exact prompt integer optimality cut formula. |
| Final-report guard blocks full-reproduction claim | 1 | Created blocker tickets for exact BD, BC SEC equivalence, and missing full experiment results; workflow moved to `BLOCKED`. |
| PDF audit found missing Base BC primal heuristic | 1 | Added `BUG-METHOD-BC-PRIMAL-HEURISTIC`; recorded in `diff.txt`; full reproduction claim remains blocked. |
| PDF audit found incomplete SAA statistics | 1 | Added `BUG-SAA-STATS`; guard now requires `method_status.SAA == paper_equivalent`; full reproduction claim remains blocked. |
