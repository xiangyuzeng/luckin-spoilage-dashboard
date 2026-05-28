# Luckin USA — 物料 Spoilage Dashboard

Single-page dashboard tracking 过期销毁 (expiration write-offs) across **44 物料
SKUs in 9 product categories** at Luckin USA stores. Data is pulled from the SCM
source-of-truth (`luckyus_scm_shopstock.t_shop_spec_stock_change_record`, reason
015), joined with store master, sales orders, and unit cost, then rendered as a
self-contained HTML file.

**Live URL:** https://xiangyuzeng.github.io/luckin-spoilage-dashboard/

**Repo:** https://github.com/xiangyuzeng/luckin-spoilage-dashboard

**Data files:** https://xiangyuzeng.github.io/luckin-spoilage-dashboard/data/

## What's in the dashboard

- 19 NYC stores across 12 months (2025-06 → 2026-05)
- **44 SKUs across 9 categories**: 奶 / 咖啡豆 / 烘焙 / 糖浆 / 酱料 / 粉 / 调味 / 饮料 / 其他
- Three metric toggles: 报损金额 USD · 报损量 (单位随规格 mL/g/个) · 损耗强度
- Grouped `<optgroup>` SKU selector — SKUs without records show greyed `（暂无数据）`
- ALL view stacks store losses **by category** (9 colors); category drill-down
  switches the stack to SKU-within-category
- Per-store drill-down with monthly bars, category/SKU donut, operator breakdown
- Pareto + heatmap + USD-based status flags (异常 / 需关注 / 正常)
- DST-aware month bucketing via `zoneinfo("America/New_York")`

## Repo layout

```
pipeline/
  sku_catalog.py      # 44 SKUs + 9 categories + unit-code labels
  pull.py             # runbook: pull cache/raw/batch_*.json + spec_metadata.json from SCM
  build_v2.py         # transform: cache/ → output/*.csv + dashboard_payload.json
  build_dashboard.py  # render:    output/dashboard_payload.json → output/dashboard.html
  refresh.sh          # cron wrapper: pull → transform → render → promote → commit → push

cache/                # raw spoilage rows + spec metadata (gitignored)
  spec_metadata.json  # cost + ratios + unit per SKU
  raw/batch_*.json    # spoilage records, batched by query size

output/               # transient build outputs (gitignored)

docs/                 # ← GitHub Pages serves this folder
  index.html          # the dashboard
  data/               # CSV + payload + build_meta downloadables
```

## Quick start

```bash
# one-time: bootstrap cache/ from an SCM session — see pipeline/pull.py runbook

# every build:
bash pipeline/refresh.sh --no-push    # builds locally without pushing
bash pipeline/refresh.sh              # builds + commits + pushes to GitHub
```

GitHub Pages serves from `main` / `docs`.

## Unit handling

Different SKUs use different consumption units:

| Unit code | Label | Examples |
|---|---|---|
| QU013 | mL | milk, syrups, sodas, coconut water |
| QU005 | g | coffee beans, powders, salt, cookies (per the SCM model) |
| QU009 | 个 | bakery items, ISI cream chargers |

Cross-SKU comparisons (stacked charts, ALL view, KPIs) **always use USD** since
mL and g cannot be added. Per-SKU drill-downs use the SKU's native unit, surfaced
in tooltips via `unit_label` on each spec.

Cost-per-unit is derived as `spec_cost_amount / (cg_dly_ratio × dly_use_ratio)`
from `t_goods_spec_cost_detail` × `t_mdm_goods_spec` (the 2025-01-01 onward
weighted average).

## Daily auto-refresh

Crontab line on the DBA workstation (the one that runs `/push-report`):

```cron
30 7 * * *  /opt/luckin-spoilage-dashboard/pipeline/refresh.sh >> /var/log/spoilage_refresh.log 2>&1
```

That runs 02:30 EST (winter) / 03:30 EDT (summer) — after the prior day's
end-of-day write-offs have settled.

The pull step today is the runbook in `pipeline/pull.py` (executed from a Claude
Code session with mcp-db-gateway attached); pure-Python pymysql is a TODO
gated on AWS Secrets Manager onboarding for the SCM read credential.

## Reconciliation

Every build cross-checks the outputs:

- `loss_records.csv` Σ `loss_usd` ==
- `store_benchmark.csv` Σ `total_loss_usd` ==
- `store_month_matrix.csv` TOTAL row ==
- `dashboard_payload.json` `meta.grand_total_usd`

## Data dictionary

| File | Contents |
|---|---|
| `docs/data/loss_records.csv` | one row per spoilage event (spec, store, dept, operator, qty, USD, unit) |
| `docs/data/store_benchmark.csv` | per-store rollup with rank, share, intensity, USD, status |
| `docs/data/store_month_matrix.csv` | store × month pivot in USD |
| `docs/data/spec_summary.csv` | per-SKU totals including unit + cost_per_unit |
| `docs/data/dashboard_payload.json` | full precomputed payload (also embedded in `index.html`) |
| `docs/data/build_meta.json` | `{build_time, git_commit, rows}` for the last refresh |

## PII note

Operator names (Luckin USA employees who keyed in the write-off) appear in
`loss_records.csv`, the payload, and the dashboard's drill-down panel. Before
making the repo public, confirm whether to:

- publish as-is (employee names visible),
- anonymize via a stable hash, or
- keep the repo private (note: GitHub Pages requires Pro/Enterprise for private
  repos).

The current `docs/data/` is **not** anonymized.
