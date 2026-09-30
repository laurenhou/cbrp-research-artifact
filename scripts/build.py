#!/usr/bin/env python3
# Copyright (c) 2026 You-Lin Hou
# SPDX-License-Identifier: BSD-2-Clause
# See LICENSES/BSD-2-Clause.txt.
"""Compile isolated modules with javac --release 17; no archived application classes.

Default: per-scheme Maven dependencies. Optional --dependency-dir loads locally
prepared JAR directories, with actual versions and hashes recorded.
"""
from __future__ import annotations
import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from common import ROOT, MODULES, environment, inventory, java_major, need, sha256, write_json

MAIN = {
    'cbrp-dl': 'src/main/java/CBRPDLFull.java',
    'bulletproofs': 'src/main/java/edu/stanford/cs/crypto/BulletproofRangeBench.java',
    'flashproofs': 'src/main/java/FlashproofRangeBench.java',
}
VENDOR = {'bulletproofs': 'bulletprooflib', 'flashproofs': 'flashproofs'}


def sources(module: str) -> list[Path]:
    out = [ROOT / MAIN[module], ROOT / 'tests/java/common/BackendInfo.java']
    out += sorted((ROOT / 'tests/java' / module).glob('*.java'))
    out += sorted((ROOT / 'src/main/java/research/cbrp/bench').glob('*.java'))
    if module in VENDOR:
        out += sorted((ROOT / 'third_party' / VENDOR[module] / 'src/main/java').rglob('*.java'))
    return out


def build(module: str, dependency_dir: Path | None) -> None:
    if java_major() < 17:
        raise RuntimeError('JDK 17+ required; the documented evaluation runtime is JDK 17')
    folder = ROOT / 'build' / module
    if folder.exists():
        shutil.rmtree(folder)
    (folder / 'classes').mkdir(parents=True)
    (folder / 'lib').mkdir()
    pom = ROOT / 'config/dependencies' / (module + '.xml')
    if dependency_dir:
        files = sorted((dependency_dir / module).glob('*.jar'))
        if not files:
            raise RuntimeError(f'No JARs in {dependency_dir / module}')
        for file in files:
            shutil.copyfile(file, folder / 'lib' / file.name)
        deps = {'mode': 'local-jars', 'note': 'Locally supplied dependency set; inspect backend_probe and hashes.'}
    else:
        subprocess.run([need('mvn'), '-B', '-ntp', '-f', str(pom),
                        'org.apache.maven.plugins:maven-dependency-plugin:3.6.1:copy-dependencies',
                        '-DincludeScope=runtime', '-DoutputDirectory='+str(folder / 'lib'),
                        '-Dmdep.copyPom=true'], check=True)
        deps = {'mode': 'maven-per-scheme', 'pom': pom.relative_to(ROOT).as_posix()}
    src = sources(module)
    import os
    cp = os.pathsep.join(map(str, sorted((folder / 'lib').glob('*.jar'))))
    if not cp:
        raise RuntimeError('no dependency JARs resolved')
    args = folder / 'javac-sources.txt'
    args.write_text('\n'.join('"'+p.as_posix()+'"' for p in src)+'\n')
    subprocess.run([need('javac'), '--release', '17', '-encoding', 'UTF-8', '-cp', cp,
                    '-d', str(folder / 'classes'), '@'+str(args)], check=True)
    # Probe the actual loaded provider; record its version and location, not just a filename.
    info = {'module': module, 'dependencies': deps, 'environment': environment(),
            'java_sources': [p.relative_to(ROOT).as_posix() for p in src],
            'inputs': inventory(src + [pom, ROOT / 'scripts/build.py']),
            'outputs': inventory(list((folder / 'classes').rglob('*.class')) + list((folder / 'lib').glob('*.jar')))}
    from common import java_cmd
    result = subprocess.run(java_cmd(module, 'BackendInfo'), check=True, text=True, capture_output=True)
    info['backend_probe'] = result.stdout.strip()
    write_json(folder / 'build.json', info)
    print(result.stdout.strip())
    print(f'BUILD PASS: {module}; {len(src)} Java source files; --release 17', flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--module', choices=(*MODULES, 'all'), default='all')
    p.add_argument('--dependency-dir', type=Path, help='Optional directory containing <scheme>/*.jar; actual dependencies are recorded')
    a = p.parse_args()
    dependency_dir = a.dependency_dir.expanduser().resolve() if a.dependency_dir else None
    for name in MODULES if a.module == 'all' else (a.module,):
        build(name, dependency_dir)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.CalledProcessError) as e:
        print(f'BUILD FAILED: {e}', file=sys.stderr)
        sys.exit(1)
