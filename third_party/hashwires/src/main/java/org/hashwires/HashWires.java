/*
 * Copyright (c) Facebook, Inc. and its affiliates.
 * Copyright (c) 2026 You-Lin Hou.
 *
 * This Java port is based on the MIT-licensed HashWires Rust implementation.
 * See third_party/hashwires/LICENSE and NOTICE.
 * SPDX-License-Identifier: MIT
 */
package org.hashwires;

import java.math.BigInteger;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

/**
 * Java 17 port of the optimized ordinary one-time HashWires baseline.
 * Protocol mapping, interoperability limits, and omitted options are recorded
 * in {@code third_party/hashwires/NOTICE}.
 */
public final class HashWires {
    public static final int HASH_BYTES = 32;
    public static final int MDP_SALT_BYTES = 16;
    public static final int SEED_BYTES = 32;

    // Domain-separation constants copied from upstream src/hashes.rs.
    private static final byte[] LEAF_SALT = ascii("01234567890123456789012345678901");
    private static final byte[] TOP_SALT = ascii("11234567890123456789012345678901");
    private static final byte[] PADDING_SALT = ascii("21234567890123456789012345678901");
    private static final byte[] SMTREE_PADDING_SALT = ascii("31234567890123456789012345678901");

    // Java-only domain separation for the counter sampler that replaces ChaCha12.
    private static final byte[] SHUFFLE_DOMAIN = ascii("HashWires/Java/SHA-256/shuffle/v1");

    private static final BigInteger ZERO = BigInteger.ZERO;
    private static final BigInteger ONE = BigInteger.ONE;
    private static final ThreadLocal<MessageDigest> SHA256 = ThreadLocal.withInitial(() -> {
        try {
            return MessageDigest.getInstance("SHA-256");
        } catch (NoSuchAlgorithmException e) {
            throw new ExceptionInInitializerError(e);
        }
    });

    private HashWires() {}

    public static Secret secret(byte[] seed, BigInteger value) {
        return new Secret(seed, value);
    }

    /** Paper Algorithm 1; the exact-power boundary uses {@code b^i <= value}. */
    public static List<BigInteger> minimumDominatingPartition(BigInteger value, int base) {
        requireSupportedBase(base);
        requireNonNegative(value, "value");
        List<BigInteger> result = new ArrayList<>();
        result.add(value);
        BigInteger exp = BigInteger.valueOf(base);
        BigInteger valuePlusOne = value.add(ONE);
        BigInteger previous = value;
        while (exp.compareTo(value) <= 0) {
            if (!valuePlusOne.mod(exp).equals(ZERO)) {
                BigInteger candidate = value.divide(exp).multiply(exp).subtract(ONE);
                if (!candidate.equals(previous)) {
                    result.add(candidate);
                    previous = candidate;
                }
            }
            exp = exp.multiply(BigInteger.valueOf(base));
        }
        return Collections.unmodifiableList(result);
    }

    public static int maximumDigits(int maxNumberBits, int base) {
        int digitBits = digitBits(base);
        if (maxNumberBits < 1 || maxNumberBits > 128 || maxNumberBits % digitBits != 0) {
            throw new IllegalArgumentException("maxNumberBits must be 1..128 and divisible by log2(base)");
        }
        int count = maxNumberBits / digitBits;
        if (Integer.bitCount(count) != 1 || count > 256) {
            throw new IllegalArgumentException("the maximum digit count must be a power of two no larger than 256");
        }
        return count;
    }

    public static int expectedProofBytes(
            BigInteger value, BigInteger threshold, int base, int maxNumberBits) {
        validateStatement(value, threshold, base, maxNumberBits);
        List<BigInteger> mdp = minimumDominatingPartition(value, base);
        int index = pickMdpIndex(threshold, mdp, base);
        int selectedDigits = significantDigits(mdp.get(index), base).length;
        int thresholdDigits = significantDigits(threshold, base).length;
        int maxDigits = maximumDigits(maxNumberBits, base);
        int height = treeHeight(maxDigits);
        boolean hasPlaPrefix = selectedDigits < maxDigits || selectedDigits > thresholdDigits;
        return thresholdDigits * HASH_BYTES + MDP_SALT_BYTES + 1 + height * HASH_BYTES
                + (hasPlaPrefix ? HASH_BYTES : 0);
    }

    public static final class Secret {
        private final BigInteger value;
        private final byte[] seed;

