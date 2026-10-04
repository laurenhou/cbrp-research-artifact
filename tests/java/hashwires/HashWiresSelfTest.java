/*
 * Copyright (c) 2026 You-Lin Hou
 * SPDX-License-Identifier: BSD-2-Clause
 * See LICENSES/BSD-2-Clause.txt.
 */
import org.hashwires.HashWires;

import java.math.BigInteger;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.HexFormat;
import java.util.List;

public final class HashWiresSelfTest {
    private static int checks;

    private static void check(boolean condition, String message) {
        checks++;
        if (!condition) throw new AssertionError(message);
    }

    private static void rejects(Runnable action, String message) {
        checks++;
        try {
            action.run();
        } catch (IllegalArgumentException expected) {
            return;
        }
        throw new AssertionError(message);
    }

    private static BigInteger bi(long value) {
        return BigInteger.valueOf(value);
    }

    private static byte[] seed() {
        byte[] seed = new byte[32];
        for (int i = 0; i < seed.length; i++) seed[i] = (byte) i;
        return seed;
    }

    public static void main(String[] args) {
        List<BigInteger> mdp = HashWires.minimumDominatingPartition(new BigInteger("312", 4), 4);
        check(mdp.equals(List.of(new BigInteger("312", 4), new BigInteger("303", 4),
                new BigInteger("233", 4))), "base-4 MDP vector");
        check(HashWires.minimumDominatingPartition(BigInteger.valueOf(3413), 16).get(0)
                .equals(BigInteger.valueOf(3413)), "MDP starts with value");
        check(HashWires.minimumDominatingPartition(bi(9999), 16)
                .equals(List.of(bi(9999), bi(9983), bi(8191))), "upstream base-16 MDP vector");
        check(HashWires.minimumDominatingPartition(bi(254), 2)
                .equals(List.of(bi(254), bi(253), bi(251), bi(247), bi(239), bi(223), bi(191), bi(127))),
                "upstream base-2 MDP vector");
        check(HashWires.minimumDominatingPartition(bi(2), 2)
                .equals(List.of(bi(2), bi(1))), "exact-power MDP boundary");

        // Exhaust all true threshold statements in a small domain.
        for (int base : new int[] {2, 4, 16}) {
            for (int value = 0; value < 16; value++) {
                HashWires.Secret smallSecret = HashWires.secret(seed(), bi(value));
                HashWires.Commitment smallCommitment = smallSecret.commit(base, 4);
                for (int threshold = 0; threshold <= value; threshold++) {
                    HashWires.Proof smallProof = smallSecret.prove(base, 4, bi(threshold));
                    check(smallCommitment.verify(smallProof, bi(threshold)),
                            "exhaustive 4-bit proof base=" + base + " value=" + value
                                    + " threshold=" + threshold);
                    for (int falseThreshold = value + 1; falseThreshold < 16; falseThreshold++) {
                        check(!smallCommitment.verify(smallProof, bi(falseThreshold)),
                                "honest proof cannot be raised above issued value base=" + base
                                        + " value=" + value + " sourceThreshold=" + threshold
                                        + " falseThreshold=" + falseThreshold);
                    }
                }
            }
        }

        for (int base : new int[] {2, 4, 16, 256}) {
            for (int bits : new int[] {32, 64}) {
                BigInteger maximum = BigInteger.ONE.shiftLeft(bits).subtract(BigInteger.ONE);
                BigInteger value = maximum.subtract(BigInteger.ONE);
                for (BigInteger threshold : new BigInteger[] {
                        BigInteger.ZERO, BigInteger.ONE, value.shiftRight(1), value.subtract(BigInteger.ONE), value}) {
                    HashWires.Secret secret = HashWires.secret(seed(), value);
                    HashWires.Commitment commitment = secret.commit(base, bits);
                    HashWires.Proof proof = secret.prove(base, bits, threshold);
                    check(commitment.verify(proof, threshold), "honest proof base=" + base + " bits=" + bits);
                    check(proof.serialize().length == HashWires.expectedProofBytes(value, threshold, base, bits),
                            "proof-size formula");
                    HashWires.Commitment decodedCommitment = HashWires.Commitment.deserialize(
                            commitment.serialize(), base, bits);
                    HashWires.Proof decodedProof = HashWires.Proof.deserialize(
                            proof.serialize(), threshold, base, bits);
                    check(decodedCommitment.verify(decodedProof, threshold), "serialization round trip");
                    check(Arrays.equals(commitment.serialize(), secret.commit(base, bits).serialize()),
                            "deterministic commitment");
                    check(Arrays.equals(proof.serialize(), secret.prove(base, bits, threshold).serialize()),
                            "deterministic proof");
                }
            }
        }

        BigInteger n32 = BigInteger.ONE.shiftLeft(32);
        BigInteger w32 = n32.subtract(BigInteger.TWO);
        BigInteger t32 = w32.subtract(BigInteger.ONE);
        check(HashWires.secret(seed(), w32).prove(16, 32, t32).serialize().length == 369,
                "paper 32-bit HW16 size");
        check(HashWires.secret(seed(), w32).prove(256, 32, t32).serialize().length == 209,
                "paper 32-bit HW256 size");
        BigInteger n64 = BigInteger.ONE.shiftLeft(64);
        BigInteger w64 = n64.subtract(BigInteger.TWO);
        BigInteger t64 = w64.subtract(BigInteger.ONE);
        check(HashWires.secret(seed(), w64).prove(16, 64, t64).serialize().length == 657,
                "paper 64-bit HW16 size");
        check(HashWires.secret(seed(), w64).prove(256, 64, t64).serialize().length == 369,
                "paper 64-bit HW256 size");
        BigInteger paperT32 = n32.shiftRight(1).add(BigInteger.ONE);
        BigInteger paperT64 = n64.shiftRight(1).add(BigInteger.ONE);
        check(HashWires.secret(seed(), w32).prove(16, 32, paperT32).serialize().length == 369,
                "paper-fixed 32-bit HW16 size");
        check(HashWires.secret(seed(), w32).prove(256, 32, paperT32).serialize().length == 209,
                "paper-fixed 32-bit HW256 size");
        check(HashWires.secret(seed(), w64).prove(16, 64, paperT64).serialize().length == 657,
                "paper-fixed 64-bit HW16 size");
        check(HashWires.secret(seed(), w64).prove(256, 64, paperT64).serialize().length == 369,
                "paper-fixed 64-bit HW256 size");

        HashWires.Secret secret = HashWires.secret(seed(), bi(402));
        HashWires.Commitment commitment = secret.commit(4, 32);
        HashWires.Proof proof = secret.prove(4, 32, bi(378));
        check(HexFormat.of().formatHex(commitment.serialize()).equals(
                        "d289b4b66e5fbd29d3882c009337ca9e65f933de4bd0954bb13152d5b32a1a26"),
                "independent SHA-256 commitment vector");
        try {
            String proofDigest = HexFormat.of().formatHex(
                    MessageDigest.getInstance("SHA-256").digest(proof.serialize()));
            check(proofDigest.equals(
                            "7bd31d4b5409a2e346a514c42126df21d16b2e36a33eb01c454d8355a710b7f9"),
                    "independent SHA-256 proof vector");
        } catch (java.security.NoSuchAlgorithmException impossible) {
            throw new AssertionError(impossible);
        }
        check(proof.serialize().length == 337, "independent proof length vector");
        byte[] altered = proof.serialize();
        altered[0] ^= 1;
        HashWires.Proof alteredProof = HashWires.Proof.deserialize(altered, bi(378), 4, 32);
        check(!commitment.verify(alteredProof, bi(378)), "altered chain node rejected");
        int saltOffset = proof.chainNodeCount() * HashWires.HASH_BYTES;
        altered = proof.serialize();
        altered[saltOffset] ^= 1;
        check(!commitment.verify(HashWires.Proof.deserialize(altered, bi(378), 4, 32), bi(378)),
                "altered MDP salt rejected");
        altered = proof.serialize();
        altered[saltOffset + HashWires.MDP_SALT_BYTES] ^= 1;
        check(!commitment.verify(HashWires.Proof.deserialize(altered, bi(378), 4, 32), bi(378)),
                "altered leaf index rejected");
        altered = proof.serialize();
        altered[saltOffset + HashWires.MDP_SALT_BYTES + 1] ^= 1;
        check(!commitment.verify(HashWires.Proof.deserialize(altered, bi(378), 4, 32), bi(378)),
                "altered Merkle sibling rejected");
        if (proof.hasPlaPrefix()) {
            altered = proof.serialize();
            altered[altered.length - 1] ^= 1;
            check(!commitment.verify(HashWires.Proof.deserialize(altered, bi(378), 4, 32), bi(378)),
                    "altered PLA prefix rejected");
        }
        byte[] alteredRoot = commitment.serialize();
        alteredRoot[0] ^= 1;
        check(!HashWires.Commitment.deserialize(alteredRoot, 4, 32).verify(proof, bi(378)),
                "altered commitment rejected");
        check(!commitment.verify(proof, bi(377)),
                "selected altered-threshold case rejected (checksum mode is not implemented)");
        rejects(() -> secret.prove(4, 32, bi(403)), "false threshold must be rejected");
        rejects(() -> HashWires.Proof.deserialize(new byte[1], bi(378), 4, 32),
                "malformed proof must be rejected");
        rejects(() -> HashWires.secret(new byte[31], BigInteger.ONE), "wrong seed length");

        HashWires.Secret zero = HashWires.secret(seed(), BigInteger.ZERO);
        HashWires.Commitment zeroCommitment = zero.commit(16, 32);
        HashWires.Proof zeroProof = zero.prove(16, 32, BigInteger.ZERO);
        check(zeroCommitment.verify(zeroProof, BigInteger.ZERO), "zero boundary supported");

        byte[] secondSeed = seed();
        secondSeed[0] ^= 1;
        check(!Arrays.equals(secret.commit(4, 32).serialize(),
                        HashWires.secret(secondSeed, bi(402)).commit(4, 32).serialize()),
                "different issuer seeds give different commitments");
        rejects(() -> secret.commit(8, 32), "unsupported base rejected");
        rejects(() -> secret.commit(16, 31), "incompatible bit length rejected");
        rejects(() -> HashWires.Commitment.deserialize(new byte[31], 16, 32),
                "wrong commitment length rejected");

        System.out.println("HASHWIRES SELFTEST PASS: " + checks
                + " assertions (functional/regression checks, not a security proof)");
    }
}
