# CBRP 研究附件

[English README](README.md)

本儲存庫配合期刊稿 *A Public-Coin Credential-Based Range Proof with Reusable Commitments* 使用。主要研究實作為 CBRP-DL 與 CBRP-KTX 功能性原型；Bulletproofs、Flashproofs 與一般單次使用的 HashWires 則是彼此隔離的比較基準。

套件包含原始碼、建置與驗證工具、實驗設定，以及歷史參考 CSV。這是研究附件，不是可直接部署的正式憑證系統。

## 環境需求

| 元件 | 需求 |
|---|---|
| 作業系統 | Linux；以下命令以 Ubuntu 為例 |
| Java | JDK 17；編譯目標為 Java 17 |
| Maven | 取得 CBRP-DL、Bulletproofs 與 Flashproofs 的依賴 |
| Python | 3.11 以上；範例環境使用 Python 3.12 |
| NumPy | `requirements.txt` 固定為 `numpy==2.3.5` |
| 記憶體 | 每個 Java 程序預設使用最多 `2g` heap |

HashWires 僅使用 JDK，並採用目前 JDK 提供的 SHA-256 provider。KTX 原型使用 NumPy。

## 1. 安裝基本工具

```bash
sudo apt update
sudo apt install -y openjdk-17-jdk maven python3 python3-venv python3-pip curl ca-certificates git unzip
java -version
javac -version
mvn -version
python3 --version
```

進行 Java 17 評估時，`java`、`javac` 以及 Maven 顯示的 Java runtime 都必須使用 JDK 17。已安裝多個 JDK 時：

```bash
sudo update-alternatives --config java
sudo update-alternatives --config javac
export JAVA_HOME="$(dirname "$(dirname "$(readlink -f "$(command -v javac)")")")"
mvn -version
```

不要替換作業系統的 `/usr/bin/python3`。Ubuntu 20.04 原有的 Python 3.8 太舊，無法使用此專案固定的 NumPy 版本；請依下列方式另外建立環境。

## 2. 解壓縮並驗證來源

```bash
mkdir -p ~/research/cbrp
unzip ~/Downloads/cbrp-research-artifact.zip -d ~/research/cbrp
cd ~/research/cbrp/cbrp-research-artifact
sha256sum -c SHA256SUMS
```

壓縮檔位於其他位置時，請調整路徑。每個版本應解壓縮到新目錄，不要覆蓋舊版本。後續命令都在包含 `scripts/`、`src/` 與 `requirements.txt` 的專案根目錄執行。

`SHA256SUMS` 涵蓋 manifest 本身以外的所有發行檔案。虛擬環境、依賴套件、編譯結果與實驗輸出都不是來源壓縮檔的一部分。

## 3. 建立 Python 環境

