import copy
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments/ktx"))
from cbrp_ktx_poc import (  # noqa: E402
    CBRP_KTX,
    M_COL,
    Q_MOD,
    challenge_vector,
    dedp,
    digit_length,
    dominates,
)


class KTXTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scheme = CBRP_KTX(2**16, 16)
        cls.table, cls.auxiliary = cls.scheme.commit(2**16 - 2)
        cls.threshold = 0x9999

    def transcript(self, challenges=(1, 2, 3)):
        state = self.scheme.start(
            self.table,
            self.auxiliary,
            2**16 - 2,
            self.threshold,
            len(challenges),
        )
        proof = self.scheme.respond(state, challenges)
        return state, proof, challenges

    def verify(self, state, proof, challenges):
        return self.scheme.verify(
            self.table,
            self.threshold,
            state.first,
            proof,
            challenges,
            len(challenges),
        )

    def test_01_all_three_challenges(self):
        state, proof, challenges = self.transcript()
        self.assertTrue(self.verify(state, proof, challenges))

    def test_02_literal_replay(self):
        state, proof, _ = self.transcript()
        self.assertFalse(self.verify(state, proof, (2, 2, 3)))

    def test_03_empty_and_truncated(self):
        state, proof, challenges = self.transcript()
        for length in range(3):
            altered = dict(proof)
            altered["responses"] = proof["responses"][:length]
            self.assertFalse(self.verify(state, altered, challenges))
        self.assertFalse(
            self.scheme.verify(
                self.table,
                self.threshold,
                (),
                {"commitments": (), "responses": ()},
                (),
                0,
            )
        )

    def test_04_invalid_challenge(self):
        state, proof, _ = self.transcript()
        self.assertFalse(self.verify(state, proof, (0, 2, 3)))
        state = self.scheme.start(
            self.table,
            self.auxiliary,
            2**16 - 2,
            self.threshold,
            3,
        )
        with self.assertRaises(ValueError):
            self.scheme.respond(state, (1, 2))

    def test_05_single_use_state(self):
        state, _, challenges = self.transcript()
        with self.assertRaises(ValueError):
            self.scheme.respond(state, challenges)

    def test_06_altered_commitment(self):
        state, proof, challenges = self.transcript()
        altered = copy.deepcopy(proof)
        commitments = list(altered["commitments"])
        commitments[0] = (b"x" * 32, commitments[0][1], commitments[0][2])
        altered["commitments"] = tuple(commitments)
        self.assertFalse(self.verify(state, altered, challenges))

    def test_07_seed_binds_permutation(self):
        state, proof, challenges = self.transcript()
        altered = copy.deepcopy(proof)
        responses = list(altered["responses"])
        response = list(responses[1])
        response[1] = b"x" * 32
        responses[1] = tuple(response)
        altered["responses"] = tuple(responses)
        self.assertFalse(self.verify(state, altered, challenges))

        first = self.scheme.perm_from_seed(b"a" * 32, 4)[0]
        second = self.scheme.perm_from_seed(b"a" * 32, 4)[0]
        self.assertTrue(
            all(np.array_equal(left, right) for left, right in zip(first, second))
        )

    def test_08_wrong_block_weight(self):
        state, proof, challenges = self.transcript()
        altered = copy.deepcopy(proof)
        altered["responses"][0][1][:M_COL] = 0
        self.assertFalse(self.verify(state, altered, challenges))

    def test_09_wrong_vector_length(self):
        state, proof, challenges = self.transcript()
        altered = copy.deepcopy(proof)
        responses = list(altered["responses"])
        response = list(responses[2])
        response[2] = response[2][:-1]
        responses[2] = tuple(response)
        altered["responses"] = tuple(responses)
        self.assertFalse(self.verify(state, altered, challenges))

    def test_10_noncanonical_coefficient(self):
        state, proof, challenges = self.transcript()
        altered = copy.deepcopy(proof)
        altered["responses"][1][2][0] += Q_MOD
        self.assertFalse(self.verify(state, altered, challenges))

    def test_11_public_statement_is_reconstructed(self):
        state, proof, challenges = self.transcript()
        table = {key: value.copy() for key, value in self.table.items()}
        table[0, 9][0] = (table[0, 9][0] + 1) % Q_MOD
        self.assertFalse(
            self.scheme.verify(
                table,
                self.threshold,
                state.first,
                proof,
                challenges,
                3,
            )
        )

    def test_12_false_statement_and_missing_witness(self):
        with self.assertRaises(ValueError):
            self.scheme.start(
                self.table,
                self.auxiliary,
                2**16 - 2,
                2**16 - 1,
                3,
            )
        with self.assertRaises(ValueError):
            self.scheme.start(
                self.table,
                {},
                2**16 - 2,
                self.threshold,
                3,
            )

    def test_13_packing_ceil(self):
        scheme = CBRP_KTX(2**16, 256)
        dimension = 2 * M_COL + 2
        vector = (dimension * 12 + 7) // 8
        self.assertEqual(
            scheme.proof_bytes([1, 2, 3], 2),
            3 * (96 + 64 + vector) + (dimension + 7) // 8 + 64,
        )
        self.assertEqual(scheme.table_bytes(), 96 * 1024)

    def test_14_dedp_exhaustive(self):
        for maximum in range(2, 40):
            for base in range(2, 7):
                length = digit_length(maximum, base)
                for threshold in range(maximum):
                    partition = dedp(threshold, base, length, maximum)
                    self.assertLessEqual(len(partition), length)
                    for value in range(maximum):
                        self.assertEqual(
                            value >= threshold,
                            any(
                                dominates(value, branch, base, length)
                                for branch in partition
                            ),
                        )

    def test_15_table_release_and_distinctness(self):
        self.assertEqual(len(self.table), self.scheme.n * self.scheme.b)
        self.assertEqual(
            len({value.tobytes() for value in self.table.values()}),
            len(self.table),
        )
        self.assertEqual(len(self.auxiliary), 63)
        for witness in self.auxiliary.values():
            self.assertEqual(int(witness.sum()), M_COL // 2)

    def test_16_fresh_values_at_boundaries(self):
        scheme = CBRP_KTX(2**16, 16, public_matrix_seed=1234)
        for value, threshold in (
            (0, 0),
            (2**16 - 1, 2**16 - 1),
            (2**16 - 2, 1),
            (32772, 32768),
        ):
            table, auxiliary = scheme.commit(value)
            state = scheme.start(table, auxiliary, value, threshold, 3)
            challenges = (1, 2, 3)
            proof = scheme.respond(state, challenges)
            self.assertTrue(
                scheme.verify(table, threshold, state.first, proof, challenges, 3)
            )
            self.assertEqual(
                len(auxiliary),
                sum((value // 16**index) % 16 + 1 for index in range(scheme.n)),
            )

    def test_17_public_seed_does_not_determine_private_values(self):
        first = CBRP_KTX(
            2**16,
            16,
            public_matrix_seed=777,
            private_seed=1,
        )
        second = CBRP_KTX(
            2**16,
            16,
            public_matrix_seed=777,
            private_seed=2,
        )
        self.assertTrue(np.array_equal(first.A, second.A))

        first_table, first_aux = first.commit(2**16 - 2)
        second_table, second_aux = second.commit(2**16 - 2)
        self.assertFalse(
            all(
                np.array_equal(first_aux[key], second_aux[key])
                for key in first_aux
            )
        )

        first_state = first.start(
            first_table,
            first_aux,
            2**16 - 2,
            self.threshold,
            1,
        )
        second_state = second.start(
            second_table,
            second_aux,
            2**16 - 2,
            self.threshold,
            1,
        )
        self.assertFalse(
            np.array_equal(
                first_state.repetitions[0][2],
                second_state.repetitions[0][2],
            )
        )


if __name__ == "__main__":
    unittest.main()
