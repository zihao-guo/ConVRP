from __future__ import annotations

import csv
import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


CANONICAL_RE = re.compile(r"^(?P<name>.+)__omega(?P<omega>100|500)__alpha(?P<alpha>20|50|80)\.json$")
EXPECTED_BASE_COUNTS = {"A": 10, "B": 7, "D": 6}
EXPECTED_RECORDS_BY_SET = {"A": 60, "B": 42, "D": 36}
EXPECTED_OMEGAS = [100, 500]
EXPECTED_ALPHAS = [0.2, 0.5, 0.8]


@dataclass(frozen=True)
class Scenario:
    id: int
    probability: float
    demands: dict[int, int]


@dataclass(frozen=True)
class Instance:
    path: Path
    set_name: str
    name: str
    capacity: int
    depot: int
    customers: tuple[int, ...]
    D: int
    vehicles: tuple[int, ...]
    penalties_skip: dict[int, float]
    penalties_consistency: dict[int, float]
    coordinates: tuple[tuple[float, float], ...]
    scenarios: tuple[Scenario, ...]
    distances: dict[tuple[int, int], int]
    metadata: dict[str, Any]

    @property
    def omega(self) -> int:
        return int(self.metadata["omega"])

    @property
    def alpha(self) -> float:
        return float(self.metadata["alpha"])


def _int_keyed_float_map(raw: dict[str, Any]) -> dict[int, float]:
    return {int(k): float(v) for k, v in raw.items()}


def _int_keyed_int_map(raw: dict[str, Any]) -> dict[int, int]:
    return {int(k): int(v) for k, v in raw.items()}


def _parse_distance_key(key: str) -> tuple[int, int]:
    left, right = key.split(",", 1)
    i, j = int(left), int(right)
    if i >= j:
        raise ValueError(f"distance key must satisfy i<j, got {key}")
    return i, j


