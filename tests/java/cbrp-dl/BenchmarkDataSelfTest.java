/*
 * Copyright (c) 2026 You-Lin Hou
 * SPDX-License-Identifier: BSD-2-Clause
 * See LICENSES/BSD-2-Clause.txt.
 */
import java.nio.file.Files;
import java.nio.file.Path;
import java.math.BigInteger;
import java.util.List;
import research.cbrp.bench.BenchmarkData;

public final class BenchmarkDataSelfTest {
    public static void main(String[] args) throws Exception {
        Path file=Files.createTempFile("cbrp-cases-",".csv");
        try {
            String head="phase,iteration,range_bits,w,t\n";
            String good=head+"warmup,1,64,18446744073709551615,0\nmeasure,1,64,9223372036854775931,9223372036854775931\nmeasure,2,64,100,90\n";
            Files.writeString(file,good);
            List<BenchmarkData.Case> rows=BenchmarkData.read(file,64,1,2);
            if(rows.size()!=3 || !rows.get(0).w().equals(BigInteger.ONE.shiftLeft(64).subtract(BigInteger.ONE)) || rows.get(1).delta().signum()!=0)
                throw new AssertionError("64-bit fixture precision");
            for(String bad:new String[]{good.replace("100,90","100,0"),good.replace("100,90","100,101"),good.replace("100,90","9223372036854775931,90"),good.replace("measure,2","measure,3")}) {
                Files.writeString(file,bad);boolean rejected=false;
                try {BenchmarkData.read(file,64,1,2);}catch(IllegalArgumentException e){rejected=true;}
                if(!rejected)throw new AssertionError("malformed/duplicate fixture accepted");
            }
            System.out.println("BENCHMARK DATA SELFTEST PASS: exact 64-bit values, phase/count/duplicate/range checks");
        } finally {Files.deleteIfExists(file);}
    }
}