        private Secret(byte[] seed, BigInteger value) {
            Objects.requireNonNull(seed, "seed");
            requireNonNegative(value, "value");
            if (seed.length != SEED_BYTES) {
                throw new IllegalArgumentException("HashWires seed must be exactly 32 bytes");
            }
            this.seed = seed.clone();
            this.value = value;
        }

        public BigInteger value() {
            return value;
        }

        public Commitment commit(int base, int maxNumberBits) {
            validateValue(value, base, maxNumberBits);
            Generation generation = generate(value, null, base, maxNumberBits, seed);
            return new Commitment(base, maxNumberBits, generation.root);
        }

        public Proof prove(int base, int maxNumberBits, BigInteger threshold) {
            validateStatement(value, threshold, base, maxNumberBits);
            Generation generation = generate(value, threshold, base, maxNumberBits, seed);
            if (generation.proof == null) {
                throw new IllegalStateException("internal proof generation failure");
            }
            return generation.proof;
        }
    }

    public static final class Commitment {
        private final int base;
        private final int maxNumberBits;
        private final byte[] root;

        private Commitment(int base, int maxNumberBits, byte[] root) {
            requireSupportedBase(base);
            maximumDigits(maxNumberBits, base);
            if (root.length != HASH_BYTES) {
                throw new IllegalArgumentException("commitment root must be 32 bytes");
            }
            this.base = base;
            this.maxNumberBits = maxNumberBits;
            this.root = root.clone();
        }

        public int base() {
            return base;
        }

        public int maxNumberBits() {
            return maxNumberBits;
        }

        public byte[] serialize() {
            return root.clone();
        }

        public static Commitment deserialize(byte[] bytes, int base, int maxNumberBits) {
            Objects.requireNonNull(bytes, "bytes");
            return new Commitment(base, maxNumberBits, bytes);
        }

        public boolean verify(Proof proof, BigInteger threshold) {
            Objects.requireNonNull(proof, "proof");
            requireInRange(threshold, maxNumberBits, "threshold");
            int[] thresholdDigits = significantDigits(threshold, base);
            int maxDigits = maximumDigits(maxNumberBits, base);
            int height = treeHeight(maxDigits);
            if (proof.chainNodes.length != thresholdDigits.length
                    || proof.siblings.length != height
                    || proof.leafIndex < 0
                    || proof.leafIndex >= maxDigits) {
                return false;
            }

            // Reconstruct the selected MDP wire nodes by hashing each proof
            // node forward by the corresponding public threshold digit.
            byte[][] mdpWireNodes = new byte[thresholdDigits.length][];
            for (int i = 0; i < thresholdDigits.length; i++) {
                byte[] node = proof.chainNodes[i].clone();
                for (int j = 0; j < thresholdDigits[i]; j++) {
                    node = hash(node);
                }
                mdpWireNodes[i] = node;
            }

            // Continue the ordered PLA. A prefix is present when truncation or
            // deterministic padding must remain hidden from the verifier.
            byte[] mdpRoot = proof.plaPrefix == null ? null : proof.plaPrefix.clone();
            for (byte[] node : mdpWireNodes) {
                mdpRoot = mdpRoot == null ? hash(node) : hash(mdpRoot, node);
            }
            if (mdpRoot == null) {
                return false;
            }
            // Section 4.2 salts each MDP root before the top accumulator so a
            // verifier cannot brute-force alternate wirings of shared chains.
            byte[] saltedMdpRoot = hash(proof.mdpSalt, mdpRoot);
            byte[] computed = MerkleTree.recoverRoot(saltedMdpRoot, proof.leafIndex, proof.siblings);
            return MessageDigest.isEqual(root, computed);
        }
    }

    public static final class Proof {
        private final byte[][] chainNodes;
        private final byte[] mdpSalt;
        private final int leafIndex;
        private final byte[][] siblings;
        private final byte[] plaPrefix;

