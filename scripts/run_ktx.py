#!/usr/bin/env python3
"""Randomized KTX-CBRP functional prototype; CSV measurements, not a security benchmark."""
from __future__ import annotations
import argparse
import json
import secrets
import sys
import time
from pathlib import Path
from common import ROOT, environment, inventory, new_run, sha256, write_json
from inputs import SAMPLING, derive_seed, generate_cases, write_cases, read_cases
from results_io import check_rows, annotate, summarize, write_csv, RAW_FIELDS, SAMPLE_FIELDS, SUMMARY_FIELDS
sys.path.insert(0,str(ROOT/'experiments/ktx'))
from cbrp_ktx_poc import CBRP_KTX, Q_MOD, N_L, M_COL, RHO, challenge_vector, dedp
import numpy as np


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--profile',choices=['random-ktx'])
    p.add_argument('--bits',type=int,choices=[16,32,64],default=16)
    p.add_argument('--bases',default='16,256')
    p.add_argument('--rho',type=int)
    p.add_argument('--seed',type=int,help='public input/matrix seed; not a protocol-nonce seed')
    p.add_argument('--warmup',type=int)
    p.add_argument('--iterations',type=int)
    p.add_argument('--repeat',type=int,default=1)
    a=p.parse_args()
    if a.profile:
        cfg=json.loads((ROOT/'config/profiles/random-ktx.json').read_text())
    else:
        cfg=dict(bits=[a.bits],bases=[int(b) for b in a.bases.split(',')],rho=RHO,warmup=0,iterations=3,q=Q_MOD,nL=N_L,m=M_COL)
    for key in ('rho','warmup','iterations'):
        if getattr(a,key) is not None:cfg[key]=getattr(a,key)
    if (cfg['q'],cfg['nL'],cfg['m'])!=(Q_MOD,N_L,M_COL):p.error('q/nL/m are fixed toy parameters')
    if not cfg['bits'] or any(b not in (16,32,64) for b in cfg['bits']) or len(set(cfg['bits']))!=len(cfg['bits']):p.error('distinct supported range bits required')
    if not 1<=cfg['rho']<=1000 or cfg['iterations']<1 or cfg['warmup']<0 or a.repeat<1 or (a.seed is not None and a.seed<0):p.error('invalid rho/count/seed')
    if not cfg['bases'] or any(b not in [16,256] for b in cfg['bases']) or len(set(cfg['bases']))!=len(cfg['bases']):p.error('distinct bases 16,256 required')
    seed=a.seed if a.seed is not None else secrets.randbits(128)
    out=new_run('random-ktx')
    meta={'status':'RUNNING','implementation_revision':'randomized-v3','sampling':SAMPLING,'input_seed':str(seed),
          'configuration':cfg,'repeat':a.repeat,'environment':environment(),'numpy':np.__version__,
          'sources':inventory([ROOT/'experiments/ktx/cbrp_ktx_poc.py',ROOT/'requirements.txt',*sorted((ROOT/'scripts').glob('*.py'))]),
          'scope':'Hash commitment placeholders; no issuer labels/signatures; toy parameters; not a security validation.',
          'input_files':[],'jobs':[]}
    write_json(out/'metadata.json',meta); measured=[];warmups=[];setups=[]
    try:
        index=0
        for repeat in range(1,a.repeat+1):
            for bits in cfg['bits']:
                fixture=out/f'inputs-r{repeat}-b{bits}.csv'
                write_cases(fixture,generate_cases(bits,cfg['warmup'],cfg['iterations'],seed,repeat))
                cases=read_cases(fixture,bits,cfg['warmup'],cfg['iterations'])
                meta['input_files'].append({'file':fixture.name,'sha256':sha256(fixture),'repeat':repeat,'bits':bits})
                for b in cfg['bases']:
                    index+=1
                    job=dict(scheme='ktx-cbrp',bits=bits,bases=[b],warmup=cfg['warmup'],iterations=cfg['iterations'],rho=cfg['rho'])
                    raw_path=out/f'{index:02d}-ktx-{bits}-b{b}.samples.csv'
                    entry={'parameters':job,'repeat':repeat,'inputs':fixture.name,'samples':raw_path.name,'status':'RUNNING'}
                    meta['jobs'].append(entry);write_json(out/'metadata.json',meta)
                    # Setup is once per configuration; each commit below creates a new table.
                    instance_seed=derive_seed(seed,f'ktx-matrix:bits={bits};base={b};repeat={repeat}')
                    begin=time.perf_counter_ns();s=CBRP_KTX(2**bits,b,seed=instance_seed);setup_ns=time.perf_counter_ns()-begin
                    setups.append(dict(job=index,repeat=repeat,scheme='ktx-cbrp',range_bits=bits,base=b,metric='public_matrix_setup_ms',milliseconds=setup_ns/1e6))
                    raw=[]
                    for c in cases:
                        w,t=int(c['w']),int(c['t'])
                        begin=time.perf_counter_ns();Y,aux=s.commit(w);commit_ns=time.perf_counter_ns()-begin
                        begin=time.perf_counter_ns();state=s.start(Y,aux,w,t,cfg['rho']);first_ns=time.perf_counter_ns()-begin
                        begin=time.perf_counter_ns();ch=challenge_vector(cfg['rho']);challenge_ns=time.perf_counter_ns()-begin
                        begin=time.perf_counter_ns();proof=s.respond(state,ch);prove_ns=first_ns+time.perf_counter_ns()-begin
                        begin=time.perf_counter_ns();ok=s.verify(Y,t,state.first,proof,ch,cfg['rho']);verify_ns=time.perf_counter_ns()-begin
                        ell=len(dedp(t,b,s.n,2**bits))
                        row={key:'' for key in RAW_FIELDS}
                        row.update(scheme='ktx-cbrp',range_bits=bits,base=b,n=s.n,ell=ell,rho=cfg['rho'],
                            phase=c['phase'],iteration=c['iteration'],w=str(w),t=str(t),delta=str(w-t),value_proved=str(w),
                            instance_seed=str(instance_seed),commit_ms=commit_ns/1e6,prove_ms=prove_ns/1e6,
                            challenge_ms=challenge_ns/1e6,verify_ms=verify_ns/1e6,proof_bytes=s.proof_bytes(ch,ell),
                            table_entries=s.n*b,table_bytes=s.table_bytes(),verified=int(ok),
                            challenge1_count=ch.count(1),challenge2_count=ch.count(2),challenge3_count=ch.count(3))
                        raw.append(row)
                        write_csv(raw_path,raw,RAW_FIELDS+['challenge1_count','challenge2_count','challenge3_count'])
                        check_rows([row],job,[c])
                        result=annotate([row],repeat,index,'numpy-'+np.__version__)[0]
                        (measured if c['phase']=='measure' else warmups).append(result)
                        write_csv(out/'samples.csv',measured,SAMPLE_FIELDS)
                        write_csv(out/'warmup.csv',warmups,SAMPLE_FIELDS)
                        write_csv(out/'summary.csv',summarize(measured,warmups),SUMMARY_FIELDS)
                        write_csv(out/'setup.csv',setups,['job','repeat','scheme','range_bits','base','metric','milliseconds'])
                        print(f'[{index}] KTX bits={bits} b={b} {c["phase"]}={c["iteration"]} ell={ell}: PASS',flush=True)
                    check_rows(raw,job,cases)
                    entry['status']='PASS';entry['samples_sha256']=sha256(raw_path)
                    write_json(out/'metadata.json',meta)
        meta['status']='PASS'
    except (Exception,KeyboardInterrupt) as e:
        meta['status']='FAILED';meta['error']=str(e)
        if meta['jobs'] and meta['jobs'][-1]['status']=='RUNNING':meta['jobs'][-1]['status']='FAILED'
        raise
    finally:
        meta['csv_files']=[{'file':p.name,'sha256':sha256(p)} for p in sorted(out.glob('*.csv'))]
        write_json(out/'metadata.json',meta);(out/'STATUS').write_text(meta['status']+'\n');print('Results: '+str(out))
    print('KTX POC PASS')


if __name__=='__main__':
    try:main()
    except (OSError,ValueError,KeyError,RuntimeError) as e:
        print('KTX RUN FAILED: '+str(e),file=sys.stderr);sys.exit(1)
