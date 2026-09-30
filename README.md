# CBRP Research Artifact

[Traditional Chinese](README.zh-TW.md)

## Requirements

| Component | Requirement / use |
|---|---|
| Shell | Linux; Ubuntu commands are shown below |
| Java | JDK 17 is the documented evaluation runtime; compilation targets Java 17 |
| Maven | Resolves separate dependency sets for the three Java implementations |
| Python | 3.11 or newer; Python 3.12 is the installation example |
| NumPy | `numpy==2.3.5`, pinned in `requirements.txt`; used by KTX and its tests |
| Memory | Each Java process defaults to a `2g` maximum heap; this is not a total machine RAM requirement |

## Step 1 — Install the basic tools

```bash
sudo apt update
sudo apt install -y openjdk-17-jdk maven python3 python3-venv python3-pip curl ca-certificates git unzip
java -version
javac -version
mvn -version
python3 --version
```

For a Java 17 evaluation, `java`, `javac` and the Java version shown by Maven must all use JDK 17. When several JDKs are installed:

```bash
sudo update-alternatives --config java
sudo update-alternatives --config javac
export JAVA_HOME="$(dirname "$(dirname "$(readlink -f "$(command -v javac)")")")"
mvn -version
```

Do not replace the operating system's `/usr/bin/python3`. Ubuntu 20.04's existing Python 3.8 is not sufficient for the pinned NumPy; Step 3 includes a separate-Python installation route.

## Step 2 — Extract the source

For the downloadable archive:

```bash
mkdir -p ~/research/cbrp-licensed
unzip ~/Downloads/cbrp-research-artifact-licensed.zip -d ~/research/cbrp-licensed
cd ~/research/cbrp-licensed/cbrp-research-artifact
sha256sum -c SHA256SUMS
```

Adjust the archive path if it is stored elsewhere. Use a **new directory**, not an overlay on an older release. For a Git checkout, use the repository's clone URL and enter its root instead. All subsequent commands run from the directory containing `scripts/`, `src/` and `requirements.txt`.

## Step 3 — Create the Python environment

**When Python 3.11 or newer is already installed:** use that interpreter, for example:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

Use `python3` instead of `python3.12` only after checking that it is a compatible version.

**When the available interpreter is older**, install a separate Python with uv. The following downloads the uv installer into a temporary file and runs it without `sudo`:

```bash
UV_INSTALLER="$(mktemp)"
curl -LsSf https://astral.sh/uv/install.sh -o "$UV_INSTALLER" &&
UV_INSTALL_DIR="$HOME/.local/bin" UV_NO_MODIFY_PATH=1 sh "$UV_INSTALLER"
export PATH="$HOME/.local/bin:$PATH"
uv --version
uv python install 3.12
uv venv --python 3.12 --seed .venv
source .venv/bin/activate
```

Use only one of the two routes above. An existing `.venv` created with an older Python must be replaced with a newly created environment, not reused as though it had upgraded itself. Preserve it separately if needed; do not overwrite project source or result directories.

Install and check the dependencies:

```bash
python --version
python -m pip install -r requirements.txt
python -m pip check
python -c "import sys, numpy; print('Python:', sys.version); print('NumPy:', numpy.__version__); print('Executable:', sys.executable)"
```

