# Luckin USA — Milk Spoilage Dashboard

Single-page dashboard tracking 过期销毁 (expiration write-offs) of Cream-O-Land
milk across Luckin USA stores. Data is pulled from the SCM source-of-truth
(`luckyus_scm_shopstock.t_shop_spec_stock_change_record`, reason 015), joined
with store master, sales orders, and unit cost, then rendered as a self-contained
HTML file.

**Live URL:** https://xiangyuzeng.github.io/luckin-spoilage-dashboard/

**Repo:** https://github.com/xiangyuzeng/luckin-spoilage-dashboard

**Data files:** https://xiangyuzeng.github.io/luckin-spoilage-dashboard/data/

## What's in the dashboard

- 19 NYC stores across 11 months (2025-07 → 2026-05)
- 4 milk variants (Fat-free / Whole / 2% Reduced / DSD packaging)
- Three metric toggles: 报损量 mL · 报损金额 USD · 损耗强度 mL/千单
- Per-store drill-down with monthly bars, spec mix donut, operator breakdown
- Pareto + heatmap + multi-spec stacked breakdown
- DST-aware month bucketing via `zoneinfo("America/New_York")`

## Repo layout

```
pipeline/
  pull.py             # STUB — pulls raw rows from SCM DB to cache/ (TODO)
  build_v2.py         # transform: cache/ → output/*.csv + dashboard_payload.json
  build_dashboard.py  # render:    output/dashboard_payload.json → output/dashboard.html
  refresh.sh          # cron wrapper: pull → transform → render → promote → commit → push

cache/                # raw spoilage rows per spec (gitignored; bootstrap from SCM)

output/               # transient build outputs (gitignored)

docs/                 # ← GitHub Pages serves this folder
  index.html          # the dashboard
  data/               # CSV + payload + build_meta downloadables
```

## Quick start

```bash
# one-time: bootstrap cache/ from an SCM session (currently a Claude Code task)

# every build:
bash pipeline/refresh.sh --no-push    # builds locally without pushing
bash pipeline/refresh.sh              # builds + commits + pushes to GitHub
```

After the first push, enable Pages: **Settings → Pages → Source = `main` branch / `docs` folder**.

## Daily auto-refresh

Crontab line on the DBA workstation (the one that runs `/push-report`):

```cron
30 7 * * *  /opt/luckin-spoilage-dashboard/pipeline/refresh.sh >> /var/log/spoilage_refresh.log 2>&1
```

That runs 02:30 EST (winter) / 03:30 EDT (summer) — after the prior day's
end-of-day write-offs have settled.

## TODO before the cron is genuinely "auto"

`pipeline/refresh.sh` step 1 currently relies on `cache/spec_*.csv|.json` being
fresh. To make the daily refresh actually pick up new data, implement
`pipeline/pull.py` — see its docstring for three suggested paths (direct
pymysql, on-prem MCP gateway HTTP, or a scheduled Claude Code agent).

Until then the cron will re-render the dashboard daily with the same data, and
the footer `build_meta` timestamp will be the only thing that changes.

## Reconciliation

Every build cross-checks four output files and the embedded JSON payload:

- `loss_records.csv` Σ `loss_qty_ml` ==
- `store_benchmark.csv` Σ `total_loss_ml` ==
- `store_month_matrix.csv` TOTAL row ==
- `dashboard_payload.json` `meta.grand_total_ml` ==
- 8th & Broadway Jan-Apr 2026 == original xlsx export (per-month equality)

Last verified totals: **9,153,978.40 mL · $8,896.23** across 19 stores, 11 months,
5,988 store records (+ 84 non-store back-office records segregated).

## Data dictionary

`docs/data/loss_records.csv` — one row per spoilage event (no PII customer data;
contains employee operator names — see note below).

`docs/data/store_benchmark.csv` — per-store rollup with rank, share, intensity,
USD, status flag (异常/需关注/正常).

`docs/data/store_month_matrix.csv` — store × month pivot in mL and USD.

`docs/data/spec_summary.csv` — per-variant totals.

`docs/data/dashboard_payload.json` — full precomputed payload (also embedded in
`index.html` for offline viewing).

`docs/data/build_meta.json` — `{build_time, git_commit, rows}` for the last
refresh; surfaced in the dashboard footer.

## PII note

Operator names (Luckin USA employees who keyed in the write-off) appear in
`loss_records.csv`, the payload, and the dashboard's drill-down panel. Before
making the repo public, confirm whether to:

- publish as-is (employee names visible),
- anonymize via a stable hash, or
- keep the repo private (note: GitHub Pages requires Pro/Enterprise for private
  repos).

The current `docs/data/` is **not** anonymized.
