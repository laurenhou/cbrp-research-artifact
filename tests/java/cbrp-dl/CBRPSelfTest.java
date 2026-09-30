import java.math.BigInteger;
import java.util.*;
import org.bouncycastle.math.ec.ECPoint;

public final class CBRPSelfTest {
    static int checks;
    static void check(boolean yes,String name) { if(!yes) throw new AssertionError(name);checks++; }
    static void rejects(Runnable r,String name) {
        try { r.run(); } catch(IllegalArgumentException|IllegalStateException e) { checks++;return; }
        throw new AssertionError(name);
    }
    static BigInteger bi(long x) { return BigInteger.valueOf(x); }
    public static void main(String[] args) {
        // Exhaustive finite ranges, including non-powers and t=0.
        for(int N=2;N<=35;N++) for(int b=2;b<=7;b++) {
            int n=CBRPDLFull.digitLength(bi(N),b);
            for(int t=0;t<N;t++) {
                List<BigInteger> S=CBRPDLFull.dedp(bi(t),b,n,bi(N));
                check(S.size()<=n,"ell <= n");
                for(int w=0;w<N;w++) {
                    int[] wd=CBRPDLFull.digits(bi(w),b,n); boolean cover=false;
                    for(BigInteger y:S) if(CBRPDLFull.dominates(wd,CBRPDLFull.digits(y,b,n))) cover=true;
                    check(cover==(w>=t),"coverage / no false branch");
                }
                for(BigInteger y:S) for(int z=t;z<N;z++) if(!y.equals(bi(z)))
                    check(!CBRPDLFull.dominates(CBRPDLFull.digits(y,b,n),CBRPDLFull.digits(bi(z),b,n)),"minimal representative");
            }
        }
        CBRPDLFull.Comb comb=new CBRPDLFull.Comb();
        check(comb.multiply(BigInteger.ZERO).isInfinity(),"comb zero");
        for(int i=0;i<5;i++) { BigInteger r=CBRPDLFull.scalar();check(comb.multiply(r).equals(CBRPDLFull.G.multiply(r)),"comb correctness"); }
        CBRPDLFull.Issuer issuer=new CBRPDLFull.Issuer(comb);
        BigInteger N=bi(256),w=bi(200),t=bi(129);
        CBRPDLFull.Issuance a=issuer.issue(N,16,w),b=issuer.issue(N,16,w);
        check(!Arrays.equals(a.credential.context.cid(),b.credential.context.cid()),"fresh same-issuer cid");
        check(a.aux.size()==22,"private release policy"); // w=0xc8: 13+9 entries
        CBRPDLFull.CheckedTable table=new CBRPDLFull.CheckedTable(a.credential,issuer.pk,N,16);
        for(int threshold:new int[]{0,1,16,128,129,190,200}) {
            CBRPDLFull.ProverState st=CBRPDLFull.start(table,a.aux,w,bi(threshold));
            BigInteger c=CBRPDLFull.scalar();CBRPDLFull.Proof p=st.respond(c);
            check(CBRPDLFull.verify(table,bi(threshold),st.first,p,c),"reusable table positive");
        }
        CBRPDLFull.ProverState state=CBRPDLFull.start(table,a.aux,w,t);
        BigInteger c=BigInteger.ZERO;CBRPDLFull.Proof proof=state.respond(c);
        check(CBRPDLFull.verify(table,t,state.first,proof,c),"zero external challenge");
        check(proof.bytes()==324,"normalized size");
        check(!CBRPDLFull.verify(table,t,state.first,proof,BigInteger.ONE),"fresh challenge rejects literal replay");
        rejects(()->state.respond(c),"nonce state reuse");
        check(!CBRPDLFull.verify(table,t,state.first,proof,CBRPDLFull.Q),"noncanonical challenge");
        BigInteger old=proof.z[0][0];proof.z[0][0]=old.add(BigInteger.ONE).mod(CBRPDLFull.Q);
        check(!CBRPDLFull.verify(table,t,state.first,proof,c),"altered response");proof.z[0][0]=old;
        check(!CBRPDLFull.verify(table,t,CBRPDLFull.start(table,a.aux,w,t).first,proof,c),"first-message binding");
        rejects(()->CBRPDLFull.start(table,a.aux,w,bi(201)),"false threshold");
        rejects(()->CBRPDLFull.start(table,Collections.emptyMap(),w,t),"missing witness");
        rejects(()->new CBRPDLFull.CheckedTable(a.credential,issuer.pk,bi(512),16),"wrong N");
        rejects(()->new CBRPDLFull.CheckedTable(a.credential,new CBRPDLFull.Issuer(comb).pk,N,16),"wrong issuer");
        List<CBRPDLFull.Entry> es=new ArrayList<>(a.credential.entries);es.remove(0);
        rejects(()->new CBRPDLFull.CheckedTable(new CBRPDLFull.Credential(a.credential.context,es),issuer.pk,N,16),"missing entry");
        es.add(es.get(0));
        rejects(()->new CBRPDLFull.CheckedTable(new CBRPDLFull.Credential(a.credential.context,es),issuer.pk,N,16),"duplicate entry");
        CBRPDLFull.Context wrongContext=new CBRPDLFull.Context("DL",issuer.id,b.credential.context.cid(),N,16,2);
        CBRPDLFull.CheckedTable moved=new CBRPDLFull.CheckedTable(new CBRPDLFull.Credential(wrongContext,a.credential.entries),issuer.pk,N,16);
        check(!CBRPDLFull.verify(moved,t,state.first,proof,c),"cross-credential labels rejected");
        List<CBRPDLFull.Entry> changed=new ArrayList<>(a.credential.entries);
        int pos=1;CBRPDLFull.Entry e=changed.get(pos); // threshold 0x81 references (0,1)
        changed.set(pos,new CBRPDLFull.Entry(e.i,e.j,e.Y,e.label(),new CBRPDLFull.Signature(e.signature.R,e.signature.z.add(BigInteger.ONE).mod(CBRPDLFull.Q))));
        CBRPDLFull.CheckedTable badSig=new CBRPDLFull.CheckedTable(new CBRPDLFull.Credential(a.credential.context,changed),issuer.pk,N,16);
        check(!CBRPDLFull.verify(badSig,t,state.first,proof,c),"tampered issuer signature");
        byte[] badLab=e.label();badLab[0]^=1;
        changed.set(pos,new CBRPDLFull.Entry(e.i,e.j,e.Y,badLab,e.signature));
        CBRPDLFull.CheckedTable badLabel=new CBRPDLFull.CheckedTable(new CBRPDLFull.Credential(a.credential.context,changed),issuer.pk,N,16);
        check(!CBRPDLFull.verify(badLabel,t,state.first,proof,c),"label recomputed");
        // Replace a public statement while retaining a genuinely signed OLD label.
        // Generate a mathematically valid proof for the replaced statement: only the
        // recomputed context/index/Y label check should reject this credential.
        BigInteger replacementWitness=bi(42);
        changed.set(pos,new CBRPDLFull.Entry(e.i,e.j,CBRPDLFull.G.multiply(replacementWitness),e.label(),e.signature));
        CBRPDLFull.CheckedTable replacedY=new CBRPDLFull.CheckedTable(new CBRPDLFull.Credential(a.credential.context,changed),issuer.pk,N,16);
        Map<Long,BigInteger> replacedAux=new HashMap<>(a.aux);replacedAux.put(1L,replacementWitness);
        CBRPDLFull.ProverState tamperedState=CBRPDLFull.start(replacedY,replacedAux,w,t);
        CBRPDLFull.Proof tamperedProof=tamperedState.respond(BigInteger.ONE);
        check(!CBRPDLFull.verify(replacedY,t,tamperedState.first,tamperedProof,BigInteger.ONE),"recomputed label binds public Y");
        check(!Arrays.equals(CBRPDLFull.encode(new byte[]{1},new byte[]{2,3}),CBRPDLFull.encode(new byte[]{1,2},new byte[]{3})),"canonical framing");
        // Independent credentials for different certified values, including boundary cases.
        Set<String> ids=new HashSet<>();
        for(int value:new int[]{0,1,15,16,127,128,200,255}) {
            CBRPDLFull.Issuance issued=issuer.issue(N,16,bi(value));
            check(ids.add(HexFormat.of().formatHex(issued.credential.context.cid())),"fresh credential each value");
            int[] wd=CBRPDLFull.digits(bi(value),16,2);
            check(issued.aux.size()==wd[0]+wd[1]+2,"new value receives exactly its witnesses");
            CBRPDLFull.CheckedTable fresh=new CBRPDLFull.CheckedTable(issued.credential,issuer.pk,N,16);
            for(int threshold:new int[]{0,value}) {
                CBRPDLFull.ProverState st=CBRPDLFull.start(fresh,issued.aux,bi(value),bi(threshold));
                BigInteger ch=CBRPDLFull.scalar();CBRPDLFull.Proof pr=st.respond(ch);
                check(CBRPDLFull.verify(fresh,bi(threshold),st.first,pr,ch),"fresh input edge-case proof");
                check(pr.bytes()==65*pr.c.length*2+32*pr.c.length,"threshold-dependent size");
            }
        }
        System.out.println("CBRP SELFTEST PASS: "+checks+" assertions (functional, not a security proof)");
    }
}