def load_instance(path: Path | str) -> Instance:
    path = Path(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    scenarios = tuple(
        Scenario(
            id=int(item["id"]),
            probability=float(item["probability"]),
            demands=_int_keyed_int_map(item["demands"]),
        )
        for item in payload["scenarios"]
    )
    return Instance(
        path=path,
        set_name=str(payload["set"]),
        name=str(payload["name"]),
        capacity=int(payload["capacity"]),
        depot=int(payload["depot"]),
        customers=tuple(int(i) for i in payload["customers"]),
        D=int(payload["D"]),
        vehicles=tuple(int(k) for k in payload["vehicles"]),
        penalties_skip=_int_keyed_float_map(payload["penalties_skip"]),
        penalties_consistency=_int_keyed_float_map(payload["penalties_consistency"]),
        coordinates=tuple((float(xy[0]), float(xy[1])) for xy in payload["coordinates"]),
        scenarios=scenarios,
        distances={_parse_distance_key(k): int(v) for k, v in payload["distances"].items()},
        metadata=dict(payload["metadata"]),
    )


def canonical_json_paths(data_root: Path | str) -> list[Path]:
    root = Path(data_root)
    return sorted((root / "processed").glob("omega*/*/*.json"))


def load_all_instances(data_root: Path | str) -> list[Instance]:
    return [load_instance(path) for path in canonical_json_paths(data_root)]


def rounded_euclidean(a: tuple[float, float], b: tuple[float, float]) -> int:
    return int(math.hypot(a[0] - b[0], a[1] - b[1]) + 0.5)


def validate_instance(instance: Instance, data_root: Path | str | None = None) -> list[str]:
    errors: list[str] = []
    rel = instance.path
    if data_root is not None:
        try:
            rel = instance.path.relative_to(Path(data_root))
        except ValueError:
            pass
    label = str(rel)

    match = CANONICAL_RE.match(instance.path.name)
    if not match:
        errors.append(f"{label}: filename does not match canonical convention")
        return errors

    file_name = match.group("name")
    file_omega = int(match.group("omega"))
    file_alpha = int(match.group("alpha")) / 100.0
    parent_omega = instance.path.parents[1].name
    parent_set = instance.path.parent.name

    if file_name != instance.name:
        errors.append(f"{label}: filename instance {file_name} != JSON name {instance.name}")
    if parent_set != instance.set_name:
        errors.append(f"{label}: parent set {parent_set} != JSON set {instance.set_name}")
    if parent_omega != f"omega{instance.omega}":
        errors.append(f"{label}: parent omega {parent_omega} != metadata omega {instance.omega}")
    if file_omega != instance.omega:
        errors.append(f"{label}: filename omega {file_omega} != metadata omega {instance.omega}")
    if abs(file_alpha - instance.alpha) > 1e-9:
        errors.append(f"{label}: filename alpha {file_alpha} != metadata alpha {instance.alpha}")
    if instance.set_name not in EXPECTED_BASE_COUNTS:
        errors.append(f"{label}: unexpected set {instance.set_name}")
    if instance.depot != 0:
        errors.append(f"{label}: depot must be 0")
    if instance.D != 1:
        errors.append(f"{label}: D must be 1")
    if instance.capacity <= 0:
        errors.append(f"{label}: capacity must be positive")
    if instance.vehicles != tuple(range(len(instance.vehicles))):
        errors.append(f"{label}: vehicles must be contiguous ids from 0")
    if len(instance.scenarios) != instance.omega:
        errors.append(f"{label}: scenario count {len(instance.scenarios)} != omega {instance.omega}")

    expected_probability = 1.0 / instance.omega
    for scenario in instance.scenarios:
        if scenario.id < 0 or scenario.id >= instance.omega:
            errors.append(f"{label}: scenario id out of range {scenario.id}")
        if abs(scenario.probability - expected_probability) > 1e-12:
            errors.append(f"{label}: scenario {scenario.id} probability mismatch")
        for customer, demand in scenario.demands.items():
            if customer not in instance.customers:
                errors.append(f"{label}: scenario {scenario.id} has unknown customer {customer}")
            if demand <= 0:
                errors.append(f"{label}: scenario {scenario.id} customer {customer} nonpositive demand")

    nodes = (instance.depot, *instance.customers)
    if max(nodes) >= len(instance.coordinates):
        errors.append(f"{label}: coordinates do not cover max node id")
    for i_pos, i in enumerate(nodes):
        for j in nodes[i_pos + 1 :]:
            expected = rounded_euclidean(instance.coordinates[i], instance.coordinates[j])
            actual = instance.distances.get((i, j))
            if actual != expected:
                errors.append(f"{label}: distance {(i, j)} expected {expected} got {actual}")

    for customer in instance.customers:
        c0i = instance.distances.get((0, customer))
        if c0i is None:
            errors.append(f"{label}: missing depot distance for customer {customer}")
            continue
        expected_skip = 3.0 * (2.0 * c0i)
        expected_consistency = 0.1 * (2.0 * c0i)
        if abs(instance.penalties_skip.get(customer, math.nan) - expected_skip) > 1e-9:
            errors.append(f"{label}: skip penalty mismatch for customer {customer}")
        if abs(instance.penalties_consistency.get(customer, math.nan) - expected_consistency) > 1e-9:
            errors.append(f"{label}: consistency penalty mismatch for customer {customer}")

    dmax = max((sum(s.demands.values()) for s in instance.scenarios), default=0)
    expected_k = max(math.ceil(2.0 * dmax / instance.capacity) - 1, instance.D + 1)
    if len(instance.vehicles) != expected_k:
        errors.append(f"{label}: vehicle count {len(instance.vehicles)} != rule {expected_k}")

    metadata = instance.metadata
    if metadata.get("epsilon") != 0.5:
        errors.append(f"{label}: metadata epsilon must be 0.5")
    return errors


def read_manifest(data_root: Path | str) -> list[dict[str, str]]:
    manifest = Path(data_root) / "processed" / "manifest.csv"
    with manifest.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def validate_dataset(instances: list[Instance], data_root: Path | str | None = None) -> dict[str, Any]:
    errors: list[str] = []
    for instance in instances:
        errors.extend(validate_instance(instance, data_root))

    records_by_set = Counter(instance.set_name for instance in instances)
    base_names: dict[str, set[str]] = defaultdict(set)
    for instance in instances:
        base_names[instance.set_name].add(instance.name)
    base_instance_counts = {key: len(base_names.get(key, set())) for key in EXPECTED_BASE_COUNTS}
    omegas = sorted({instance.omega for instance in instances})
    alphas = sorted({instance.alpha for instance in instances})

    if len(instances) != 138:
        errors.append(f"expected 138 canonical stochastic instances, found {len(instances)}")
    if dict(records_by_set) != EXPECTED_RECORDS_BY_SET:
        errors.append(f"records by set mismatch: {dict(records_by_set)}")
    if base_instance_counts != EXPECTED_BASE_COUNTS:
        errors.append(f"base instance counts mismatch: {base_instance_counts}")
    if omegas != EXPECTED_OMEGAS:
        errors.append(f"omega values mismatch: {omegas}")
    if alphas != EXPECTED_ALPHAS:
        errors.append(f"alpha values mismatch: {alphas}")

    if data_root is not None:
        manifest_rows = read_manifest(data_root)
        manifest_paths = {_normalize_manifest_path(row["out"]) for row in manifest_rows}
        expected_paths = {
            str(instance.path.relative_to(Path(data_root)))
            for instance in instances
        }
        if manifest_paths != expected_paths:
            missing = sorted(expected_paths - manifest_paths)
            extra = sorted(manifest_paths - expected_paths)
            errors.append(f"manifest path mismatch: missing={missing[:5]} extra={extra[:5]}")

    return {
        "valid": not errors,
        "total_instances": len(instances),
        "records_by_set": {key: records_by_set.get(key, 0) for key in ["A", "B", "D"]},
        "base_instance_counts": base_instance_counts,
        "base_instance_names": {key: sorted(base_names.get(key, set())) for key in ["A", "B", "D"]},
        "omegas": omegas,
        "alphas": alphas,
        "errors": errors,
    }


def _normalize_manifest_path(path: str) -> str:
    return path.removeprefix("data/")


def summary_rows(instances: list[Instance]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    grouped: dict[tuple[str, int, float], list[Instance]] = defaultdict(list)
    for instance in instances:
        grouped[(instance.set_name, instance.omega, instance.alpha)].append(instance)

    for (set_name, omega, alpha), group in sorted(grouped.items()):
        customer_counts = [len(instance.customers) for instance in group]
        vehicle_counts = [len(instance.vehicles) for instance in group]
        rows.append(
            {
                "set": set_name,
                "omega": omega,
                "alpha": alpha,
                "records": len(group),
                "base_instances": len({instance.name for instance in group}),
                "min_customers": min(customer_counts),
                "max_customers": max(customer_counts),
                "min_vehicles": min(vehicle_counts),
                "max_vehicles": max(vehicle_counts),
            }
        )
    return rows
