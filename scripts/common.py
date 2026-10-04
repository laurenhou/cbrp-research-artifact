# Copyright (c) 2026 You-Lin Hou
# SPDX-License-Identifier: BSD-2-Clause
# See LICENSES/BSD-2-Clause.txt.
"""Path-independent helpers shared by the research experiment commands."""
from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULES = ("cbrp-dl", "hashwires", "bulletproofs", "flashproofs")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def need(tool: str) -> str:
    path = shutil.which(tool)
    if not path:
        raise RuntimeError(f"{tool} not found; follow README environment setup")
    return path


def capture(command: list[str]) -> str:
    try:
        process = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unavailable"
    output = (process.stdout + process.stderr).strip()
    return output if process.returncode == 0 and output else "unavailable"


def java_major() -> int:
    match = re.search(r"javac\s+(\d+)", capture([need("javac"), "-version"]))
    if not match:
        raise RuntimeError("cannot detect javac version")
    return int(match.group(1))


def environment() -> dict:
    output = {
        "utc": datetime.now(timezone.utc).isoformat(),
        "python": sys.version,
        "platform": platform.platform(),
        "java": capture(["java", "-version"]),
        "javac": capture(["javac", "-version"]),
        "cpu_count": os.cpu_count(),
    }
    if Path("/proc/cpuinfo").exists():
        output["cpu"] = next(
            (
                line.split(":", 1)[1].strip()
                for line in Path("/proc/cpuinfo").read_text().splitlines()
                if line.startswith("model name")
            ),
            "unknown",
        )
    if Path("/proc/meminfo").exists():
        output["memory"] = Path("/proc/meminfo").read_text().splitlines()[0]
    if (ROOT / ".git").exists():
        output["git_commit"] = capture(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"]
        )
        output["git_status"] = capture(
            ["git", "-C", str(ROOT), "status", "--porcelain"]
        )
    return output


def inventory(paths) -> list[dict]:
    return [
        {"path": path.relative_to(ROOT).as_posix(), "sha256": sha256(path)}
        for path in sorted(paths)
    ]


def normalize_public_text(value: str) -> str:
    """Replace the active project path in metadata intended for sharing."""
    return value.replace(str(ROOT), "$ROOT")


def public_command(command: list[str]) -> list[str]:
    """Return a portable command representation without workstation paths."""
    output = [normalize_public_text(str(part)) for part in command]
    if output:
        output[0] = Path(output[0]).name
    return output


def _actual_build_outputs(module: str) -> set[str]:
    folder = ROOT / "build" / module
    files = list((folder / "classes").rglob("*.class"))
    files += list((folder / "lib").glob("*.jar"))
    return {path.relative_to(ROOT).as_posix() for path in files}


def current_build(module: str) -> dict:
    path = ROOT / "build" / module / "build.json"
    if not path.exists():
        raise RuntimeError(f"Build first: python3 scripts/build.py --module {module}")
    info = json.loads(path.read_text(encoding="utf-8"))

    recorded_outputs = {entry["path"] for entry in info["outputs"]}
    actual_outputs = _actual_build_outputs(module)
    if recorded_outputs != actual_outputs:
        added = sorted(actual_outputs - recorded_outputs)
        missing = sorted(recorded_outputs - actual_outputs)
        details = []
        if added:
            details.append("extra=" + ",".join(added))
        if missing:
            details.append("missing=" + ",".join(missing))
        raise RuntimeError("Build output set changed; rebuild first (" + "; ".join(details) + ")")

    for entry in info["inputs"] + info["outputs"]:
        file = ROOT / entry["path"]
        if not file.is_file() or sha256(file) != entry["sha256"]:
            raise RuntimeError(
                f"Changed/missing build file {entry['path']}; rebuild first"
            )

    from build import sources

    current_sources = {
        source.relative_to(ROOT).as_posix() for source in sources(module)
    }
    if current_sources != set(info["java_sources"]):
        raise RuntimeError("Java source set changed; rebuild first")
    return info


def java_cmd(module: str, main: str, args=(), heap: str = "2g") -> list[str]:
    if module not in MODULES or not re.fullmatch(r"[1-9][0-9]*[mgMG]", heap):
        raise ValueError("invalid module or heap (example: 2g)")
    folder = ROOT / "build" / module
    classpath = os.pathsep.join(
        map(str, [folder / "classes", *sorted((folder / "lib").glob("*.jar"))])
    )
    return [
        need("java"),
        "-ea",
        "-Duser.language=en",
        "-Duser.country=US",
        "-Xms128m",
        "-Xmx" + heap,
        "-cp",
        classpath,
        main,
        *map(str, args),
    ]


def new_run(label: str, parent: str = "runs") -> Path:
    safe = re.sub(r"[^A-Za-z0-9_-]", "-", label)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    path = ROOT / "results" / parent / f"{stamp}-{safe}"
    path.mkdir(parents=True, exist_ok=False)
    return path
