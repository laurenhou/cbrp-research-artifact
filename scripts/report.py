#!/usr/bin/env python3
# Copyright (c) 2026 You-Lin Hou
# SPDX-License-Identifier: BSD-2-Clause
# See LICENSES/BSD-2-Clause.txt.
"""Validate a completed run and recompute summaries, or copy reference CSVs."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from common import ROOT, new_run, sha256
from inputs import read_cases
from results_io import (
    AGGREGATE_SUMMARY_FIELDS,
    SAMPLE_FIELDS,
    SUMMARY_FIELDS,
    annotate,
    check_rows,
    read_csv,
    summarize,
    summarize_aggregate,
    write_csv,
)

SUPPORTED_REVISIONS = {"journal-artifact-v2", "randomized-v4"}


def _strings(rows: list[dict]) -> list[dict]:
    return [{key: str(value) for key, value in row.items()} for row in rows]


def validate_run(run: Path):
    metadata = json.loads((run / "metadata.json").read_text(encoding="utf-8"))
    if metadata.get("status") != "PASS" or (
        run / "STATUS"
    ).read_text(encoding="utf-8").strip() != "PASS":
        raise ValueError("refusing failed or incomplete run")
    if metadata.get("implementation_revision") not in SUPPORTED_REVISIONS:
        raise ValueError(
            "unsupported run schema; historical values are available with --reference"
        )

    for record in metadata["csv_files"]:
        if Path(record["file"]).name != record["file"]:
            raise ValueError("invalid run filename")
        file = run / record["file"]
        if not file.is_file() or sha256(file) != record["sha256"]:
            raise ValueError("CSV hash mismatch: " + record["file"])

    measured: list[dict] = []
    warmups: list[dict] = []
    for index, entry in enumerate(metadata["jobs"], 1):
        if entry["status"] != "PASS":
            raise ValueError("unfinished job")
        job = entry["parameters"]
        repeat = entry["repeat"]
        for name in ("inputs", "samples"):
            if Path(entry[name]).name != entry[name]:
                raise ValueError("invalid job filename")
        cases = read_cases(
            run / entry["inputs"],
            job["bits"],
            job["warmup"],
            job["iterations"],
            require_distinct=metadata.get("input_mode", "randomized")
            != "paper-fixed",
        )
        rows = read_csv(run / entry["samples"])
        check_rows(rows, job, cases)
        mode = (
            "numpy-" + metadata["numpy"]
            if job["scheme"] == "ktx-cbrp"
            else metadata["builds"][job["scheme"]]["dependencies"]["mode"]
        )
        for row in annotate(rows, repeat, index, mode):
            (measured if row["phase"] == "measure" else warmups).append(row)

    if _strings(measured) != read_csv(run / "samples.csv") or _strings(
        warmups
    ) != read_csv(run / "warmup.csv"):
        raise ValueError("combined samples do not match per-job CSV files")

    summary = summarize(measured, warmups)
    aggregate = summarize_aggregate(measured, warmups)
    if _strings(summary) != read_csv(run / "summary.csv"):
        raise ValueError("summary differs from recomputed sample statistics")
    if _strings(aggregate) != read_csv(run / "summary-aggregate.csv"):
        raise ValueError("aggregate summary differs from recomputed statistics")
    return measured, warmups, summary, aggregate


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--reference",
        action="store_true",
        help="copy historical reference CSV values; do not execute proofs",
    )
    group.add_argument("--run", type=Path, help="completed benchmark run directory")
    args = parser.parse_args()

    if args.reference:
        output = new_run("historical-reference", parent="reports")
        for file in sorted((ROOT / "results/reference").glob("*.csv")):
            shutil.copyfile(file, output / file.name)
        write_csv(
            output / "source.csv",
            [
                {
                    "kind": "historical-reference",
                    "source": "results/reference",
                    "note": "Stored historical values, not new measurements.",
                }
            ],
        )
    else:
        run = args.run.expanduser().resolve()
        measured, warmups, summary, aggregate = validate_run(run)
        metadata = json.loads((run / "metadata.json").read_text(encoding="utf-8"))
        fixed = metadata.get("input_mode") == "paper-fixed"
        output = new_run(
            "paper-fixed-report" if fixed else "randomized-report",
            parent="reports",
        )
        write_csv(output / "samples.csv", measured, SAMPLE_FIELDS)
        write_csv(output / "warmup.csv", warmups, SAMPLE_FIELDS)
        write_csv(output / "summary.csv", summary, SUMMARY_FIELDS)
        write_csv(
            output / "summary-aggregate.csv",
            aggregate,
            AGGREGATE_SUMMARY_FIELDS,
        )
        shutil.copyfile(run / "setup.csv", output / "setup.csv")
        write_csv(
            output / "source.csv",
            [
                {
                    "kind": (
                        "paper-fixed-fresh-hashwires-commitment"
                        if fixed
                        else "randomized-fresh-credential-or-commitment"
                    ),
                    "source": run.name,
                    "metadata_sha256": sha256(run / "metadata.json"),
                    "note": (
                        "Repeated w=N-2,t=floor(N/2)+1 with a fresh ordinary "
                        "HashWires commitment each execution."
                        if fixed
                        else "Randomized inputs with fresh credentials, tables, or "
                        "commitments as identified by each timing_scope value."
                    ),
                }
            ],
        )
    print("REPORT PASS: " + str(output))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError) as error:
        print("REPORT FAILED: " + str(error), file=sys.stderr)
        sys.exit(1)
