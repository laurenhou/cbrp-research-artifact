#!/usr/bin/env python3
# Copyright (c) 2026 You-Lin Hou
# SPDX-License-Identifier: BSD-2-Clause
# See LICENSES/BSD-2-Clause.txt.
"""Functional/regression checks. Does not establish any cryptographic security theorem."""
from __future__ import annotations
import argparse
import subprocess
import sys
from common import ROOT, MODULES, current_build, java_cmd


def main():
    p=argparse.ArgumentParser(description=__doc__)
    group=p.add_mutually_exclusive_group()
    group.add_argument('--python-only',action='store_true')
    group.add_argument('--java-only',action='store_true')
    a=p.parse_args()
    if not a.java_only:
        subprocess.run([sys.executable,'-m','unittest','discover','-s',str(ROOT/'tests'),'-p','test_*.py','-v'],check=True,cwd=ROOT)
    if not a.python_only:
        for module,main in zip(MODULES,['CBRPSelfTest','BPSelfTest','FPSelfTest']):
            current_build(module)
            subprocess.run(java_cmd(module,main),check=True,cwd=ROOT)
        subprocess.run(java_cmd('cbrp-dl','BenchmarkDataSelfTest'),check=True,cwd=ROOT)
    print('TEST PASS')


if __name__=='__main__':
    try:main()
    except (OSError,ValueError,RuntimeError,subprocess.CalledProcessError) as e:
        print('TEST FAILED: '+str(e),file=sys.stderr);sys.exit(1)
