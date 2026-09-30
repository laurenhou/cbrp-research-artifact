"""CSV schemas, input/size validation, and statistics for randomized benchmarks."""
from __future__ import annotations
import csv
import math
import statistics
from pathlib import Path

RAW_FIELDS = ['scheme','range_bits','base','n','ell','K','L','rho','phase','iteration','w','t','delta',
              'value_proved','credential_id','instance_seed','commit_ms','table_check_ms','prove_ms',
              'challenge_ms','verify_ms','proof_bytes','table_entries','table_bytes','verified']
SAMPLE_FIELDS = RAW_FIELDS + ['challenge1_count','challenge2_count','challenge3_count',
                             'measured_total_ms','repeat','job','dependency_mode']
TIMINGS = ['commit_ms','table_check_ms','prove_ms','challenge_ms','verify_ms','measured_total_ms']
GROUP = ['scheme','dependency_mode','range_bits','base','n','K','L','rho','repeat','job']
SUMMARY_FIELDS = GROUP + ['warmup','iterations'] + [f'{k}_{s}' for k in TIMINGS + ['proof_bytes','ell']
    for s in ['mean','stddev','min','max']] + ['table_entries','table_bytes']


def write_csv(path: Path, rows: list[dict], fields=None) -> None:
    if fields is None:
        fields = list(dict.fromkeys(k for row in rows for k in row))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction='raise', lineterminator='\n')
        writer.writeheader(); writer.writerows(rows)


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
            raise ValueError('missing/duplicate CSV header')
        rows = list(reader)
    if any(None in row or any(v is None for v in row.values()) for row in rows):
        raise ValueError('malformed CSV row')
    return rows


def branch_count(t: int, b: int, bits: int) -> int:
    n = (bits + b.bit_length() - 2) // (b.bit_length() - 1)
    return len({((t + b**k - 1) // b**k) * b**k for k in range(n)
                if ((t + b**k - 1) // b**k) * b**k < 2**bits})


def check_rows(rows: list[dict], job: dict, cases: list[dict]) -> None:
    """Validate every warm-up and measurement against its recorded test input."""
    groups = job.get('bases', []) if job['scheme'] in ('cbrp-dl','ktx-cbrp') else ['']
    if len(rows) != len(groups) * len(cases):
        raise ValueError('raw sample count mismatch')
    actual_groups = {str(row.get('base','')) for row in rows}
    if actual_groups != {str(b) for b in groups}:
        raise ValueError('unexpected or missing base')
    ids = set()
    for b in groups:
        subset = [row for row in rows if str(row.get('base','')) == str(b)]
        if len(subset) != len(cases):
            raise ValueError('missing configuration samples')
        for row, case in zip(subset, cases):
            if row['scheme'] != job['scheme'] or int(row['range_bits']) != job['bits']:
                raise ValueError('scheme/range mismatch')
            if row['phase'] != case['phase'] or int(row['iteration']) != int(case['iteration']):
                raise ValueError('sample phase/iteration mismatch')
            w,t = int(row['w']),int(row['t'])
            if w != int(case['w']) or t != int(case['t']) or not 0 <= t <= w < 2**job['bits']:
                raise ValueError('test input mismatch')
            if int(row['delta']) != w-t or int(row['verified']) != 1:
                raise ValueError('invalid delta or rejected proof')
            expected_value = w if job['scheme'] in ('cbrp-dl','ktx-cbrp') else w-t
            if int(row['value_proved']) != expected_value:
                raise ValueError('wrong value passed to proof implementation')
            for field in ['commit_ms','prove_ms','verify_ms']:
                if row.get(field,'') == '': raise ValueError('missing required timing')
            for field in TIMINGS:
                value = row.get(field,'')
                if value != '' and (not math.isfinite(float(value)) or float(value)<0):
                    raise ValueError('invalid timing sample')
            scheme = job['scheme']
            if scheme in ('cbrp-dl','ktx-cbrp'):
                n = (job['bits'] + int(b).bit_length()-2) // (int(b).bit_length()-1)
                ell = branch_count(t,int(b),job['bits'])
                if int(row['n']) != n or int(row['ell']) != ell:
                    raise ValueError('branch count does not match the actual threshold')
                if int(row['table_entries']) != n*int(b):
                    raise ValueError('table entry count mismatch')
                if scheme == 'cbrp-dl':
                    expected_size = 65*ell*n + 32*ell
                    expected_table = 130*n*int(b)
                    cid = row.get('credential_id','')
                    if len(cid)!=64 or any(c not in '0123456789abcdef' for c in cid) or cid in ids:
                        raise ValueError('missing, malformed or reused credential identifier')
                    ids.add(cid)
                    if row.get('table_check_ms','') == '' or row.get('challenge_ms','') == '':
                        raise ValueError('missing credential check/challenge timing')
                else:
                    rho = int(row['rho'])
                    if rho != job['rho']: raise ValueError('rho mismatch')
                    counts = [int(row[f'challenge{i}_count']) for i in (1,2,3)]
                    if min(counts)<0 or sum(counts)!=rho: raise ValueError('invalid challenge counts')
                    dim=n*512+ell
                    expected_size=rho*(96+64+(dim*12+7)//8)+counts[0]*((dim+7)//8)+(counts[1]+counts[2])*32
                    expected_table=(n*int(b)*128*12+7)//8
                if int(row['table_bytes']) != expected_table:
                    raise ValueError('table size mismatch')
            else:
                expected_size={'bulletproofs':{32:622,64:688},'flashproofs':{32:746,64:1005}}[scheme][job['bits']]
                if scheme=='flashproofs' and (int(row['K']),int(row['L'])) != {32:(3,11),64:(4,16)}[job['bits']]:
                    raise ValueError('incorrect Flashproofs K/L')
            if int(row['proof_bytes']) != expected_size:
                raise ValueError('proof-size mismatch')


def annotate(rows: list[dict], repeat: int, job: int, mode: str) -> list[dict]:
    output=[]
    for original in rows:
        row={k: original.get(k,'') for k in SAMPLE_FIELDS}
        row.update(repeat=repeat,job=job,dependency_mode=mode)
        row['measured_total_ms']=format(sum(float(row[k]) for k in TIMINGS[:-1] if row[k]!=''),'.9f')
        output.append(row)
    return output


def summarize(rows: list[dict], warmups: list[dict] = ()) -> list[dict]:
    groups={}
    for row in rows:
        if row['phase']!='measure':raise ValueError('only measured rows belong in samples.csv')
        key=tuple(str(row.get(k,'')) for k in GROUP)
        groups.setdefault(key,[]).append(row)
    output=[]
    for key, samples in groups.items():
        result=dict(zip(GROUP,key))
        result.update(iterations=len(samples),warmup=sum(tuple(str(r.get(k,'')) for k in GROUP)==key for r in warmups))
        for field in TIMINGS+['proof_bytes','ell']:
            values=[float(r[field]) for r in samples if r.get(field,'')!='']
            if values and len(values)!=len(samples):raise ValueError('partially missing metric')
            if values and any(not math.isfinite(v) or v<0 for v in values):raise ValueError('invalid metric')
            result[field+'_mean']=statistics.fmean(values) if values else ''
            result[field+'_stddev']=statistics.stdev(values) if len(values)>1 else ''
            result[field+'_min']=min(values) if values else ''
            result[field+'_max']=max(values) if values else ''
        for field in ['table_entries','table_bytes']:
            values={str(r.get(field,'')) for r in samples}
            if len(values)!=1:raise ValueError('inconsistent table dimensions')
            result[field]=values.pop()
        output.append(result)
    return output
