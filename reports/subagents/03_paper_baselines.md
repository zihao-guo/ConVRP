# PaperBaselineAgent Report

Required input state: `ENV_CHECK`

Observed input state: `ENV_CHECK` in `state/workflow_state.json`

Output transition: `ENV_CHECK -> FORMAT_LOCKED` is ready, but `state/workflow_state.json` was not modified per instruction.

Concurrency note: a final sanity check after writing this agent's outputs showed `state/workflow_state.json` at `DATA_AUDIT`, transitioned by `DataAuditAgent` at `2026-05-19T17:10:00+02:00`. PaperBaselineAgent did not modify the workflow state file.

## Extraction Method

I used the local paper PDF:

`/home/zeio99/Alv/paper/Alvarez et al. - 2024 - The consistent vehicle routing problem with stocha.pdf`

`pdftotext` was unavailable, so I extracted the embedded PDF text layer with Python `pypdf` into `/tmp/alvarez_paper_pypdf.txt`. I then manually transcribed the requested paper-reported tables into `configs/paper_baselines.json`.

Extracted structures:

- `table_1_method_comparison`
- `table_2_gap_by_omega_and_set`
- `table_3_saa_bc_solution_attributes`
- `appendix_b11_saa_bc`
- `appendix_b12_saa_bd`
- `metadata`

## OCR And Manual Uncertainty

No OCR was used. The PDF had an extractable text layer, and the requested tables were readable in the extracted text.

Manual transcription uncertainty is low for the requested tables. The table rows and numeric columns were preserved clearly enough to transcribe. The paper marks the selected SAA parameter configurations with an asterisk; those rows are recorded with `selected_for_main_experiments: true` in JSON and numeric values without the asterisk.

No missing requested entries were identified. The JSON metadata still documents the missing-value policy: unreadable or missing entries should be represented as `null` with notes rather than invented values.

## Paths Changed

- `configs/paper_baselines.json`
- `reports/subagents/03_paper_baselines.md`

## Workflow Notes

Only the allowed project files were written. Temporary extraction output was placed under `/tmp`. `state/workflow_state.json` was not modified by PaperBaselineAgent.
