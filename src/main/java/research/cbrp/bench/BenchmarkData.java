/*
 * Copyright (c) 2026 You-Lin Hou
 * SPDX-License-Identifier: BSD-2-Clause
 * See LICENSES/BSD-2-Clause.txt.
 */
package research.cbrp.bench;

import java.io.IOException;
import java.io.PrintWriter;
import java.math.BigInteger;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.*;

/** Shared public test-case input and per-execution CSV output. No protocol RNG. */
public final class BenchmarkData {
    private BenchmarkData() {}
    public record Case(String phase, int iteration, BigInteger w, BigInteger t) {
        public BigInteger delta() { return w.subtract(t); }
    }
    public static final String HEADER = "scheme,range_bits,base,n,ell,K,L,rho,phase,iteration,w,t,delta,value_proved,credential_id,public_matrix_seed,commit_ms,standalone_commit_ms,table_check_ms,prove_ms,challenge_ms,verify_ms,proof_bytes,proof_size_basis,timing_scope,table_entries,table_bytes,verified";

    public static List<Case> read(Path file, int bits, int warmup, int iterations) throws IOException {
        return read(file, bits, warmup, iterations, true);
    }
    public static List<Case> read(
            Path file, int bits, int warmup, int iterations, boolean requireDistinct) throws IOException {
        if ((bits != 32 && bits != 64) || warmup < 0 || iterations < 1)
            throw new IllegalArgumentException("bits=32/64, warmup>=0, iterations>=1 required");
        List<String> lines = Files.readAllLines(file, StandardCharsets.UTF_8);
        if (lines.isEmpty() || !lines.get(0).equals("phase,iteration,range_bits,w,t"))
            throw new IllegalArgumentException("unexpected fixture CSV header");
        BigInteger N = BigInteger.ONE.shiftLeft(bits);
        Set<BigInteger> ws = new HashSet<>(), ts = new HashSet<>();
        int nw = 0, nm = 0;
        boolean measureStarted = false;
        List<Case> out = new ArrayList<>();
        for (int line = 1; line < lines.size(); line++) {
            String[] p = lines.get(line).split(",", -1);
            if (p.length != 5) throw new IllegalArgumentException("invalid fixture row " + (line+1));
            String phase = p[0]; int index = Integer.parseInt(p[1]);
            BigInteger w = new BigInteger(p[3]), t = new BigInteger(p[4]);
            if (Integer.parseInt(p[2]) != bits || t.signum() < 0 || t.compareTo(w) > 0 || w.compareTo(N) >= 0)
                throw new IllegalArgumentException("fixture outside 0<=t<=w<N");
            boolean newW = ws.add(w), newT = ts.add(t);
            if (requireDistinct && (!newW || !newT))
                throw new IllegalArgumentException("w and t must each be distinct within a fixture schedule");
            if (phase.equals("warmup")) {
                if (measureStarted || index != ++nw) throw new IllegalArgumentException("invalid warmup order");
                if (index <= warmup) out.add(new Case(phase,index,w,t));
            } else if (phase.equals("measure")) {
                measureStarted = true;
                if (index != ++nm) throw new IllegalArgumentException("invalid measurement order");
                if (index <= iterations) out.add(new Case(phase,index,w,t));
            } else throw new IllegalArgumentException("invalid fixture phase");
        }
        if (nw < warmup || nm < iterations) throw new IllegalArgumentException("insufficient fixture rows");
        return List.copyOf(out);
    }
    public static Map<String,String> row(String scheme, int bits, Case c) {
        Map<String,String> row = new LinkedHashMap<>();
        row.put("scheme",scheme); row.put("range_bits",Integer.toString(bits));
        row.put("phase",c.phase()); row.put("iteration",Integer.toString(c.iteration()));
        row.put("w",c.w().toString()); row.put("t",c.t().toString()); row.put("delta",c.delta().toString());
        return row;
    }
    public static void value(Map<String,String> row, String key, Object value) { row.put(key,value.toString()); }
    public static void timing(Map<String,String> row, String key, long ns) {
        row.put(key,String.format(Locale.ROOT,"%.9f",ns/1e6));
    }
    public static final class Csv implements AutoCloseable {
        private final PrintWriter out;
        public Csv(Path path) throws IOException {
            out = new PrintWriter(Files.newBufferedWriter(path,StandardCharsets.UTF_8));
            out.println(HEADER); out.flush();
        }
        public void write(Map<String,String> row) throws IOException {
            String[] fields = HEADER.split(","); List<String> cells = new ArrayList<>();
            for (String field : fields) {
                String v = row.getOrDefault(field,"");
                if (v.contains(",") || v.contains("\n") || v.contains("\r") || v.contains("\""))
                    throw new IllegalArgumentException("invalid numeric CSV field");
                cells.add(v);
            }
            out.println(String.join(",",cells)); out.flush();
            if (out.checkError()) throw new IOException("writing benchmark CSV failed");
        }
        @Override public void close() throws IOException {
            out.close();
            if (out.checkError()) throw new IOException("closing benchmark CSV failed");
        }
    }
}
