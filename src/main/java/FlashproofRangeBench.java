/*
 * Copyright (C) 2026 You-Lin Hou
 * SPDX-License-Identifier: GPL-3.0-only
 *
 * This file is free software: you can redistribute it and/or modify it
 * under the terms of the GNU General Public License, version 3.
 * It is distributed WITHOUT ANY WARRANTY; without even the implied
 * warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSES/GPL-3.txt for the complete license.
 *
 * 2026-09-30: Project-specific Flashproofs benchmark/test integration;
 * upstream source files and their copyright notices are retained.
 */
import commitment.Commiter;
import config.BouncyKey;
import config.Config;
import zkp.range.RangeZKPK3;
import zkp.range.RangeZKPK4;

import java.lang.reflect.Field;
import java.math.BigInteger;
import java.util.List;
import java.util.Map;
import java.nio.file.Path;
import research.cbrp.bench.BenchmarkData;

public final class FlashproofRangeBench {

    private static Object makeProof(BigInteger x, int bits, int L) {
        if (bits <= 32) {
            return new RangeZKPK3(x, bits, L);
        } else {
            return new RangeZKPK4(x, bits, L);
        }
    }

    private static boolean verifyProof(Object proof) {
        if (proof instanceof RangeZKPK3) {
            return ((RangeZKPK3) proof).verify();
        } else if (proof instanceof RangeZKPK4) {
            return ((RangeZKPK4) proof).verify();
        }
        throw new IllegalArgumentException("unsupported proof type");
    }

    private static int sizeOf(Object proof, String fieldName) throws Exception {
        Field field = proof.getClass().getDeclaredField(fieldName);
        field.setAccessible(true);
        return ((List<?>) field.get(proof)).size();
    }

    private static int pointCount(Object proof) throws Exception {
        return sizeOf(proof, "cqs")
                + sizeOf(proof, "css")
                + sizeOf(proof, "cts");
    }

    private static int scalarCount(Object proof) throws Exception {
        return sizeOf(proof, "vs") + 2;
    }

    /** Baseline proves a range for delta=w-t, not issuer certification of the original w. */
    public static void main(String[] args) throws Exception {
        if(args.length!=6) throw new IllegalArgumentException("Use scripts/run.py; expected bits L warmup iterations input.csv samples.csv");
        int bits=Integer.parseInt(args[0]),L=Integer.parseInt(args[1]),warm=Integer.parseInt(args[2]),iters=Integer.parseInt(args[3]);
        if(L!=(bits==32?11:16)) throw new IllegalArgumentException("L=11 for 32 bits; L=16 for 64 bits");
        int K=bits==32?3:4;
        List<BenchmarkData.Case> cases=BenchmarkData.read(Path.of(args[4]),bits,warm,iters);
        long setup=System.nanoTime();
        Config.getInstance().init(new BouncyKey("bn128"));Commiter commiter=Config.getInstance().getCommiter();
        System.err.printf(java.util.Locale.ROOT,"public_setup_ms=%.9f%n",(System.nanoTime()-setup)/1e6);
        try(BenchmarkData.Csv csv=new BenchmarkData.Csv(Path.of(args[5]))) {
            for(BenchmarkData.Case c:cases) {
                BigInteger x=c.delta();
                // Standalone commitment timing; the proof constructor has its own internal commitments.
                long begin=System.nanoTime();commiter.commitTo(x);long commitNs=System.nanoTime()-begin;
                begin=System.nanoTime();Object proof=makeProof(x,bits,L);long proveNs=System.nanoTime()-begin;
                begin=System.nanoTime();boolean ok=verifyProof(proof);long verifyNs=System.nanoTime()-begin;
                Map<String,String> row=BenchmarkData.row("flashproofs",bits,c);
                BenchmarkData.value(row,"K",K);BenchmarkData.value(row,"L",L);BenchmarkData.value(row,"value_proved",x);
                BenchmarkData.timing(row,"commit_ms",commitNs);BenchmarkData.timing(row,"prove_ms",proveNs);BenchmarkData.timing(row,"verify_ms",verifyNs);
                BenchmarkData.value(row,"proof_bytes",pointCount(proof)*33+scalarCount(proof)*32);
                BenchmarkData.value(row,"verified",ok?1:0);csv.write(row);
                if(!ok) throw new IllegalStateException("verification failed");
            }
        }
        System.out.println("FLASHPROOFS BENCH PASS");
    }
}
