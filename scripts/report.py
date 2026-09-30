#!/usr/bin/env python3
"""Validate a completed run and recompute CSV summaries, or copy historical CSV tables."""
from __future__ import annotations
import argparse
import json
import shutil
import sys
from pathlib import Path
from common import ROOT, new_run, sha256
from inputs import read_cases
from results_io import read_csv, check_rows, annotate, summarize, write_csv, SAMPLE_FIELDS, SUMMARY_FIELDS


def validate_run(run: Path):
    meta=json.loads((run/'metadata.json').read_text())
    if meta.get('status')!='PASS' or (run/'STATUS').read_text().strip()!='PASS':
        raise ValueError('refusing failed or incomplete run')
    if meta.get('implementation_revision')!='randomized-v3':
        raise ValueError('unsupported run schema; historical values are available with --reference')
    for record in meta['csv_files']:
        if Path(record['file']).name != record['file']:raise ValueError('invalid run filename')
        file=run/record['file']
        if not file.is_file() or sha256(file)!=record['sha256']:
            raise ValueError('CSV hash mismatch: '+record['file'])
    measured=[];warmups=[]
    for index, entry in enumerate(meta['jobs'],1):
        if entry['status']!='PASS':raise ValueError('unfinished job')
        job=entry['parameters'];repeat=entry['repeat']
        for name in ('inputs','samples'):
            if Path(entry[name]).name!=entry[name]:raise ValueError('invalid job filename')
        cases=read_cases(run/entry['inputs'],job['bits'],job['warmup'],job['iterations'])
        rows=read_csv(run/entry['samples']);check_rows(rows,job,cases)
        mode=('numpy-'+meta['numpy']) if job['scheme']=='ktx-cbrp' else meta['builds'][job['scheme']]['dependencies']['mode']
        for row in annotate(rows,repeat,index,mode):
            (measured if row['phase']=='measure' else warmups).append(row)
    # Combined rows and summaries must match recomputation, not merely carry hashes.
    combined=read_csv(run/'samples.csv')
    warm=read_csv(run/'warmup.csv')
    def strings(rows):return [{k:str(v) for k,v in r.items()} for r in rows]
    if strings(measured)!=combined or strings(warmups)!=warm:
        raise ValueError('combined samples do not match per-job CSV files')
    summary=summarize(measured,warmups)
    stored=read_csv(run/'summary.csv')
    if strings(summary)!=stored:raise ValueError('summary differs from recomputed sample statistics')
    return measured,warmups,summary


def main():
    p=argparse.ArgumentParser(description=__doc__)
    group=p.add_mutually_exclusive_group(required=True)
    group.add_argument('--reference',action='store_true',help='copy historical thesis CSV values; do not execute proofs')
    group.add_argument('--run',type=Path,help='completed randomized run directory')
    a=p.parse_args()
    if a.reference:
        out=new_run('historical-reference',parent='reports')
        for file in sorted((ROOT/'results/reference').glob('*.csv')):shutil.copyfile(file,out/file.name)
        write_csv(out/'source.csv',[{'kind':'historical-reference','source':'results/reference','note':'Stored thesis values, not new measurements.'}])
    else:
        run=a.run.expanduser().resolve()
        measured,warmups,summary=validate_run(run)
        out=new_run('randomized-report',parent='reports')
        write_csv(out/'samples.csv',measured,SAMPLE_FIELDS)
        write_csv(out/'warmup.csv',warmups,SAMPLE_FIELDS)
        write_csv(out/'summary.csv',summary,SUMMARY_FIELDS)
        shutil.copyfile(run/'setup.csv',out/'setup.csv')
        write_csv(out/'source.csv',[{'kind':'randomized-fresh-credential','source':run.name,'metadata_sha256':sha256(run/'metadata.json'),
                                   'note':'Randomized inputs; no same-credential reuse or amortization estimate.'}])
    print('REPORT PASS: '+str(out))


if __name__=='__main__':
    try:main()
    except (OSError,ValueError,KeyError) as e:
        print('REPORT FAILED: '+str(e),file=sys.stderr);sys.exit(1)
