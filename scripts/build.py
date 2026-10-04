#!/usr/bin/env python3
# Copyright (c) 2026 You-Lin Hou
# SPDX-License-Identifier: BSD-2-Clause
# See LICENSES/BSD-2-Clause.txt.
"""Compile isolated modules with javac --release 17; no archived application classes.

The CBRP-DL, Bulletproofs and Flashproofs modules resolve their own Maven
runtime dependencies. The HashWires Java port deliberately uses only the JDK
SHA-256 provider and therefore has an empty dependency classpath.
"""
from __future__ import annotations
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from common import ROOT, MODULES, environment, inventory, java_major, need, write_json

MAIN = {
    'cbrp-dl': 'src/main/java/CBRPDLFull.java',
    'hashwires': 'src/main/java/research/baselines/hashwires/HashWiresRangeBench.java',
    'bulletproofs': 'src/main/java/edu/stanford/cs/crypto/BulletproofRangeBench.java',
    'flashproofs': 'src/main/java/FlashproofRangeBench.java',
}
VENDOR = {
    'hashwires': 'hashwires',
    'bulletproofs': 'bulletprooflib',
    'flashproofs': 'flashproofs',
}
PROBE = {
    'hashwires': ('tests/java/common/HashBackendInfo.java', 'HashBackendInfo'),
}
NO_DEPENDENCIES = {'hashwires'}


def sources(module: str) -> list[Path]:
    probe, _ = PROBE.get(module, ('tests/java/common/BackendInfo.java', 'BackendInfo'))
    out = [ROOT / MAIN[module], ROOT / probe]
    out += sorted((ROOT / 'tests/java' / module).glob('*.java'))
    out += sorted((ROOT / 'src/main/java/research/cbrp/bench').glob('*.java'))
    if module in VENDOR:
        out += sorted((ROOT / 'third_party' / VENDOR[module] / 'src/main/java').rglob('*.java'))
    # Avoid accidental duplicate source arguments if a main file is under a globbed tree.
    return list(dict.fromkeys(out))


def build(module: str, dependency_dir: Path | None) -> None:
    if java_major() < 17:
        raise RuntimeError('JDK 17+ required; the documented evaluation runtime is JDK 17')
    folder = ROOT / 'build' / module
    if folder.exists():
        shutil.rmtree(folder)
    (folder / 'classes').mkdir(parents=True)
    (folder / 'lib').mkdir()
    pom = ROOT / 'config/dependencies' / (module + '.xml')

    if module in NO_DEPENDENCIES:
        supplied = sorted((dependency_dir / module).glob('*.jar')) if dependency_dir else []
        if supplied:
            raise RuntimeError('HashWires is a JDK-only module; remove supplied hashwires JARs')
        deps = {
            'mode': 'jdk-only',
            'pom': pom.relative_to(ROOT).as_posix(),
            'note': 'No third-party JARs; SHA-256 is supplied by the active JDK provider.',
        }
    elif dependency_dir:
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
    missing = [file for file in [*src, pom] if not file.is_file()]
    if missing:
        raise RuntimeError('missing build input: ' + ', '.join(str(file) for file in missing))
    jars = sorted((folder / 'lib').glob('*.jar'))
    if module not in NO_DEPENDENCIES and not jars:
        raise RuntimeError('no dependency JARs resolved')
    cp = os.pathsep.join(map(str, jars))
    args = folder / 'javac-sources.txt'
    args.write_text('\n'.join('"'+path.as_posix()+'"' for path in src)+'\n', encoding='utf-8')
    command = [need('javac'), '--release', '17', '-encoding', 'UTF-8']
    if cp:
        command += ['-cp', cp]
    command += ['-d', str(folder / 'classes'), '@'+str(args)]
    subprocess.run(command, check=True)

    info = {'module': module, 'dependencies': deps, 'environment': environment(),
            'java_sources': [path.relative_to(ROOT).as_posix() for path in src],
            'inputs': inventory(src + [pom, ROOT / 'scripts/build.py', ROOT / 'scripts/common.py']),
            'outputs': inventory(list((folder / 'classes').rglob('*.class')) + jars)}
    from common import java_cmd
    probe_main = PROBE.get(module, ('', 'BackendInfo'))[1]
    result = subprocess.run(java_cmd(module, probe_main), check=True, text=True, capture_output=True)
    info['backend_probe'] = result.stdout.strip()
    write_json(folder / 'build.json', info)
    print(result.stdout.strip())
    print(f'BUILD PASS: {module}; {len(src)} Java source files; --release 17', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--module', choices=(*MODULES, 'all'), default='all')
    parser.add_argument('--dependency-dir', type=Path,
                        help='Optional directory containing <scheme>/*.jar; actual dependencies are recorded')
    args = parser.parse_args()
    dependency_dir = args.dependency_dir.expanduser().resolve() if args.dependency_dir else None
    for name in MODULES if args.module == 'all' else (args.module,):
        build(name, dependency_dir)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f'BUILD FAILED: {error}', file=sys.stderr)
        sys.exit(1)
