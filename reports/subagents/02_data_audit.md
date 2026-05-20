# DataAuditAgent Report

## State Contract

- Required input state: `ENV_CHECK`
- Observed input state: `ENV_CHECK`
- Transition performed: `ENV_CHECK -> DATA_AUDIT -> FORMAT_LOCKED`

## Files Audited

- Data root: `/mnt/e/currentWORK/AAA_Project/P3/data`
- Full file inventory: `reports/data_samples/file_inventory.txt`
- Samples by file type: `reports/data_samples/`
- Canonical processed root: `/mnt/e/currentWORK/AAA_Project/P3/data/processed/omega100` and `/mnt/e/currentWORK/AAA_Project/P3/data/processed/omega500`

## Locked Format

Created `DATA_FORMAT.md` before implementing the parser. The locked optimization input is the canonical processed JSON format:

`processed/omega{100,500}/{A,B,D}/{instance}__omega{100,500}__alpha{20,50,80}.json`

Raw `.vrp` files are audited as provenance only. The optimizer must not infer stochastic fields from raw files.

## Parser And Validation

Implemented:

- `src/alv/data.py`
- `scripts/audit_data.py`
- `tests/test_data_loader.py`

Validation output:

- `results/processed/data_validation.json`
- `results/tables/data_summary.csv`

The validator checks filename conventions, set/omega/alpha agreement, manifest agreement after normalizing the observed `data/` prefix, scenario probabilities, distance values, penalty rules, and vehicle-count rules.

## Results

- Canonical stochastic JSON files: 138
- Base deterministic instances: 23
- Base instance counts: A=10, B=7, D=6
- Records by set: A=60, B=42, D=36
- Omega values: 100, 500
- Alpha values: 0.2, 0.5, 0.8
- Validation errors: 0

## Tests

Command:

```bash
PYTHONPATH=src python3 -m unittest tests.test_data_loader -v
```

Result: 2 tests passed.

Audit command:

```bash
PYTHONPATH=src python3 scripts/audit_data.py
```

Result: `{"valid": true, "total_instances": 138}`.

## Notes

The data directory also contains legacy/intermediate JSON under `processed/instances/**`. Those files use a different schema and are not optimization inputs. This is documented in `DATA_FORMAT.md`.

