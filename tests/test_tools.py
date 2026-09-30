# Copyright (c) 2026 You-Lin Hou
# SPDX-License-Identifier: BSD-2-Clause
# See LICENSES/BSD-2-Clause.txt.
import copy
import csv
import json
import math
import statistics
import sys
import tempfile
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from run import validate_job
from inputs import generate_cases, write_cases, read_cases
from results_io import RAW_FIELDS, check_rows, annotate, summarize, write_csv, read_csv, branch_count


class ToolTests(unittest.TestCase):
    def test_profiles(self):
        cfg=json.loads((ROOT/'config/profiles/random-java.json').read_text())
        self.assertEqual(len(cfg['jobs']),6)
        for j in cfg['jobs']:validate_job(j)
        cfg=json.loads((ROOT/'config/profiles/smoke.json').read_text())
        self.assertTrue(all(j['iterations']>=3 for j in cfg['jobs']))

    def test_invalid_params(self):
        for extra in [dict(bits=16),dict(warmup=-1),dict(iterations=0),dict(scheme='shim'),dict(bases=[16,16])]:
            j=dict(scheme='cbrp-dl',bits=32,warmup=0,iterations=1,bases=[16]);j.update(extra)
            with self.assertRaises(ValueError):validate_job(j)

    def test_distinct_valid_inputs(self):
        for bits in (16,32,64):
            rows=generate_cases(bits,10,200,314159)
            ws=[int(r['w']) for r in rows];ts=[int(r['t']) for r in rows]
            self.assertEqual(len(set(ws)),210);self.assertEqual(len(set(ts)),210)
            self.assertTrue(all(0<=t<=w<2**bits for w,t in zip(ws,ts)))
            self.assertEqual([r['phase'] for r in rows[:10]],['warmup']*10)
            self.assertTrue(any(w!=(2**bits-2) for w in ws))

    def test_fixture_seed(self):
        a=generate_cases(64,2,10,123)
        self.assertEqual(a,generate_cases(64,2,10,123))
        self.assertNotEqual(a,generate_cases(64,2,10,124))
        self.assertNotEqual(a,generate_cases(64,2,10,123,repeat=2))

    def test_fixture_validation(self):
        with tempfile.TemporaryDirectory() as d:
            file=Path(d)/'inputs.csv';rows=generate_cases(32,3,5,99)
            write_cases(file,rows)
            subset=read_cases(file,32,1,2)
            self.assertEqual(len(subset),3)
            bad=copy.deepcopy(rows);bad[-1]['w']=bad[-2]['w'];write_cases(file,bad)
            with self.assertRaises(ValueError):read_cases(file,32,3,5)
            bad=copy.deepcopy(rows);bad[0]['t']=str(2**32);write_cases(file,bad)
            with self.assertRaises(ValueError):read_cases(file,32,3,5)
            write_cases(file,rows)
            with self.assertRaises(ValueError):read_cases(file,32,4,5)

    def test_64bit_csv_exactness(self):
        rows=[dict(phase='measure',iteration=1,range_bits=64,w=str(2**64-1),t=str(2**63+123))]
        with tempfile.TemporaryDirectory() as d:
            file=Path(d)/'input.csv';write_cases(file,rows)
            self.assertEqual(read_cases(file,64,0,1),rows)

    def test_sampler_limits(self):
        for args in [(0,0,1,0),(65,0,1,0),(16,-1,1,0),(16,0,0,0),(16,0,1,-1),(2,1,4,0)]:
            with self.assertRaises(ValueError):generate_cases(*args)

    def cb_rows(self):
        cases=[dict(phase='measure',iteration=1,range_bits=32,w=str(2**32-1),t='0'),
               dict(phase='measure',iteration=2,range_bits=32,w=str(2**32-2),t=str(2**31+1))]
        rows=[]
        for i,c in enumerate(cases):
            row={k:'' for k in RAW_FIELDS};ell=branch_count(int(c['t']),16,32)
            row.update(c);row.update(scheme='cbrp-dl',base=16,n=8,ell=ell,delta=str(int(c['w'])-int(c['t'])),value_proved=c['w'],
                                    credential_id=f'{i:064x}',commit_ms=i+1,table_check_ms=1,prove_ms=2,challenge_ms=0,verify_ms=3,
                                    proof_bytes=65*ell*8+32*ell,table_entries=128,table_bytes=130*128,verified=1)
            rows.append(row)
        job=dict(scheme='cbrp-dl',bits=32,bases=[16],warmup=0,iterations=2)
        return rows,job,cases

    def test_variable_ell_and_size(self):
        rows,j,c=self.cb_rows();check_rows(rows,j,c)
        self.assertEqual([r['ell'] for r in rows],[1,8])
        self.assertNotEqual(rows[0]['proof_bytes'],rows[1]['proof_bytes'])
        rows[0]['ell']=8
        with self.assertRaises(ValueError):check_rows(rows,j,c)

    def test_input_and_credential_checks(self):
        rows,j,c=self.cb_rows()
        for change in [('w','123'),('t','123'),('value_proved','123'),('delta','123'),('proof_bytes',0),('verified',0),('prove_ms',float('nan'))]:
            bad=copy.deepcopy(rows);bad[0][change[0]]=change[1]
            with self.assertRaises(ValueError):check_rows(bad,j,c)
        rows[1]['credential_id']=rows[0]['credential_id']
        with self.assertRaises(ValueError):check_rows(rows,j,c)

    def test_statistics(self):
        rows,j,c=self.cb_rows();rows=annotate(rows,1,1,'test')
        summary=summarize(rows)[0]
        self.assertEqual(summary['iterations'],2)
        self.assertEqual(summary['commit_ms_mean'],1.5)
        self.assertEqual(summary['commit_ms_stddev'],statistics.stdev([1,2]))
        self.assertEqual(summary['ell_min'],1);self.assertEqual(summary['ell_max'],8)
        self.assertEqual(summarize(rows[:1])[0]['commit_ms_stddev'],'')
        self.assertEqual(summary['measured_total_ms_mean'],7.5)

    def test_warmups_excluded(self):
        rows,j,c=self.cb_rows();rows=annotate(rows,1,1,'test')
        warm=copy.deepcopy(rows[0]);warm['phase']='warmup';warm['commit_ms']=999999
        result=summarize(rows,[warm])[0]
        self.assertEqual(result['warmup'],1);self.assertEqual(result['commit_ms_mean'],1.5)
        with self.assertRaises(ValueError):summarize([warm])

    def test_baseline_difference(self):
        rows,j,c=self.cb_rows();row=rows[0]
        row.update(scheme='bulletproofs',base='',n='',ell='',credential_id='',table_entries='',table_bytes='',
                   table_check_ms='',challenge_ms='',value_proved=row['delta'],proof_bytes=622)
        job=dict(scheme='bulletproofs',bits=32,warmup=0,iterations=1)
        check_rows([row],job,c[:1])
        row['proof_bytes']=621
        with self.assertRaises(ValueError):check_rows([row],job,c[:1])

    def test_reference_csv(self):
        java=read_csv(ROOT/'results/reference/java.csv');ktx=read_csv(ROOT/'results/reference/ktx.csv')
        self.assertEqual(len(java),10);self.assertEqual(len(ktx),6)
        self.assertEqual(next(r for r in java if r['scheme']=='cbrp-dl' and r['range_bits']=='32' and r['base']=='65536')['proof_bytes'],'324')

    def test_ktx_profile(self):
        cfg=json.loads((ROOT/'config/profiles/random-ktx.json').read_text())
        self.assertEqual((cfg['q'],cfg['nL'],cfg['m'],cfg['rho']),(4093,128,512,137))
        self.assertGreater(cfg['iterations'],1)


if __name__=='__main__':unittest.main()
