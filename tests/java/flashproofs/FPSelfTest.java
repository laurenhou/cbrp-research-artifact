import config.*;
import zkp.range.RangeZKPK3;
import java.lang.reflect.Field;
import java.math.BigInteger;
import java.util.List;
public final class FPSelfTest {
    @SuppressWarnings("unchecked")
    public static void main(String[] args) throws Exception {
        Config.getInstance().init(new BouncyKey("bn128"));
        RangeZKPK3 p=new RangeZKPK3(BigInteger.valueOf(123),32,11);
        if(!p.verify()) throw new AssertionError("honest proof rejected");
        Field f=p.getClass().getDeclaredField("vs");f.setAccessible(true);
        List<BigInteger> values=(List<BigInteger>)f.get(p);values.set(0,values.get(0).add(BigInteger.ONE));
        if(p.verify()) throw new AssertionError("altered response accepted");
        System.out.println("FLASHPROOFS SELFTEST PASS: honest accepted, altered response rejected");
    }
}