        private Proof(
                byte[][] chainNodes,
                byte[] mdpSalt,
                int leafIndex,
                byte[][] siblings,
                byte[] plaPrefix) {
            this.chainNodes = cloneMatrix(chainNodes, HASH_BYTES, "chain node");
            if (mdpSalt.length != MDP_SALT_BYTES) {
                throw new IllegalArgumentException("MDP salt must be 16 bytes");
            }
            if (leafIndex < 0 || leafIndex > 255) {
                throw new IllegalArgumentException("leaf index must fit one unsigned byte");
            }
            this.mdpSalt = mdpSalt.clone();
            this.leafIndex = leafIndex;
            this.siblings = cloneMatrix(siblings, HASH_BYTES, "Merkle sibling");
            if (plaPrefix != null && plaPrefix.length != HASH_BYTES) {
                throw new IllegalArgumentException("PLA prefix must be 32 bytes");
            }
            this.plaPrefix = plaPrefix == null ? null : plaPrefix.clone();
        }

        public int chainNodeCount() {
            return chainNodes.length;
        }

        public int merkleHeight() {
            return siblings.length;
        }

        public boolean hasPlaPrefix() {
            return plaPrefix != null;
        }

        public int serializedSize() {
            return chainNodes.length * HASH_BYTES + MDP_SALT_BYTES + 1
                    + siblings.length * HASH_BYTES + (plaPrefix == null ? 0 : HASH_BYTES);
        }

        public byte[] serialize() {
            ByteBuffer out = ByteBuffer.allocate(serializedSize());
            for (byte[] node : chainNodes) {
                out.put(node);
            }
            out.put(mdpSalt);
            out.put((byte) leafIndex);
            for (byte[] sibling : siblings) {
                out.put(sibling);
            }
            if (plaPrefix != null) {
                out.put(plaPrefix);
            }
            return out.array();
        }

        public static Proof deserialize(
                byte[] input, BigInteger threshold, int base, int maxNumberBits) {
            Objects.requireNonNull(input, "input");
            requireInRange(threshold, maxNumberBits, "threshold");
            requireSupportedBase(base);
            int nodeCount = significantDigits(threshold, base).length;
            int height = treeHeight(maximumDigits(maxNumberBits, base));
            int minimum = nodeCount * HASH_BYTES + MDP_SALT_BYTES + 1 + height * HASH_BYTES;
            boolean hasPrefix;
            if (input.length == minimum) {
                hasPrefix = false;
            } else if (input.length == minimum + HASH_BYTES) {
                hasPrefix = true;
            } else {
                throw new IllegalArgumentException("non-canonical HashWires proof length");
            }
            ByteBuffer in = ByteBuffer.wrap(input);
            byte[][] nodes = new byte[nodeCount][HASH_BYTES];
            for (byte[] node : nodes) {
                in.get(node);
            }
            byte[] salt = new byte[MDP_SALT_BYTES];
            in.get(salt);
            int leaf = Byte.toUnsignedInt(in.get());
            byte[][] siblings = new byte[height][HASH_BYTES];
            for (byte[] sibling : siblings) {
                in.get(sibling);
            }
            byte[] prefix = null;
            if (hasPrefix) {
                prefix = new byte[HASH_BYTES];
                in.get(prefix);
            }
            if (in.hasRemaining()) {
                throw new IllegalArgumentException("trailing HashWires proof bytes");
            }
            return new Proof(nodes, salt, leaf, siblings, prefix);
        }
    }

    private static Generation generate(
            BigInteger value,
            BigInteger threshold,
            int base,
            int maxNumberBits,
            byte[] seed) {
        int maxDigits = maximumDigits(maxNumberBits, base);

        List<BigInteger> mdp = minimumDominatingPartition(value, base);
        // Significant digits are right-aligned under the fixed public width.
        List<int[]> splits = new ArrayList<>(mdp.size());
        for (BigInteger item : mdp) {
            splits.add(significantDigits(item, base));
        }

        // All branches reuse one multichain set.
        List<byte[][]> chains = computeHashChains(seed, splits.get(0), base);
        List<byte[][]> wires = wireMdpSplits(splits, chains);

        int selected = -1;
        int[] thresholdDigits = null;
        byte[] selectedPlaPrefix = null;
        if (threshold != null) {
            selected = pickMdpIndex(threshold, mdp, base);
            thresholdDigits = significantDigits(threshold, base);
            if (!dominates(splits.get(selected), thresholdDigits)) {
                throw new IllegalStateException("selected MDP element does not dominate threshold");
            }
        }

        // The selected branch retains the prefix needed by verification.
        byte[][] plaRoots = new byte[wires.size()][];
        for (int i = 0; i < wires.size(); i++) {
            int desired = i == selected ? thresholdDigits.length : wires.get(i).length;
            PlaResult pla = plaAccumulator(seed, wires.get(i), maxDigits, desired);
            plaRoots[i] = pla.root;
            if (i == selected) {
                selectedPlaPrefix = pla.prefix;
            }
        }

        byte[][] salts = new byte[plaRoots.length][];
        byte[][] saltedRoots = new byte[plaRoots.length][];
        for (int i = 0; i < plaRoots.length; i++) {
            salts[i] = deriveSubseed(TOP_SALT, seed, i, MDP_SALT_BYTES);
            saltedRoots[i] = hash(salts[i], plaRoots[i]);
        }

        // Fixed-size deterministic placement hides the number and order of branches.
        int[] positions = deterministicIndexes(saltedRoots.length, maxDigits, seed);
        byte[] smtSecret = deriveSubseed(SMTREE_PADDING_SALT, seed, 0, HASH_BYTES);
        MerkleTree tree = new MerkleTree(saltedRoots, positions, maxDigits, smtSecret);

        Proof proof = null;
        if (threshold != null) {
            byte[][] nodes = provingChainNodes(chains, splits.get(selected), thresholdDigits);
            byte[][] siblings = tree.inclusionPath(positions[selected]);
            proof = new Proof(nodes, salts[selected], positions[selected], siblings, selectedPlaPrefix);
        }
        return new Generation(tree.root(), proof);
    }

