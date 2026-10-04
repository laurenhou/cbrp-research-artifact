# License information

This is a component-licensed source distribution, not a repository-wide MIT,
BSD, or GPL grant. The scope below applies to the supplied files. Existing
third-party licenses are preserved; licenses of independent source components
are not erased when those components are combined into a GPL program.

## Flashproofs benchmark program

The Flashproofs benchmark program assembled in this distribution is provided
under the GNU General Public License, version 3. Its project-specific files are
licensed under **GPL-3.0-only**:

- `src/main/java/FlashproofRangeBench.java`
- `tests/java/flashproofs/FPSelfTest.java`

The assembled program includes the retained Java sources in
`third_party/flashproofs/src/main/java/`, the benchmark/test files above, and the
shared `BenchmarkData.java` and `BackendInfo.java` files listed below. GNU GPL
version 3 applies to that combined program as a whole. The retained MIT notices
for permissive upstream portions and the BSD-2-Clause notices for shared
utilities must also be preserved; those portions keep their separate permissive
licenses for independent use.

The original [Flashproofs License](third_party/flashproofs/License) identifies
GPLv3-origin code in `utils/RandGenerator.java` from the Paillier Threshold
Encryption Toolbox by James Garrity and Sean Hall. This file remains in the
runtime dependency graph. The original upstream notice is not rewritten as a
claim that every individual Flashproofs file originated under GPL.

The full GPL is in [LICENSES/GPL-3.txt](LICENSES/GPL-3.txt) and
[third_party/flashproofs/LICENSE-GPL.txt](third_party/flashproofs/LICENSE-GPL.txt).
The latter supplies the exact filename referenced in the retained upstream
notice. [The integration notice](third_party/flashproofs/NOTICE) identifies the
included components and dated project-specific additions.

The build collects Flashproofs sources separately from CBRP-DL and
BulletProofLib and executes each Java module in its own JVM. Neither
`CBRPDLFull.java` nor `cbrp_ktx_poc.py` is part of the Flashproofs build. Their
reserved status below places no additional restriction on the Flashproofs
program, its GPL rights, or the separately licensed shared utilities.

## BSD-2-Clause project components

Copyright (c) 2026 You-Lin Hou, for the project-authored portions in this section.
These portions are licensed under [BSD-2-Clause](LICENSES/BSD-2-Clause.txt).
This grant does not replace copyright or license notices for any incorporated
third-party material and does not claim ownership of that material.

### Java benchmark utilities and baseline integration

- `src/main/java/research/baselines/hashwires/HashWiresRangeBench.java`
- `tests/java/hashwires/HashWiresSelfTest.java`
- `tests/java/common/HashBackendInfo.java`
- `src/main/java/edu/stanford/cs/crypto/BulletproofRangeBench.java`
- `src/main/java/research/cbrp/bench/BenchmarkData.java`
- `tests/java/bulletproofs/BPSelfTest.java`
- `tests/java/common/BackendInfo.java`
- `tests/java/cbrp-dl/BenchmarkDataSelfTest.java`

The HashWires driver/self-test use the MIT-licensed Java protocol port described
below. The Bulletproofs driver and its self-test use the MIT-licensed
BulletProofLib source subset. The BSD grant is for project-specific integration,
tests and measurement plumbing, not a relabeling of either MIT component.

### Build, input, execution, CSV reporting, and tool tests

- `scripts/build.py`
- `scripts/common.py`
- `scripts/inputs.py`
- `scripts/report.py`
- `scripts/results_io.py`
- `scripts/run.py`
- `scripts/run_ktx.py`
- `scripts/test.py`
- `tests/test_tools.py`

### Dependency declarations, configuration, and instructions

- `config/dependencies/bulletproofs.xml`
- `config/dependencies/cbrp-dl.xml`
- `config/dependencies/flashproofs.xml`
- `config/dependencies/hashwires.xml`
- `.gitattributes`
- `.gitignore`
- `.java-version`
- `.python-version`
- `requirements.txt`
- `README.md`
- `README.zh-TW.md`
- `LICENSE`
- `LICENSE-STATUS.md`
- `THIRD_PARTY_NOTICES.md`
- `provenance/sources.json`
- `third_party/hashwires/NOTICE`
- `config/profiles/check-java.json`
- `config/profiles/hashwires-paper-fixed.json`
- `config/profiles/random-java.json`
- `config/profiles/random-ktx.json`
- `config/profiles/smoke.json`

