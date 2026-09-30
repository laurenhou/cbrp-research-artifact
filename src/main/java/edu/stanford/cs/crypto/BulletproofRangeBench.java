package edu.stanford.cs.crypto;

import edu.stanford.cs.crypto.efficientct.GeneratorParams;
import edu.stanford.cs.crypto.efficientct.algebra.BN128Group;
import edu.stanford.cs.crypto.efficientct.algebra.BN128Point;
import edu.stanford.cs.crypto.efficientct.commitments.PeddersenCommitment;
import edu.stanford.cs.crypto.efficientct.rangeproof.RangeProof;
import edu.stanford.cs.crypto.efficientct.rangeproof.RangeProofProver;
import edu.stanford.cs.crypto.efficientct.rangeproof.RangeProofVerifier;

import java.math.BigInteger;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import research.cbrp.bench.BenchmarkData;

/** BN128 baseline on the derived value delta=w-t. Does not certify the original w. */
public final class BulletproofRangeBench {
    public static void main(String[] args) throws Exception {
        if(args.length!=5) throw new IllegalArgumentException("Use scripts/run.py; expected bits warmup iterations input.csv samples.csv");
        int bits=Integer.parseInt(args[0]),warm=Integer.parseInt(args[1]),iters=Integer.parseInt(args[2]);
        List<BenchmarkData.Case> cases=BenchmarkData.read(Path.of(args[3]),bits,warm,iters);
        long setup=System.nanoTime();
        BN128Group group=new BN128Group();
        GeneratorParams<BN128Point> params=GeneratorParams.generateParams(bits,group);
        RangeProofProver<BN128Point> prover=new RangeProofProver<>();
        RangeProofVerifier<BN128Point> verifier=new RangeProofVerifier<>();
        System.err.printf(java.util.Locale.ROOT,"public_setup_ms=%.9f%n",(System.nanoTime()-setup)/1e6);
        try(BenchmarkData.Csv csv=new BenchmarkData.Csv(Path.of(args[4]))) {
            for(BenchmarkData.Case c:cases) {
                BigInteger x=c.delta(); // public benchmark transformation, outside timed regions
                long begin=System.nanoTime();
                PeddersenCommitment<BN128Point> witness=new PeddersenCommitment<>(params.getBase(),x);
                BN128Point commitment=witness.getCommitment();long commitNs=System.nanoTime()-begin;
                begin=System.nanoTime();RangeProof<BN128Point> proof=prover.generateProof(params,commitment,witness);long proveNs=System.nanoTime()-begin;
                begin=System.nanoTime();verifier.verify(params,commitment,proof);long verifyNs=System.nanoTime()-begin;
                Map<String,String> row=BenchmarkData.row("bulletproofs",bits,c);
                BenchmarkData.value(row,"value_proved",x);
                BenchmarkData.timing(row,"commit_ms",commitNs);BenchmarkData.timing(row,"prove_ms",proveNs);BenchmarkData.timing(row,"verify_ms",verifyNs);
                BenchmarkData.value(row,"proof_bytes",proof.numElements()*33+proof.numInts()*32);
                BenchmarkData.value(row,"verified",1);csv.write(row);
            }
        }
        System.out.println("BULLETPROOFS BENCH PASS");
    }
}
