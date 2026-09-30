import edu.stanford.cs.crypto.efficientct.*;
import edu.stanford.cs.crypto.efficientct.algebra.*;
import edu.stanford.cs.crypto.efficientct.commitments.PeddersenCommitment;
import edu.stanford.cs.crypto.efficientct.rangeproof.*;
import java.math.BigInteger;
public final class BPSelfTest {
    public static void main(String[] args) throws Exception {
        BN128Group g=new BN128Group();GeneratorParams<BN128Point> pp=GeneratorParams.generateParams(32,g);
        PeddersenCommitment<BN128Point> w=new PeddersenCommitment<>(pp.getBase(),BigInteger.valueOf(123));
        BN128Point c=w.getCommitment();RangeProof<BN128Point> p=new RangeProofProver<BN128Point>().generateProof(pp,c,w);
        RangeProofVerifier<BN128Point> v=new RangeProofVerifier<>();v.verify(pp,c,p);
        try {v.verify(pp,c.add(g.generator()),p);} catch(VerificationFailedException e) {
            System.out.println("BULLETPROOFS SELFTEST PASS: honest accepted, altered commitment rejected");return;
        }
        throw new AssertionError("altered commitment accepted");
    }
}