已安裝 Python 3.11 以上時：

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip check
python -c "import sys, numpy; print(sys.version); print(numpy.__version__); print(sys.executable)"
```

只有確認 `python3` 的版本相容後，才將 `python3.12` 改成 `python3`。

目前只有較舊的 Python 時，可用 `uv` 另外安裝：

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

用舊版 Python 建立的環境必須重建；重新啟用環境不會升級其中的直譯器。NumPy 應顯示版本 `2.3.5`。

## 4. 編譯 Java 實作

```bash
python scripts/build.py
```

各方案使用彼此隔離的 classpath，並在獨立 JVM 中執行。

| 方案 | 直接依賴 |
|---|---|
| CBRP-DL | Bouncy Castle 1.61 |
| Bulletproofs | Bouncy Castle 1.57、Cyclops React 2.0.0-FINAL、Guava 24.1.1-jre |
| Flashproofs | Bouncy Castle 1.56、Guava 23.0 |
| HashWires | 無；使用 JDK SHA-256 |

依賴宣告位於 `config/dependencies/`。專案根目錄不是 Maven project；請使用 `scripts/build.py`，不要以 `mvn package` 取代。完整建置成功時會顯示四個 `BUILD PASS`，並把來源、依賴、provider 與 class 雜湊值記錄在 `build/<scheme>/build.json`。

使用離線依賴時：

```bash
python scripts/build.py --dependency-dir /path/to/dependencies
```

指定目錄必須包含 `cbrp-dl/*.jar`、`bulletproofs/*.jar` 與 `flashproofs/*.jar`。HashWires 不接受任何 JAR。Local-JAR 模式會記錄為 `local-jars`，不會被視為已獨立確認符合 Maven 宣告。來源壓縮檔不包含依賴 JAR。

Runner 會拒絕遭變更、缺少或額外出現的 class／JAR。修改來源或依賴後，必須重新建置。

## 5. 執行測試

```bash
python scripts/test.py
```

成功時以 `TEST PASS` 結束。測試內容包括：

- DedP coverage 與邊界案例；
- CBRP-DL、Bulletproofs、Flashproofs 與 HashWires 的正確／竄改測試；
- HashWires MDP、序列化與 proof-size 回歸測試；
- KTX statement、challenge、witness shape、replay 與 state 單次使用測試；
- 確認公開 KTX matrix seed 無法決定私密 witness 或 mask 的回歸測試；
- 64-bit CSV 精確保存、計時彙整、跨 repeat 統計與測資檢查。

這些是功能與回歸測試，不是密碼學安全性的證明。

```bash
python scripts/test.py --java-only
python scripts/test.py --python-only
```

## 6. 執行小規模端到端檢查

```bash
python scripts/run.py --profile smoke
python scripts/run_ktx.py --bits 16 --bases 16 --rho 3 --warmup 0 --iterations 3
```

Java smoke profile 會以 32 bits 執行四個 Java 方案，CBRP-DL 與 HashWires 使用 `b=16`，量測三組測資且不預熱。KTX 命令每份 proof 使用三次 Stern repetition。這些命令只用來檢查安裝與輸出流程，不是正式效能或安全性估計。

需要更完整的 Java 覆蓋、但暫不建立昂貴的 CBRP-DL `b=65536` 表格時：

```bash
python scripts/run.py --profile check-java
```

## 比較基準與範圍

| 比較基準 | 用途 | 範圍說明 |
|---|---|---|
| Bulletproofs | 一般範圍證明比較基準 | 對 `delta=w-t` 做範圍證明；不認證發證方原始的 `w` |
| Flashproofs | 一般範圍證明比較基準 | 以自身分解參數證明 `delta` |
| HashWires | 信任發證方、以雜湊為基礎的 CBRP 比較基準 | 最佳化的一般單次使用方案；不含 Section 5.2 外層 `T`-time wrapper |

HashWires Java port 保留 Minimum Dominating Partition、共用 multichain、Padded Linear Accumulation、每個 MDP 的 salt、deterministic placement，以及固定高度的 padded Merkle accumulator。與論文及所記錄 Rust snapshot 的對照、刻意差異與未實作功能，記錄於 [`third_party/hashwires/NOTICE`](third_party/hashwires/NOTICE)。

HashWires 在 proof generation 時會重建 commitment 相關狀態，以取得 inclusion path。因此，即使 `commit_ms` 與 `prove_ms` 都屬於本實驗量測的新 one-time workflow，兩者仍包含重複工作。請依個別欄位與 `timing_scope` 解讀，不要把跨方案的加總視為共同的線上成本。

固定 statement 的 HashWires profile 使用 `w=N-2` 與 `t=floor(N/2)+1`，且每次執行都產生新的 seed 與 commitment：

```bash
python scripts/run.py --profile hashwires-paper-fixed
```

## 7. 執行 Java 實驗配置

先執行適中的單一配置：

```bash
python scripts/run.py --scheme cbrp-dl --bits 32 --bases 256 --warmup 2 --iterations 10
```

完整 profile：

```bash
python scripts/run.py --profile random-java
```

| 方案 | 位元數 | 基底／分解 | 預熱 | 正式量測 |
|---|---|---|---:|---:|
| CBRP-DL | 32、64 | `b=16,256,65536` | 10 | 50 |
| Bulletproofs | 32、64 | 對 `delta` 的二進位證明 | 5 | 20 |
| Flashproofs | 32 | `K=3,L=11` | 5 | 20 |
| Flashproofs | 64 | `K=4,L=16` | 5 | 20 |
| HashWires | 32、64 | `b=16,256`、SHA-256 | 5 | 20 |

此 profile 會產生 14 組配置摘要與 460 次正式量測。每個 `(scheme, bits, base)` Java 配置都在獨立 JVM 執行，因此後面的 radix 不會繼承前一個 radix 的 JIT 或垃圾回收狀態。

CBRP-DL 每次執行都發行一張新的完整憑證表。HashWires 每次執行都建立新的普通 one-time commitment。Bulletproofs 與 Flashproofs 證明的是位移後的 `delta=w-t`，不是與憑證綁定的 `w` statement。

常用覆寫方式：

```bash
python scripts/run.py --profile random-java --warmup 0 --iterations 2
python scripts/run.py --scheme hashwires --bits 64 --bases 16,256 --warmup 5 --iterations 20
python scripts/run.py --scheme bulletproofs --bits 64 --warmup 5 --iterations 20
python scripts/run.py --scheme flashproofs --bits 64 --warmup 5 --iterations 20
```

`--heap 4g` 可調整 JVM heap。`--repeat 3` 會建立獨立測資序列與 JVM execution。`--timeout 600` 會限制每個 JVM 最多執行 600 秒。每個 repeat／job 的摘要位於 `summary.csv`；`summary-aggregate.csv` 會合併相同配置的多次 repeat。

## 8. 執行 KTX 原型配置

```bash
python scripts/run_ktx.py --profile random-ktx
```

此 profile 涵蓋 16／32／64-bit 範圍與 `b=16,256`，並使用 `q=4093`、`nL=128`、`m=512`、`rho=137`。六組配置各預熱兩次、正式量測 20 次。每組配置都會建立新的 KTX instance 與公開矩陣；不同 repeat 的配置順序會以可重現方式重新排列。

記錄的 seed 只控制公開測資與公開矩陣。私密 witness 與 mask 使用獨立、未記錄、由作業系統 entropy 初始化的 PRNG。這項分離可避免由公開 seed 重建私密值，但本原型仍使用 toy parameters 與 hash commitment，不是正式或完整的後量子實作。

降低次數的範例：

```bash
python scripts/run_ktx.py --profile random-ktx --warmup 1 --iterations 3
```

## 9. 理解結果檔案

每次執行都會在 `results/runs/` 建立新目錄：

```bash
ls -lt results/runs/
```

| 檔案 | 內容 |
|---|---|
| `samples.csv` | 所有正式量測列 |
| `warmup.csv` | 不納入統計的預熱列 |
| `summary.csv` | 各 repeat／job 的統計 |
| `summary-aggregate.csv` | 合併相同配置跨 repeat／job 的統計 |
| `inputs-r<repeat>-b<bits>.csv` | 完整合成測資，包含 warm-up |
| `NN-*.samples.csv` | 各程序／配置的原始觀測值 |
| `setup.csv` | 每輪計時區域以外的 setup 與預計算 |
| `metadata.json`、`STATUS` | 環境、配置、雜湊、執行策略與完成狀態 |
| Java `*.stdout.log`、`*.stderr.log` | 進度與診斷訊息 |

CSV 使用明確的計時欄位：

| 欄位 | 意義 |
|---|---|
| `commit_ms` | 依方案代表 issuance、table construction 或 commitment；Flashproofs 留空 |
| `standalone_commit_ms` | 僅 Flashproofs 使用的診斷 commitment；proof constructor 不會使用它 |
| `table_check_ms` | CBRP-DL 憑證表驗證 |
| `prove_ms`、`challenge_ms`、`verify_ms` | 各 proof 階段的量測 |
| `online_total_ms` | `prove_ms + challenge_ms + verify_ms` |
| `recorded_total_ms` | 非診斷 workflow 計時區域的加總；不含 `standalone_commit_ms` |
| `timing_scope` | 說明該列實際代表的方案 workflow |

`online_total_ms` 與 `recorded_total_ms` 是資料整理欄位，不代表各方案擁有相同介面或工作負載。跨方案比較時，應比較明確命名的階段，並考慮憑證發行、表格重用、statement 差異，以及 HashWires 的重複工作。

`proof_bytes` 會搭配 `proof_size_basis`：

- `actual-serialization`：HashWires serializer 實際輸出的 byte 數；
- `canonical-element-model`：CBRP-DL 與 Bulletproofs 的 point／scalar element 計算；
- `reflected-element-model`：Flashproofs 透過 reflection 統計 point／scalar list；
- `packed-estimate-12-bit`：KTX 的 12-bit packed 估計，不是 NumPy 記憶體表示大小。

CSV 會明文保存合成祕密值，以便檢查工作負載。不要使用真實憑證的祕密值作為 benchmark input。試算表匯入 64-bit 整數與 seed 欄位時，應指定為文字，避免自動四捨五入。

Java runner 的 `--seed` 只控制測資。KTX runner 的 seed 只控制測資與公開矩陣。協議金鑰、witness、mask、commitment 與 challenge 使用其他亂數來源。

## 10. 驗證並彙整完成的執行

將占位符換成 runner 顯示的實際目錄：

```bash
python scripts/report.py --run "results/runs/ACTUAL_RUN_DIRECTORY"
```

報告工具會檢查完成狀態、CSV 雜湊、測資、原始列、欄位描述、proof size、計時加總與兩種 summary，然後在 `results/reports/` 建立驗證後的副本，不修改原始 run。

只複製所保存的歷史數值、不執行 proof：

```bash
python scripts/report.py --reference
```

歷史 CSV 與新量測分開保存，且不包含新產生的 HashWires 結果。

## 專案結構

```text
cbrp-research-artifact/
├── README.md / README.zh-TW.md
├── config/                 # 依賴宣告與實驗設定
├── src/main/java/          # CBRP-DL、比較 drivers、共用 CSV 工具
├── experiments/ktx/        # KTX-CBRP 功能性原型
├── third_party/            # 隔離的保留／移植比較來源
├── scripts/                # 建置、測試、runner、測資與報告工具
├── tests/                  # 功能與回歸測試
├── results/reference/      # 歷史 CSV，不是新量測
├── provenance/             # 來源沿革與第三方 patch
├── LICENSES/               # 授權文字
└── SHA256SUMS              # 發行檔案完整性 manifest
```

`.venv/`、`build/`、`results/runs/`、`results/reports/`、cache、JAR 與 class 都是本機產物。它們由 Git 忽略，也不包含在來源壓縮檔。需要共同檢查實驗結果時，應另外提供完整 run 目錄。

## 常見問題

**無法安裝 NumPy 2.3.5：** 先檢查 `python --version`。Python 3.8 不受支援；請依上方說明建立獨立的 Python 3.12 環境，不要直接更改 `requirements.txt`。

**找不到 Maven 或依賴解析失敗：** 檢查 `mvn -version` 與網路。離線 local-JAR 模式會與 Maven 模式分開記錄。

**出現 `Changed/missing build file` 或 `Build output set changed`：** 重新執行 `python scripts/build.py`。Runner 會刻意拒絕過期或額外的 class／JAR。

**大基底 CBRP-DL 長時間沒有新畫面：** 每次執行都會建立並簽署 `n*b` 個表項。查看目前的 `*.stderr.log`；部分 CSV 不代表執行已完成。

**目前的 size 或 timing 與歷史表格不同：** 現行實驗會改變 `w`、`t`、branch count、憑證與 commitment。HashWires proof length 也可能隨 truncation 與 PLA padding 改變。這些是工作負載差異，不只是一般量測誤差。

**可以直接部署嗎？** 不可以。本套件未提供經稽核的 constant-time 實作、正式網路協議、持久化 issuer registry，或正式 KTX 參數與 commitment。

## 授權

本儲存庫採元件層級授權，而不是單一全專案授權。整合後的 Flashproofs benchmark program 採 GPL-3.0-only。明列的專案建置／執行工具、共用 utilities、HashWires driver／tests 與 Bulletproofs integration 採 BSD-2-Clause。HashWires Java protocol port 與 BulletProofLib 保留上游 MIT 條款。CBRP-DL 與 KTX 研究核心在本版本中未另行授予軟體授權。

各檔案的確切範圍見 [LICENSE](LICENSE)、[LICENSE-STATUS.md](LICENSE-STATUS.md) 與 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
