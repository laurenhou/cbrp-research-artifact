/*
 * Copyright (c) 2026 You-Lin Hou
 * SPDX-License-Identifier: BSD-2-Clause
 * See LICENSES/BSD-2-Clause.txt.
 */
import org.bouncycastle.jce.provider.BouncyCastleProvider;
import org.bouncycastle.math.ec.ECPoint;
public final class BackendInfo {
    public static void main(String[] args) {
        System.out.println(new BouncyCastleProvider().getInfo());
        System.out.println("ECPoint="+ECPoint.class.getProtectionDomain().getCodeSource().getLocation());
        System.out.println("Java="+System.getProperty("java.version"));
    }
}