NumPy must report `2.3.5`, and the executable must be inside this environment. On a later shell session, return to the project and run `source .venv/bin/activate` again. See the official [NumPy requirement](https://pypi.org/project/numpy/2.3.5/), [uv installation](https://docs.astral.sh/uv/getting-started/installation/) and [Python installation guide](https://docs.astral.sh/uv/guides/install-python/).

## Step 4 — Build the Java implementations

```bash
python scripts/build.py
```

Each scheme has its own classpath and JVM. Direct dependencies are declared in `config/dependencies/`:

| Scheme | Direct dependencies |
|---|---|
| CBRP-DL | Bouncy Castle 1.61 |
| Bulletproofs | Bouncy Castle 1.57, Cyclops React 2.0.0-FINAL, Guava 24.1.1-jre |
| Flashproofs | Bouncy Castle 1.56, Guava 23.0 |

Maven downloads dependencies; the script compiles the source. **`mvn package` in the repository root is not the build entry point.** Successful compilation prints three `BUILD PASS` messages. Actual providers, Java versions and dependency/source hashes are recorded in `build/<scheme>/build.json`. Rebuild after editing source or changing dependencies.

An optional `--dependency-dir /path/to/dependencies` accepts locally prepared `cbrp-dl/*.jar`, `bulletproofs/*.jar` and `flashproofs/*.jar` subdirectories. This is recorded as `local-jars`, not as a verified match to the declared dependencies. No private archive is required by either build interface. Dependency JARs are not included in this source distribution.

## Step 5 — Run the tests

```bash
python scripts/test.py
```

Success ends with `TEST PASS`. Tests include DedP coverage and boundary cases, valid and invalid proofs, context/signature checks, single-use response state, KTX challenge/shape checks, distinct input values, exact 64-bit CSV values and result accounting. They are functional checks, not proofs of cryptographic security.

For one part only:

```bash
python scripts/test.py --java-only
python scripts/test.py --python-only
```

## Step 6 — Run small end-to-end checks

```bash
python scripts/run.py --profile smoke
python scripts/run_ktx.py --bits 16 --bases 16 --rho 3 --warmup 0 --iterations 3
```

The Java smoke profile executes all three schemes at 32 bits, with `b=16` for CBRP-DL, **three measured pairs** and no warm-up. The KTX command uses only three Stern repetitions per proof. These are installation checks, not performance or security estimates.

For broader Java functional coverage without the expensive `b=65536` table:

```bash
python scripts/run.py --profile check-java
```

This covers 32/64 bits and CBRP bases 16/256, with one warm-up and three measured executions per configuration. Every successful command prints its new result directory and ends with `RUN PASS` or `KTX POC PASS`.

## Step 7 — Run Java experiments

Each round reads a distinct synthetic pair `0 <= t <= w < 2^bits`; `w` and `t` are each unique within a fixture schedule. Configurations of the same range/repetition share fixtures. CBRP uses fresh credentials; the baselines prove the range of `delta = w-t`, without issuer certification or a link to an external commitment to `w`.

A moderate individual configuration:

```bash
python scripts/run.py --scheme cbrp-dl --bits 32 --bases 256 --warmup 2 --iterations 10
```

The full parameter grid is:

```bash
python scripts/run.py --profile random-java
```

| Scheme | Bits | Base / decomposition | Warm-ups | Measured executions |
|---|---|---|---:|---:|
| CBRP-DL | 32, 64 | `b=16,256,65536` | 10 | 50 |
| Bulletproofs | 32, 64 | Binary range proof of `delta` | 5 | 20 |
| Flashproofs | 32 | `K=3,L=11` | 5 | 20 |
| Flashproofs | 64 | `K=4,L=16` | 5 | 20 |

This produces 10 configuration summaries and 380 measured executions. **CBRP generates a full table in every warm-up and measured execution**, so large-base runs are much more expensive than building one table and reusing it. The full high-base grid has not been completed in the validation environment; no fixed runtime guarantee is provided. Start with the small checks.

Counts may be overridden explicitly, and the actual configuration is recorded:

```bash
python scripts/run.py --profile random-java --warmup 0 --iterations 2
python scripts/run.py --scheme bulletproofs --bits 64 --warmup 5 --iterations 20
python scripts/run.py --scheme flashproofs --bits 64 --warmup 5 --iterations 20
```

`--heap 4g` changes the per-JVM heap when memory permits. `--repeat 3` creates independent JVM runs and fixture schedules. `--timeout 600` limits each JVM to 600 seconds; timeout/interruption does not count as a successful result.

## Step 8 — Run the KTX prototype grid

```bash
python scripts/run_ktx.py --profile random-ktx
```

The grid contains 16/32/64-bit ranges, bases 16/256, `q=4093`, `nL=128`, `m=512` and `rho=137`. Each of the six configurations has two warm-ups and 20 measured executions. Public matrix setup is once per configuration; every round creates a new table and corresponding witnesses for its `w`.

A reduced-count grid:

```bash
python scripts/run_ktx.py --profile random-ktx --warmup 1 --iterations 3
```

The prototype uses hash commitments as placeholders and omits issuer labels/signatures. Its toy parameters and seed-derived permutations do not instantiate all formal KTX assumptions. The repetition count is **not a security-level guarantee for this implementation**.

## Step 9 — Locate the CSV results

Every execution creates a separate directory under `results/runs/`:

```bash
ls -lt results/runs/
```

| File | Content |
|---|---|
| `samples.csv` | One row per measured execution: actual `w,t`, sizes, timings and verification result |
| `warmup.csv` | Warm-up executions, excluded from summary statistics |
| `summary.csv` | Per-configuration means, sample standard deviations, minima and maxima |
| `inputs-r<repeat>-b<bits>.csv` | Recorded input fixtures, including warm-ups |
| `NN-*.samples.csv` | Per-job raw observations, including warm-ups |
| `setup.csv` | Setup/precomputation timings outside the per-round measurement regions |
| `metadata.json`, `STATUS` | Environment, configuration, seeds, hashes and completion status |
| Java `*.stdout.log`, `*.stderr.log` | Progress and diagnostic output |

**All numerical measurement tables are CSV.** JSON is only metadata/configuration; there is no separate JSON-only KTX result or Markdown-only result table.

The CSV contains **synthetic test secrets in plaintext** for inspection. Never use live credential secrets as benchmark input. For 64-bit values, import `w`, `t`, `delta`, `value_proved` and seeds as text in spreadsheet software to avoid rounding; the CSV itself stores exact decimal integers.

Use `--seed 12345` with the same configuration to regenerate the same test fixtures. This controls **test data only**, not all protocol randomness, transcripts or timing. Without `--seed`, a new input seed is generated and recorded for each invocation.

## Step 10 — Validate and summarize a completed run

Replace the placeholder with the result directory printed by the runner:

```bash
python scripts/report.py --run "results/runs/ACTUAL_RUN_DIRECTORY"
```

The report command checks completion, CSV hashes, fixture-to-sample correspondence, sizes and summary statistics. It writes CSV copies and recomputed summaries under `results/reports/`, leaving the original run unchanged. Failed, incomplete, modified or unsupported old-format runs are rejected. No fresh-credential measurements are turned into a same-table break-even claim.

To copy historical values without executing proofs:

```bash
python scripts/report.py --reference
```

Historical CSV files are labeled separately. Preserve a complete run directory to retain the inputs, observations, environment and validation information together.

## Repository layout

```text
cbrp-research-artifact/
├── README.md / README.zh-TW.md
├── config/                 # Dependency declarations and current experiment profiles
├── src/main/java/          # CBRP-DL, baseline drivers, shared CSV input/output
├── experiments/ktx/        # KTX-CBRP functional prototype
├── third_party/            # Required baseline source and original notices
├── scripts/                # Build, tests, fixtures, runners and CSV reports
├── tests/                  # Functional, boundary and data-accounting tests
├── results/reference/      # Historical CSV values, not current measurements
├── provenance/             # Source lineage and third-party source differences
├── LICENSES/               # Third-party license texts
└── SHA256SUMS              # Integrity of this source snapshot
```

Generated `build/`, `.venv/`, `results/runs/` and `results/reports/` are excluded from the source archive and ignored by Git. Result directories must be shared separately when they are needed for reproduction.

## Troubleshooting

**NumPy installation stops at version 1.24.4 / no matching 2.3.5:** inspect `python --version`. Python 3.8 does not meet this pin's requirement. Use the separate-Python route in Step 3, not a silent change to `requirements.txt`.

**Missing Maven / dependency download fails:** check `mvn -version` and connectivity. Preserve the error. Locally supplied JARs are explicitly distinguished from the Maven dependency set.

**`Changed/missing build file`:** re-run `python scripts/build.py` using the intended dependency route. Old `.class` files cannot be used after editing sources.

**Large-base CBRP appears quiet:** each round regenerates `n*b` entries and signatures. Inspect the latest `*.stderr.log`; do not treat a partial CSV as a completed run.

**Timing or proof size differs from historical tables:** this version varies `w,t`, `ell` and credentials. The workload difference is intentional and must not be mistaken for timing noise.

**Formal deployment:** no production network protocol, audited constant-time implementation, persistent issuer registry or production KTX parameter/commitment instantiation is provided.

## Licenses

This repository uses component-specific licenses, not a single repository-wide
license. The assembled Flashproofs benchmark is GPLv3; project-specific
Bulletproofs integration and listed shared tools are BSD-2-Clause;
BulletProofLib keeps its original MIT license. CBRP-DL and KTX research cores
have no additional license grant in this distribution.
See [LICENSE](LICENSE), [the exact file scopes](LICENSE-STATUS.md), and
[third-party notices](THIRD_PARTY_NOTICES.md).