    private static List<byte[][]> computeHashChains(byte[] seed, int[] valueDigits, int base) {
        List<byte[][]> chains = new ArrayList<>(valueDigits.length);
        for (int i = 0; i < valueDigits.length; i++) {
            byte[] subSeed = deriveSubseed(LEAF_SALT, seed, i, HASH_BYTES);
            int length = i == 0 ? valueDigits[0] + 1 : base;
            byte[][] chain = new byte[length][HASH_BYTES];
            chain[0] = subSeed;
            for (int j = 1; j < length; j++) {
                chain[j] = hash(chain[j - 1]);
            }
            chains.add(chain);
        }
        return chains;
    }

    private static List<byte[][]> wireMdpSplits(List<int[]> splits, List<byte[][]> chains) {
        List<byte[][]> result = new ArrayList<>(splits.size());
        for (int[] split : splits) {
            int offset = chains.size() - split.length;
            if (offset < 0) {
                throw new IllegalStateException("MDP has more digits than issued value");
            }
            byte[][] wire = new byte[split.length][HASH_BYTES];
            for (int i = 0; i < split.length; i++) {
                byte[][] chain = chains.get(offset + i);
                if (split[i] < 0 || split[i] >= chain.length) {
                    throw new IllegalStateException("MDP digit outside shared hash chain");
                }
                wire[i] = chain[split[i]];
            }
            result.add(wire);
        }
        return result;
    }

    private static PlaResult plaAccumulator(
            byte[] seed, byte[][] list, int maxLength, int desiredLength) {
        if (list.length < 1 || list.length > maxLength
                || desiredLength < 1 || desiredLength > list.length) {
            throw new IllegalArgumentException("invalid PLA dimensions");
        }
        byte[] prefix = null;
        byte[] output = null;
        if (list.length < maxLength) {
            prefix = hash(PADDING_SALT, seed);
            output = prefix;
        }
        for (int i = 0; i < list.length; i++) {
            if (i != 0 && list.length > desiredLength && i == list.length - desiredLength) {
                prefix = output.clone();
            }
            output = output == null ? hash(list[i]) : hash(output, list[i]);
        }
        return new PlaResult(output, prefix);
    }

    private static byte[][] provingChainNodes(
            List<byte[][]> chains, int[] selectedMdpDigits, int[] thresholdDigits) {
        int chainOffset = chains.size() - thresholdDigits.length;
        int mdpOffset = selectedMdpDigits.length - thresholdDigits.length;
        if (chainOffset < 0 || mdpOffset < 0) {
            throw new IllegalStateException("threshold digit length exceeds selected MDP path");
        }
        byte[][] result = new byte[thresholdDigits.length][HASH_BYTES];
        for (int i = 0; i < thresholdDigits.length; i++) {
            int distance = selectedMdpDigits[mdpOffset + i] - thresholdDigits[i];
            if (distance < 0 || distance >= chains.get(chainOffset + i).length) {
                throw new IllegalStateException("threshold is not dominated by selected MDP path");
            }
            result[i] = chains.get(chainOffset + i)[distance];
        }
        return result;
    }

