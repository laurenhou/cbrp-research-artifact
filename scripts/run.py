#!/usr/bin/env python3
# Copyright (c) 2026 You-Lin Hou
# SPDX-License-Identifier: BSD-2-Clause
# See LICENSES/BSD-2-Clause.txt.
"""Run Java benchmarks and save fixtures, raw samples, and summaries as CSV."""
from __future__ import annotations

import argparse
import copy
import json
import re
import secrets
import subprocess
import sys
from pathlib import Path

from common import (
    MODULES,
    ROOT,
    current_build,
    environment,
    inventory,
    java_cmd,
    new_run,
    public_command,
    sha256,
    write_json,
)
from inputs import (
    PAPER_FIXED_SAMPLING,
    RANDOM_SAMPLING,
    generate_cases,
    generate_paper_fixed_cases,
    read_cases,
    write_cases,
)
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


def validate_job(job: dict) -> None:
    if job.get("scheme") not in MODULES or job.get("bits") not in (32, 64):
        raise ValueError(
            "use cbrp-dl/hashwires/bulletproofs/flashproofs and 32/64 bits"
        )
    for field, minimum in (("warmup", 0), ("iterations", 1)):
        if type(job.get(field)) is not int or job[field] < minimum:
            raise ValueError(f"{field} must be integer >= {minimum}")
    if job["scheme"] == "cbrp-dl":
        bases = job.get("bases", [])
        if (
            not bases
            or any(
                type(base) is not int or base not in (16, 256, 65536)
                for base in bases
            )
            or len(set(bases)) != len(bases)
        ):
            raise ValueError(
                "distinct CBRP-DL bases drawn from 16,256,65536 required"
            )
    elif job["scheme"] == "hashwires":
        bases = job.get("bases", [])
        if (
            not bases
            or any(
                type(base) is not int or base not in (2, 4, 16, 256)
                for base in bases
            )
            or len(set(bases)) != len(bases)
        ):
            raise ValueError(
                "distinct HashWires bases drawn from 2,4,16,256 required"
            )


def expand_jobs(jobs: list[dict]) -> list[dict]:
    """Run each radix in a separate JVM to avoid fixed order/JIT carry-over."""
    expanded = []
    for original in jobs:
        if original["scheme"] in ("cbrp-dl", "hashwires"):
            for base in original["bases"]:
                job = copy.deepcopy(original)
                job["bases"] = [base]
                expanded.append(job)
        else:
            expanded.append(copy.deepcopy(original))
    return expanded


