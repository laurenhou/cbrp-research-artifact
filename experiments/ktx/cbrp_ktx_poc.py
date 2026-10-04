"""KTX-CBRP functional PoC; algorithm numbers refer to the accompanying journal manuscript.

Toy parameters and hash commitments; issuer labels/signatures are omitted.
This is not a production KTX implementation; see the manuscript evaluation scope.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import math
import secrets
import numpy as np

Q_MOD, N_L, M_COL, RHO = 4093, 128, 512, 137


def digit_length(N: int, b: int) -> int:
    if N < 2 or b < 2:
        raise ValueError('N >= 2 and b >= 2 required')
    n, capacity = 0, 1
    while capacity < N:
        n += 1
        capacity *= b
    return n


def digits(x: int, b: int, n: int) -> list[int]:
    if x < 0 or b < 2 or n < 1:
        raise ValueError('invalid digit input')
    out = []
    for _ in range(n):
        x, r = divmod(x, b)
        out.append(r)
    if x:
        raise ValueError('integer does not fit digit length')
    return out


# Algorithm 1: DedP_b(t).
def dedp(t: int, b: int, n: int, N: int) -> list[int]:
    if not 0 <= t < N or n != digit_length(N, b):
        raise ValueError('invalid threshold or digit length')
    return sorted({y for k in range(n) if (y := ((t + b**k - 1) // b**k) * b**k) < N})


def dominates(w: int, y: int, b: int, n: int) -> bool:
    return all(a >= c for a, c in zip(digits(w, b, n), digits(y, b, n)))


def com(msg: bytes, randomness: bytes) -> bytes:
    """Engineering hash placeholder, NOT the statistically hiding KTX Com."""
    return hashlib.sha256(msg + randomness).digest()


def ser(v: np.ndarray) -> bytes:
    return v.astype('<u2').tobytes()  # explicit little-endian uint16; packed estimator is separate


# Section 2.4.5: independent verifier challenges.
def challenge_vector(rho: int) -> tuple[int, ...]:
    if rho < 1:
        raise ValueError('rho must be positive')
    return tuple(secrets.randbelow(3) + 1 for _ in range(rho))


def valid_challenges(challenges, rho: int) -> bool:
    return (type(rho) is int and rho >= 1 and isinstance(challenges, (tuple, list)) and len(challenges) == rho
            and all(type(c) is int and 1 <= c <= 3 for c in challenges))


@dataclass
class ProverState:
    """Private state. Only `first` is sent before the verifier challenge."""
    first: tuple
    xstar: np.ndarray
    repetitions: list
    used: bool = False


class CBRP_KTX:
    # Algorithm 10, steps 1-3 (PoC): public parameters and matrix.
    def __init__(
        self,
        N: int,
        b: int,
        public_matrix_seed: int = 20260706,
        *,
        private_seed: int | None = None,
    ):
        self.N, self.b, self.n = N, b, digit_length(N, b)
        if self.n * b > 1_000_000:
            raise ValueError('research harness table limit: 1,000,000 entries')
        if type(public_matrix_seed) is not int or public_matrix_seed < 0:
            raise ValueError('public matrix seed must be a nonnegative integer')
        if private_seed is not None and (type(private_seed) is not int or private_seed < 0):
            raise ValueError('private test seed must be a nonnegative integer')

        # Only the public matrix is derived from the recorded public seed.
        public_rng = np.random.Generator(np.random.PCG64(public_matrix_seed))
        self.A = public_rng.integers(0, Q_MOD, size=(N_L, M_COL), dtype=np.int64)

        # Witnesses and masks use an independent, unrecorded source. The optional
        # private_seed is a deterministic unit-test hook, not a benchmark input.
        private_entropy = (
            private_seed
            if private_seed is not None
            else int.from_bytes(secrets.token_bytes(32), 'big')
        )
        self._private_rng = np.random.Generator(np.random.PCG64(private_entropy))

    # Algorithm 11, steps 2-4 and 6-7 (PoC): table and authorized witnesses.
    def commit(self, w: int):
        if not 0 <= w < self.N:
            raise ValueError('w outside [0,N)')
        wd = digits(w, self.b, self.n)
        Y, aux, seen = {}, {}, set()
        for i in range(self.n):
            for j in range(self.b):
                for attempt in range(1000):
                    x = np.zeros(M_COL, dtype=np.int64)
                    x[self._private_rng.choice(M_COL, M_COL // 2, replace=False)] = 1
                    y = (self.A @ x) % Q_MOD
                    image = ser(y)
                    if image not in seen:
                        break
                else:
                    raise RuntimeError('toy image resampling did not terminate')
                seen.add(image)
                Y[i, j] = y
                if j <= wd[i]:
                    aux[i, j] = x
        return Y, aux

    def table_bytes(self) -> int:
        return math.ceil(self.n * self.b * N_L * (Q_MOD - 1).bit_length() / 8)

    # Algorithm 12, steps 1 and 3 / Algorithm 13, steps 1 and 7: public statement.
    def build_statement(self, Y, t: int):
        S = dedp(t, self.b, self.n, self.N)
        branches = [digits(y, self.b, self.n) for y in S]
        images = []
        for br in branches:
            for i in range(self.n):
                if not self.valid_vector(Y.get((i, br[i])), N_L):
                    raise ValueError('missing or malformed public image')
            images.append(np.concatenate([Y[i, br[i]] for i in range(self.n)]))
        return S, branches, np.column_stack(images)

    # Section 2.4.5: A_star times v, using AND blocks and the OR tail.
    def apply_Astar(self, Ymat, v):
        head = v[:self.n * M_COL].reshape(self.n, M_COL)
        out = np.concatenate([(self.A @ block) % Q_MOD for block in head])
        return (out + Ymat @ v[self.n * M_COL:]) % Q_MOD

    def perm_from_seed(self, seed: bytes, ell: int):
        if not isinstance(seed, bytes) or len(seed) != 32:
            raise ValueError('permutation seed must be 32 bytes')
        # Seed-derived block and tail permutations (PoC).
        g = np.random.Generator(np.random.PCG64(int.from_bytes(seed, 'big')))
        return [g.permutation(M_COL) for _ in range(self.n)], g.permutation(ell)

    def apply_perm(self, perm, v):
        blocks, tail = perm
        return np.concatenate([v[i * M_COL:(i+1) * M_COL][blocks[i]] for i in range(self.n)]
                              + [v[self.n * M_COL:][tail]])

    @staticmethod
    def valid_vector(v, dim: int) -> bool:
        return (isinstance(v, np.ndarray) and v.shape == (dim,)
                and np.issubdtype(v.dtype, np.integer) and bool(np.all((v >= 0) & (v < Q_MOD))))

    # Section 2.4.5: witness-shape check for the AND-OR relation.
    def in_shape(self, v, ell: int) -> bool:
        if not self.valid_vector(v, self.n * M_COL + ell):
            return False
        for block in v[:self.n * M_COL].reshape(self.n, M_COL):
            if not np.all((block == 0) | (block == 1)) or int(block.sum()) != M_COL // 2:
                return False
        tail = v[self.n * M_COL:]
        return np.count_nonzero(tail) == 1 and tail[tail != 0][0] == Q_MOD - 1

    # Algorithm 12, steps 1-4: branch witness and KTX first messages.
    def start(self, Y, aux, w: int, t: int, rho: int = RHO) -> ProverState:
        if not 0 <= t <= w < self.N or type(rho) is not int or rho < 1:
            raise ValueError('invalid statement or repetition count')
        S, branches, Ymat = self.build_statement(Y, t)
        ell = len(S)
        s = next(r for r, y in enumerate(S) if dominates(w, y, self.b, self.n))
        xstar = np.zeros(self.n * M_COL + ell, dtype=np.int64)
        for i in range(self.n):
            x = aux.get((i, branches[s][i]))
            if not self.valid_vector(x, M_COL):
                raise ValueError('missing witness')
            xstar[i * M_COL:(i+1) * M_COL] = x
        xstar[self.n * M_COL + s] = Q_MOD - 1
        if not self.in_shape(xstar, ell) or np.any(self.apply_Astar(Ymat, xstar)):
            raise ValueError('witness does not satisfy the AND-OR relation')
        reps, first = [], []
        for _ in range(rho):
            seed = secrets.token_bytes(32)
            perm = self.perm_from_seed(seed, ell)
            mask = self._private_rng.integers(0, Q_MOD, size=len(xstar), dtype=np.int64)
            r1, r2, r3 = [secrets.token_bytes(32) for _ in range(3)]
            ar = self.apply_Astar(Ymat, mask)
            pmask = self.apply_perm(perm, mask)
            first.append((com(seed + ser(ar), r1), com(ser(pmask), r2),
                          com(ser(self.apply_perm(perm, (xstar + mask) % Q_MOD)), r3)))
            reps.append((seed, perm, mask, pmask, r1, r2, r3))
        return ProverState(tuple(first), xstar, reps)

    # Algorithm 12, steps 4-5 / Section 2.4.5: challenge responses and transcript.
    def respond(self, state: ProverState, challenges):
        if state.used:
            raise ValueError('first message already answered')
        if not valid_challenges(challenges, len(state.first)):
            raise ValueError('invalid external challenge vector')
        state.used = True
        responses = []
        for ch, (seed, perm, mask, pmask, r1, r2, r3) in zip(challenges, state.repetitions):
            if ch == 1:
                responses.append((1, self.apply_perm(perm, state.xstar), pmask.copy(), r2, r3))
            elif ch == 2:
                responses.append((2, seed, (state.xstar + mask) % Q_MOD, r1, r3))
            else:
                responses.append((3, seed, mask.copy(), r1, r2))
        state.repetitions.clear()
        state.xstar.fill(0)
        return {'commitments': state.first, 'responses': tuple(responses)}

    # Algorithm 13, steps 7-8 (PoC): verify the KTX proof component.
    def verify(self, Y, t: int, first, proof, expected_challenges, rho: int = RHO) -> bool:
        try:
            if not valid_challenges(expected_challenges, rho) or not isinstance(proof, dict):
                return False
            cmts, responses = proof['commitments'], proof['responses']
            if len(first) != rho or len(cmts) != rho or len(responses) != rho or cmts != first:
                return False
            _, _, Ymat = self.build_statement(Y, t)
            ell = Ymat.shape[1]
            dim = self.n * M_COL + ell
            for i in range(rho):
                cmt, ch, response = cmts[i], expected_challenges[i], responses[i]
                if len(cmt) != 3 or any(not isinstance(c, bytes) or len(c) != 32 for c in cmt):
                    return False
                if len(response) != 5 or response[0] != ch:
                    return False
                c1, c2, c3 = cmt
                _, a, v, r1, r2 = response
                if any(not isinstance(r, bytes) or len(r) != 32 for r in (r1, r2)) or not self.valid_vector(v, dim):
                    return False
                if ch == 1:
                    if not self.in_shape(a, ell):
                        return False
                    if com(ser(v), r1) != c2 or com(ser((a + v) % Q_MOD), r2) != c3:
                        return False
                else:
                    perm = self.perm_from_seed(a, ell)
                    if com(a + ser(self.apply_Astar(Ymat, v)), r1) != c1:
                        return False
                    target = c3 if ch == 2 else c2
                    if com(ser(self.apply_perm(perm, v)), r2) != target:
                        return False
            return True
        except (ValueError, KeyError, IndexError, TypeError, AttributeError):
            return False

    def proof_bytes(self, challenges, ell: int) -> int:
        """Section 6.6: packed-size estimate, excluding verifier challenges."""
        dim = self.n * M_COL + ell
        vector = (dim * (Q_MOD - 1).bit_length() + 7) // 8
        return sum(96 + 64 + vector + ((dim + 7) // 8 if ch == 1 else 32) for ch in challenges)
