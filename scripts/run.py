#!/usr/bin/env python3
# Copyright (c) 2026 You-Lin Hou
# SPDX-License-Identifier: BSD-2-Clause
# See LICENSES/BSD-2-Clause.txt.
"""Run randomized Java benchmarks and save raw samples and summaries as CSV."""
from __future__ import annotations
import argparse
import json
import re
import secrets
import subprocess
import sys
from pathlib import Path
from common import ROOT, MODULES, current_build, environment, inventory, java_cmd, new_run, sha256, write_json
from inputs import SAMPLING, generate_cases, write_cases, read_cases
from results_io import read_csv, check_rows, annotate, summarize, write_csv, SAMPLE_FIELDS, SUMMARY_FIELDS


def validate_job(job):
    if job.get('scheme') not in MODULES or job.get('bits') not in (32,64):
        raise ValueError('use cbrp-dl/bulletproofs/flashproofs and 32/64 bits')
    for field, minimum in [('warmup',0),('iterations',1)]:
        if type(job.get(field)) is not int or job[field]<minimum:
            raise ValueError(f'{field} must be integer >= {minimum}')
    if job['scheme']=='cbrp-dl':
        bases=job.get('bases',[])
        if not bases or any(type(b) is not int or b not in (16,256,65536) for b in bases) or len(set(bases))!=len(bases):
            raise ValueError('distinct bases drawn from 16,256,65536 required')


