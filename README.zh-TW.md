# CBRP Research Artifact

[English](README.md)

## 環境需求

| 元件 | 需求／用途 |
|---|---|
| Shell | Linux；以下使用 Ubuntu 安裝命令 |
| Java | 文件採 JDK 17 作為評估 runtime；編譯目標為 Java 17 |
| Maven | 分別取得三個 Java 方案的依賴 |
| Python | 3.11 以上；安裝範例使用 Python 3.12 |
| NumPy | `requirements.txt` 固定為 `numpy==2.3.5`，用於 KTX 及其測試 |
| 記憶體 | 每個 Java 程序的 heap 上限預設為 `2g`；不代表整台機器只需 2 GiB RAM |

## 步驟 1：安裝基本工具

```bash
sudo apt update
sudo apt install -y openjdk-17-jdk maven python3 python3-venv python3-pip curl ca-certificates git unzip
java -version
javac -version
mvn -version
python3 --version
```

進行 Java 17 評估時，`java`、`javac` 及 Maven 顯示的 Java 版本都應使用 JDK 17。已安裝多個 JDK 時，可分別選擇並檢查：

```bash
sudo update-alternatives --config java
sudo update-alternatives --config javac
export JAVA_HOME="$(dirname "$(dirname "$(readlink -f "$(command -v javac)")")")"
mvn -version
```

不要替換作業系統的 `/usr/bin/python3`。Ubuntu 20.04 原有的 Python 3.8 不符合此 NumPy 固定版本的需求；步驟 3 提供另外安裝 Python 的方式。

## 步驟 2：取得原始碼

使用下載的來源壓縮檔：

```bash
mkdir -p ~/research/cbrp-licensed
unzip ~/Downloads/cbrp-research-artifact-licensed.zip -d ~/research/cbrp-licensed
cd ~/research/cbrp-licensed/cbrp-research-artifact
sha256sum -c SHA256SUMS
```

壓縮檔位於其他位置時，調整輸入路徑。請使用**新目錄**，不要覆蓋較舊版本。透過 Git 取得程式時，使用儲存庫提供的 Clone URL，並進入專案根目錄即可。後續命令均在包含 `scripts/`、`src/` 及 `requirements.txt` 的目錄執行。

## 步驟 3：建立 Python 環境

**已安裝 Python 3.11 以上時**，使用該直譯器建立環境。例如使用 Python 3.12：

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

只有確認 `python3` 的版本相容後，才將上述 `python3.12` 改成 `python3`。

**目前只有較舊的 Python 時**，可使用 uv 另外安裝。下列命令先下載 uv 安裝程式到暫存檔，再以一般使用者權限執行；不要在安裝命令前加 `sudo`：

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

以上兩條路線擇一執行。以舊 Python 建立的 `.venv` 不會自動升級，須另外建立相容的新環境；需要備份時應另行保留舊環境，不要覆寫原始碼或實驗結果。

接著安裝與檢查依賴：

```bash
python --version
python -m pip install -r requirements.txt
python -m pip check
python -c "import sys, numpy; print('Python:', sys.version); print('NumPy:', numpy.__version__); print('Executable:', sys.executable)"
```

