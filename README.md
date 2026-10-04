# CBRP Research Artifact

[繁體中文說明](README.zh-TW.md)

This repository accompanies the journal manuscript *A Public-Coin Credential-Based Range Proof with Reusable Commitments*. Its primary research implementations are CBRP-DL and the CBRP-KTX functional prototype. Bulletproofs, Flashproofs, and ordinary one-time HashWires are isolated comparison baselines.

The package contains source code, build and validation tools, experiment profiles, and historical reference CSV files. It is a research artifact, not a production credential system.

## Requirements

| Component | Requirement |
|---|---|
| Operating system | Linux; the commands below use Ubuntu |
| Java | JDK 17; compilation targets Java 17 |
| Maven | Resolves dependencies for CBRP-DL, Bulletproofs, and Flashproofs |
| Python | 3.11 or newer; Python 3.12 is the example environment |
| NumPy | `numpy==2.3.5`, pinned in `requirements.txt` |
| Memory | Each Java process defaults to a `2g` maximum heap |

HashWires is JDK-only and uses the active JDK SHA-256 provider. The KTX prototype uses NumPy.

## 1. Install the basic tools

```bash
sudo apt update
sudo apt install -y openjdk-17-jdk maven python3 python3-venv python3-pip curl ca-certificates git unzip
java -version
javac -version
mvn -version
python3 --version
```

For a Java 17 evaluation, `java`, `javac`, and the Java runtime shown by Maven must all use JDK 17. When several JDKs are installed:

```bash
sudo update-alternatives --config java
sudo update-alternatives --config javac
export JAVA_HOME="$(dirname "$(dirname "$(readlink -f "$(command -v javac)")")")"
mvn -version
```

Do not replace the operating system's `/usr/bin/python3`. Ubuntu 20.04's Python 3.8 is too old for the pinned NumPy release; create a separate environment as shown below.

## 2. Extract and verify the source

```bash
mkdir -p ~/research/cbrp
unzip ~/Downloads/cbrp-research-artifact.zip -d ~/research/cbrp
cd ~/research/cbrp/cbrp-research-artifact
sha256sum -c SHA256SUMS
```

Adjust the archive path as needed. Extract each release into a new directory rather than overlaying an older copy. All later commands run from the project root containing `scripts/`, `src/`, and `requirements.txt`.

`SHA256SUMS` covers the release files other than the manifest itself. Generated environments, dependencies, classes, and run outputs are not part of the source archive.

## 3. Create the Python environment

