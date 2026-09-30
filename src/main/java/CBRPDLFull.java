import org.bouncycastle.math.ec.ECCurve;
import org.bouncycastle.math.ec.ECPoint;

import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import research.cbrp.bench.BenchmarkData;
import java.math.BigInteger;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.*;

/** CBRP-DL research implementation; algorithm numbers refer to the thesis.
 * Interactive public-coin Schnorr OR-of-AND, not a Fiat-Shamir transform.
 */
public final class CBRPDLFull {
    // Algorithm 6, step 1: SetupDL - group parameters.
    static final BigInteger P = new BigInteger("21888242871839275222246405745257275088696311157297823662689037894645226208583");
    static final BigInteger Q = new BigInteger("21888242871839275222246405745257275088548364400416034343698204186575808495617");
    static final ECCurve CURVE = new ECCurve.Fp(P, BigInteger.ZERO, BigInteger.valueOf(3), Q, BigInteger.ONE);
    static final ECPoint G = CURVE.validatePoint(BigInteger.ONE, BigInteger.TWO);
    static final SecureRandom RNG = new SecureRandom();
    static final int POINT_BYTES = 33, SCALAR_BYTES = 32;

    /** Rejection sampling on ALL of Z_q, including zero (Chapter 4). */
    static BigInteger scalar() {
        BigInteger r;
        do { r = new BigInteger(Q.bitLength(), RNG); } while (r.compareTo(Q) >= 0);
        return r;
    }
    static BigInteger nonzeroScalar() {
        BigInteger r;
        do { r = scalar(); } while (r.signum() == 0);
        return r;
    }
    static boolean canonicalScalar(BigInteger r) { return r != null && r.signum() >= 0 && r.compareTo(Q) < 0; }
    static byte[] bytes(String s) { return s.getBytes(StandardCharsets.UTF_8); }
    // Algorithm 6, step 4: label hash.
    static byte[] hash(byte[] v) {
        try { return MessageDigest.getInstance("SHA-256").digest(v); }
        catch (Exception e) { throw new IllegalStateException(e); }
    }
    /** Length-prefix every field; no platform-default charset or ambiguous concatenation. */
    static byte[] encode(byte[]... fields) {
        try {
            ByteArrayOutputStream b = new ByteArrayOutputStream();
            DataOutputStream d = new DataOutputStream(b);
            for (byte[] f : fields) { d.writeInt(f.length); d.write(f); }
            return b.toByteArray();
        } catch (IOException e) { throw new IllegalStateException(e); }
    }
    static byte[] integer(long v) { return BigInteger.valueOf(v).toByteArray(); }
    static boolean validPoint(ECPoint p) {
        return p != null && CURVE.equals(p.getCurve()) && (p.isInfinity() || p.isValid());
    }
    // Algorithm 6, step 2: range digit length.
    static int digitLength(BigInteger N, int b) {
        if (N == null || N.compareTo(BigInteger.TWO) < 0 || b < 2) throw new IllegalArgumentException("N>=2, b>=2 required");
        int n = 0; BigInteger capacity = BigInteger.ONE;
        while (capacity.compareTo(N) < 0) { capacity = capacity.multiply(BigInteger.valueOf(b)); n++; }
        return n;
    }
    static void inRange(BigInteger v, BigInteger N) {
        if (v == null || v.signum() < 0 || v.compareTo(N) >= 0) throw new IllegalArgumentException("value outside [0,N)");
    }
    static int[] digits(BigInteger x, int b, int n) {
        if (x == null || x.signum() < 0 || b < 2 || n < 1) throw new IllegalArgumentException("invalid digits input");
        int[] out = new int[n]; BigInteger bb = BigInteger.valueOf(b);
        for (int i=0;i<n;i++) { BigInteger[] qr=x.divideAndRemainder(bb); out[i]=qr[1].intValueExact(); x=qr[0]; }
        if (x.signum()!=0) throw new IllegalArgumentException("value does not fit digit length");
        return out;
    }
    // Algorithm 1: DedP_b(t) - rounded boundaries, filtered and deduplicated.
    static List<BigInteger> dedp(BigInteger t, int b, int n, BigInteger N) {
        inRange(t,N);
        if (n!=digitLength(N,b)) throw new IllegalArgumentException("incorrect n");
        Set<BigInteger> set = new TreeSet<>(); BigInteger power=BigInteger.ONE;
        for (int k=0;k<n;k++) {
            BigInteger y=t.add(power).subtract(BigInteger.ONE).divide(power).multiply(power);
            if (y.compareTo(N)<0) set.add(y);
            power=power.multiply(BigInteger.valueOf(b));
        }
        return new ArrayList<>(set);
    }
    static boolean dominates(int[] w, int[] y) {
        if (w.length!=y.length) return false;
        for (int i=0;i<w.length;i++) if (w[i]<y[i]) return false;
        return true;
    }