    private static int[] deterministicIndexes(int count, int maximum, byte[] seed) {
        if (count < 1 || count > maximum) {
            throw new IllegalArgumentException("invalid deterministic shuffle dimensions");
        }
        int[] indexes = new int[maximum];
        for (int i = 0; i < maximum; i++) {
            indexes[i] = i;
        }
        DeterministicSampler sampler = new DeterministicSampler(seed);
        for (int i = 0; i < count; i++) {
            int j = i + sampler.nextInt(maximum - i);
            int tmp = indexes[i];
            indexes[i] = indexes[j];
            indexes[j] = tmp;
        }
        return Arrays.copyOf(indexes, count);
    }

    private static int pickMdpIndex(BigInteger threshold, List<BigInteger> mdp, int base) {
        int[] thresholdDigits = significantDigits(threshold, base);
        for (int i = mdp.size() - 1; i >= 0; i--) {
            if (dominates(significantDigits(mdp.get(i), base), thresholdDigits)) {
                return i;
            }
        }
        throw new IllegalArgumentException("threshold exceeds issued value or has no dominating MDP branch");
    }

    private static boolean dominates(int[] upper, int[] lower) {
        int offset = upper.length - lower.length;
        if (offset < 0) {
            return false;
        }
        for (int i = 0; i < lower.length; i++) {
            if (upper[offset + i] < lower[i]) {
                return false;
            }
        }
        return true;
    }

    private static int[] significantDigits(BigInteger value, int base) {
        requireNonNegative(value, "value");
        requireSupportedBase(base);
        if (value.signum() == 0) {
            return new int[] {0};
        }
        BigInteger radix = BigInteger.valueOf(base);
        List<Integer> littleEndian = new ArrayList<>();
        BigInteger current = value;
        while (current.signum() != 0) {
            BigInteger[] qr = current.divideAndRemainder(radix);
            littleEndian.add(qr[1].intValueExact());
            current = qr[0];
        }
        int[] result = new int[littleEndian.size()];
        for (int i = 0; i < result.length; i++) {
            result[i] = littleEndian.get(result.length - 1 - i);
        }
        return result;
    }

    private static byte[] deriveSubseed(
            byte[] salt, byte[] seed, long index, int outputLength) {
        if (outputLength < 1 || outputLength > HASH_BYTES) {
            throw new IllegalArgumentException("invalid derived output length");
        }
        byte[] indexBytes = ByteBuffer.allocate(Long.BYTES)
                .order(ByteOrder.LITTLE_ENDIAN).putLong(index).array();
        return Arrays.copyOf(hash(salt, indexBytes, seed), outputLength);
    }

    private static byte[] hash(byte[]... inputs) {
        MessageDigest digest = SHA256.get();
        digest.reset();
        for (byte[] input : inputs) {
            digest.update(input);
        }
        return digest.digest();
    }

    private static int digitBits(int base) {
        return switch (base) {
            case 2 -> 1;
            case 4 -> 2;
            case 16 -> 4;
            case 256 -> 8;
            default -> throw new IllegalArgumentException("HashWires supports bases 2, 4, 16, and 256");
        };
    }

    private static void requireSupportedBase(int base) {
        digitBits(base);
    }

    private static int treeHeight(int leaves) {
        return Integer.numberOfTrailingZeros(leaves);
    }

    private static void validateValue(BigInteger value, int base, int maxNumberBits) {
        requireSupportedBase(base);
        maximumDigits(maxNumberBits, base);
        requireInRange(value, maxNumberBits, "value");
    }

    private static void validateStatement(
            BigInteger value, BigInteger threshold, int base, int maxNumberBits) {
        validateValue(value, base, maxNumberBits);
        requireInRange(threshold, maxNumberBits, "threshold");
        if (threshold.compareTo(value) > 0) {
            throw new IllegalArgumentException("threshold exceeds issued value");
        }
    }

    private static void requireInRange(BigInteger value, int bits, String name) {
        requireNonNegative(value, name);
        if (value.bitLength() > bits) {
            throw new IllegalArgumentException(name + " is outside [0,2^bits)");
        }
    }

    private static void requireNonNegative(BigInteger value, String name) {
        Objects.requireNonNull(value, name);
        if (value.signum() < 0) {
            throw new IllegalArgumentException(name + " must be nonnegative");
        }
    }

