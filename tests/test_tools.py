# Copyright (c) 2026 You-Lin Hou
# SPDX-License-Identifier: BSD-2-Clause
# See LICENSES/BSD-2-Clause.txt.
import copy
import json
import statistics
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from run import expand_jobs, validate_job
from inputs import generate_cases, generate_paper_fixed_cases, write_cases, read_cases
from results_io import (
    RAW_FIELDS, check_rows, annotate, summarize, summarize_aggregate, write_csv, read_csv,
    branch_count, hashwires_mdp, hashwires_expected_proof_bytes,
)


class ToolTests(unittest.TestCase):
    def test_profiles(self):
        cfg = json.loads((ROOT / 'config/profiles/random-java.json').read_text())
        self.assertEqual(len(cfg['jobs']), 8)
        for job in cfg['jobs']:
            validate_job(job)
        expanded = expand_jobs(cfg['jobs'])
        self.assertEqual(len(expanded), 14)
        self.assertTrue(all(len(job.get('bases', [0])) == 1 for job in expanded))
        cfg = json.loads((ROOT / 'config/profiles/smoke.json').read_text())
        self.assertEqual(len(cfg['jobs']), 4)
        self.assertTrue(all(job['iterations'] >= 3 for job in cfg['jobs']))
        self.assertTrue(any(job['scheme'] == 'hashwires' for job in cfg['jobs']))
        cfg = json.loads((ROOT / 'config/profiles/hashwires-paper-fixed.json').read_text())
        self.assertEqual(cfg['input_mode'], 'paper-fixed')
        self.assertEqual({job['bits'] for job in cfg['jobs']}, {32, 64})
        self.assertTrue(all(job['scheme'] == 'hashwires' for job in cfg['jobs']))
        for job in cfg['jobs']:
            validate_job(job)

    def test_invalid_params(self):
        for extra in [dict(bits=16), dict(warmup=-1), dict(iterations=0),
                      dict(scheme='shim'), dict(bases=[16, 16])]:
            job = dict(scheme='cbrp-dl', bits=32, warmup=0, iterations=1, bases=[16])
            job.update(extra)
            with self.assertRaises(ValueError):
                validate_job(job)
        for bases in ([], [8], [16, 16], [65536]):
            with self.assertRaises(ValueError):
                validate_job(dict(scheme='hashwires', bits=32, warmup=0,
                                  iterations=1, bases=bases))

    def test_distinct_valid_inputs(self):
        for bits in (16, 32, 64):
            rows = generate_cases(bits, 10, 200, 314159)
            ws = [int(row['w']) for row in rows]
            ts = [int(row['t']) for row in rows]
            self.assertEqual(len(set(ws)), 210)
            self.assertEqual(len(set(ts)), 210)
            self.assertTrue(all(0 <= t <= w < 2**bits for w, t in zip(ws, ts)))
            self.assertEqual([row['phase'] for row in rows[:10]], ['warmup'] * 10)
            self.assertTrue(any(w != (2**bits - 2) for w in ws))

    def test_fixture_seed(self):
        first = generate_cases(64, 2, 10, 123)
        self.assertEqual(first, generate_cases(64, 2, 10, 123))
        self.assertNotEqual(first, generate_cases(64, 2, 10, 124))
        self.assertNotEqual(first, generate_cases(64, 2, 10, 123, repeat=2))

    def test_paper_fixed_fixture(self):
        for bits in (32, 64):
            rows = generate_paper_fixed_cases(bits, 2, 3)
            self.assertEqual(len(rows), 5)
            self.assertEqual({int(row['w']) for row in rows}, {2**bits - 2})
            self.assertEqual({int(row['t']) for row in rows}, {2**(bits - 1) + 1})
            with tempfile.TemporaryDirectory() as directory:
                file = Path(directory) / 'fixed.csv'
                write_cases(file, rows)
                self.assertEqual(read_cases(file, bits, 2, 3, require_distinct=False), rows)
                with self.assertRaises(ValueError):
                    read_cases(file, bits, 2, 3)

    def test_fixture_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / 'inputs.csv'
            rows = generate_cases(32, 3, 5, 99)
            write_cases(file, rows)
            subset = read_cases(file, 32, 1, 2)
            self.assertEqual(len(subset), 3)
            bad = copy.deepcopy(rows)
            bad[-1]['w'] = bad[-2]['w']
            write_cases(file, bad)
            with self.assertRaises(ValueError):
                read_cases(file, 32, 3, 5)
            bad = copy.deepcopy(rows)
            bad[0]['t'] = str(2**32)
            write_cases(file, bad)
            with self.assertRaises(ValueError):
                read_cases(file, 32, 3, 5)
            write_cases(file, rows)
            with self.assertRaises(ValueError):
                read_cases(file, 32, 4, 5)

    def test_64bit_csv_exactness(self):
        rows = [dict(phase='measure', iteration=1, range_bits=64,
                     w=str(2**64 - 1), t=str(2**63 + 123))]
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / 'input.csv'
            write_cases(file, rows)
            self.assertEqual(read_cases(file, 64, 0, 1), rows)

    def test_sampler_limits(self):
        for args in [(0, 0, 1, 0), (65, 0, 1, 0), (16, -1, 1, 0),
                     (16, 0, 0, 0), (16, 0, 1, -1), (2, 1, 4, 0)]:
            with self.assertRaises(ValueError):
                generate_cases(*args)

    def cb_rows(self):
        cases = [
            dict(phase='measure', iteration=1, range_bits=32, w=str(2**32 - 1), t='0'),
            dict(phase='measure', iteration=2, range_bits=32, w=str(2**32 - 2),
                 t=str(2**31 + 1)),
        ]
        rows = []
        for index, case in enumerate(cases):
            row = {key: '' for key in RAW_FIELDS}
            ell = branch_count(int(case['t']), 16, 32)
            row.update(case)
            row.update(
                scheme='cbrp-dl', base=16, n=8, ell=ell,
                delta=str(int(case['w']) - int(case['t'])), value_proved=case['w'],
                credential_id=f'{index:064x}', commit_ms=index + 1, table_check_ms=1,
                prove_ms=2, challenge_ms=0, verify_ms=3,
                proof_bytes=65 * ell * 8 + 32 * ell,
                proof_size_basis='canonical-element-model',
                timing_scope='fresh-credential-workflow',
                table_entries=128, table_bytes=130 * 128, verified=1,
            )
            rows.append(row)
        job = dict(scheme='cbrp-dl', bits=32, bases=[16], warmup=0, iterations=2)
        return rows, job, cases

    def hw_rows(self):
        cases = [
            dict(phase='measure', iteration=1, range_bits=32, w=str(2**32 - 2),
                 t=str(2**31 + 1)),
            dict(phase='measure', iteration=2, range_bits=32, w='1000000', t='500000'),
        ]
        rows = []
        for case in cases:
            w, t = int(case['w']), int(case['t'])
            row = {key: '' for key in RAW_FIELDS}
            row.update(case)
            row.update(
                scheme='hashwires', base=16, n=8, ell=len(hashwires_mdp(w, 16)),
                delta=str(w - t), value_proved=str(w), commit_ms=1, prove_ms=2,
                verify_ms=3, proof_bytes=hashwires_expected_proof_bytes(w, t, 16, 32),
                proof_size_basis='actual-serialization',
                timing_scope='fresh-one-time-workflow-with-proof-side-recomputation',
                verified=1,
            )
            rows.append(row)
        job = dict(scheme='hashwires', bits=32, bases=[16], warmup=0, iterations=2)
        return rows, job, cases

    def test_variable_ell_and_size(self):
        rows, job, cases = self.cb_rows()
        check_rows(rows, job, cases)
        self.assertEqual([row['ell'] for row in rows], [1, 8])
        self.assertNotEqual(rows[0]['proof_bytes'], rows[1]['proof_bytes'])
        rows[0]['ell'] = 8
        with self.assertRaises(ValueError):
            check_rows(rows, job, cases)

    def test_input_and_credential_checks(self):
        rows, job, cases = self.cb_rows()
        for field, value in [('w', '123'), ('t', '123'), ('value_proved', '123'),
                             ('delta', '123'), ('proof_bytes', 0), ('verified', 0),
                             ('prove_ms', float('nan'))]:
            bad = copy.deepcopy(rows)
            bad[0][field] = value
            with self.assertRaises(ValueError):
                check_rows(bad, job, cases)
        rows[1]['credential_id'] = rows[0]['credential_id']
        with self.assertRaises(ValueError):
            check_rows(rows, job, cases)

    def test_hashwires_rows_and_paper_sizes(self):
        rows, job, cases = self.hw_rows()
        check_rows(rows, job, cases)
        bad = copy.deepcopy(rows)
        bad[0]['proof_bytes'] = int(bad[0]['proof_bytes']) + 1
        with self.assertRaises(ValueError):
            check_rows(bad, job, cases)
        bad = copy.deepcopy(rows)
        bad[0]['ell'] = int(bad[0]['ell']) + 1
        with self.assertRaises(ValueError):
            check_rows(bad, job, cases)

        w32, t32 = 2**32 - 2, 2**32 - 3
        w64, t64 = 2**64 - 2, 2**64 - 3
        self.assertEqual(hashwires_expected_proof_bytes(w32, t32, 16, 32), 369)
        self.assertEqual(hashwires_expected_proof_bytes(w32, t32, 256, 32), 209)
        self.assertEqual(hashwires_expected_proof_bytes(w64, t64, 16, 64), 657)
        self.assertEqual(hashwires_expected_proof_bytes(w64, t64, 256, 64), 369)
        self.assertEqual(hashwires_expected_proof_bytes(w32, 2**31 + 1, 16, 32), 369)
        self.assertEqual(hashwires_expected_proof_bytes(w32, 2**31 + 1, 256, 32), 209)
        self.assertEqual(hashwires_expected_proof_bytes(w64, 2**63 + 1, 16, 64), 657)
        self.assertEqual(hashwires_expected_proof_bytes(w64, 2**63 + 1, 256, 64), 369)

    def test_hashwires_mdp_vectors(self):
        self.assertEqual(hashwires_mdp(int('312', 4), 4),
                         [int('312', 4), int('303', 4), int('233', 4)])
        self.assertEqual(hashwires_mdp(3413, 16)[0], 3413)
        self.assertEqual(hashwires_mdp(255, 2), [255])
        self.assertEqual(hashwires_mdp(2, 2), [2, 1])

    def test_statistics(self):
        rows, _, _ = self.cb_rows()
        rows = annotate(rows, 1, 1, 'test')
        summary = summarize(rows)[0]
        self.assertEqual(summary['iterations'], 2)
        self.assertEqual(summary['commit_ms_mean'], 1.5)
        self.assertEqual(summary['commit_ms_stddev'], statistics.stdev([1, 2]))
        self.assertEqual(summary['ell_min'], 1)
        self.assertEqual(summary['ell_max'], 8)
        self.assertEqual(summarize(rows[:1])[0]['commit_ms_stddev'], '')
        self.assertEqual(summary['online_total_ms_mean'], 5.0)
        self.assertEqual(summary['recorded_total_ms_mean'], 7.5)
        aggregate = summarize_aggregate(rows)[0]
        self.assertEqual(aggregate['iterations'], 2)
        self.assertEqual(aggregate['repeats'], 1)

    def test_warmups_excluded(self):
        rows, _, _ = self.cb_rows()
        rows = annotate(rows, 1, 1, 'test')
        warm = copy.deepcopy(rows[0])
        warm['phase'] = 'warmup'
        warm['commit_ms'] = 999999
        result = summarize(rows, [warm])[0]
        self.assertEqual(result['warmup'], 1)
        self.assertEqual(result['commit_ms_mean'], 1.5)
        with self.assertRaises(ValueError):
            summarize([warm])

    def test_baseline_difference(self):
        rows, _, cases = self.cb_rows()
        row = rows[0]
        row.update(scheme='bulletproofs', base='', n='', ell='', credential_id='',
                   table_entries='', table_bytes='', table_check_ms='', challenge_ms='',
                   value_proved=row['delta'], proof_bytes=622,
                   proof_size_basis='canonical-element-model',
                   timing_scope='fresh-commitment-workflow')
        job = dict(scheme='bulletproofs', bits=32, warmup=0, iterations=1)
        check_rows([row], job, cases[:1])
        row['proof_bytes'] = 621
        with self.assertRaises(ValueError):
            check_rows([row], job, cases[:1])

    def test_csv_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'rows.csv'
            rows = [{'a': '1', 'b': '2'}, {'a': '3', 'b': '4'}]
            write_csv(path, rows, ['a', 'b'])
            self.assertEqual(read_csv(path), rows)

    def test_reference_csv(self):
        java = read_csv(ROOT / 'results/reference/java.csv')
        ktx = read_csv(ROOT / 'results/reference/ktx.csv')
        self.assertEqual(len(java), 10)
        self.assertEqual(len(ktx), 6)
        row = next(row for row in java if row['scheme'] == 'cbrp-dl'
                   and row['range_bits'] == '32' and row['base'] == '65536')
        self.assertEqual(row['proof_bytes'], '324')

    def test_ktx_profile(self):
        cfg = json.loads((ROOT / 'config/profiles/random-ktx.json').read_text())
        self.assertEqual((cfg['q'], cfg['nL'], cfg['m'], cfg['rho']), (4093, 128, 512, 137))
        self.assertGreater(cfg['iterations'], 1)


if __name__ == '__main__':
    unittest.main()
