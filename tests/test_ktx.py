import copy
import sys
import unittest
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'experiments/ktx'))
from cbrp_ktx_poc import CBRP_KTX,digit_length,dedp,dominates,challenge_vector,Q_MOD,M_COL


class KTXTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s=CBRP_KTX(2**16,16)
        cls.Y,cls.aux=cls.s.commit(2**16-2)
        cls.t=0x9999

    def transcript(self, challenges=(1,2,3)):
        state=self.s.start(self.Y,self.aux,2**16-2,self.t,len(challenges))
        proof=self.s.respond(state,challenges)
        return state,proof,challenges

    def verify(self,state,proof,challenges):
        return self.s.verify(self.Y,self.t,state.first,proof,challenges,len(challenges))

    def test_01_all_three_challenges(self):
        st,p,c=self.transcript();self.assertTrue(self.verify(st,p,c))

    def test_02_literal_replay(self):
        st,p,c=self.transcript();self.assertFalse(self.verify(st,p,(2,2,3)))

    def test_03_empty_and_truncated(self):
        st,p,c=self.transcript()
        for k in range(3):
            q=dict(p);q['responses']=p['responses'][:k];self.assertFalse(self.verify(st,q,c))
        self.assertFalse(self.s.verify(self.Y,self.t,(),{'commitments':(),'responses':()},(),0))

    def test_04_invalid_challenge(self):
        st,p,c=self.transcript();self.assertFalse(self.verify(st,p,(0,2,3)))
        st=self.s.start(self.Y,self.aux,2**16-2,self.t,3)
        with self.assertRaises(ValueError):self.s.respond(st,(1,2))

    def test_05_single_use_state(self):
        st,p,c=self.transcript()
        with self.assertRaises(ValueError):self.s.respond(st,c)

    def test_06_altered_commitment(self):
        st,p,c=self.transcript();q=copy.deepcopy(p)
        cm=list(q['commitments']);cm[0]=(b'x'*32,cm[0][1],cm[0][2]);q['commitments']=tuple(cm)
        self.assertFalse(self.verify(st,q,c))

    def test_07_seed_really_binds_permutation(self):
        st,p,c=self.transcript();q=copy.deepcopy(p);r=list(q['responses']);x=list(r[1]);x[1]=b'x'*32;r[1]=tuple(x);q['responses']=tuple(r)
        self.assertFalse(self.verify(st,q,c))
        self.assertTrue(all(np.array_equal(a,b) for a,b in zip(self.s.perm_from_seed(b'a'*32,4)[0],self.s.perm_from_seed(b'a'*32,4)[0])))

    def test_08_wrong_block_weight(self):
        st,p,c=self.transcript();q=copy.deepcopy(p);q['responses'][0][1][:M_COL]=0
        self.assertFalse(self.verify(st,q,c))

    def test_09_wrong_vector_length(self):
        st,p,c=self.transcript();q=copy.deepcopy(p);r=list(q['responses']);x=list(r[2]);x[2]=x[2][:-1];r[2]=tuple(x);q['responses']=tuple(r)
        self.assertFalse(self.verify(st,q,c))

    def test_10_noncanonical_coefficient(self):
        st,p,c=self.transcript();q=copy.deepcopy(p);q['responses'][1][2][0]+=Q_MOD
        self.assertFalse(self.verify(st,q,c))

    def test_11_public_statement_is_reconstructed(self):
        st,p,c=self.transcript();Y={k:v.copy() for k,v in self.Y.items()};Y[0,9][0]=(Y[0,9][0]+1)%Q_MOD
        self.assertFalse(self.s.verify(Y,self.t,st.first,p,c,3))

    def test_12_false_statement_and_missing_witness(self):
        with self.assertRaises(ValueError):self.s.start(self.Y,self.aux,2**16-2,2**16-1,3)
        with self.assertRaises(ValueError):self.s.start(self.Y,{},2**16-2,self.t,3)

    def test_13_packing_ceil(self):
        s=CBRP_KTX(2**16,256);dim=2*M_COL+2
        vector=(dim*12+7)//8
        self.assertEqual(s.proof_bytes([1,2,3],2),3*(96+64+vector)+(dim+7)//8+64)
        self.assertEqual(s.table_bytes(),96*1024)

    def test_14_dedp_exhaustive(self):
        for N in range(2,40):
            for b in range(2,7):
                n=digit_length(N,b)
                for t in range(N):
                    S=dedp(t,b,n,N)
                    self.assertLessEqual(len(S),n)
                    for w in range(N):self.assertEqual(w>=t,any(dominates(w,y,b,n) for y in S))

    def test_15_table_release_and_distinctness(self):
        self.assertEqual(len(self.Y),self.s.n*self.s.b)
        self.assertEqual(len({v.tobytes() for v in self.Y.values()}),len(self.Y))
        self.assertEqual(len(self.aux),63)
        for x in self.aux.values():self.assertEqual(int(x.sum()),M_COL//2)

    def test_16_fresh_values_at_boundaries(self):
        s=CBRP_KTX(2**16,16,seed=1234)
        for w,t in [(0,0),(2**16-1,2**16-1),(2**16-2,1),(32772,32768)]:
            Y,aux=s.commit(w)
            state=s.start(Y,aux,w,t,3)
            challenges=(1,2,3)
            proof=s.respond(state,challenges)
            self.assertTrue(s.verify(Y,t,state.first,proof,challenges,3))
            self.assertEqual(len(aux),sum((w//16**i)%16+1 for i in range(s.n)))


if __name__=='__main__':unittest.main()