def command(job, input_path, sample_path, heap):
    s,bits,warm,it=job['scheme'],job['bits'],job['warmup'],job['iterations']
    if s=='cbrp-dl':
        main='CBRPDLFull';args=[bits,','.join(map(str,job['bases'])),warm,it,input_path,sample_path]
    elif s=='bulletproofs':
        main='edu.stanford.cs.crypto.BulletproofRangeBench';args=[bits,warm,it,input_path,sample_path]
    else:
        main='FlashproofRangeBench';args=[bits,11 if bits==32 else 16,warm,it,input_path,sample_path]
    return java_cmd(s,main,args,heap)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    group=p.add_mutually_exclusive_group()
    group.add_argument('--profile', help='smoke (default), random-java, or a profile JSON path')
    group.add_argument('--scheme', choices=MODULES)
    p.add_argument('--bits', type=int, default=32)
    p.add_argument('--bases', default='16,256')
    p.add_argument('--warmup', type=int)
    p.add_argument('--iterations', type=int)
    p.add_argument('--seed', type=int, help='public test-input seed; omitted means generate and record a new seed')
    p.add_argument('--repeat', type=int, default=1, help='independent JVM executions and fixture schedules')
    p.add_argument('--heap', default='2g')
    p.add_argument('--timeout', type=int, default=0, help='per-JVM seconds; 0=no timeout')
    a=p.parse_args()
    if a.repeat<1 or a.timeout<0 or (a.seed is not None and a.seed<0):p.error('repeat>=1, timeout>=0, seed>=0 required')
    if a.scheme:
        job=dict(scheme=a.scheme,bits=a.bits,warmup=a.warmup if a.warmup is not None else (10 if a.scheme=='cbrp-dl' else 5),
                 iterations=a.iterations if a.iterations is not None else (50 if a.scheme=='cbrp-dl' else 20))
        if a.scheme=='cbrp-dl':job['bases']=[int(b) for b in a.bases.split(',')]
        cfg={'jobs':[job]};label=a.scheme
    else:
        label=a.profile or 'smoke';path=Path(label)
        if not path.is_file():path=ROOT/'config/profiles'/(label+'.json')
        cfg=json.loads(path.read_text());label=path.stem
        for job in cfg['jobs']:
            if a.warmup is not None:job['warmup']=a.warmup
            if a.iterations is not None:job['iterations']=a.iterations
    if not cfg.get('jobs'):raise ValueError('empty profile')
    for job in cfg['jobs']:validate_job(job)
    builds={s:current_build(s) for s in {j['scheme'] for j in cfg['jobs']}}
    command(cfg['jobs'][0],ROOT/'input-placeholder.csv',ROOT/'output-placeholder.csv',a.heap)
    seed=a.seed if a.seed is not None else secrets.randbits(128)
    out=new_run(label)
    meta={'status':'RUNNING','implementation_revision':'randomized-v3','sampling':SAMPLING,'input_seed':str(seed),
          'environment':environment(),'configuration':cfg,'repeat':a.repeat,'builds':builds,'jobs':[],
          'sources':inventory(sorted((ROOT/'scripts').glob('*.py'))),
          'workload':'Fresh w,t each execution; fresh CBRP credential per execution; baselines prove a range for delta=w-t.',
          'input_files':[]}
    write_json(out/'metadata.json',meta); measured=[];warmups=[];setups=[]
    try:
        schedules={}
        for repeat in range(1,a.repeat+1):
            for bits in sorted({j['bits'] for j in cfg['jobs']}):
                jobs=[j for j in cfg['jobs'] if j['bits']==bits]
                nw=max(j['warmup'] for j in jobs);ni=max(j['iterations'] for j in jobs)
                path=out/f'inputs-r{repeat}-b{bits}.csv'
                write_cases(path,generate_cases(bits,nw,ni,seed,repeat))
                schedules[repeat,bits]=path
                meta['input_files'].append({'file':path.name,'sha256':sha256(path),'repeat':repeat,'bits':bits})
        write_json(out/'metadata.json',meta)
        index=0
        for repeat in range(1,a.repeat+1):
            for job in cfg['jobs']:
                index+=1;prefix=f'{index:02d}-{job["scheme"]}-{job["bits"]}'
                stdout,stderr,samples=[out/(prefix+ext) for ext in ('.stdout.log','.stderr.log','.samples.csv')]
                fixture=schedules[repeat,job['bits']]
                cases=read_cases(fixture,job['bits'],job['warmup'],job['iterations'])
                cmd=command(job,fixture,samples,a.heap)
                entry={'parameters':job,'command':cmd,'repeat':repeat,'status':'RUNNING','stdout':stdout.name,
                       'stderr':stderr.name,'samples':samples.name,'inputs':fixture.name}
                meta['jobs'].append(entry);write_json(out/'metadata.json',meta)
                print(f'[{index}] {job["scheme"]} bits={job["bits"]} bases={job.get("bases","-")} warmup={job["warmup"]} iterations={job["iterations"]}',flush=True)
                if job['scheme']=='cbrp-dl':print('  Fresh credential EVERY round; progress is recorded in '+stderr.name,flush=True)
                with stdout.open('w') as so,stderr.open('w') as se:
                    proc=subprocess.run(cmd,stdout=so,stderr=se,timeout=a.timeout or None)
                entry['exit_code']=proc.returncode
                if proc.returncode:raise RuntimeError(f'JVM failed; read {stderr}')
                raw=read_csv(samples);check_rows(raw,job,cases)
                entry['samples_sha256']=sha256(samples)
                for row in annotate(raw,repeat,index,builds[job['scheme']]['dependencies']['mode']):
                    (measured if row['phase']=='measure' else warmups).append(row)
                for line in stderr.read_text().splitlines():
                    match=re.fullmatch(r'(?:base=(\d+),)?([a-z_]+_ms)=([0-9.]+)',line)
                    if match:setups.append(dict(job=index,repeat=repeat,scheme=job['scheme'],range_bits=job['bits'],base=match[1] or '',metric=match[2],milliseconds=match[3]))
                entry['status']='PASS'
                write_csv(out/'samples.csv',measured,SAMPLE_FIELDS)
                write_csv(out/'warmup.csv',warmups,SAMPLE_FIELDS)
                write_csv(out/'summary.csv',summarize(measured,warmups),SUMMARY_FIELDS)
                write_csv(out/'setup.csv',setups,['job','repeat','scheme','range_bits','base','metric','milliseconds'])
                write_json(out/'metadata.json',meta)
        meta['status']='PASS'
    except (Exception,KeyboardInterrupt) as e:
        meta['status']='FAILED';meta['error']=str(e)
        if meta['jobs'] and meta['jobs'][-1]['status']=='RUNNING':meta['jobs'][-1]['status']='FAILED'
        raise
    finally:
        meta['csv_files']=[{'file':p.name,'sha256':sha256(p)} for p in sorted(out.glob('*.csv'))]
        write_json(out/'metadata.json',meta);(out/'STATUS').write_text(meta['status']+'\n')
        print('Results: '+str(out),flush=True)
    print('RUN PASS')


if __name__=='__main__':
    try:main()
    except (OSError,ValueError,KeyError,RuntimeError,subprocess.SubprocessError) as e:
        print('RUN FAILED: '+str(e),file=sys.stderr);sys.exit(1)