    private static byte[][] cloneMatrix(byte[][] input, int width, String name) {
        Objects.requireNonNull(input, name + "s");
        byte[][] result = new byte[input.length][];
        for (int i = 0; i < input.length; i++) {
            if (input[i] == null || input[i].length != width) {
                throw new IllegalArgumentException(name + " must be " + width + " bytes");
            }
            result[i] = input[i].clone();
        }
        return result;
    }

    private static byte[] ascii(String text) {
        return text.getBytes(StandardCharsets.US_ASCII);
    }

    private record Generation(byte[] root, Proof proof) {
        private Generation {
            root = root.clone();
        }
    }

    private record PlaResult(byte[] root, byte[] prefix) {
        private PlaResult {
            root = root.clone();
            prefix = prefix == null ? null : prefix.clone();
        }
    }

    private static final class MerkleTree {
        private final List<byte[][]> levels;
        private final int leafCount;

        private MerkleTree(
                byte[][] actualLeaves,
                int[] positions,
                int leafCount,
                byte[] paddingSecret) {
            if (actualLeaves.length != positions.length || Integer.bitCount(leafCount) != 1) {
                throw new IllegalArgumentException("invalid Merkle tree dimensions");
            }
            this.leafCount = leafCount;
            byte[][] leaves = new byte[leafCount][];
            for (int i = 0; i < actualLeaves.length; i++) {
                int position = positions[i];
                if (position < 0 || position >= leafCount || leaves[position] != null) {
                    throw new IllegalArgumentException("invalid or duplicate Merkle leaf position");
                }
                leaves[position] = actualLeaves[i].clone();
            }
            int height = treeHeight(leafCount);
            // Empty positions are filled deterministically from the secret,
            // height, and position, keeping the public tree shape fixed.
            for (int i = 0; i < leafCount; i++) {
                if (leaves[i] == null) {
                    leaves[i] = hash(
                            paddingSecret,
                            ByteBuffer.allocate(8).putInt(height).putInt(i).array());
                }
            }
            // Parent nodes use the same left || right concatenation hash that
            // verification applies when recovering the root from a path.
            levels = new ArrayList<>();
            levels.add(leaves);
            byte[][] current = leaves;
            while (current.length > 1) {
                byte[][] parent = new byte[current.length / 2][];
                for (int i = 0; i < parent.length; i++) {
                    parent[i] = hash(current[2 * i], current[2 * i + 1]);
                }
                levels.add(parent);
                current = parent;
            }
        }

        private byte[] root() {
            return levels.get(levels.size() - 1)[0].clone();
        }

        private byte[][] inclusionPath(int leafIndex) {
            if (leafIndex < 0 || leafIndex >= leafCount) {
                throw new IllegalArgumentException("leaf index outside tree");
            }
            byte[][] siblings = new byte[levels.size() - 1][HASH_BYTES];
            int index = leafIndex;
            for (int level = 0; level < siblings.length; level++) {
                siblings[level] = levels.get(level)[index ^ 1].clone();
                index >>>= 1;
            }
            return siblings;
        }

        private static byte[] recoverRoot(byte[] leaf, int leafIndex, byte[][] siblings) {
            byte[] current = leaf.clone();
            int index = leafIndex;
            for (byte[] sibling : siblings) {
                current = (index & 1) == 0 ? hash(current, sibling) : hash(sibling, current);
                index >>>= 1;
            }
            return current;
        }
    }

    private static final class DeterministicSampler {
        private final byte[] seed;
        private long counter;
        private byte[] block = new byte[0];
        private int offset;

        private DeterministicSampler(byte[] seed) {
            this.seed = seed.clone();
        }

        private int nextInt(int bound) {
            if (bound <= 0) {
                throw new IllegalArgumentException("bound must be positive");
            }
            long modulus = 1L << 32;
            long limit = modulus - modulus % bound;
            long sample;
            do {
                sample = Integer.toUnsignedLong(nextWord());
            } while (sample >= limit);
            return (int) (sample % bound);
        }

        private int nextWord() {
            if (offset + Integer.BYTES > block.length) {
                byte[] count = ByteBuffer.allocate(Long.BYTES).putLong(counter++).array();
                block = hash(SHUFFLE_DOMAIN, seed, count);
                offset = 0;
            }
            int value = ByteBuffer.wrap(block, offset, Integer.BYTES).getInt();
            offset += Integer.BYTES;
            return value;
        }
    }
}
