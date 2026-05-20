# Alvarez ConVRP Reproduction Findings

## Initial Repository

- Root: `/home/zeio99/Alv`
- Existing repository content at start: paper PDF only, plus generated directories created for this workflow.
- Git repository status: `/home/zeio99/Alv` is not a git repository.
- Paper PDF exists at `paper/Alvarez et al. - 2024 - The consistent vehicle routing problem with stocha.pdf`.

## Data

- Primary data path exists: `/mnt/e/currentWORK/AAA_Project/P3/data`.
- Visible files include `processed/manifest.csv`, summary JSON files, and raw ZIP archives:
  - `/mnt/e/currentWORK/AAA_Project/P3/data/raw/ConVRP_0.7.zip`
  - `/mnt/e/currentWORK/AAA_Project/P3/data/raw/ConVRP_small.zip`
- The system does not have the `unzip` command available; use Python `zipfile`.
- Processed data README states the canonical dataset is 138 JSON files under `processed/omega100` and `processed/omega500`.
- `processed/manifest.csv` columns are `set,instance,customers,omega,alpha,seed,out`.
- Raw A ZIP has 10 `.vrp` files plus readme; raw B ZIP has 12 `.vrp` files plus readme. The processed paper set uses 10 A, 7 B, and 6 D instances.
- Example processed JSON top-level fields observed: `set`, `name`, `capacity`, `depot`, `customers`, `D`, `vehicles`, `penalties_skip`, `penalties_consistency`, `coordinates`, `scenarios`, and likely metadata fields later in the file.
- Full canonical JSON schema fields are `D`, `capacity`, `coordinates`, `customers`, `depot`, `distances`, `metadata`, `name`, `penalties_consistency`, `penalties_skip`, `scenarios`, `set`, `vehicles`.
- Canonical data validation passed with 138 stochastic instances, base counts A=10/B=7/D=6, records A=60/B=42/D=36, omega values `[100,500]`, alpha values `[0.2,0.5,0.8]`, and zero validation errors.
- Manifest `out` paths include a leading `data/` prefix, while files are found under the configured data root after removing that prefix.
- `processed/instances/**` contains legacy/intermediate JSON with a different schema; `DATA_FORMAT.md` locks optimization input to `processed/omega{100,500}/{A,B,D}/*.json`.

## Paper Baselines

- PaperBaselineAgent created `configs/paper_baselines.json` and `reports/subagents/03_paper_baselines.md`.
- Baselines were extracted from the local paper PDF text layer by a subagent and are for alignment only, not optimization.

## Model Core

- `src/alv/model.py` implements the core extensive-form model without SEC separation.
- PDF alignment found that second-stage `z`/`x` variables and recourse costs must be defined on each scenario's `C_omega`/`E_omega`; the model has been corrected and covered by `test_second_stage_variables_exist_only_for_present_customers_and_edges`.
- SEC separation remains assigned to BranchCutAgent.
- Model-core tests require the conda environment and network access for the WLS license.

## Branch-Cut And Benders

- `src/alv/branch_cut.py` implements root-node fractional SEC separation with an internal exact max-flow/min-cut routine plus Gurobi lazy integer incumbent SEC separation at `MIPSOL`.
- PDF Section 3.2.1 uses Concorde for minimum `s-t` cuts; the current internal max-flow implementation is an exact min-cut replacement and is documented as paper-equivalent at the mathematical separation level.
- PDF Section 3.2.1 and Appendix A require the Base BC primal heuristic; current BC implements it at integer incumbents by fixing first-stage `y`, solving all scenario subproblems, and injecting a candidate solution with `cbSetSolution`.
- `src/alv/benders.py` is now paper-style branch-and-check: the master is solved once and Benders integer optimality cuts are separated inside the Gurobi incumbent callback.
- Benders lower-bound cuts now use the prompt-specified per-scenario formula.
- Benders integer optimality cuts now use the prompt-specified no-good optimality formula.
- Fixed-y scenario evaluations now use lazy SEC separation.

## SAA

- `src/alv/saa.py` implements paper protocol defaults for SAA-BC and SAA-BD without launching long-running experiments.
- SAA-BD now inherits the corrected paper-equivalent BD branch-and-check implementation.
- PDF Section 3.1 and Appendix B require SAA lower-bound, variance, opt-gap, and sample-gap statistics; `src/alv/saa.py` computes them and `scripts/run_single.py` serializes them.
- Table 3 requires full-Omega solution attributes; corrected SAA raw results now include full-Omega travel/consistency/skipping decomposition, skipped-customer percentage, cluster count, and violation level.

## Experiment Verification

- `scripts/submit_full.py --dry-run` plans 552 jobs for 138 instances and 4 methods.
- `scripts/check_result_completeness.py` enforces 552 raw method-instance results before table alignment can be treated as complete.
- A pre-fix queue and a pre-schema queue were archived and are excluded from final completeness.
- The corrected 552-job full experiment queue is running in tmux with concurrency 2. Current full experiment completeness remains false until all corrected raw results are present.
- Deeper PDF audit found one more model-level blocker before final experiment completion: fixed-y scenario subproblems must match PDF Section 3.2.2 formulas (21)-(30) and must not inherit full-model SBC (16).
- The old fixed-y subproblem path reused `build_extensive_form` on a one-scenario instance and fixed `y`, which could incorrectly force high-index vehicle routes to be no more active than lower-index routes in the scenario subproblem.
- The new shared `src/alv/subproblem.py` implements the PDF recourse problem directly and is now used by BD, SAA full-Omega evaluation, and the BC primal heuristic.
- Pre-fix raw results and registry were archived under `results/archive_pdf_exact_subproblem_fix/20260519_190000/`; final completeness must be based only on new paper-equivalent raw results.
- Background queue reliability finding: direct tmux sessions can keep long BD Gurobi jobs alive, but long Gurobi child processes launched under the Python queue worker with `subprocess.Popen` disappeared without raw files in this environment. The queue now uses one tmux session per running job and treats missing dead pids/sessions without raw as pending for restart.
- Guard input finding: `scripts/final_report_guard.py` reads `results/processed/result_completeness.json`; `scripts/check_result_completeness.py` now refreshes that JSON file by default so final readiness cannot rely on stale completeness data.

## Environment

- Primary conda env exists: `/home/zeio99/miniconda3/envs/p3-cvrpsd`.
- Conda profile script exists: `/home/zeio99/miniconda3/etc/profile.d/conda.sh`.
- `gurobipy` imports in the required environment and reports Gurobi `(13, 0, 1)`.
- The original tiny MIP solve failed because `GRB_LICENSE_FILE=/mnt/d/P3/gurobi.lic` could not be opened. A direct filesystem check on the license path returned `Input/output error`.
- User provided a WSL-readable WLS license at `/mnt/c/Users/User/Downloads/gurobi.lic`.
- `scripts/activate_env.sh` now exports that license path when present.
- `scripts/check_environment.py` verifies the deployment check. Latest verified result: tiny MIP `OPTIMAL`, objective `1.0`, `Threads=1`, `MIPGap=1e-5`, `LazyConstraints=1`.