NumPy 應顯示 `2.3.5`，執行檔應位於新建立的虛擬環境內。重新開啟終端機後，回到專案目錄，再執行 `source .venv/bin/activate`。官方文件：[NumPy 版本需求](https://pypi.org/project/numpy/2.3.5/)、[uv 安裝](https://docs.astral.sh/uv/getting-started/installation/)、[Python 安裝指南](https://docs.astral.sh/uv/guides/install-python/)。

## 步驟 4：編譯 Java 實作

```bash
python scripts/build.py
```

各方案分開建立 classpath，並使用獨立 JVM 執行。直接依賴宣告位於 `config/dependencies/`：

| 方案 | 直接依賴 |
|---|---|
| CBRP-DL | Bouncy Castle 1.61 |
| Bulletproofs | Bouncy Castle 1.57、Cyclops React 2.0.0-FINAL、Guava 24.1.1-jre |
| Flashproofs | Bouncy Castle 1.56、Guava 23.0 |

Maven 負責取得依賴，腳本負責編譯原始碼。**不要在根目錄以 `mvn package` 取代此命令。** 全部成功時會出現三個 `BUILD PASS`。實際載入的 provider、Java 版本、依賴與來源雜湊值記錄在 `build/<scheme>/build.json`。原始碼或依賴變更後，應重新編譯。

選用參數 `--dependency-dir /path/to/dependencies` 可讀取預先備妥的 `cbrp-dl/*.jar`、`bulletproofs/*.jar`、`flashproofs/*.jar` 子目錄。紀錄會標示為 `local-jars`，不會當成已確認符合宣告版本的依賴。兩種建置介面都不需要私人封存檔；來源包不附帶依賴 JAR。

## 步驟 5：執行測試

```bash
python scripts/test.py
```

成功時以 `TEST PASS` 結束。測試涵蓋 DedP coverage 與邊界案例、有效與無效證明、context／簽章檢查、response state 的單次使用、KTX challenge／shape 檢查、不重複測資、64-bit 整數的 CSV 精確保存，以及結果計算。

這些是功能測試，不是密碼學安全定理的證明。亦可分開執行：

```bash
python scripts/test.py --java-only
python scripts/test.py --python-only
```

## 步驟 6：執行小規模流程檢查

```bash
python scripts/run.py --profile smoke
python scripts/run_ktx.py --bits 16 --bases 16 --rho 3 --warmup 0 --iterations 3
```

Java smoke 設定會執行三個方案的 32-bit 實驗，CBRP-DL 使用 `b=16`；各方案**正式量測三組不同的 `w,t`**，不預熱。KTX 命令每份 proof 僅執行三次 Stern repetition。這些命令用來檢查安裝與輸出流程，不作為正式效能或安全性估計。

需要涵蓋更多 Java 配置、但暫不建立昂貴的 `b=65536` 表格時：

```bash
python scripts/run.py --profile check-java
```

此設定涵蓋 32／64 bits、CBRP 的 `b=16,256`，各配置預熱一次、正式量測三次。成功的 runner 會顯示新建立的結果目錄，並以 `RUN PASS` 或 `KTX POC PASS` 結束。

## 步驟 7：執行 Java 實驗

每輪讀取不同的合成測資 `0 <= t <= w < 2^bits`；同一份序列內，`w` 與 `t` 各自不重複。相同範圍／重複編號的配置共用測資。CBRP 使用新憑證；比較基準對 `delta = w-t` 做範圍證明，不包含發證方認證，也未連結至外部既有的 `w` 承諾。

先執行適中的單一配置：

```bash
python scripts/run.py --scheme cbrp-dl --bits 32 --bases 256 --warmup 2 --iterations 10
```

完整參數配置：

```bash
python scripts/run.py --profile random-java
```

| 方案 | 位元數 | 基底／內部分解 | 預熱次數 | 正式量測次數 |
|---|---|---|---:|---:|
| CBRP-DL | 32、64 | `b=16,256,65536` | 10 | 50 |
| Bulletproofs | 32、64 | 對 `delta` 的二進位範圍證明 | 5 | 20 |
| Flashproofs | 32 | `K=3,L=11` | 5 | 20 |
| Flashproofs | 64 | `K=4,L=16` | 5 | 20 |

此配置產生 10 列配置摘要、380 次正式量測。**CBRP 在每次預熱與正式量測中都建立完整新表**，大基底會比「建表一次後重用」耗時許多。驗證環境尚未完成包含大基底的完整配置，沒有固定完成時間的保證；應先跑小規模流程。

可明確覆寫次數，實際參數會記錄在輸出中：

```bash
python scripts/run.py --profile random-java --warmup 0 --iterations 2
python scripts/run.py --scheme bulletproofs --bits 64 --warmup 5 --iterations 20
python scripts/run.py --scheme flashproofs --bits 64 --warmup 5 --iterations 20
```

記憶體足夠時，可用 `--heap 4g` 調整 JVM heap。`--repeat 3` 會產生獨立 JVM 執行與測資序列；`--timeout 600` 則限制每個 JVM 最多執行 600 秒。逾時或中斷不算成功完成的實驗。

## 步驟 8：執行 KTX 原型配置

```bash
python scripts/run_ktx.py --profile random-ktx
```

此配置包含 16／32／64-bit 範圍與 `b=16,256`，採用 `q=4093`、`nL=128`、`m=512`、`rho=137`。六組配置各預熱兩次、正式量測 20 次。公開矩陣每個配置建立一次；每輪皆依新的 `w` 建立新表與對應 witnesses。

降低執行次數的範例：

```bash
python scripts/run_ktx.py --profile random-ktx --warmup 1 --iterations 3
```

原型使用 hash commitment placeholders，沒有 issuer labels／signatures。Toy 參數及 seed 衍生排列不代表完整實作形式化 KTX 假設；repetition 次數**不構成本實作安全等級的保證**。

## 步驟 9：查看 CSV 結果

每次執行都會在 `results/runs/` 建立獨立目錄：

```bash
ls -lt results/runs/
```

| 檔案 | 內容 |
|---|---|
| `samples.csv` | 每列是一輪正式量測，包含實際 `w,t`、尺寸、時間及驗證結果 |
| `warmup.csv` | 預熱量測，排除於摘要統計之外 |
| `summary.csv` | 各配置的平均值、樣本標準差、最小值及最大值 |
| `inputs-r<repeat>-b<bits>.csv` | 實際測資，包含預熱資料 |
| `NN-*.samples.csv` | 各工作原始觀測值，包含預熱 |
| `setup.csv` | 逐輪計時區域之外的 setup／預計算時間 |
| `metadata.json`、`STATUS` | 環境、配置、seed、雜湊值及完成狀態 |
| Java `*.stdout.log`、`*.stderr.log` | 執行進度與診斷訊息 |

**數值量測表全部使用 CSV。** JSON 僅記錄 metadata／設定，不再以 JSON 單獨保存 KTX 實驗結果，也不以 Markdown 作為唯一的數據輸出。

CSV 會明文記錄**合成測試祕密值**以供檢查；不要使用真實憑證的祕密值作為測資。64-bit 整數在 CSV 內以精確十進位字串保存；使用試算表軟體匯入時，應將 `w`、`t`、`delta`、`value_proved` 與 seed 欄位指定為文字，避免被自動四捨五入。

加入 `--seed 12345` 並使用相同配置，可以重新產生相同測資。這只控制**測試資料**，不固定全部協議隨機性、proof transcript 或執行時間。不指定 `--seed` 時，每次執行都會產生新的 input seed 並記錄在 metadata。

## 步驟 10：驗證及彙整完成的執行

以下占位符須替換成 runner 顯示的實際結果目錄：

```bash
python scripts/report.py --run "results/runs/ACTUAL_RUN_DIRECTORY"
```

報告工具會檢查完成狀態、CSV 雜湊值、測資與樣本的對應、尺寸與摘要統計，再於 `results/reports/` 建立 CSV 副本及重新計算的摘要，不修改原始 run。失敗、不完整、遭修改或不支援的舊格式會被拒絕。工具不會把每輪新憑證的量測換算成重用同一張表的 break-even 宣稱。

只複製歷史數值、不執行證明：

```bash
python scripts/report.py --reference
```

歷史 CSV 與新量測分開標示。保留完整 run 目錄，才能一併保存測資、觀測值、環境與驗證資訊。

## 專案結構

```text
cbrp-research-artifact/
├── README.md / README.zh-TW.md
├── config/                 # 依賴宣告及現行實驗配置
├── src/main/java/          # CBRP-DL、比較基準、共用 CSV 輸入輸出
├── experiments/ktx/        # KTX-CBRP 功能性原型
├── third_party/            # 必要比較基準來源及原始 notices
├── scripts/                # 建置、測試、測資、runner、CSV 報告
├── tests/                  # 功能、邊界及結果計算測試
├── results/reference/      # 歷史 CSV 數值，不是本次新量測
├── provenance/             # 來源紀錄及第三方原始碼差異
├── LICENSES/               # 第三方授權文字
└── SHA256SUMS              # 本來源快照的完整性校驗
```

`build/`、`.venv/`、`results/runs/` 及 `results/reports/` 是本地產物，不包含在來源壓縮檔中，也由 Git 忽略。需要共同檢查實驗結果時，應另外提供完整結果目錄。

## 常見問題

**NumPy 可安裝版本只到 1.24.4／找不到 2.3.5：** 先檢查 `python --version`。Python 3.8 不符合此固定版本的要求；使用步驟 3 另外安裝 Python，不要直接更改 `requirements.txt`。

**找不到 Maven／依賴下載失敗：** 檢查 `mvn -version` 及網路，保留錯誤訊息。本地 JAR 模式會與 Maven 依賴模式明確區分。

**出現 `Changed/missing build file`：** 使用原定的依賴路線重新執行 `python scripts/build.py`。修改來源後不能沿用舊 `.class`。

**大基底的 CBRP 長時間沒有新畫面：** 每輪都會重新建立 `n*b` 個表項與簽章。查看最新的 `*.stderr.log`；不能把部分 CSV 當成已完成的結果。

**時間或 proof size 與歷史表格不同：** 現行版本會變更 `w,t`、`ell` 與憑證。這是實驗工作負載的改變，不只是一般量測誤差。

**能否直接部署：** 本專案未提供正式網路協議、經稽核的 constant-time 實作、持久化 issuer registry 或正式 KTX 參數／commitment。

## 授權

本專案採分區授權，不使用單一全專案授權。整合後的 Flashproofs 比較程式
採 GPLv3；專案新增的 Bulletproofs 測試程式及明列的共用工具採 BSD-2-Clause；
BulletProofLib 保留原有 MIT 授權。CBRP-DL 與 KTX 研究核心在此版本中
未另行授予軟體授權。
完整範圍見 [LICENSE](LICENSE)、[各檔案的授權說明](LICENSE-STATUS.md)
及[第三方聲明](THIRD_PARTY_NOTICES.md)。
