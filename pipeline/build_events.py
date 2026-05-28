"""build_events.py — derive a compact granular event table for the dashboard.

Inputs (preferred in order):
  1. output/loss_records.csv + output/dashboard_payload.json (fresh from build_v2.py)
  2. docs/data/loss_records.csv + docs/data/dashboard_payload.json (committed fallback)

Override via env vars INDIR / OUTDIR (defaults: matching pair from the search above;
OUTDIR defaults to INDIR).

Output: <OUTDIR>/events.json
  {
    "stores_index": [{"dept_id":..., "shop_no":..., "store_name":..., "area":...}, ...],
    "rows": [["YYYY-MM-DD", store_idx, spec_idx, loss_usd, loss_qty], ...]
  }

Rules
- Aggregated per (date, store_idx, spec_idx) — multiple intra-day events for the same
  store/spec are summed (the dashboard never surfaces sub-day timestamps).
- date is the wall-clock America/New_York date (loss_records.csv `ny_time`[:10]).
- store_idx → stores_index; spec_idx → payload.meta.specs[idx].
- Category is NOT duplicated per row — read via meta.specs[spec_idx].cat.
- Only is_store == True rows (the 2 non-store back-office depts stay on the monthly panel).
- loss_usd rounded to 4 dp; loss_qty rounded to 3 dp.

Reconciliation (assertions; fail loudly):
  - Σ events.loss_usd == payload.meta.grand_total_usd                      ($0.01)
  - Per-month event sum == payload.meta.system_monthly_usd[month]          ($0.01)
  - Per-store per-month event sum == store.monthly_usd[month]              ($0.01)
"""
import csv, json, os, sys
from collections import defaultdict

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

def _resolve_indir():
    if os.environ.get("INDIR"):
        return os.environ["INDIR"]
    for candidate in (os.path.join(REPO_ROOT, "output"),
                      os.path.join(REPO_ROOT, "docs", "data")):
        if (os.path.exists(os.path.join(candidate, "loss_records.csv"))
            and os.path.exists(os.path.join(candidate, "dashboard_payload.json"))):
            return candidate
    print("ERROR: cannot locate loss_records.csv + dashboard_payload.json in output/ or docs/data/",
          file=sys.stderr)
    sys.exit(1)

INDIR = _resolve_indir()
OUTDIR = os.environ.get("OUTDIR", INDIR)
os.makedirs(OUTDIR, exist_ok=True)

LOSS_CSV = os.path.join(INDIR, "loss_records.csv")
PAYLOAD  = os.path.join(INDIR, "dashboard_payload.json")
OUT      = os.path.join(OUTDIR, "events.json")

print(f"reading {LOSS_CSV}")
print(f"reading {PAYLOAD}")

payload = json.load(open(PAYLOAD, encoding="utf-8"))
specs = payload["meta"]["specs"]
spec_idx_by_mid = {sp["mid"]: i for i, sp in enumerate(specs)}
months = payload["meta"]["months"]
month_idx = {m: i for i, m in enumerate(months)}

# stores_index follows payload.stores_all order for cheap correspondence.
stores_all = payload["stores_all"]
stores_index = [{
    "dept_id":    s["dept_id"],
    "shop_no":    s["shop_no"],
    "store_name": s["store_name"],
    "area":       s["area"],
} for s in stores_all]
store_idx_by_key = {(s["dept_id"], s["shop_no"]): i for i, s in enumerate(stores_index)}

# Aggregate to (date, store_idx, spec_idx).
agg = defaultdict(lambda: [0.0, 0.0])
unmapped_store = 0
unmapped_spec = 0
skipped_nonstore = 0
with open(LOSS_CSV, encoding="utf-8") as f:
    for r in csv.DictReader(f):
        if r["is_store"].lower() != "true":
            skipped_nonstore += 1
            continue
        try:
            sidx = store_idx_by_key[(int(r["dept_id"]), r["shop_no"])]
        except KeyError:
            unmapped_store += 1
            continue
        spidx = spec_idx_by_mid.get(r["spec_mid"])
        if spidx is None:
            unmapped_spec += 1
            continue
        date = r["ny_time"][:10]
        usd = float(r["loss_usd"])
        qty = float(r["loss_qty"])
        bucket = agg[(date, sidx, spidx)]
        bucket[0] += usd
        bucket[1] += qty

