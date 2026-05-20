# PDF Alignment Audit

## State Contract

- Agent: ReproductionLeadAgent
- Required input state: any state at or after `MODEL_CORE_READY`
- Observed state at original audit time: `BLOCKED`
- Current state after follow-up fixes: `FULL_EXPERIMENT_RUNNING`
- Output transition: no transition from this report update

## Paper Source

- Local PDF: `paper/Alvarez et al. - 2024 - The consistent vehicle routing problem with stocha.pdf`
- Text extraction: local PDF text layer through `pypdf`; no OCR.
- Scope checked in this pass: formulation, BC, BD, SAA protocol, data generation, Tables 1-3, Appendix A/B descriptions.

## Confirmed Matches

- Solver protocol is documented as the intended difference: paper CPLEX 22.1, reproduction Gurobi 13.0.1, with `Threads=1` and `MIPGap=1e-5`.
- Data generation parameters match the paper and user contract: `|Omega| in {100, 500}`, `alpha in {0.2, 0.5, 0.8}`, equal scenario probabilities, `epsilon=0.5`, `D=1`, vehicle count formula, and penalty formulas.
- SAA main configurations match the paper: SAA-BC uses `M=20, |N|=5`; SAA-BD uses `M=20, |N|=15`; sample time limit is 30 minutes; standalone BC/BD time limit is 10 hours.
- The model was corrected to define second-stage variables and costs on each scenario's `C_omega` and `E_omega` only.

## Blocking Deviations From Original Audit

- This section records the state observed during the original PDF audit. Those method-level deviations were subsequently fixed and are not the current method status.

## Current PDF Alignment Status

- BC SEC separation is currently implemented as paper-equivalent: root-node fractional SEC separation and integer incumbent SEC separation are both active. The code uses an internal exact Edmonds-Karp min-cut routine instead of Concorde to separate the same minimum `s-t` cut SEC family. This is an implementation of the same separation problem, not an added model constraint or new algorithmic variant.
- BC Base primal heuristic is currently implemented: at every integer incumbent, the current first-stage `y` is fixed, every scenario subproblem is solved using the PDF recourse formulation (21)-(30), and the resulting candidate is submitted to Gurobi with `cbSetSolution`.
- BD is currently implemented as paper-equivalent branch-and-check: the master is optimized once, and each feasible incumbent `(y*, theta*)` triggers all scenario subproblems inside the master branch-and-bound callback; violated integer optimality cuts are added with `cbLazy`.
- Fixed-y scenario subproblems are currently implemented directly from PDF formulas (21)-(30). They do not inherit full-model assignment activation, valid assignment inequalities, first-stage consistency, or vehicle-order SBCs.
- SAA statistics are implemented and serialized in raw results. Appendix B alignment still cannot be completed until the full 552 corrected raw results exist.
- Full experiments are running but incomplete. Therefore no table-by-table full reproduction claim is valid yet.

## Tickets

- Fixed method blockers: `BUG-METHOD-BC-SEC`, `BUG-METHOD-BD-EXACT`, `BUG-METHOD-BC-PRIMAL-HEURISTIC`, `BUG-SAA-STATS`, and `BUG-METHOD-FIXED-Y-SUBPROBLEM-SBC`.
- Remaining blocker: `BUG-FULL-EXPERIMENT-NOT-RUN`, because the full 552-job experiment has not completed.

## Notes

The paper text contains a data-description ambiguity on page 14: it first states that Set A contains 10 instances, then says that 12 Set A instances were considered, while the same paragraph says the generated instances come from 23 deterministic instances. The project follows the user contract and the 138-instance table arithmetic: A/B/D = 10 + 7 + 6 = 23.
