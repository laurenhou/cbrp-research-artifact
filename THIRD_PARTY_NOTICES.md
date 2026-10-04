# Third-party sources and notices

Original source headers and license notices are retained. The source lineage is recorded in `provenance/sources.json`; `provenance/third-party.patch` records differences from the retained upstream snapshots. This notice does not grant a repository-wide license.


## BulletProofLib

Source identifier: `https://github.com/bbuenz/BulletProofLib`.

The BN128 range-proof subset contains 26 Java source files and the original [MIT license](third_party/bulletprooflib/LICENSE), copyright 2017 Benedikt Bünz. The retained code includes changes relative to its source snapshot, including unused-import removal and diagnostic-output changes. The corresponding diff is retained; this modified subset continues to be provided under its original MIT terms. A locally recorded snapshot identifier is not an independent verification of the present remote repository.

## Flashproofs

Source identifier: `https://github.com/wangnan-vincent/Flashproofs`.

The subset contains `RangeZKPK3`, `RangeZKPK4` and required dependencies: 19 Java source files. The original [License](third_party/flashproofs/License) contains MIT notices for Nan Wang and Benedikt Bünz, and separately identifies `utils/RandGenerator.java` as using GPLv3-origin code from the Paillier Threshold Encryption Toolbox by James Garrity and Sean Hall.

`RandGenerator.java` remains a runtime dependency for library randomness. The [GPL-3 text](LICENSES/GPL-3.txt) is retained and an identical copy is supplied as [LICENSE-GPL.txt](third_party/flashproofs/LICENSE-GPL.txt), the filename referenced by the original notice. The original upstream `License` and all 19 retained Java files are unchanged by this licensing update. Relative to the recorded upstream ZIP, `zkp/ZKP.java` has LF-normalized line endings; the other 18 Java files and the `License` are byte-identical.

The assembled Flashproofs benchmark program is provided under GNU GPL version 3. Its project-specific driver and self-test are GPL-3.0-only; the separately licensed shared utilities are BSD-2-Clause. See the dated [integration notice](third_party/flashproofs/NOTICE) and [file-level scope](LICENSE-STATUS.md). Existing MIT permissions and attribution for individual upstream portions are not removed.

`zkp/TestConstants.java` is referenced by the range-proof classes and is necessary for compilation. The randomized benchmark wrapper reads synthetic `w,t` from CSV and calls the retained proof implementation with `w-t`; it does not change the upstream range-proof equations.

## HashWires

Source identifier: `https://github.com/novifinancial/hashwires`.

The recorded upstream ZIP identifies snapshot
`473f726f243c8ac1329d9eccda0947f0a111311e` and is licensed under MIT,
Copyright (c) Facebook, Inc. and its affiliates. The original MIT text is
retained at [third_party/hashwires/LICENSE](third_party/hashwires/LICENSE).

`third_party/hashwires/src/main/java/org/hashwires/HashWires.java` is a
Java 17 derivative/port rather than a byte-identical retained Rust file. It
implements the optimized ordinary one-time construction: MDP computation,
shared multichains, PLA, 16-byte MDP salts, deterministic leaf placement and a
fixed-height deterministically padded Merkle accumulator. It uses the JDK
SHA-256 provider. The project-specific benchmark driver and tests are separately
BSD-2-Clause.

The Java port uses a domain-separated SHA-256 counter sampler for its
Durstenfeld-style shuffle instead of the Rust snapshot's ChaCha12 sampler. It
follows paper Algorithm 1 at exact powers of the base (`b^i <= x`), checks
actual digit-wise dominance when selecting a branch, and represents zero with
one significant zero digit for the artifact's `[0,2^bits)` domain. These edge
choices intentionally differ from the recorded Rust snapshot. Its canonical
proof encoding follows the paper's element-count accounting and is not claimed
to be byte-for-byte interoperable with the Rust crate. The ordinary
construction's internal Merkle accumulator is present; the outer
Section 5.2 T-time wrapper and optional checksum chain are absent. See the
[port notice](third_party/hashwires/NOTICE) and
[provenance record](provenance/sources.json). Because this is a language port,
`provenance/third-party.patch` is not a line-by-line representation of it.

## Other dependencies

Bouncy Castle, Cyclops React, Guava and their transitive dependencies, and NumPy retain their respective licenses. The HashWires module uses only the active JDK SHA-256 provider and adds no third-party JAR. Maven dependency declarations are in `config/dependencies/`; NumPy is specified in `requirements.txt`. No dependency JAR, wheel, virtual environment or compiled application class is distributed in this source archive.

Repository-level license information is in [LICENSE-STATUS.md](LICENSE-STATUS.md).