When Python 3.11 or newer is already installed:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip check
python -c "import sys, numpy; print(sys.version); print(numpy.__version__); print(sys.executable)"
```

Use `python3` instead of `python3.12` only after confirming that it is compatible.

When the available interpreter is older, install a separate Python with `uv`:

```bash
UV_INSTALLER="$(mktemp)"
curl -LsSf https://astral.sh/uv/install.sh -o "$UV_INSTALLER" &&
UV_INSTALL_DIR="$HOME/.local/bin" UV_NO_MODIFY_PATH=1 sh "$UV_INSTALLER"
export PATH="$HOME/.local/bin:$PATH"
uv python install 3.12
uv venv --python 3.12 --seed .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip check
```

An environment created with an older Python must be recreated; activating it does not upgrade its interpreter. NumPy should report version `2.3.5`.

## 4. Build the Java implementations

```bash
python scripts/build.py
```

Each scheme has an isolated classpath and runs in its own JVM.

| Scheme | Direct dependencies |
|---|---|
| CBRP-DL | Bouncy Castle 1.61 |
| Bulletproofs | Bouncy Castle 1.57, Cyclops React 2.0.0-FINAL, Guava 24.1.1-jre |
| Flashproofs | Bouncy Castle 1.56, Guava 23.0 |
| HashWires | None; JDK SHA-256 |

Dependency declarations are under `config/dependencies/`. The root directory is not a Maven project; use `scripts/build.py`, not `mvn package`. A successful full build prints four `BUILD PASS` messages and records source, dependency, provider, and class hashes in `build/<scheme>/build.json`.

For an offline dependency set:

```bash
python scripts/build.py --dependency-dir /path/to/dependencies
```

The supplied directory must contain `cbrp-dl/*.jar`, `bulletproofs/*.jar`, and `flashproofs/*.jar`. HashWires accepts no JARs. Local JAR mode is recorded as `local-jars`; it is not treated as independent verification of the Maven declarations. Dependency JARs are not included in this source distribution.

The run tools reject changed, missing, or additional class/JAR outputs. Rebuild after editing source or changing dependencies.

## 5. Run the tests

```bash
python scripts/test.py
```

Success ends with `TEST PASS`. The suite includes:

- DedP coverage and boundary cases;
- CBRP-DL, Bulletproofs, Flashproofs, and HashWires honest/tampered checks;
- HashWires MDP, serialization, and proof-size regressions;
- KTX statement, challenge, witness-shape, replay, and single-use-state checks;
- a regression check that the public KTX matrix seed does not determine private witnesses or masks;
- exact 64-bit CSV handling, timing accounting, result aggregation, and fixture validation.

These are functional and regression tests, not cryptographic security proofs.

```bash
python scripts/test.py --java-only
python scripts/test.py --python-only
```

## 6. Run small end-to-end checks

```bash
python scripts/run.py --profile smoke
python scripts/run_ktx.py --bits 16 --bases 16 --rho 3 --warmup 0 --iterations 3
```

The Java smoke profile executes all four Java schemes at 32 bits, with `b=16` for CBRP-DL and HashWires, three measured input pairs, and no warm-up. The KTX command uses three Stern repetitions. These commands check installation and output handling; they are not performance or security estimates.

For broader Java coverage without the expensive CBRP-DL `b=65536` table:

```bash
python scripts/run.py --profile check-java
```

## Comparison baselines and scope

| Baseline | Role | Scope note |
|---|---|---|
| Bulletproofs | General range-proof baseline | Proves the range of `delta=w-t`; it does not certify the issuer's original `w` |
| Flashproofs | General range-proof baseline | Proves `delta` with its own decomposition parameters |
| HashWires | Trusted-issuer hash-based CBRP baseline | Optimized ordinary one-time construction; the outer Section 5.2 `T`-time wrapper is not included |

The HashWires Java port retains minimum dominating partitions, shared multichains, padded linear accumulation, per-MDP salts, deterministic placement, and the construction's fixed-height padded Merkle accumulator. The mapping to the paper and recorded Rust snapshot, intentional differences, and omitted optional features are documented in [`third_party/hashwires/NOTICE`](third_party/hashwires/NOTICE).

HashWires proof generation reconstructs commitment-related state to obtain the inclusion path. Its `commit_ms` and `prove_ms` therefore contain overlapping computation even though both operations occur in the measured fresh one-time workflow. Use the individual timing fields and `timing_scope`; do not interpret a cross-scheme sum as a common online cost.

The fixed-statement HashWires profile uses `w=N-2` and `t=floor(N/2)+1`, with a fresh seed and commitment in every execution:

```bash
python scripts/run.py --profile hashwires-paper-fixed
```

## 7. Run the Java experiment grid

A moderate individual configuration:

```bash
python scripts/run.py --scheme cbrp-dl --bits 32 --bases 256 --warmup 2 --iterations 10
```

The complete profile is:

```bash
python scripts/run.py --profile random-java
```

| Scheme | Bits | Base/decomposition | Warm-ups | Measurements |
|---|---|---|---:|---:|
| CBRP-DL | 32, 64 | `b=16,256,65536` | 10 | 50 |
| Bulletproofs | 32, 64 | Binary proof of `delta` | 5 | 20 |
| Flashproofs | 32 | `K=3,L=11` | 5 | 20 |
| Flashproofs | 64 | `K=4,L=16` | 5 | 20 |
| HashWires | 32, 64 | `b=16,256`, SHA-256 | 5 | 20 |

The profile produces 14 configuration summaries and 460 measured executions. Each `(scheme, bits, base)` Java configuration runs in a separate JVM, so later radices do not inherit JIT or garbage-collection state from earlier radices.

CBRP-DL issues a fresh full credential table in every execution. HashWires creates a fresh ordinary one-time commitment in every execution. Bulletproofs and Flashproofs prove the shifted value `delta=w-t`, not a credential-bound statement about `w`.

Useful overrides:

```bash
python scripts/run.py --profile random-java --warmup 0 --iterations 2
python scripts/run.py --scheme hashwires --bits 64 --bases 16,256 --warmup 5 --iterations 20
python scripts/run.py --scheme bulletproofs --bits 64 --warmup 5 --iterations 20
python scripts/run.py --scheme flashproofs --bits 64 --warmup 5 --iterations 20
```

`--heap 4g` changes the JVM heap limit. `--repeat 3` creates independent fixture schedules and JVM executions. `--timeout 600` limits each JVM to 600 seconds. Per-repeat summaries remain in `summary.csv`; `summary-aggregate.csv` combines matching configurations across repeats.

## 8. Run the KTX prototype grid

```bash
python scripts/run_ktx.py --profile random-ktx
```

The profile covers 16/32/64-bit ranges with `b=16,256`, using `q=4093`, `nL=128`, `m=512`, and `rho=137`. Each of the six configurations has two warm-ups and 20 measurements. A fresh KTX instance and public matrix are created per configuration, and the configuration order is deterministically shuffled for each repeat.

The recorded seed controls public fixtures and public matrices only. Private witnesses and masks use an independent, unrecorded entropy-seeded PRNG. This separation prevents reconstruction from the public seed, but the prototype still uses toy parameters and hash commitments and is not a production or complete post-quantum implementation.

A smaller run:

```bash
python scripts/run_ktx.py --profile random-ktx --warmup 1 --iterations 3
```

## 9. Understand the result files

Each run creates a new directory under `results/runs/`:

```bash
ls -lt results/runs/
```

| File | Contents |
|---|---|
| `samples.csv` | All measured rows |
| `warmup.csv` | Warm-up rows excluded from statistics |
| `summary.csv` | Statistics for each repeat/job |
| `summary-aggregate.csv` | Statistics combined across matching repeats/jobs |
| `inputs-r<repeat>-b<bits>.csv` | Exact synthetic fixtures, including warm-ups |
| `NN-*.samples.csv` | Raw per-process/per-configuration observations |
| `setup.csv` | Setup and precomputation outside per-case timing regions |
| `metadata.json`, `STATUS` | Environment, configuration, hashes, execution policy, and completion state |
| Java `*.stdout.log`, `*.stderr.log` | Progress and diagnostics |

The CSV timing fields are deliberately explicit:

| Field | Meaning |
|---|---|
| `commit_ms` | Scheme-specific issuance, table construction, or commitment work; blank for Flashproofs |
| `standalone_commit_ms` | Flashproofs-only diagnostic commitment that is not consumed by the proof constructor |
| `table_check_ms` | CBRP-DL credential-table validation |
| `prove_ms`, `challenge_ms`, `verify_ms` | Measured proof phases |
| `online_total_ms` | `prove_ms + challenge_ms + verify_ms` |
| `recorded_total_ms` | Sum of non-diagnostic measured workflow regions; excludes `standalone_commit_ms` |
| `timing_scope` | Identifies the scheme-specific workflow represented by the row |

`online_total_ms` and `recorded_total_ms` are bookkeeping fields, not proof that the schemes expose identical interfaces or workloads. Cross-scheme conclusions should compare named phases and account for credential issuance, table reuse, statement differences, and overlapping HashWires work.

`proof_bytes` is accompanied by `proof_size_basis`:

- `actual-serialization`: bytes emitted by the HashWires serializer;
- `canonical-element-model`: point/scalar element accounting for CBRP-DL and Bulletproofs;
- `reflected-element-model`: reflected point/scalar list accounting for Flashproofs;
- `packed-estimate-12-bit`: packed KTX estimate, not the prototype's in-memory NumPy representation.

CSV files contain synthetic secret values to make the workload auditable. Do not use real credential secrets as benchmark inputs. Import 64-bit integer and seed columns as text in spreadsheet software to avoid rounding.

For Java runs, `--seed` controls fixtures only. For KTX runs, it controls fixtures and public matrices only. Protocol keys, witnesses, masks, commitments, and challenges use separate randomness.

## 10. Validate and summarize a completed run

Replace the placeholder with the directory printed by the runner:

```bash
python scripts/report.py --run "results/runs/ACTUAL_RUN_DIRECTORY"
```

The report tool verifies completion status, CSV hashes, fixtures, raw rows, descriptors, proof sizes, timing accounting, and both summary files. It writes a validated copy under `results/reports/` without modifying the original run.

To copy the stored historical values without executing proofs:

```bash
python scripts/report.py --reference
```

Historical CSVs are kept separate from new measurements and do not include newly generated HashWires results.

## Repository layout

```text
cbrp-research-artifact/
├── README.md / README.zh-TW.md
├── config/                 # Dependency declarations and experiment profiles
├── src/main/java/          # CBRP-DL, baseline drivers, shared CSV utilities
├── experiments/ktx/        # KTX-CBRP functional prototype
├── third_party/            # Isolated retained/ported comparison sources
├── scripts/                # Build, test, runner, fixture, and report tools
├── tests/                  # Functional and regression tests
├── results/reference/      # Historical CSV values, not new measurements
├── provenance/             # Source lineage and retained third-party patch
├── LICENSES/               # License texts
└── SHA256SUMS              # Release-file integrity manifest
```

`.venv/`, `build/`, `results/runs/`, `results/reports/`, caches, JARs, and classes are local outputs. They are ignored by Git and excluded from the source archive. Share a complete run directory separately when experiment results need review.

## Troubleshooting

**NumPy 2.3.5 is unavailable:** check `python --version`. Python 3.8 is unsupported; create the separate Python 3.12 environment described above rather than changing `requirements.txt`.

**Maven is missing or dependency resolution fails:** inspect `mvn -version` and network access. Offline local-JAR mode is recorded separately from Maven mode.

**`Changed/missing build file` or `Build output set changed`:** rerun `python scripts/build.py`. The runners intentionally reject stale or additional classes/JARs.

**A large-base CBRP-DL run appears inactive:** each execution creates and signs `n*b` table entries. Inspect the current `*.stderr.log`; a partial CSV is not a completed run.

**Current sizes or timings differ from the historical tables:** current runs vary `w`, `t`, branch count, credentials, and commitments. HashWires proof length can also vary with truncation and PLA padding. These are workload differences, not merely timing noise.

**Can this code be deployed directly?** No. The package does not provide an audited constant-time implementation, a production network protocol, persistent issuer registry, or production KTX parameters and commitments.

## Licenses

The repository uses component-level licensing rather than a single repository-wide license. The assembled Flashproofs benchmark program is GPL-3.0-only. The listed project-authored build/run tools, shared utilities, HashWires driver/tests, and Bulletproofs integration are BSD-2-Clause. The HashWires Java protocol port and BulletProofLib retain their upstream MIT terms. CBRP-DL and the KTX research core have no new software license grant in this release.

See [LICENSE](LICENSE), [LICENSE-STATUS.md](LICENSE-STATUS.md), and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for exact file-level scope.
