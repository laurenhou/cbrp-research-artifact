# Copyright (c) 2026 You-Lin Hou
# SPDX-License-Identifier: BSD-2-Clause
# See LICENSES/BSD-2-Clause.txt.
"""Deterministic, public benchmark fixtures; never used for cryptographic coins."""
from __future__ import annotations
import csv
import hashlib
import random
from pathlib import Path

INPUT_FIELDS = ['phase', 'iteration', 'range_bits', 'w', 't']
SAMPLING = 'uniform-valid-pairs-distinct-coordinates-v1'


def derive_seed(seed: int, label: str) -> int:
    if type(seed) is not int or seed < 0:
        raise ValueError('seed must be a nonnegative integer')
    return int.from_bytes(hashlib.sha256(f'CBRP/fixtures/v1:{seed}:{label}'.encode('ascii')).digest(), 'big')


def generate_cases(bits: int, warmup: int, iterations: int, seed: int, repeat: int = 1) -> list[dict]:
    """Each proposal draws w,t independently in [0,2**bits).

    Reject t>w and any previously accepted w OR t in this schedule. Thus each
    next pair is uniform over remaining admissible pairs under ideal random bits,
    not two independent uniform marginals. Warm-ups participate in deduplication.
    The local PRNG controls fixtures only; keys/nonces/challenges use other RNGs.
    """
    if type(bits) is not int or not 1 <= bits <= 64:
        raise ValueError('bits must be an integer in 1..64')
    if type(warmup) is not int or type(iterations) is not int or warmup < 0 or iterations < 1:
        raise ValueError('warmup>=0 and iterations>=1 required')
    if type(repeat) is not int or repeat < 1:
        raise ValueError('repeat>=1 required')
    count = warmup + iterations
    if count > (1 << bits):
        raise ValueError('not enough distinct w and t values for this schedule')
    rng = random.Random(derive_seed(seed, f'bits={bits};repeat={repeat}'))
    used_w, used_t, rows = set(), set(), []
    attempts, limit = 0, max(10000, count * 10000)
    for phase, n in [('warmup', warmup), ('measure', iterations)]:
        for i in range(1, n + 1):
            while True:
                attempts += 1
                if attempts > limit:
                    raise ValueError('distinct-pair sampler exhausted its attempt limit; reduce sample count or choose another seed')
                w, t = rng.getrandbits(bits), rng.getrandbits(bits)
                if t <= w and w not in used_w and t not in used_t:
                    break
            used_w.add(w); used_t.add(t)
            rows.append(dict(phase=phase, iteration=i, range_bits=bits, w=str(w), t=str(t)))
    return rows


def write_cases(path: Path, rows: list[dict]) -> None:
    with path.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=INPUT_FIELDS, lineterminator='\n')
        writer.writeheader(); writer.writerows(rows)


def read_cases(path: Path, bits: int, warmup: int, iterations: int) -> list[dict]:
    with path.open(encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != INPUT_FIELDS:
            raise ValueError('unexpected fixture CSV header')
        rows = list(reader)
    expected = {'warmup': 1, 'measure': 1}
    used_w, used_t, selected = set(), set(), []
    measure_started = False
    for row in rows:
        if None in row or any(v is None for v in row.values()):
            raise ValueError('malformed fixture CSV')
        phase = row['phase']
        if phase not in expected or (measure_started and phase == 'warmup'):
            raise ValueError('invalid fixture phase order')
        if phase == 'measure': measure_started = True
        index, w, t = int(row['iteration']), int(row['w']), int(row['t'])
        if int(row['range_bits']) != bits or not 0 <= t <= w < 2**bits:
            raise ValueError('fixture range/statement mismatch')
        if index != expected[phase] or w in used_w or t in used_t:
            raise ValueError('duplicate input or invalid iteration order')
        expected[phase] += 1; used_w.add(w); used_t.add(t)
        if index <= (warmup if phase == 'warmup' else iterations):
            selected.append(dict(phase=phase, iteration=index, range_bits=bits, w=str(w), t=str(t)))
    if expected['warmup'] - 1 < warmup or expected['measure'] - 1 < iterations:
        raise ValueError('insufficient fixture rows')
    return selected
