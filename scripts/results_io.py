# Copyright (c) 2026 You-Lin Hou
# SPDX-License-Identifier: BSD-2-Clause
# See LICENSES/BSD-2-Clause.txt.
"""CSV schemas, input/size validation, and statistics for benchmark runs."""
from __future__ import annotations

import csv
import math
import statistics
from pathlib import Path

RAW_FIELDS = [
    "scheme",
    "range_bits",
    "base",
    "n",
    "ell",
    "K",
    "L",
    "rho",
    "phase",
    "iteration",
    "w",
    "t",
    "delta",
    "value_proved",
    "credential_id",
    "public_matrix_seed",
    "commit_ms",
    "standalone_commit_ms",
    "table_check_ms",
    "prove_ms",
    "challenge_ms",
    "verify_ms",
    "proof_bytes",
    "proof_size_basis",
    "timing_scope",
    "table_entries",
    "table_bytes",
    "verified",
]

SAMPLE_FIELDS = RAW_FIELDS + [
    "challenge1_count",
    "challenge2_count",
    "challenge3_count",
    "online_total_ms",
    "recorded_total_ms",
    "repeat",
    "job",
    "dependency_mode",
]

INPUT_TIMINGS = [
    "commit_ms",
    "standalone_commit_ms",
    "table_check_ms",
    "prove_ms",
    "challenge_ms",
    "verify_ms",
]
SUMMARY_TIMINGS = INPUT_TIMINGS + ["online_total_ms", "recorded_total_ms"]

DESCRIPTORS = {
    "cbrp-dl": ("canonical-element-model", "fresh-credential-workflow"),
    "ktx-cbrp": ("packed-estimate-12-bit", "fresh-toy-table-workflow"),
    "hashwires": (
        "actual-serialization",
        "fresh-one-time-workflow-with-proof-side-recomputation",
    ),
    "bulletproofs": ("canonical-element-model", "fresh-commitment-workflow"),
    "flashproofs": (
        "reflected-element-model",
        "proof-workflow-with-standalone-commitment-diagnostic",
    ),
}

GROUP = [
    "scheme",
    "dependency_mode",
    "proof_size_basis",
    "timing_scope",
    "range_bits",
    "base",
    "n",
    "K",
    "L",
    "rho",
    "repeat",
    "job",
]
AGGREGATE_GROUP = [field for field in GROUP if field not in ("repeat", "job")]
METRICS = SUMMARY_TIMINGS + ["proof_bytes", "ell"]
SUMMARY_FIELDS = GROUP + ["warmup", "iterations"] + [
    f"{key}_{stat}"
    for key in METRICS
    for stat in ("mean", "stddev", "min", "max")
] + ["table_entries", "table_bytes"]
AGGREGATE_SUMMARY_FIELDS = AGGREGATE_GROUP + [
    "repeats",
    "jobs",
    "warmup",
    "iterations",
] + [
    f"{key}_{stat}"
    for key in METRICS
    for stat in ("mean", "stddev", "min", "max")
] + ["table_entries", "table_bytes"]


