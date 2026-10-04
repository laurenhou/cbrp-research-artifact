#!/usr/bin/env python3
# Copyright (c) 2026 You-Lin Hou
# SPDX-License-Identifier: BSD-2-Clause
# See LICENSES/BSD-2-Clause.txt.
"""Run the randomized KTX-CBRP functional prototype and write CSV results."""
from __future__ import annotations

import argparse
import json
import random
import secrets
import sys
import time
from pathlib import Path

import numpy as np

from common import ROOT, environment, inventory, new_run, sha256, write_json
from inputs import RANDOM_SAMPLING, derive_seed, generate_cases, read_cases, write_cases
from results_io import (
    AGGREGATE_SUMMARY_FIELDS,
    RAW_FIELDS,
    SAMPLE_FIELDS,
    SUMMARY_FIELDS,
    annotate,
    check_rows,
    summarize,
    summarize_aggregate,
    write_csv,
)

sys.path.insert(0, str(ROOT / "experiments/ktx"))
from cbrp_ktx_poc import (  # noqa: E402
    CBRP_KTX,
    M_COL,
    N_L,
    Q_MOD,
    RHO,
    challenge_vector,
    dedp,
)

CHALLENGE_FIELDS = ["challenge1_count", "challenge2_count", "challenge3_count"]
SETUP_FIELDS = [
    "job",
    "repeat",
    "scheme",
    "range_bits",
    "base",
    "metric",
    "milliseconds",
]


def _write_combined_outputs(
    output: Path,
    measured: list[dict],
    warmups: list[dict],
    setups: list[dict],
) -> None:
    write_csv(output / "samples.csv", measured, SAMPLE_FIELDS)
    write_csv(output / "warmup.csv", warmups, SAMPLE_FIELDS)
    write_csv(output / "summary.csv", summarize(measured, warmups), SUMMARY_FIELDS)
    write_csv(
        output / "summary-aggregate.csv",
        summarize_aggregate(measured, warmups),
        AGGREGATE_SUMMARY_FIELDS,
    )
    write_csv(output / "setup.csv", setups, SETUP_FIELDS)


