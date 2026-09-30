# Historical reference values

These CSV files transcribe the existing tables from **A Public-Coin Credential-Based Range Proof with Reusable Commitments**, by You-Lin Hou, National Taiwan Normal University. The reference document has 98 PDF pages; its SHA-256 is recorded in `provenance/sources.json`.

| CSV | Source |
|---|---|
| `java.csv` | Tables 6.4 and 6.5; PDF pages 81–82, printed pages 69–70 |
| `ktx.csv` | Table 6.8; PDF page 86, printed page 74 |
| `amortization-reported.csv` | Tables 6.6 and 6.7; PDF page 84, printed page 72 |
| `environment.csv` | Table 6.1 and accompanying environment description |

These are historical values, **not results of randomized-v3**. The CBRP-DL experiment described in §6.5.1 fixed `w=N-2`, `t=floor(N/2)+1` and reused a table within each configuration. Current executions randomize `w,t` and create new credentials every round. Consequently, the historical timing, proof sizes and amortization statements do not describe the current workload.

The KTX table records prototype observations rather than raw per-round samples. Its original NumPy version and exact thresholds were not specified in the reference. The existing decimal values and approximate amortization wording are preserved, not recomputed or silently reconciled with newer measurements.

`python scripts/report.py --reference` copies these CSV tables into a separately labeled report directory without running a benchmark. Active experimental data is written only to new `results/runs/` directories.
