/*
 * Copyright (c) 2026 You-Lin Hou
 * SPDX-License-Identifier: BSD-2-Clause
 * See LICENSES/BSD-2-Clause.txt.
 */
package research.baselines.hashwires;

import org.hashwires.HashWires;
import research.cbrp.bench.BenchmarkData;

import java.math.BigInteger;
import java.nio.file.Path;
import java.security.SecureRandom;
import java.util.List;
import java.util.Map;

/**
 * Same-JVM SHA-256 benchmark driver for the ordinary one-time HashWires
 * comparison baseline. The protocol implementation itself is kept under
 * {@code third_party/hashwires}; this class only adapts it to the artifact's
 * shared CSV fixtures, timing fields, and result format.
 */
public final class HashWiresRangeBench {
    private static final SecureRandom RNG = new SecureRandom();

    private HashWiresRangeBench() {}

    public static void main(String[] args) throws Exception {
        if (args.length != 6 && args.length != 7) {
            throw new IllegalArgumentException(
                    "Use scripts/run.py; expected bits bases warmup iterations input.csv samples.csv [allow-repeated]");
        }
        boolean allowRepeated = args.length == 7 && args[6].equals("allow-repeated");
        if (args.length == 7 && !allowRepeated) {
            throw new IllegalArgumentException("unknown fixture mode");
        }
        int bits = Integer.parseInt(args[0]);
        int[] bases = parseBases(args[1], bits);
        int warmup = Integer.parseInt(args[2]);
        int iterations = Integer.parseInt(args[3]);
        List<BenchmarkData.Case> cases = BenchmarkData.read(
                Path.of(args[4]), bits, warmup, iterations, !allowRepeated);

        try (BenchmarkData.Csv csv = new BenchmarkData.Csv(Path.of(args[5]))) {
            for (int base : bases) {
                int n = HashWires.maximumDigits(bits, base);
                for (BenchmarkData.Case c : cases) {
                    System.err.printf("hashwires base=%d phase=%s iteration=%d%n",
                            base, c.phase(), c.iteration());
                    // Match the upstream benchmark boundary: random issuer-seed
                    // generation is setup work and is excluded from all timed regions.
                    byte[] seed = new byte[HashWires.SEED_BYTES];
                    RNG.nextBytes(seed);
                    HashWires.Secret secret = HashWires.secret(seed, c.w());

                    long begin = System.nanoTime();
                    HashWires.Commitment commitment = secret.commit(base, bits);
                    long commitNs = System.nanoTime() - begin;

                    // Upstream proof generation reconstructs commitment-related
                    // state in order to build the selected Merkle inclusion path.
                    begin = System.nanoTime();
                    HashWires.Proof proof = secret.prove(base, bits, c.t());
                    long proveNs = System.nanoTime() - begin;

                    begin = System.nanoTime();
                    boolean verified = commitment.verify(proof, c.t());
                    long verifyNs = System.nanoTime() - begin;
                    if (!verified) {
                        throw new IllegalStateException("HashWires verification failed");
                    }

                    Map<String, String> row = BenchmarkData.row("hashwires", bits, c);
                    BenchmarkData.value(row, "base", base);
                    BenchmarkData.value(row, "n", n);
                    BenchmarkData.value(row, "ell",
                            HashWires.minimumDominatingPartition(c.w(), base).size());
                    BenchmarkData.value(row, "value_proved", c.w());
                    BenchmarkData.timing(row, "commit_ms", commitNs);
                    BenchmarkData.timing(row, "prove_ms", proveNs);
                    BenchmarkData.timing(row, "verify_ms", verifyNs);
                    // Report the actual canonical Java proof bytes, not Java
                    // object size or an asymptotic estimate.
                    BenchmarkData.value(row, "proof_bytes", proof.serialize().length);
                    BenchmarkData.value(row, "proof_size_basis", "actual-serialization");
                    BenchmarkData.value(row, "timing_scope",
                            "fresh-one-time-workflow-with-proof-side-recomputation");
                    BenchmarkData.value(row, "verified", 1);
                    csv.write(row);
                }
            }
        }
        System.out.println("HASHWIRES BENCH PASS");
    }

    private static int[] parseBases(String input, int bits) {
        String[] parts = input.split(",", -1);
        if (parts.length == 0) {
            throw new IllegalArgumentException("at least one base is required");
        }
        int[] result = new int[parts.length];
        java.util.Set<Integer> seen = new java.util.HashSet<>();
        for (int i = 0; i < parts.length; i++) {
            result[i] = Integer.parseInt(parts[i]);
            HashWires.maximumDigits(bits, result[i]); // validates base/range compatibility
            if (!seen.add(result[i])) {
                throw new IllegalArgumentException("duplicate base");
            }
        }
        return result;
    }
}