def _configuration_order(
    bits: list[int],
    bases: list[int],
    seed: int,
    repeat: int,
) -> list[tuple[int, int]]:
    configurations = [(range_bits, base) for range_bits in bits for base in bases]
    order_rng = random.Random(derive_seed(seed, f"ktx-order:repeat={repeat}"))
    order_rng.shuffle(configurations)
    return configurations


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=["random-ktx"])
    parser.add_argument("--bits", type=int, choices=[16, 32, 64], default=16)
    parser.add_argument("--bases", default="16,256")
    parser.add_argument("--rho", type=int)
    parser.add_argument(
        "--seed",
        type=int,
        help="public input/matrix seed; never used for private witnesses or masks",
    )
    parser.add_argument("--warmup", type=int)
    parser.add_argument("--iterations", type=int)
    parser.add_argument("--repeat", type=int, default=1)
    args = parser.parse_args()

    if args.profile:
        configuration = json.loads(
            (ROOT / "config/profiles/random-ktx.json").read_text(encoding="utf-8")
        )
    else:
        configuration = {
            "bits": [args.bits],
            "bases": [int(base) for base in args.bases.split(",")],
            "rho": RHO,
            "warmup": 0,
            "iterations": 3,
            "q": Q_MOD,
            "nL": N_L,
            "m": M_COL,
        }

    for key in ("rho", "warmup", "iterations"):
        value = getattr(args, key)
        if value is not None:
            configuration[key] = value

    if (
        configuration["q"],
        configuration["nL"],
        configuration["m"],
    ) != (Q_MOD, N_L, M_COL):
        parser.error("q/nL/m are fixed toy parameters")
    if (
        not configuration["bits"]
        or any(bits not in (16, 32, 64) for bits in configuration["bits"])
        or len(set(configuration["bits"])) != len(configuration["bits"])
    ):
        parser.error("distinct supported range bits required")
    if (
        not 1 <= configuration["rho"] <= 1000
        or configuration["iterations"] < 1
        or configuration["warmup"] < 0
        or args.repeat < 1
        or (args.seed is not None and args.seed < 0)
    ):
        parser.error("invalid rho/count/seed")
    if (
        not configuration["bases"]
        or any(base not in (16, 256) for base in configuration["bases"])
        or len(set(configuration["bases"])) != len(configuration["bases"])
    ):
        parser.error("distinct bases 16,256 required")

    seed = args.seed if args.seed is not None else secrets.randbits(128)
    output = new_run("random-ktx")
    metadata = {
        "status": "RUNNING",
        "implementation_revision": "randomized-v4",
        "sampling": RANDOM_SAMPLING,
        "input_seed": str(seed),
        "configuration": configuration,
        "execution_policy": (
            "fresh KTX instance per configuration; configuration order is "
            "deterministically shuffled for each repeat"
        ),
        "private_randomness": (
            "Witnesses and masks use an independent unrecorded entropy-seeded "
            "private PRNG; the recorded public seed controls only fixtures and matrices."
        ),
        "repeat": args.repeat,
        "environment": environment(),
        "numpy": np.__version__,
        "sources": inventory(
            [
                ROOT / "experiments/ktx/cbrp_ktx_poc.py",
                ROOT / "requirements.txt",
                *sorted((ROOT / "scripts").glob("*.py")),
            ]
        ),
        "scope": (
            "Hash commitment placeholders; no issuer labels/signatures; toy "
            "parameters; not a security validation."
        ),
        "input_files": [],
        "jobs": [],
    }
    write_json(output / "metadata.json", metadata)

    measured: list[dict] = []
    warmups: list[dict] = []
    setups: list[dict] = []
    try:
        fixtures: dict[tuple[int, int], tuple[Path, list[dict]]] = {}
        for repeat in range(1, args.repeat + 1):
            for bits in configuration["bits"]:
                fixture_path = output / f"inputs-r{repeat}-b{bits}.csv"
                write_cases(
                    fixture_path,
                    generate_cases(
                        bits,
                        configuration["warmup"],
                        configuration["iterations"],
                        seed,
                        repeat,
                    ),
                )
                cases = read_cases(
                    fixture_path,
                    bits,
                    configuration["warmup"],
                    configuration["iterations"],
                )
                fixtures[repeat, bits] = (fixture_path, cases)
                metadata["input_files"].append(
                    {
                        "file": fixture_path.name,
                        "sha256": sha256(fixture_path),
                        "repeat": repeat,
                        "bits": bits,
                    }
                )
        write_json(output / "metadata.json", metadata)

        index = 0
        for repeat in range(1, args.repeat + 1):
            order = _configuration_order(
                configuration["bits"],
                configuration["bases"],
                seed,
                repeat,
            )
            for bits, base in order:
                index += 1
                fixture_path, cases = fixtures[repeat, bits]
                job = {
                    "scheme": "ktx-cbrp",
                    "bits": bits,
                    "bases": [base],
                    "warmup": configuration["warmup"],
                    "iterations": configuration["iterations"],
                    "rho": configuration["rho"],
                }
                raw_path = output / f"{index:02d}-ktx-{bits}-b{base}.samples.csv"
                matrix_seed = derive_seed(
                    seed,
                    f"ktx-matrix:bits={bits};base={base};repeat={repeat}",
                )
                entry = {
                    "parameters": job,
                    "repeat": repeat,
                    "public_matrix_seed": str(matrix_seed),
                    "inputs": fixture_path.name,
                    "samples": raw_path.name,
                    "status": "RUNNING",
                }
                metadata["jobs"].append(entry)
                write_json(output / "metadata.json", metadata)

                setup_begin = time.perf_counter_ns()
                scheme = CBRP_KTX(
                    2**bits,
                    base,
                    public_matrix_seed=matrix_seed,
                )
                setup_ns = time.perf_counter_ns() - setup_begin
                setups.append(
                    {
                        "job": index,
                        "repeat": repeat,
                        "scheme": "ktx-cbrp",
                        "range_bits": bits,
                        "base": base,
                        "metric": "public_matrix_setup_ms",
                        "milliseconds": setup_ns / 1e6,
                    }
                )

                raw: list[dict] = []
                for case in cases:
                    w, t = int(case["w"]), int(case["t"])

                    begin = time.perf_counter_ns()
                    table, auxiliary = scheme.commit(w)
                    commit_ns = time.perf_counter_ns() - begin

                    begin = time.perf_counter_ns()
                    state = scheme.start(
                        table,
                        auxiliary,
                        w,
                        t,
                        configuration["rho"],
                    )
                    first_ns = time.perf_counter_ns() - begin

                    begin = time.perf_counter_ns()
                    challenges = challenge_vector(configuration["rho"])
                    challenge_ns = time.perf_counter_ns() - begin

                    begin = time.perf_counter_ns()
                    proof = scheme.respond(state, challenges)
                    prove_ns = first_ns + time.perf_counter_ns() - begin

                    begin = time.perf_counter_ns()
                    verified = scheme.verify(
                        table,
                        t,
                        state.first,
                        proof,
                        challenges,
                        configuration["rho"],
                    )
                    verify_ns = time.perf_counter_ns() - begin

                    ell = len(dedp(t, base, scheme.n, 2**bits))
                    row = {field: "" for field in RAW_FIELDS}
                    row.update(
                        scheme="ktx-cbrp",
                        range_bits=bits,
                        base=base,
                        n=scheme.n,
                        ell=ell,
                        rho=configuration["rho"],
                        phase=case["phase"],
                        iteration=case["iteration"],
                        w=str(w),
                        t=str(t),
                        delta=str(w - t),
                        value_proved=str(w),
                        public_matrix_seed=str(matrix_seed),
                        commit_ms=commit_ns / 1e6,
                        prove_ms=prove_ns / 1e6,
                        challenge_ms=challenge_ns / 1e6,
                        verify_ms=verify_ns / 1e6,
                        proof_bytes=scheme.proof_bytes(challenges, ell),
                        proof_size_basis="packed-estimate-12-bit",
                        timing_scope="fresh-toy-table-workflow",
                        table_entries=scheme.n * base,
                        table_bytes=scheme.table_bytes(),
                        verified=int(verified),
                        challenge1_count=challenges.count(1),
                        challenge2_count=challenges.count(2),
                        challenge3_count=challenges.count(3),
                    )
                    raw.append(row)
                    print(
                        f"[{index}] KTX bits={bits} b={base} "
                        f"{case['phase']}={case['iteration']} ell={ell}: PASS",
                        flush=True,
                    )

                check_rows(raw, job, cases)
                write_csv(raw_path, raw, RAW_FIELDS + CHALLENGE_FIELDS)
                annotated = annotate(
                    raw,
                    repeat,
                    index,
                    "numpy-" + np.__version__,
                )
                for row in annotated:
                    (measured if row["phase"] == "measure" else warmups).append(row)
                entry["status"] = "PASS"
                entry["samples_sha256"] = sha256(raw_path)
                _write_combined_outputs(output, measured, warmups, setups)
                write_json(output / "metadata.json", metadata)
        metadata["status"] = "PASS"
    except KeyboardInterrupt:
        metadata["status"] = "FAILED"
        metadata["error"] = "interrupted"
        if metadata["jobs"] and metadata["jobs"][-1]["status"] == "RUNNING":
            metadata["jobs"][-1]["status"] = "FAILED"
        raise
    except Exception as error:
        metadata["status"] = "FAILED"
        metadata["error"] = str(error)
        if metadata["jobs"] and metadata["jobs"][-1]["status"] == "RUNNING":
            metadata["jobs"][-1]["status"] = "FAILED"
        raise
    finally:
        metadata["csv_files"] = [
            {"file": path.name, "sha256": sha256(path)}
            for path in sorted(output.glob("*.csv"))
        ]
        write_json(output / "metadata.json", metadata)
        (output / "STATUS").write_text(metadata["status"] + "\n", encoding="utf-8")
        print("Results: " + str(output), flush=True)
    print("KTX POC PASS")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("KTX RUN FAILED: interrupted", file=sys.stderr)
        sys.exit(130)
    except (OSError, ValueError, KeyError, RuntimeError) as error:
        print("KTX RUN FAILED: " + str(error), file=sys.stderr)
        sys.exit(1)
