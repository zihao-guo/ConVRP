# Locked Data Format

This file locks the input format for the Alvarez ConVRP reproduction. The optimizer must read the canonical processed JSON instances under `/mnt/e/currentWORK/AAA_Project/P3/data/processed/omega100` and `/mnt/e/currentWORK/AAA_Project/P3/data/processed/omega500`. Raw `.vrp` files are audited as provenance only; optimization code must not infer missing stochastic fields from raw files.

## Data Roots

- Data root: `/mnt/e/currentWORK/AAA_Project/P3/data`
- Canonical processed root: `/mnt/e/currentWORK/AAA_Project/P3/data/processed`
- Canonical stochastic files: `processed/omega{omega}/{set}/{instance}__omega{omega}__alpha{alpha_pct}.json`
- Manifest: `processed/manifest.csv`
- Generated legacy/intermediate JSON under `processed/instances/**` is not an optimization input. It is retained in the data directory but has a different schema.

## Expected Canonical Counts

- Base deterministic instances: 23 total.
- Base sets:
  - Set A: 10 instances named `convrp_10_test_1` through `convrp_10_test_5` and `convrp_12_test_1` through `convrp_12_test_5`.
  - Set B: 7 instances named `Christofides_{1,2,3,6,7,8,12}_5_0.7`.
  - Set D: 6 instances named `D_christofides_{6,7,8}_n{20,30}`.
- Stochastic instances: `23 * 2 * 3 = 138`.
- Omega values: `100`, `500`.
- Alpha values: `0.2`, `0.5`, `0.8`.

## Manifest Format

`processed/manifest.csv` has a header row:

```csv
set,instance,customers,omega,alpha,seed,out
```

Each row points to one canonical stochastic JSON file. The observed `out` path uses POSIX separators and includes a leading `data/` prefix, for example `data/processed/omega100/A/convrp_10_test_1__omega100__alpha20.json`. The parser normalizes this leading `data/` prefix before comparing it with files under the configured data root.

## Canonical JSON Filename Convention

The filename must match:

```text
{instance}__omega{omega}__alpha{alpha_pct}.json
```

where:

- `omega` is `100` or `500`.
- `alpha_pct` is `20`, `50`, or `80`.
- `alpha = alpha_pct / 100`.
- The parent directory must be `omega{omega}/{A|B|D}` and must agree with JSON fields and metadata.

## Canonical JSON Top-Level Fields

Each canonical JSON file must have exactly these top-level fields:

- `set`: string, one of `A`, `B`, `D`.
- `name`: base deterministic instance id.
- `capacity`: positive integer vehicle capacity `Q`.
- `depot`: integer depot id, always `0`.
- `customers`: ordered list of positive integer customer ids.
- `D`: integer consistency parameter, expected `1`.
- `vehicles`: ordered list of integer vehicle ids, expected `0..|K|-1`.
- `penalties_skip`: object keyed by customer id as a string; value is `b_i`.
- `penalties_consistency`: object keyed by customer id as a string; value is `o_i`.
- `coordinates`: list indexed by node id; each entry is `[x, y]`.
- `scenarios`: list of scenario objects.
- `distances`: object keyed by `"i,j"` with `i < j`; value is rounded Euclidean distance.
- `metadata`: object with generation rules and provenance.

## Coordinates and Distances

- Node ids are integers.
- Depot id is `0`.
- `coordinates[0]` is the depot coordinate.
- For every customer id `i`, `coordinates[i]` must exist and contain two numeric values.
- Distances are rounded Euclidean values:

```text
c_ij = int(sqrt((x_i-x_j)^2 + (y_i-y_j)^2) + 0.5)
```

- `distances` must include every undirected pair `i,j` with `i < j` over `{0} union customers`.

## Scenario Blocks

Each scenario object has:

- `id`: integer in `0..omega-1`.
- `probability`: numeric value equal to `1 / omega`.
- `demands`: object keyed by present customer id as a string; value is positive integer demand.

A customer is present in a scenario if and only if its id is present in the scenario `demands` object. Missing customers have zero demand and are not in `C_omega`.

## Alpha, Omega, and Base Set Extraction

- `omega` is extracted from `metadata.omega`, filename `__omega{omega}__`, and parent directory `omega{omega}`. All three must agree.
- `alpha` is extracted from `metadata.alpha` and filename `__alpha{alpha_pct}`. They must agree using `alpha_pct in {20,50,80}`.
- Base set is extracted from JSON field `set`, the parent set directory, and the manifest row. They must agree.
- Base instance id is extracted from JSON field `name`, manifest row `instance`, and the filename prefix before `__omega`. They must agree.

## Paper Rule Fields

The processed JSON must satisfy these rules:

- Equal scenario probability: `rho_omega = 1 / |Omega|`.
- `epsilon = 0.5` in `metadata.epsilon`.
- `D = 1`.
- Set A nominal demand rule: `dbar_i = 2`.
- Sets B and D nominal demand rule: `dbar_i = max positive demand in the deterministic instance`.
- Vehicle count rule:

```text
|K| = max{ ceil(2 * dmax_Omega / Q) - 1, D + 1 }
dmax_Omega = max_omega sum_{i in C_omega} d_iomega
```

- Penalties:

```text
b_i = 3 * (2 * c_0i)
o_i = 0.1 * (2 * c_0i)
```

The parser must verify the vehicle count and penalties from JSON content. It must not recompute stochastic scenarios.

## Raw `.vrp` Provenance Format

Raw deterministic files are TSPLIB-like text files with headers such as:

- `NAME`
- `TYPE`
- `DIMENSION`
- `NUM_DAYS`
- `CAPACITY`
- `EDGE_WEIGHT_TYPE`
- `NODE_COORD_SECTION`
- `DEMAND_SECTION`
- `SVC_TIME_SECTION`
- `DEPOT_SECTION`
- `EOF`

The depot coordinate appears in `DEPOT_SECTION`; customer coordinates appear in `NODE_COORD_SECTION`; multi-day deterministic demands appear in `DEMAND_SECTION`, with `-1` indicating absence. These raw files are provenance for the processed JSON and are not consumed by the optimizer.