def write_csv(path: Path, rows: list[dict], fields=None) -> None:
    if fields is None:
        fields = list(dict.fromkeys(key for row in rows for key in row))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(
            output,
            fieldnames=fields,
            extrasaction="raise",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
            raise ValueError("missing/duplicate CSV header")
        rows = list(reader)
    if any(None in row or any(value is None for value in row.values()) for row in rows):
        raise ValueError("malformed CSV row")
    return rows


def branch_count(t: int, base: int, bits: int) -> int:
    n = (bits + base.bit_length() - 2) // (base.bit_length() - 1)
    return len(
        {
            ((t + base**k - 1) // base**k) * base**k
            for k in range(n)
            if ((t + base**k - 1) // base**k) * base**k < 2**bits
        }
    )


def hashwires_mdp(value: int, base: int) -> list[int]:
    """HashWires Algorithm 1 MDP in descending order."""
    if value < 0 or base not in (2, 4, 16, 256):
        raise ValueError("invalid HashWires MDP input")
    result = [value]
    previous = value
    exponent = base
    while exponent <= value:
        if (value + 1) % exponent != 0:
            candidate = value // exponent * exponent - 1
            if candidate != previous:
                result.append(candidate)
                previous = candidate
        exponent *= base
    return result


def _significant_digits(value: int, base: int) -> tuple[int, ...]:
    if value < 0:
        raise ValueError("negative digit input")
    if value == 0:
        return (0,)
    digits: list[int] = []
    while value:
        value, digit = divmod(value, base)
        digits.append(digit)
    return tuple(reversed(digits))


def _digitwise_dominates(upper: int, lower: int, base: int) -> bool:
    upper_digits = _significant_digits(upper, base)
    lower_digits = _significant_digits(lower, base)
    offset = len(upper_digits) - len(lower_digits)
    return offset >= 0 and all(
        upper_digits[offset + index] >= digit
        for index, digit in enumerate(lower_digits)
    )


def _significant_digit_count(value: int, base: int) -> int:
    if value < 0:
        raise ValueError("negative digit input")
    if value == 0:
        return 1
    count = 0
    while value:
        value //= base
        count += 1
    return count


def hashwires_expected_proof_bytes(
    value: int,
    threshold: int,
    base: int,
    bits: int,
) -> int:
    """Canonical Java proof length for the ordinary optimized port."""
    if not 0 <= threshold <= value < 2**bits or bits not in (32, 64):
        raise ValueError("invalid HashWires statement")
    digit_bits = {2: 1, 4: 2, 16: 4, 256: 8}.get(base)
    if digit_bits is None or bits % digit_bits:
        raise ValueError("invalid HashWires base/range")
    maximum_digits = bits // digit_bits
    if maximum_digits & (maximum_digits - 1):
        raise ValueError("HashWires maximum digit count must be a power of two")
    mdp = hashwires_mdp(value, base)
    selected = next(
        item for item in reversed(mdp) if _digitwise_dominates(item, threshold, base)
    )
    selected_digits = _significant_digit_count(selected, base)
    threshold_digits = _significant_digit_count(threshold, base)
    merkle_height = maximum_digits.bit_length() - 1
    has_pla_prefix = (
        selected_digits < maximum_digits or selected_digits > threshold_digits
    )
    return (
        threshold_digits * 32
        + 16
        + 1
        + merkle_height * 32
        + (32 if has_pla_prefix else 0)
    )


def _require_timing(row: dict, field: str) -> None:
    if row.get(field, "") == "":
        raise ValueError(f"missing required timing: {field}")


def _check_descriptors(row: dict, scheme: str) -> None:
    expected_basis, expected_scope = DESCRIPTORS[scheme]
    if row.get("proof_size_basis") != expected_basis:
        raise ValueError("incorrect proof-size basis")
    if row.get("timing_scope") != expected_scope:
        raise ValueError("incorrect timing scope")


def check_rows(rows: list[dict], job: dict, cases: list[dict]) -> None:
    """Validate every warm-up and measurement against its recorded test input."""
    grouped_schemes = ("cbrp-dl", "ktx-cbrp", "hashwires")
    groups = job.get("bases", []) if job["scheme"] in grouped_schemes else [""]
    if len(rows) != len(groups) * len(cases):
        raise ValueError("raw sample count mismatch")
    actual_groups = {str(row.get("base", "")) for row in rows}
    if actual_groups != {str(base) for base in groups}:
        raise ValueError("unexpected or missing base")

    credential_ids = set()
    for base in groups:
        subset = [row for row in rows if str(row.get("base", "")) == str(base)]
        if len(subset) != len(cases):
            raise ValueError("missing configuration samples")
        for row, case in zip(subset, cases):
            scheme = job["scheme"]
            if row["scheme"] != scheme or int(row["range_bits"]) != job["bits"]:
                raise ValueError("scheme/range mismatch")
            if row["phase"] != case["phase"] or int(row["iteration"]) != int(
                case["iteration"]
            ):
                raise ValueError("sample phase/iteration mismatch")

            w, t = int(row["w"]), int(row["t"])
            if (
                w != int(case["w"])
                or t != int(case["t"])
                or not 0 <= t <= w < 2 ** job["bits"]
            ):
                raise ValueError("test input mismatch")
            if int(row["delta"]) != w - t or int(row["verified"]) != 1:
                raise ValueError("invalid delta or rejected proof")

            expected_value = w if scheme in grouped_schemes else w - t
            if int(row["value_proved"]) != expected_value:
                raise ValueError("wrong value passed to proof implementation")

            _require_timing(row, "prove_ms")
            _require_timing(row, "verify_ms")
            if scheme == "flashproofs":
                _require_timing(row, "standalone_commit_ms")
                if row.get("commit_ms", "") != "":
                    raise ValueError("Flashproofs standalone commitment must be diagnostic")
            else:
                _require_timing(row, "commit_ms")
                if row.get("standalone_commit_ms", "") != "":
                    raise ValueError("unexpected standalone commitment timing")

            for field in INPUT_TIMINGS:
                value = row.get(field, "")
                if value != "" and (
                    not math.isfinite(float(value)) or float(value) < 0
                ):
                    raise ValueError("invalid timing sample")
            _check_descriptors(row, scheme)

            if scheme in ("cbrp-dl", "ktx-cbrp"):
                n = (job["bits"] + int(base).bit_length() - 2) // (
                    int(base).bit_length() - 1
                )
                ell = branch_count(t, int(base), job["bits"])
                if int(row["n"]) != n or int(row["ell"]) != ell:
                    raise ValueError("branch count does not match the actual threshold")
                if int(row["table_entries"]) != n * int(base):
                    raise ValueError("table entry count mismatch")

                if scheme == "cbrp-dl":
                    expected_size = 65 * ell * n + 32 * ell
                    expected_table = 130 * n * int(base)
                    credential_id = row.get("credential_id", "")
                    if (
                        len(credential_id) != 64
                        or any(
                            char not in "0123456789abcdef" for char in credential_id
                        )
                        or credential_id in credential_ids
                    ):
                        raise ValueError(
                            "missing, malformed or reused credential identifier"
                        )
                    credential_ids.add(credential_id)
                    if row.get("public_matrix_seed", "") != "":
                        raise ValueError("unexpected public matrix seed")
                    _require_timing(row, "table_check_ms")
                    _require_timing(row, "challenge_ms")
                else:
                    rho = int(row["rho"])
                    if rho != job["rho"]:
                        raise ValueError("rho mismatch")
                    seed = row.get("public_matrix_seed", "")
                    if not seed.isdecimal() or int(seed) < 0:
                        raise ValueError("missing or malformed public matrix seed")
                    counts = [int(row[f"challenge{i}_count"]) for i in (1, 2, 3)]
                    if min(counts) < 0 or sum(counts) != rho:
                        raise ValueError("invalid challenge counts")
                    dimension = n * 512 + ell
                    expected_size = (
                        rho * (96 + 64 + (dimension * 12 + 7) // 8)
                        + counts[0] * ((dimension + 7) // 8)
                        + (counts[1] + counts[2]) * 32
                    )
                    expected_table = (
                        n * int(base) * 128 * 12 + 7
                    ) // 8
                    _require_timing(row, "challenge_ms")
                if int(row["table_bytes"]) != expected_table:
                    raise ValueError("table size mismatch")

            elif scheme == "hashwires":
                digit_bits = {2: 1, 4: 2, 16: 4, 256: 8}[int(base)]
                n = job["bits"] // digit_bits
                ell = len(hashwires_mdp(w, int(base)))
                if int(row["n"]) != n or int(row["ell"]) != ell:
                    raise ValueError("HashWires digit/MDP count mismatch")
                if row.get("table_entries", "") != "" or row.get(
                    "table_bytes", ""
                ) != "":
                    raise ValueError("HashWires must not report CBRP table dimensions")
                if (
                    row.get("credential_id", "") != ""
                    or row.get("public_matrix_seed", "") != ""
                    or row.get("table_check_ms", "") != ""
                    or row.get("challenge_ms", "") != ""
                ):
                    raise ValueError("unexpected HashWires field")
                expected_size = hashwires_expected_proof_bytes(
                    w, t, int(base), job["bits"]
                )

            else:
                if row.get("credential_id", "") != "" or row.get(
                    "public_matrix_seed", ""
                ) != "":
                    raise ValueError("unexpected baseline identifier")
                expected_size = {
                    "bulletproofs": {32: 622, 64: 688},
                    "flashproofs": {32: 746, 64: 1005},
                }[scheme][job["bits"]]
                if scheme == "flashproofs" and (
                    int(row["K"]),
                    int(row["L"]),
                ) != {32: (3, 11), 64: (4, 16)}[job["bits"]]:
                    raise ValueError("incorrect Flashproofs K/L")

            if int(row["proof_bytes"]) != expected_size:
                raise ValueError("proof-size mismatch")


def _sum_timings(row: dict, fields: tuple[str, ...]) -> float:
    return sum(float(row[field]) for field in fields if row.get(field, "") != "")


def annotate(rows: list[dict], repeat: int, job: int, mode: str) -> list[dict]:
    output = []
    for original in rows:
        row = {key: original.get(key, "") for key in SAMPLE_FIELDS}
        row.update(repeat=repeat, job=job, dependency_mode=mode)
        row["online_total_ms"] = format(
            _sum_timings(row, ("prove_ms", "challenge_ms", "verify_ms")),
            ".9f",
        )
        row["recorded_total_ms"] = format(
            _sum_timings(
                row,
                (
                    "commit_ms",
                    "table_check_ms",
                    "prove_ms",
                    "challenge_ms",
                    "verify_ms",
                ),
            ),
            ".9f",
        )
        output.append(row)
    return output


def _summary_rows(
    rows: list[dict],
    warmups: list[dict],
    group_fields: list[str],
) -> list[dict]:
    groups: dict[tuple[str, ...], list[dict]] = {}
    for row in rows:
        if row["phase"] != "measure":
            raise ValueError("only measured rows belong in samples.csv")
        key = tuple(str(row.get(field, "")) for field in group_fields)
        groups.setdefault(key, []).append(row)

    output = []
    for key, samples in groups.items():
        result = dict(zip(group_fields, key))
        result["iterations"] = len(samples)
        result["warmup"] = sum(
            tuple(str(row.get(field, "")) for field in group_fields) == key
            for row in warmups
        )
        if group_fields == AGGREGATE_GROUP:
            result["repeats"] = len({row["repeat"] for row in samples})
            result["jobs"] = len({row["job"] for row in samples})

        for field in METRICS:
            values = [
                float(row[field])
                for row in samples
                if row.get(field, "") != ""
            ]
            if values and len(values) != len(samples):
                raise ValueError("partially missing metric")
            if values and any(
                not math.isfinite(value) or value < 0 for value in values
            ):
                raise ValueError("invalid metric")
            result[field + "_mean"] = statistics.fmean(values) if values else ""
            result[field + "_stddev"] = (
                statistics.stdev(values) if len(values) > 1 else ""
            )
            result[field + "_min"] = min(values) if values else ""
            result[field + "_max"] = max(values) if values else ""

        for field in ("table_entries", "table_bytes"):
            values = {str(row.get(field, "")) for row in samples}
            if len(values) != 1:
                raise ValueError("inconsistent table dimensions")
            result[field] = values.pop()
        output.append(result)
    return output


def summarize(rows: list[dict], warmups: list[dict] = ()) -> list[dict]:
    return _summary_rows(rows, list(warmups), GROUP)


def summarize_aggregate(rows: list[dict], warmups: list[dict] = ()) -> list[dict]:
    return _summary_rows(rows, list(warmups), AGGREGATE_GROUP)
