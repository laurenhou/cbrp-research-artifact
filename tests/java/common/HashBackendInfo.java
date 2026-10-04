/*
 * Copyright (c) 2026 You-Lin Hou
 * SPDX-License-Identifier: BSD-2-Clause
 * See LICENSES/BSD-2-Clause.txt.
 */
import java.security.MessageDigest;

public final class HashBackendInfo {
    public static void main(String[] args) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        System.out.println("MessageDigest=" + digest.getAlgorithm());
        System.out.println("Provider=" + digest.getProvider().getName() + " " + digest.getProvider().getVersionStr());
        System.out.println("ProviderInfo=" + digest.getProvider().getInfo());
        System.out.println("Java=" + System.getProperty("java.version"));
    }
}