    /** Original 8-bit fixed-base table; used ONLY by the issuer, never online proofs. */
    static final class Comb {
        final ECPoint[][] tab = new ECPoint[(Q.bitLength()+7)/8][256];
        Comb() {
            ECPoint bi=G;
            for (int i=0;i<tab.length;i++) {
                tab[i][0]=CURVE.getInfinity(); ECPoint acc=bi;
                for (int d=1;d<256;d++) { tab[i][d]=acc.normalize(); acc=acc.add(bi); }
                for (int k=0;k<8;k++) bi=bi.twice();
                bi=bi.normalize();
            }
        }
        ECPoint multiply(BigInteger x) {
            ECPoint out=CURVE.getInfinity();
            for (int i=0;i<tab.length;i++) { int d=x.shiftRight(8*i).intValue()&255; if(d!=0) out=out.add(tab[i][d]); }
            return out;
        }
    }
    static final class Context {
        final String schemeID,issuerID; final BigInteger N; final int b,n; private final byte[] cid;
        Context(String schemeID,String issuerID,byte[] cid,BigInteger N,int b,int n) {
            this.schemeID=Objects.requireNonNull(schemeID); this.issuerID=Objects.requireNonNull(issuerID);
            this.cid=cid.clone(); this.N=N; this.b=b; this.n=n;
        }
        byte[] encoding() {
            return encode(bytes(schemeID),bytes(issuerID),cid,N.toByteArray(),integer(b),integer(n));
        }
        byte[] cid() { return cid.clone(); }
    }
    static final class Signature {
        final ECPoint R; final BigInteger z;
        Signature(ECPoint R,BigInteger z) { this.R=R;this.z=z; }
    }
    static final class Entry {
        final int i,j; final ECPoint Y; final Signature signature; private final byte[] label;
        Entry(int i,int j,ECPoint Y,byte[] label,Signature signature) {
            this.i=i;this.j=j;this.Y=Y;this.label=label.clone();this.signature=signature;
        }
        byte[] label() { return label.clone(); }
    }
    // Section 3.2: bind each table entry to its credential context.
    static byte[] label(Context c,int i,int j,ECPoint Y) {
        return hash(encode(c.encoding(),integer(i),integer(j),Y.getEncoded(true)));
    }
    static BigInteger signatureChallenge(ECPoint R,ECPoint pk,byte[] msg) {
        return new BigInteger(1,hash(encode(bytes("CBRP/issuer-Schnorr/v1"),R.getEncoded(true),pk.getEncoded(true),msg))).mod(Q);
    }
    static boolean verifySignature(ECPoint pk,byte[] msg,Signature s) {
        if(s==null || !canonicalScalar(s.z) || !validPoint(s.R) || s.R.isInfinity()) return false;
        BigInteger e=signatureChallenge(s.R,pk,msg);
        return G.multiply(s.z).equals(s.R.add(pk.multiply(e)));
    }
    static final class Credential {
        final Context context; final List<Entry> entries;
        Credential(Context context,List<Entry> entries) {
            this.context=context;this.entries=Collections.unmodifiableList(new ArrayList<>(entries));
        }
    }
    static final class Issuance {
        final Credential credential; final Map<Long,BigInteger> aux;
        Issuance(Credential credential,Map<Long,BigInteger> aux) {
            this.credential=credential;this.aux=Collections.unmodifiableMap(new HashMap<>(aux));
        }
    }
    static long key(int i,int j,int b) { return (long)i*b+j; }
    // Algorithm 6, step 3: issuer keys and used credential identifiers.
    static final class Issuer {
        private final BigInteger sk=nonzeroScalar();
        final ECPoint pk=G.multiply(sk).normalize();
        final String id=HexFormat.of().formatHex(hash(pk.getEncoded(true)));
        private final Set<String> usedIds=new HashSet<>();
        final Comb comb;
        Issuer(Comb comb) { this.comb=comb; }
        Signature sign(byte[] message) {
            BigInteger k=nonzeroScalar(); ECPoint R=comb.multiply(k).normalize();
            return new Signature(R,k.add(signatureChallenge(R,pk,message).multiply(sk)).mod(Q));
        }
        // Algorithm 7: CommitDL.
        synchronized Issuance issue(BigInteger N,int b,BigInteger w) {
            inRange(w,N); int n=digitLength(N,b);
            if ((long)n*b>1_000_000) throw new IllegalArgumentException("research harness table limit: 1,000,000 entries");
            // Algorithm 7, steps 1 and 4: fresh credential context.
            byte[] cid=new byte[32]; String id;
            do { RNG.nextBytes(cid);id=HexFormat.of().formatHex(cid); } while(!usedIds.add(id));
            Context ctx=new Context("DL",this.id,cid,N,b,n);
            int[] wd=digits(w,b,n);
            List<Entry> entries=new ArrayList<>(n*b); Map<Long,BigInteger> aux=new HashMap<>();
            // Algorithm 7, step 3: generate the complete signed table.
            for(int i=0;i<n;i++) for(int j=0;j<b;j++) {
                BigInteger x=scalar(); ECPoint Y=comb.multiply(x).normalize();
                byte[] lab=label(ctx,i,j,Y); entries.add(new Entry(i,j,Y,lab,sign(lab)));
                // Algorithm 7, step 5: release authorized witnesses.
                if(j<=wd[i]) aux.put(key(i,j,b),x);
            }
            return new Issuance(new Credential(ctx,entries),aux);
        }
    }
    // Section 3.3 / Algorithm 9, step 2: one-time table and context checks.
    static final class CheckedTable {
        final Context context; final ECPoint issuerKey; private final Map<Long,Entry> entries;
        CheckedTable(Credential credential,ECPoint trustedIssuerKey,BigInteger expectedN,int expectedB) {
            context=Objects.requireNonNull(credential.context);
            if (!"DL".equals(context.schemeID) || !context.N.equals(expectedN) || context.b!=expectedB
                || context.n!=digitLength(expectedN,expectedB) || context.cid.length!=32
                || !validPoint(trustedIssuerKey) || trustedIssuerKey.isInfinity()
                || !context.issuerID.equals(HexFormat.of().formatHex(hash(trustedIssuerKey.getEncoded(true)))))
                throw new IllegalArgumentException("credential context / parameters / issuer mismatch");
            issuerKey=trustedIssuerKey;
            if(credential.entries.size()!=(long)context.n*context.b) throw new IllegalArgumentException("incomplete table");
            Map<Long,Entry> map=new HashMap<>();
            for(Entry e:credential.entries) {
                if(e==null || e.i<0 || e.i>=context.n || e.j<0 || e.j>=context.b || !validPoint(e.Y)
                    || e.label.length!=32 || e.signature==null || !validPoint(e.signature.R)
                    || e.signature.R.isInfinity() || !canonicalScalar(e.signature.z)
                    || map.put(key(e.i,e.j,context.b),e)!=null) throw new IllegalArgumentException("malformed or duplicate entry");
            }
            entries=Collections.unmodifiableMap(map);
        }
        Entry get(int i,int j) { return entries.get(key(i,j,context.b)); }
        long tableBytes() { return (long)context.n*context.b*(POINT_BYTES+32+POINT_BYTES+SCALAR_BYTES); }
    }
    static ECPoint[][] clonePoints(ECPoint[][] a) {
        ECPoint[][] copy=new ECPoint[a.length][];
        for(int i=0;i<a.length;i++) copy[i]=a[i].clone();
        return copy;
    }
    static final class FirstMessage {
        private final ECPoint[][] a;
        FirstMessage(ECPoint[][] a) { this.a=clonePoints(a); }
    }
    static final class Proof {
        final ECPoint[][] a; final BigInteger[] c; final BigInteger[][] z;
        Proof(ECPoint[][] a,BigInteger[] c,BigInteger[][] z) {
            this.a=clonePoints(a);this.c=c.clone();this.z=new BigInteger[z.length][];
            for(int i=0;i<z.length;i++) this.z[i]=z[i].clone();
        }
        int bytes() { return a.length*a[0].length*65+c.length*32; }
    }
    /** First message and PRIVATE, single-use response state. Never send this state to verifier. */
    static final class ProverState {
        final FirstMessage first; private final BigInteger[] c,alpha,witness;
        private final BigInteger[][] z; private final int branch; private boolean used;
        ProverState(ECPoint[][] a,BigInteger[] c,BigInteger[][] z,BigInteger[] alpha,BigInteger[] witness,int branch) {
            first=new FirstMessage(a);this.c=c;this.z=z;this.alpha=alpha;this.witness=witness;this.branch=branch;
        }
        // Algorithm 8, steps 4-5: Schnorr response and completed transcript.
        synchronized Proof respond(BigInteger challenge) {
            if(used) throw new IllegalStateException("a first message may be answered only once");
            if(!canonicalScalar(challenge)) throw new IllegalArgumentException("challenge outside Z_q");
            used=true; BigInteger real=challenge;
            for(int k=0;k<c.length;k++) if(k!=branch) real=real.subtract(c[k]);
            c[branch]=real.mod(Q);
            for(int i=0;i<alpha.length;i++) z[branch][i]=alpha[i].add(c[branch].multiply(witness[i])).mod(Q);
            Proof proof=new Proof(first.a,c,z);
            Arrays.fill(alpha,null);Arrays.fill(witness,null);
            return proof;
        }
    }
    // Algorithm 8, steps 1-4: branch selection and Schnorr first message.
    static ProverState start(CheckedTable table,Map<Long,BigInteger> aux,BigInteger w,BigInteger t) {
        Context ctx=table.context;inRange(w,ctx.N);inRange(t,ctx.N);
        if(w.compareTo(t)<0) throw new IllegalArgumentException("w below threshold");
        List<BigInteger> S=dedp(t,ctx.b,ctx.n,ctx.N); int ell=S.size(),n=ctx.n;
        int[][] branches=new int[ell][]; int selected=-1;int[] wd=digits(w,ctx.b,n);
        for(int k=0;k<ell;k++) {
            branches[k]=digits(S.get(k),ctx.b,n);
            if(selected<0 && dominates(wd,branches[k])) selected=k;
        }
        if(selected<0) throw new IllegalArgumentException("no available branch");
        ECPoint[][] a=new ECPoint[ell][n]; BigInteger[][] z=new BigInteger[ell][n];
        BigInteger[] c=new BigInteger[ell],alpha=new BigInteger[n],witness=new BigInteger[n];
        for(int i=0;i<n;i++) {
            witness[i]=aux.get(key(i,branches[selected][i],ctx.b));
            if(!canonicalScalar(witness[i])) throw new IllegalArgumentException("missing witness");
            alpha[i]=scalar();a[selected][i]=G.multiply(alpha[i]).normalize();
        }
        for(int k=0;k<ell;k++) if(k!=selected) {
            c[k]=scalar();
            for(int i=0;i<n;i++) {
                z[k][i]=scalar();ECPoint Y=table.get(i,branches[k][i]).Y;
                a[k][i]=G.multiply(z[k][i]).subtract(Y.multiply(c[k])).normalize();
            }
        }
        return new ProverState(a,c,z,alpha,witness,selected);
    }
    // Algorithm 9: VerifyDL using the received first message and verifier challenge.
    static boolean verify(CheckedTable table,BigInteger t,FirstMessage received,Proof proof,BigInteger challenge) {
        try {
            Context ctx=table.context;inRange(t,ctx.N);
            if(received==null || proof==null || !canonicalScalar(challenge)) return false;
            List<BigInteger> S=dedp(t,ctx.b,ctx.n,ctx.N); int ell=S.size(),n=ctx.n;
            if(proof.a.length!=ell || proof.c.length!=ell || proof.z.length!=ell || received.a.length!=ell) return false;
            BigInteger sum=BigInteger.ZERO;
            for(int k=0;k<ell;k++) {
                if(!canonicalScalar(proof.c[k]) || proof.a[k].length!=n || proof.z[k].length!=n || received.a[k].length!=n) return false;
                sum=sum.add(proof.c[k]);
                for(int i=0;i<n;i++) if(!canonicalScalar(proof.z[k][i]) || !validPoint(proof.a[k][i])
                    || !proof.a[k][i].equals(received.a[k][i])) return false;
            }
            if(!sum.mod(Q).equals(challenge)) return false;
            Set<Long> seen=new HashSet<>();
            for(int k=0;k<ell;k++) {
                int[] br=digits(S.get(k),ctx.b,n);
                for(int i=0;i<n;i++) {
                    Entry e=table.get(i,br[i]); if(e==null) return false;
                    if(seen.add(key(i,br[i],ctx.b))) {
                        // Algorithm 9, step 5: verify the label and issuer signature.
                        byte[] expected=label(ctx,i,br[i],e.Y);
                        if(!MessageDigest.isEqual(expected,e.label) || !verifySignature(table.issuerKey,expected,e.signature)) return false;
                    }
                    // Algorithm 9, step 7: check the Schnorr equation.
                    if(!G.multiply(proof.z[k][i]).equals(proof.a[k][i].add(e.Y.multiply(proof.c[k])))) return false;
                }
            }
            return true;
        } catch(IllegalArgumentException | NullPointerException | IndexOutOfBoundsException e) { return false; }
    }
    static void exercise(CheckedTable table,Map<Long,BigInteger> aux,BigInteger w,BigInteger t) {
        ProverState state=start(table,aux,w,t);
        BigInteger c=scalar(); // verifier coin AFTER the first message
        Proof p=state.respond(c);
        if(!verify(table,t,state.first,p,c)) throw new IllegalStateException("verification failed");
    }
    /** CLI: bits bases_csv warmup iterations input_csv samples_csv. */
    public static void main(String[] args) throws Exception {
        if (args.length != 6) throw new IllegalArgumentException("Use scripts/run.py; expected bits bases warmup iterations input.csv samples.csv");
        Locale.setDefault(Locale.ROOT);
        int bits=Integer.parseInt(args[0]);
        int[] bases=Arrays.stream(args[1].split(",")).mapToInt(Integer::parseInt).toArray();
        int warm=Integer.parseInt(args[2]), iters=Integer.parseInt(args[3]);
        if (bases.length == 0 || Arrays.stream(bases).distinct().count() != bases.length)
            throw new IllegalArgumentException("distinct bases required");
        for(int b:bases) if(b!=16 && b!=256 && b!=65536) throw new IllegalArgumentException("base=16/256/65536");
        List<BenchmarkData.Case> cases=BenchmarkData.read(Path.of(args[4]),bits,warm,iters);
        BigInteger N=BigInteger.ONE.shiftLeft(bits);
        long begin=System.nanoTime();Comb comb=new Comb();
        System.err.printf("public_comb_precompute_ms=%.9f%n",(System.nanoTime()-begin)/1e6);
        try (BenchmarkData.Csv csv=new BenchmarkData.Csv(Path.of(args[5]))) {
            for (int b:bases) {
                begin=System.nanoTime(); Issuer issuer=new Issuer(comb);
                System.err.printf("base=%d,issuer_setup_ms=%.9f%n",b,(System.nanoTime()-begin)/1e6);
                for (BenchmarkData.Case c:cases) {
                    System.err.printf("base=%d,phase=%s,iteration=%d: generating fresh credential%n",b,c.phase(),c.iteration());
                    // A new w receives a NEW table and exactly its authorized private subset.
                    // No private witnesses are accumulated from previous trials.
                    begin=System.nanoTime(); Issuance issued=issuer.issue(N,b,c.w());long commitNs=System.nanoTime()-begin;
                    begin=System.nanoTime(); CheckedTable table=new CheckedTable(issued.credential,issuer.pk,N,b);long checkNs=System.nanoTime()-begin;
                    begin=System.nanoTime(); ProverState state=start(table,issued.aux,c.w(),c.t());long firstNs=System.nanoTime()-begin;
                    begin=System.nanoTime(); BigInteger challenge=scalar();long challengeNs=System.nanoTime()-begin;
                    begin=System.nanoTime(); Proof proof=state.respond(challenge);long proveNs=firstNs+System.nanoTime()-begin;
                    begin=System.nanoTime(); boolean ok=verify(table,c.t(),state.first,proof,challenge);long verifyNs=System.nanoTime()-begin;
                    int n=table.context.n,ell=proof.c.length;
                    if(ell<1 || ell>n) throw new IllegalStateException("invalid branch count");
                    Map<String,String> row=BenchmarkData.row("cbrp-dl",bits,c);
                    BenchmarkData.value(row,"base",b);BenchmarkData.value(row,"n",n);BenchmarkData.value(row,"ell",ell);
                    BenchmarkData.value(row,"value_proved",c.w());
                    BenchmarkData.value(row,"credential_id",HexFormat.of().formatHex(table.context.cid()));
                    BenchmarkData.timing(row,"commit_ms",commitNs);BenchmarkData.timing(row,"table_check_ms",checkNs);
                    BenchmarkData.timing(row,"prove_ms",proveNs);BenchmarkData.timing(row,"challenge_ms",challengeNs);
                    BenchmarkData.timing(row,"verify_ms",verifyNs);
                    BenchmarkData.value(row,"proof_bytes",proof.bytes());BenchmarkData.value(row,"table_entries",(long)n*b);
                    BenchmarkData.value(row,"table_bytes",table.tableBytes());BenchmarkData.value(row,"verified",ok?1:0);
                    csv.write(row);
                    if(!ok) throw new IllegalStateException("verification failed");
                }
            }
        }
        System.out.println("CBRP BENCH PASS");
    }
}