def command(
    job: dict,
    input_path: Path,
    sample_path: Path,
    heap: str,
    input_mode: str = "randomized",
) -> list[str]:
    scheme, bits = job["scheme"], job["bits"]
    warmup, iterations = job["warmup"], job["iterations"]
    if scheme == "cbrp-dl":
        main = "CBRPDLFull"
        args = [
            bits,
            ",".join(map(str, job["bases"])),
            warmup,
            iterations,
            input_path,
            sample_path,
        ]
    elif scheme == "hashwires":
        main = "research.baselines.hashwires.HashWiresRangeBench"
        args = [
            bits,
            ",".join(map(str, job["bases"])),
            warmup,
            iterations,
            input_path,
            sample_path,
        ]
        if input_mode == "paper-fixed":
            args.append("allow-repeated")
    elif scheme == "bulletproofs":
        main = "edu.stanford.cs.crypto.BulletproofRangeBench"
        args = [bits, warmup, iterations, input_path, sample_path]
    else:
        main = "FlashproofRangeBench"
        args = [
            bits,
            11 if bits == 32 else 16,
            warmup,
            iterations,
            input_path,
            sample_path,
        ]
    return java_cmd(scheme, main, args, heap)


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
    write_csv(
        output / "setup.csv",
        setups,
        [
            "job",
            "repeat",
            "scheme",
            "range_bits",
            "base",
            "metric",
            "milliseconds",
        ],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--profile",
        help=(
            "smoke (default), check-java, random-java, "
            "hashwires-paper-fixed, or a profile JSON path"
        ),
    )
    group.add_argument("--scheme", choices=MODULES)
    parser.add_argument("--bits", type=int, default=32)
    parser.add_argument("--bases", default="16,256")
    parser.add_argument("--warmup", type=int)
    parser.add_argument("--iterations", type=int)
    parser.add_argument(
        "--seed",
        type=int,
        help="public test-input seed; omitted means generate and record a new seed",
    )
    parser.add_argument(
        "--input-mode",
        choices=("randomized", "paper-fixed"),
        help=(
            "fixture mode; paper-fixed repeats w=N-2,t=floor(N/2)+1 "
            "and is HashWires-only"
        ),
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="independent JVM executions and fixture schedules",
    )
    parser.add_argument("--heap", default="2g")
    parser.add_argument(
        "--timeout",
        type=int,
        default=0,
        help="per-JVM seconds; 0=no timeout",
    )
    args = parser.parse_args()
    if args.repeat < 1 or args.timeout < 0 or (
        args.seed is not None and args.seed < 0
    ):
        parser.error("repeat>=1, timeout>=0, seed>=0 required")

    if args.scheme:
        baseline = args.scheme != "cbrp-dl"
        job = {
            "scheme": args.scheme,
            "bits": args.bits,
            "warmup": (
                args.warmup if args.warmup is not None else (5 if baseline else 10)
            ),
            "iterations": (
                args.iterations
                if args.iterations is not None
                else (20 if baseline else 50)
            ),
        }
        if args.scheme in ("cbrp-dl", "hashwires"):
            job["bases"] = [int(base) for base in args.bases.split(",")]
        configuration = {"jobs": [job]}
        label = args.scheme
    else:
        label = args.profile or "smoke"
        profile_path = Path(label)
        if not profile_path.is_file():
            profile_path = ROOT / "config/profiles" / (label + ".json")
        configuration = json.loads(profile_path.read_text(encoding="utf-8"))
        label = profile_path.stem
        for job in configuration["jobs"]:
            if args.warmup is not None:
                job["warmup"] = args.warmup
            if args.iterations is not None:
                job["iterations"] = args.iterations

    input_mode = args.input_mode or configuration.get("input_mode", "randomized")
    if input_mode not in ("randomized", "paper-fixed"):
        raise ValueError("invalid input_mode")
    if input_mode == "paper-fixed" and any(
        job.get("scheme") != "hashwires"
        for job in configuration.get("jobs", [])
    ):
        raise ValueError("paper-fixed mode is restricted to HashWires jobs")
    if not configuration.get("jobs"):
        raise ValueError("empty profile")

    for job in configuration["jobs"]:
        validate_job(job)
    jobs = expand_jobs(configuration["jobs"])
    builds = {
        scheme: current_build(scheme) for scheme in {job["scheme"] for job in jobs}
    }
    command(
        jobs[0],
        ROOT / "input-placeholder.csv",
        ROOT / "output-placeholder.csv",
        args.heap,
        input_mode,
    )

    seed = args.seed if args.seed is not None else secrets.randbits(128)
    output = new_run(label)
    metadata = {
        "status": "RUNNING",
        "implementation_revision": "journal-artifact-v2",
        "sampling": (
            PAPER_FIXED_SAMPLING if input_mode == "paper-fixed" else RANDOM_SAMPLING
        ),
        "input_mode": input_mode,
        "input_seed": str(seed),
        "environment": environment(),
        "configuration": configuration,
        "execution_policy": "one radix per JVM process",
        "expanded_jobs": jobs,
        "repeat": args.repeat,
        "builds": builds,
        "jobs": [],
        "sources": inventory(sorted((ROOT / "scripts").glob("*.py"))),
        "workload": (
            "Repeated paper statement w=N-2,t=floor(N/2)+1; fresh ordinary "
            "HashWires seed/commitment per execution."
            if input_mode == "paper-fixed"
            else "Fresh w,t each execution; fresh CBRP credential or HashWires "
            "seed/commitment per execution; CBRP-DL and HashWires prove w>=t "
            "directly; algebraic baselines prove delta=w-t."
        ),
        "input_files": [],
    }
    write_json(output / "metadata.json", metadata)

    measured: list[dict] = []
    warmups: list[dict] = []
    setups: list[dict] = []
    try:
        schedules: dict[tuple[int, int], Path] = {}
        for repeat in range(1, args.repeat + 1):
            for bits in sorted({job["bits"] for job in jobs}):
                bit_jobs = [job for job in jobs if job["bits"] == bits]
                number_warmups = max(job["warmup"] for job in bit_jobs)
                number_iterations = max(job["iterations"] for job in bit_jobs)
                fixture_path = output / f"inputs-r{repeat}-b{bits}.csv"
                fixture_rows = (
                    generate_paper_fixed_cases(
                        bits,
                        number_warmups,
                        number_iterations,
                    )
                    if input_mode == "paper-fixed"
                    else generate_cases(
                        bits,
                        number_warmups,
                        number_iterations,
                        seed,
                        repeat,
                    )
                )
                write_cases(fixture_path, fixture_rows)
                schedules[repeat, bits] = fixture_path
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
            for job in jobs:
                index += 1
                base_suffix = (
                    f"-b{job['bases'][0]}" if job.get("bases") else ""
                )
                prefix = f"{index:02d}-{job['scheme']}-{job['bits']}{base_suffix}"
                stdout_path = output / (prefix + ".stdout.log")
                stderr_path = output / (prefix + ".stderr.log")
                samples_path = output / (prefix + ".samples.csv")
                fixture_path = schedules[repeat, job["bits"]]
                cases = read_cases(
                    fixture_path,
                    job["bits"],
                    job["warmup"],
                    job["iterations"],
                    require_distinct=input_mode != "paper-fixed",
                )
                run_command = command(
                    job,
                    fixture_path,
                    samples_path,
                    args.heap,
                    input_mode,
                )
                entry = {
                    "parameters": job,
                    "command": public_command(run_command),
                    "repeat": repeat,
                    "status": "RUNNING",
                    "stdout": stdout_path.name,
                    "stderr": stderr_path.name,
                    "samples": samples_path.name,
                    "inputs": fixture_path.name,
                }
                metadata["jobs"].append(entry)
                write_json(output / "metadata.json", metadata)

                print(
                    f"[{index}] {job['scheme']} bits={job['bits']} "
                    f"bases={job.get('bases', '-')} warmup={job['warmup']} "
                    f"iterations={job['iterations']}",
                    flush=True,
                )
                if job["scheme"] in ("cbrp-dl", "hashwires"):
                    print(
                        "  Fresh credential/commitment every round; progress is "
                        f"recorded in {stderr_path.name}",
                        flush=True,
                    )
                with stdout_path.open(
                    "w", encoding="utf-8"
                ) as stdout_log, stderr_path.open(
                    "w", encoding="utf-8"
                ) as stderr_log:
                    process = subprocess.run(
                        run_command,
                        stdout=stdout_log,
                        stderr=stderr_log,
                        timeout=args.timeout or None,
                        check=False,
                    )
                entry["exit_code"] = process.returncode
                if process.returncode:
                    raise RuntimeError(f"JVM failed; read {stderr_path}")

                raw = read_csv(samples_path)
                check_rows(raw, job, cases)
                entry["samples_sha256"] = sha256(samples_path)
                annotated = annotate(
                    raw,
                    repeat,
                    index,
                    builds[job["scheme"]]["dependencies"]["mode"],
                )
                for row in annotated:
                    (measured if row["phase"] == "measure" else warmups).append(row)

                default_base = str(job.get("bases", [""])[0])
                for line in stderr_path.read_text(encoding="utf-8").splitlines():
                    match = re.fullmatch(
                        r"(?:base=(\d+),)?([a-z_]+_ms)=([0-9.]+)", line
                    )
                    if match:
                        setups.append(
                            {
                                "job": index,
                                "repeat": repeat,
                                "scheme": job["scheme"],
                                "range_bits": job["bits"],
                                "base": match[1] or default_base,
                                "metric": match[2],
                                "milliseconds": match[3],
                            }
                        )
                entry["status"] = "PASS"
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
    print("RUN PASS")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("RUN FAILED: interrupted", file=sys.stderr)
        sys.exit(130)
    except (
        OSError,
        ValueError,
        KeyError,
        RuntimeError,
        subprocess.SubprocessError,
    ) as error:
        print("RUN FAILED: " + str(error), file=sys.stderr)
        sys.exit(1)
