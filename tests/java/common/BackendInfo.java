/*
 * Copyright (c) 2026 You-Lin Hou
 * SPDX-License-Identifier: BSD-2-Clause
 * See LICENSES/BSD-2-Clause.txt.
 */
import org.bouncycastle.jce.provider.BouncyCastleProvider;
import org.bouncycastle.math.ec.ECPoint;

import java.net.URI;
import java.nio.file.Path;

public final class BackendInfo {
    private static String sourceName(Class<?> type) {
        try {
            URI location = type.getProtectionDomain().getCodeSource().getLocation().toURI();
            Path path = Path.of(location);
            Path name = path.getFileName();
            return name == null ? "classes" : name.toString();
        } catch (Exception ignored) {
            return "unavailable";
        }
    }

    public static void main(String[] args) {
        System.out.println(new BouncyCastleProvider().getInfo());
        System.out.println("ECPointSource=" + sourceName(ECPoint.class));
        System.out.println("Java=" + System.getProperty("java.version"));
    }
}
