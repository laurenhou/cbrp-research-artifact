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
MODULES = ('cbrp-dl', 'bulletproofs', 'flashproofs')


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def need(tool: str) -> str:
    p = shutil.which(tool)
    if not p:
        raise RuntimeError(f'{tool} not found; follow README environment setup')
    return p


def capture(command: list[str]) -> str:
    try:
        p = subprocess.run(command, capture_output=True, text=True, timeout=15)
        return (p.stdout + p.stderr).strip()
    except (OSError, subprocess.TimeoutExpired):
        return 'unavailable'


def java_major() -> int:
    m = re.search(r'javac\s+(\d+)', capture([need('javac'), '-version']))
    if not m:
        raise RuntimeError('cannot detect javac version')
    return int(m.group(1))


def environment() -> dict:
    out = dict(utc=datetime.now(timezone.utc).isoformat(), python=sys.version,
               platform=platform.platform(), java=capture(['java', '-version']),
               javac=capture(['javac', '-version']), cpu_count=os.cpu_count())
    if Path('/proc/cpuinfo').exists():
        out['cpu'] = next((s.split(':', 1)[1].strip() for s in Path('/proc/cpuinfo').read_text().splitlines()
                           if s.startswith('model name')), 'unknown')
    if Path('/proc/meminfo').exists():
        out['memory'] = Path('/proc/meminfo').read_text().splitlines()[0]
    if (ROOT / '.git').exists():
        out['git_commit'] = capture(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'])
        out['git_status'] = capture(['git', '-C', str(ROOT), 'status', '--porcelain'])
    return out


def inventory(paths) -> list[dict]:
    return [{'path': p.relative_to(ROOT).as_posix(), 'sha256': sha256(p)} for p in sorted(paths)]


def current_build(module: str) -> dict:
    path = ROOT / 'build' / module / 'build.json'
    if not path.exists():
        raise RuntimeError(f'Build first: python3 scripts/build.py --module {module}')
    info = json.loads(path.read_text())
    for e in info['inputs'] + info['outputs']:
        p = ROOT / e['path']
        if not p.is_file() or sha256(p) != e['sha256']:
            raise RuntimeError(f'Changed/missing build file {e["path"]}; rebuild first')
    from build import sources
    if {p.relative_to(ROOT).as_posix() for p in sources(module)} != set(info['java_sources']):
        raise RuntimeError('Java source set changed; rebuild first')
    return info


def java_cmd(module: str, main: str, args=(), heap='2g') -> list[str]:
    if module not in MODULES or not re.fullmatch(r'[1-9][0-9]*[mgMG]', heap):
        raise ValueError('invalid module or heap (example: 2g)')
    folder = ROOT / 'build' / module
    cp = os.pathsep.join(map(str, [folder / 'classes', *sorted((folder / 'lib').glob('*.jar'))]))
    return [need('java'), '-ea', '-Duser.language=en', '-Duser.country=US', '-Xms128m', '-Xmx'+heap,
            '-cp', cp, main, *map(str, args)]


def new_run(label: str, parent='runs') -> Path:
    safe = re.sub(r'[^A-Za-z0-9_-]', '-', label)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
    path = ROOT / 'results' / parent / f'{stamp}-{safe}'
    path.mkdir(parents=True, exist_ok=False)
    return path