# --- pre-round reconciliation (the aggregation itself must be exact) ---
ev_total_usd_full = sum(usd for usd, qty in agg.values())
payload_total_usd = payload["meta"]["grand_total_usd"]
assert abs(ev_total_usd_full - payload_total_usd) < 0.01, (
    f"PRE-ROUND event total ${ev_total_usd_full:,.4f} != payload total ${payload_total_usd:,.4f} "
    f"(Δ ${ev_total_usd_full - payload_total_usd:+,.4f})"
)

sys_monthly = payload["meta"]["system_monthly_usd"]
ev_monthly_full = [0.0] * len(months)
for (date, sidx, spidx), (usd, qty) in agg.items():
    mi = month_idx.get(date[:7])
    if mi is not None:
        ev_monthly_full[mi] += usd
for i, m in enumerate(months):
    assert abs(ev_monthly_full[i] - sys_monthly[i]) < 0.01, (
        f"PRE-ROUND month {m}: events ${ev_monthly_full[i]:,.4f} != payload ${sys_monthly[i]:,.4f} "
        f"(Δ ${ev_monthly_full[i] - sys_monthly[i]:+,.4f})"
    )

# All-stores × all-months reconciliation against payload (pre-round).
per_store_month = {}  # (sidx, mi) → usd
for (date, sidx, spidx), (usd, qty) in agg.items():
    mi = month_idx.get(date[:7])
    if mi is None: continue
    per_store_month[(sidx, mi)] = per_store_month.get((sidx, mi), 0.0) + usd
per_store_warn = 0
for sidx, s in enumerate(stores_all):
    for i, m in enumerate(months):
        ev = per_store_month.get((sidx, i), 0.0)
        if abs(ev - s["monthly_usd"][i]) > 0.01:
            per_store_warn += 1
            if per_store_warn <= 5:
                print(f"  RECON WARN: store {s['store_name']} month {m}: "
                      f"events ${ev:,.4f} != payload ${s['monthly_usd'][i]:,.4f}")
assert per_store_warn == 0, f"per-store per-month reconciliation failed on {per_store_warn} (store,month) cells"

# Now round for the on-wire file. Track post-round error so we surface any
# rounding bias above ordinary noise (~$0.1 across the whole dataset).
rows = []
for (date, sidx, spidx), (usd, qty) in sorted(agg.items()):
    rows.append([date, sidx, spidx, round(usd, 4), round(qty, 3)])
ev_total_usd_rounded = sum(r[3] for r in rows)
round_drift = ev_total_usd_rounded - ev_total_usd_full
if abs(round_drift) > 1.0:
    print(f"WARN: post-round drift ${round_drift:+,.4f} exceeds $1 — rounding precision insufficient",
          file=sys.stderr)

events_doc = {
    "stores_index": stores_index,
    "rows": rows,
}
with open(OUT, "w", encoding="utf-8") as f:
    # separators=(",",":") keeps the file compact
    json.dump(events_doc, f, ensure_ascii=False, separators=(",", ":"))

size = os.path.getsize(OUT)
print(f"wrote {OUT}  ({size:,} bytes, {len(rows):,} aggregated rows)")
print(f"reconciliation: pre-round events ${ev_total_usd_full:,.4f} == payload ${payload_total_usd:,.4f}")
print(f"reconciliation: post-round events ${ev_total_usd_rounded:,.4f} (drift ${round_drift:+,.4f})")
print(f"reconciliation: all {len(months)} system months match payload (Δ ≤ $0.01)")
print(f"reconciliation: all {len(stores_all)} stores × {len(months)} months match payload (Δ ≤ $0.01)")
print(f"skipped non-store rows: {skipped_nonstore}; unmapped store/spec: {unmapped_store}/{unmapped_spec}")
if size > 4 * 1024 * 1024:
    print(f"  NOTE: events.json is > 4 MB ({size/1024/1024:.2f} MB) — consider gzip follow-up", file=sys.stderr)