The grant for these instructions and metadata covers their project-authored
text only. Third-party quotations/notices and the license texts themselves
remain governed by their original terms. The listed scripts may refer to or
invoke separately licensed components; this does not grant a license to those
components. In particular, licensing `run_ktx.py` does not license the imported
KTX research implementation.

## Retained and ported third-party sources

`third_party/hashwires/src/main/java/org/hashwires/HashWires.java` is a
Java 17 derivative/port of the recorded MIT-licensed HashWires Rust snapshot.
It preserves the upstream Facebook copyright notice and adds the port author's
copyright notice; the Java protocol file is distributed under the same MIT
terms in `third_party/hashwires/LICENSE`. The port notice records the
implemented ordinary one-time scope and material differences from the Rust
crate, including the JDK SHA-256 backend, deterministic shuffle sampler, Java
proof encoding, exclusion of the outer Section 5.2 T-time wrapper and exclusion
of the optional checksum chain. The language port is not represented as a
line-for-line entry in `provenance/third-party.patch`.

The 26 Java source files under `third_party/bulletprooflib/` retain the
[original MIT license](third_party/bulletprooflib/LICENSE), including the
copyright notice for Benedikt Bünz as written in that license. Retained
modifications to this subset are distributed under the same MIT terms.
`provenance/third-party.patch` preserves their differences from the recorded
snapshot and does not change the licenses of the represented source files.

The 19 Java files under `third_party/flashproofs/` match the source text of
the retained snapshot identified in `provenance/sources.json`. The sole byte-level
difference is LF-normalized line endings in `zkp/ZKP.java`; no source statements
differ. Their original [License](third_party/flashproofs/License), MIT
attributions and GPLv3 origin notice are preserved. Component attribution is detailed in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Research-specific material without a new license grant

No additional software license is selected here for:

- `src/main/java/CBRPDLFull.java`
- `experiments/ktx/cbrp_ktx_poc.py`
- `tests/java/cbrp-dl/CBRPSelfTest.java`
- `tests/test_ktx.py`
- `results/reference/`

These files are not included in the GPL or BSD grants above. Their availability
in this source distribution must not be represented as a repository-wide open
source license. This reservation does not withdraw any pre-existing permission,
limit rights granted for third-party or expressly licensed components, or
restrict use of unprotected facts or other rights available under applicable law.

## Source and dependency distribution

This package distributes source, configuration, and instructions, not compiled
applications, JAR dependencies, Python wheels, or a virtual environment. All project-specific source and build/run scripts for the Java modules are
included. HashWires is JDK-only; its reproducible entry points are
`scripts/build.py --module hashwires` and `scripts/run.py --scheme hashwires`.
Flashproofs uses `scripts/build.py --module flashproofs` and
`scripts/run.py --scheme flashproofs`; see the README for interpreter commands
and environment setup.

Bouncy Castle, Guava, Cyclops React, NumPy and transitive dependencies keep their
own licenses. The package declares dependencies in `config/dependencies/` and
`requirements.txt` rather than redistributing their binaries. A downstream
binary distribution of the Flashproofs program must meet GPLv3 section 6 for
its complete Corresponding Source, including applicable linked dependencies
and build information; this source-only archive is not a prewritten source
offer or a certification for an arbitrary binary/dependency combination.

## License notice date

2026-09-30: the project-specific Flashproofs integration is offered under
GPL-3.0-only, the listed tools/instructions under BSD-2-Clause, and the existing
third-party notices are preserved.

2026-10-04: the ordinary one-time HashWires Java protocol port is added under
MIT, with its project-specific driver, tests, build integration and instructions
under BSD-2-Clause. No HashWires measurements are added to the historical
reference CSV files.
