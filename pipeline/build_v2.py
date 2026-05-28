"""V2 builder — heterogeneous-unit version covering 44 物料 SKUs.

Inputs:
  cache/spec_metadata.json     — { specs: {sku: {spec_cost, cg_dly_ratio, dly_use_ratio,
                                                use_unit_mid, scm_name}} }
  cache/raw/batch_*.json       — MCP tool-result envelopes containing rows with
                                 {spec_mid, operator_dept_id, operator_dept_name,
                                  operator_name, total_adjust_num, operated_time}
  pipeline/sku_catalog.py      — SKU_CATALOG (cat+label), CATEGORIES, UNIT_LABELS

Outputs:
  output/loss_records.csv          — tidy rows, one per spoilage record
  output/store_benchmark.csv       — per-store rollups + USD-based status flags
  output/store_month_matrix.csv    — store × month matrix (USD)
  output/spec_summary.csv          — per-SKU totals
  output/dashboard_payload.json    — JSON consumed by build_dashboard.py

Unit handling: each SKU's cost_per_unit = spec_cost / (cg_dly_ratio * dly_use_ratio).
loss_qty is in the SKU's use unit (mL / g / 个). loss_usd = loss_qty * cost_per_unit
and is the only cross-SKU comparable metric.
"""
import csv, json, os, glob, math
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

from sku_catalog import SKU_CATALOG, CATEGORIES, CATEGORY_LABEL, UNIT_LABELS

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT_DIR = os.path.join(REPO_ROOT, "output")
CACHE_DIR = os.path.join(REPO_ROOT, "cache")
RAW_DIR = os.path.join(CACHE_DIR, "raw")
os.makedirs(OUT_DIR, exist_ok=True)
NY = ZoneInfo("America/New_York")

# ===== assemble SPECS from catalog + cache/spec_metadata.json =====
META = json.load(open(os.path.join(CACHE_DIR, "spec_metadata.json"), encoding="utf-8"))["specs"]
SPECS = {}
for sku, cat in SKU_CATALOG.items():
    m = META.get(sku)
    if not m:
        raise SystemExit(f"missing metadata for {sku} in cache/spec_metadata.json")
    cost = float(m["spec_cost"])
    cg = float(m["cg_dly_ratio"])
    du = float(m["dly_use_ratio"])
    use_unit = m["use_unit_mid"]
    unit_label = UNIT_LABELS.get(use_unit, use_unit)
    SPECS[sku] = {
        "name": m.get("scm_name", cat["label_cn"]),
        "label_cn": cat["label_cn"],
        "cat": cat["cat"],
        "cat_label": CATEGORY_LABEL[cat["cat"]],
        "spec_cost": cost,
        "cg_dly_ratio": cg,
        "dly_use_ratio": du,
        "use_unit_mid": use_unit,
        "unit_label": unit_label,
        "cost_per_unit": cost / (cg * du),
    }
print(f"loaded {len(SPECS)} specs across {len({s['cat'] for s in SPECS.values()})} categories")

# ===== store master (subset of luckyus_opshop.t_shop_info status=1, NY area) =====
SHOP_MASTER = {
    1127:  ("US00001", "8th & Broadway"),
    1128:  ("US00002", "28th & 6th"),
    1140:  ("US00003", "100 Maiden Ln"),
    20011: ("US00004", "37th & Broadway"),
    1141:  ("US00005", "54th & 8th"),
    20010: ("US00006", "102 Fulton"),
    20009: ("US00007", "108th & Broadway"),
    20008: ("US00008", "33rd & 10th"),
    20016: ("US00010", "154 Bleecker"),
    20019: ("US00012", "16th & 6th"),
    20022: ("US00015", "41st & Lexington"),
    20025: ("US00018", "40th & 10th"),
    20026: ("US00019", "29th & 3rd"),
    20027: ("US00020", "21st & 3rd"),
    20029: ("US00022", "23rd & 8th"),
    20031: ("US00024", "15th & 3rd"),
    20032: ("US00025", "221 Grand"),
    20035: ("US00027", "52nd & Madison"),
}
NON_STORE_DEPTS = {1124, 1112}
AREA_LABEL = "Area 1 (NYC)"

# ===== sales data (from t_order_store_fact, cycle_type=3 hourly, rolled to store-month) =====
SALES = [
    (1127,"2025-07",389091),(1127,"2025-08",398356),(1127,"2025-09",467770),(1127,"2025-10",467086),
    (1127,"2025-11",385513),(1127,"2025-12",298141),(1127,"2026-01",246171),(1127,"2026-02",305852),
    (1127,"2026-03",355478),(1127,"2026-04",423711),(1127,"2026-05",186781),
    (1128,"2025-07",364922),(1128,"2025-08",365091),(1128,"2025-09",273165),(1128,"2025-10",266065),
    (1128,"2025-11",237707),(1128,"2025-12",167698),(1128,"2026-01",149761),(1128,"2026-02",141557),
    (1128,"2026-03",188600),(1128,"2026-04",190441),(1128,"2026-05",133147),
    (1140,"2025-09",150712),(1140,"2025-10",200465),(1140,"2025-11",153920),(1140,"2025-12",127541),
    (1140,"2026-01",131879),(1140,"2026-02",114029),(1140,"2026-03",145956),(1140,"2026-04",155563),(1140,"2026-05",112675),
    (1141,"2025-08",66133),(1141,"2025-09",236475),(1141,"2025-10",257454),(1141,"2025-11",228092),
    (1141,"2025-12",176817),(1141,"2026-01",180002),(1141,"2026-02",154711),(1141,"2026-03",203892),
    (1141,"2026-04",214830),(1141,"2026-05",153115),
    (20008,"2025-12",142844),(20008,"2026-01",155770),(20008,"2026-02",141938),
    (20008,"2026-03",181210),(20008,"2026-04",214552),(20008,"2026-05",155052),
    (20009,"2026-04",7395),(20009,"2026-05",183644),
    (20010,"2025-08",40505),(20010,"2025-09",285829),(20010,"2025-10",302193),(20010,"2025-11",251807),
    (20010,"2025-12",216570),(20010,"2026-01",197533),(20010,"2026-02",177969),(20010,"2026-03",227248),
    (20010,"2026-04",246615),(20010,"2026-05",172830),
    (20011,"2025-11",68260),(20011,"2025-12",210119),(20011,"2026-01",195218),(20011,"2026-02",211966),
    (20011,"2026-03",295481),(20011,"2026-04",327364),(20011,"2026-05",229530),
    (20016,"2026-04",5624),(20016,"2026-05",57870),
    (20019,"2026-03",23824),(20019,"2026-04",104767),(20019,"2026-05",75691),
    (20022,"2026-04",6397),(20022,"2026-05",133356),
    (20025,"2026-05",7671),
    (20026,"2026-04",89884),(20026,"2026-05",100754),
    (20027,"2026-02",110889),(20027,"2026-03",140982),(20027,"2026-04",136550),(20027,"2026-05",100561),
    (20029,"2026-05",4771),
    (20031,"2025-12",55066),(20031,"2026-01",123712),(20031,"2026-02",107067),(20031,"2026-03",136004),
    (20031,"2026-04",151164),(20031,"2026-05",103324),
    (20032,"2025-12",152358),(20032,"2026-01",269076),(20032,"2026-02",208262),(20032,"2026-03",273980),
    (20032,"2026-04",110595),(20032,"2026-05",190694),
    (20035,"2026-02",16072),(20035,"2026-03",214714),(20035,"2026-04",256440),(20035,"2026-05",169689),
]
SALES_MAP = {(s, m): q for s, m, q in SALES}

# ===== load raw spoilage rows from cache/raw/batch_*.json =====
def load_tool_result_rows(path):
    arr = json.load(open(path, encoding="utf-8"))
    inner = json.loads(arr[0]["text"])
    return inner["rows"]

raw_rows = []
for fp in sorted(glob.glob(os.path.join(RAW_DIR, "batch_*.json"))):
    rs = load_tool_result_rows(fp)
    raw_rows.extend(rs)
    print(f"  loaded {len(rs):>5} rows from {os.path.relpath(fp, REPO_ROOT)}")

# drop rows for SKUs not in catalog (defensive: catalog is the whitelist)
raw_rows = [r for r in raw_rows if r.get("spec_mid") in SPECS]
specs_with_data = {r["spec_mid"] for r in raw_rows}
print(f"loaded {len(raw_rows)} raw spoilage rows across {len(specs_with_data)}/{len(SPECS)} specs with data")
print(f"specs with no records: {sorted(set(SPECS) - specs_with_data)}")

# ===== DST-aware bucketing + DST audit =====
def parse_utc(s):
    dt = datetime.fromisoformat(s)
    return dt.replace(tzinfo=timezone.utc)

dst_drift = []
for r in raw_rows:
    utc_dt = parse_utc(r["operated_time"])
    ny_dt = utc_dt.astimezone(NY)
    fixed_est_dt = utc_dt.replace(tzinfo=None) - timedelta(hours=5)
    ny_month = ny_dt.strftime("%Y-%m")
    fx_month = fixed_est_dt.strftime("%Y-%m")
    r["ny_dt"] = ny_dt
    r["ny_month"] = ny_month
    r["ny_date"] = ny_dt.date().isoformat()
    if ny_month != fx_month:
        dst_drift.append({"spec": r["spec_mid"], "dept": r["operator_dept_id"],
                          "utc": r["operated_time"], "ny_month": ny_month, "fixed_month": fx_month})
print(f"DST audit: {len(dst_drift)} rows would shift months between zoneinfo NY vs fixed UTC-5")

# ===== normalize records =====
records = []
for r in raw_rows:
    dept_id = r["operator_dept_id"]
    dept_name = r["operator_dept_name"]
    qty = float(r["total_adjust_num"])
    if qty == 0: continue
    if dept_id == 20008 and dept_name == "JFK 24":
        shop_no, store_name, is_store = "JFK-KIOSK", "JFK 24", True
    elif dept_id in NON_STORE_DEPTS:
        shop_no, store_name, is_store = "NON-STORE", dept_name, False
    elif dept_id in SHOP_MASTER:
        shop_no, store_name = SHOP_MASTER[dept_id]
        is_store = True
    else:
        shop_no, store_name, is_store = "UNKNOWN", dept_name, True
    spec = SPECS[r["spec_mid"]]
    loss_qty = abs(qty)
    loss_usd = loss_qty * spec["cost_per_unit"]
    records.append({
        "spec_mid": r["spec_mid"],
        "spec_name": spec["label_cn"],
        "category": spec["cat"],
        "unit_label": spec["unit_label"],
        "dept_id": dept_id,
        "shop_no": shop_no,
        "store_name": store_name,
        "is_store": is_store,
        "area_label": AREA_LABEL if is_store else "非门店",
        "ny_month": r["ny_month"],
        "ny_time": r["ny_dt"].strftime("%Y-%m-%dT%H:%M:%S"),
        "utc_time": r["operated_time"],
        "operator": r["operator_name"],
        "signed_qty": qty,
        "loss_qty": loss_qty,
        "loss_usd": loss_usd,
        "source": "in-store app",
    })

# ===== month axis =====
months_all = sorted({r["ny_month"] for r in records})

# ===== write tidy loss_records.csv =====
fields = ["spec_mid","spec_name","category","unit_label","store_name","shop_no","dept_id","area_label","is_store",
          "ny_month","ny_time","utc_time","operator","signed_qty","loss_qty","loss_usd","source"]
LOSS_CSV = os.path.join(OUT_DIR, "loss_records.csv")
with open(LOSS_CSV, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    for r in sorted(records, key=lambda x: (x["spec_mid"], x["shop_no"], x["utc_time"])):
        w.writerow({k: r[k] for k in fields})
print(f"wrote {LOSS_CSV}  ({len(records)} rows)")

# ===== per-spec rollups (single-SKU views; use native unit) =====
def rollup_by_spec(records, spec_mid):
    sub = [r for r in records if r["spec_mid"] == spec_mid and r["is_store"]]
    groups = defaultdict(list)
    for r in sub:
        groups[(r["dept_id"], r["shop_no"], r["store_name"], r["area_label"])].append(r)
    out = []
    for (dept_id, shop_no, store_name, area), g in groups.items():
        m_qty = defaultdict(float); m_usd = defaultdict(float)
        op_qty = defaultdict(float); op_cnt = defaultdict(int)
        for r in g:
            m_qty[r["ny_month"]] += r["loss_qty"]
            m_usd[r["ny_month"]] += r["loss_usd"]
            op_qty[r["operator"]] += r["loss_qty"]
            op_cnt[r["operator"]] += 1
        monthly_qty = [m_qty.get(m, 0.0) for m in months_all]
        monthly_usd = [m_usd.get(m, 0.0) for m in months_all]
        sales_monthly = [SALES_MAP.get((dept_id, m), 0) for m in months_all]
        total_qty = sum(monthly_qty); total_usd = sum(monthly_usd); total_sales = sum(sales_monthly)
        intensity_monthly = [(q/s*1000.0) if s>0 else 0.0 for q, s in zip(monthly_qty, sales_monthly)]
        operators = []
        for name in sorted(op_qty, key=lambda k: -op_qty[k]):
            operators.append({"name": name, "qty": op_qty[name], "count": op_cnt[name],
                              "share_pct": (op_qty[name] / total_qty * 100.0) if total_qty else 0.0})
        last_idx = max((i for i, v in enumerate(monthly_qty) if v > 0), default=None)
        latest_mom = None
        if last_idx is not None and last_idx >= 1 and monthly_qty[last_idx - 1] > 0:
            latest_mom = (monthly_qty[last_idx] - monthly_qty[last_idx-1]) / monthly_qty[last_idx-1] * 100.0
        worst_idx = max(range(len(monthly_qty)), key=lambda i: monthly_qty[i]) if monthly_qty else 0
        intensity_total = (total_qty / total_sales * 1000.0) if total_sales > 0 else None
        out.append({
            "dept_id": dept_id, "shop_no": shop_no, "store_name": store_name, "area": area,
            "total_loss_qty": total_qty, "total_loss_usd": total_usd, "total_sales": total_sales,
            "record_count": len(g),
            "monthly_qty": monthly_qty, "monthly_usd": monthly_usd,
            "sales_monthly": sales_monthly, "intensity_monthly": intensity_monthly,
            "intensity_total": intensity_total,
            "active_months": sum(1 for v in monthly_qty if v > 0),
            "first_month": next((m for m, v in zip(months_all, monthly_qty) if v > 0), None),
            "last_active_month": months_all[last_idx] if last_idx is not None else None,
            "latest_month_value_qty": monthly_qty[last_idx] if last_idx is not None else 0.0,
            "latest_mom_pct": latest_mom,
            "worst_month": months_all[worst_idx] if monthly_qty else None,
            "worst_month_value_qty": monthly_qty[worst_idx] if monthly_qty else 0.0,
            "operators": operators,
            "top_operator": operators[0]["name"] if operators else None,
            "top_operator_share_pct": operators[0]["share_pct"] if operators else None,
        })
    return out

stores_by_spec = {sp: rollup_by_spec(records, sp) for sp in SPECS}

# ===== per-category rollups (mid-level cross-spec aggregation) =====
def rollup_by_category(records, cat):
    sub = [r for r in records if r["category"] == cat and r["is_store"]]
    groups = defaultdict(list)
    for r in sub:
        groups[(r["dept_id"], r["shop_no"], r["store_name"], r["area_label"])].append(r)
    out = []
    for (dept_id, shop_no, store_name, area), g in groups.items():
        m_usd = defaultdict(float)
        for r in g:
            m_usd[r["ny_month"]] += r["loss_usd"]
        monthly_usd = [m_usd.get(m, 0.0) for m in months_all]
        sales_monthly = [SALES_MAP.get((dept_id, m), 0) for m in months_all]
        total_usd = sum(monthly_usd); total_sales = sum(sales_monthly)
        out.append({
            "dept_id": dept_id, "shop_no": shop_no, "store_name": store_name, "area": area,
            "total_loss_usd": total_usd, "total_sales": total_sales,
            "record_count": len(g),
            "monthly_usd": monthly_usd,
            "sales_monthly": sales_monthly,
        })
    return out

stores_by_cat = {cat_id: rollup_by_category(records, cat_id) for cat_id, _ in CATEGORIES}

# ===== ALL rollup (USD only — units mix across SKUs) =====
def rollup_all(records):
    sub = [r for r in records if r["is_store"]]
    groups = defaultdict(list)
    for r in sub:
        groups[(r["dept_id"], r["shop_no"], r["store_name"], r["area_label"])].append(r)
    out = []
    for (dept_id, shop_no, store_name, area), g in groups.items():
        m_usd = defaultdict(float)
        op_usd = defaultdict(float); op_cnt = defaultdict(int)
        spec_breakdown = defaultdict(lambda: {"qty": 0.0, "usd": 0.0, "count": 0, "unit": ""})
        cat_breakdown = defaultdict(lambda: {"usd": 0.0, "count": 0})
        for r in g:
            m_usd[r["ny_month"]] += r["loss_usd"]
            op_usd[r["operator"]] += r["loss_usd"]
            op_cnt[r["operator"]] += 1
            sb = spec_breakdown[r["spec_mid"]]
            sb["qty"]   += r["loss_qty"]
            sb["usd"]   += r["loss_usd"]
            sb["count"] += 1
            sb["unit"]   = r["unit_label"]
            cb = cat_breakdown[r["category"]]
            cb["usd"]   += r["loss_usd"]
            cb["count"] += 1
        monthly_usd = [m_usd.get(m, 0.0) for m in months_all]
        sales_monthly = [SALES_MAP.get((dept_id, m), 0) for m in months_all]
        total_usd = sum(monthly_usd); total_sales = sum(sales_monthly)
        # USD-based intensity (USD per 1k orders)
        intensity_monthly = [(u/s*1000.0) if s>0 else 0.0 for u, s in zip(monthly_usd, sales_monthly)]
        intensity_total = (total_usd / total_sales * 1000.0) if total_sales > 0 else None
        operators = []
        for name in sorted(op_usd, key=lambda k: -op_usd[k]):
            operators.append({"name": name, "qty": op_usd[name], "count": op_cnt[name],
                              "share_pct": (op_usd[name]/total_usd*100.0) if total_usd else 0.0})
        last_idx = max((i for i, v in enumerate(monthly_usd) if v > 0), default=None)
        latest_mom = None
        if last_idx is not None and last_idx >= 1 and monthly_usd[last_idx - 1] > 0:
            latest_mom = (monthly_usd[last_idx]-monthly_usd[last_idx-1])/monthly_usd[last_idx-1]*100.0
        worst_idx = max(range(len(monthly_usd)), key=lambda i: monthly_usd[i]) if monthly_usd else 0
        out.append({
            "dept_id": dept_id, "shop_no": shop_no, "store_name": store_name, "area": area,
            "total_loss_usd": total_usd, "total_sales": total_sales,
            "record_count": len(g),
            "monthly_usd": monthly_usd,
            "sales_monthly": sales_monthly, "intensity_monthly": intensity_monthly,
            "intensity_total": intensity_total,
            "active_months": sum(1 for v in monthly_usd if v > 0),
            "first_month": next((m for m, v in zip(months_all, monthly_usd) if v > 0), None),
            "last_active_month": months_all[last_idx] if last_idx is not None else None,
            "latest_month_value_usd": monthly_usd[last_idx] if last_idx is not None else 0.0,
            "latest_mom_pct": latest_mom,
            "worst_month": months_all[worst_idx] if monthly_usd else None,
            "worst_month_value_usd": monthly_usd[worst_idx] if monthly_usd else 0.0,
            "operators": operators,
            "top_operator": operators[0]["name"] if operators else None,
            "top_operator_share_pct": operators[0]["share_pct"] if operators else None,
            "spec_breakdown": dict(spec_breakdown),
            "cat_breakdown": dict(cat_breakdown),
        })
    return out

stores_all = rollup_all(records)

# ===== status flags (compute on USD for ALL view) =====
def add_stats_usd(stores):
    totals = [s["total_loss_usd"] for s in stores]
    n = len(totals)
    sys_total = sum(totals)
    mean = sys_total / n if n else 0
    st = sorted(totals)
    def pct(arr, p):
        if not arr: return 0
        k = (len(arr)-1)*p; f=math.floor(k); c=math.ceil(k)
        return arr[int(k)] if f==c else arr[f]*(c-k)+arr[c]*(k-f)
    med = pct(st, 0.5); q1 = pct(st, 0.25); q3 = pct(st, 0.75)
    iqr = q3-q1; uf = q3+1.5*iqr
    std = math.sqrt(sum((t-mean)**2 for t in totals)/n) if n else 0
    stores.sort(key=lambda s: -s["total_loss_usd"])
    for i, s in enumerate(stores, 1):
        s["rank"] = i
        s["share_of_system_pct"] = (s["total_loss_usd"]/sys_total*100) if sys_total else 0
        s["vs_mean_pct"] = ((s["total_loss_usd"]-mean)/mean*100) if mean else 0
        s["vs_median_pct"] = ((s["total_loss_usd"]-med)/med*100) if med else 0
        s["z_score"] = ((s["total_loss_usd"]-mean)/std) if std else 0
        s["percentile"] = ((n-i+1)/n*100) if n else 0
        out = (iqr>0 and s["total_loss_usd"]>uf) or (std>0 and s["z_score"]>=2)
        attn = (s["total_loss_usd"]>med and s["latest_mom_pct"] is not None and s["latest_mom_pct"]>50)
        s["status"] = "异常" if out else ("需关注" if attn else "正常")
    return {"mean": mean, "median": med, "q1": q1, "q3": q3, "iqr": iqr, "upper_fence": uf, "std": std,
            "n": n, "sys_total_usd": sys_total}

def add_stats_qty(stores):
    """Per-spec views: rank by total_loss_qty (native unit); status flags on qty."""
    totals = [s["total_loss_qty"] for s in stores]
    n = len(totals)
    sys_total = sum(totals)
    mean = sys_total / n if n else 0
    st = sorted(totals)
    def pct(arr, p):
        if not arr: return 0
        k = (len(arr)-1)*p; f=math.floor(k); c=math.ceil(k)
        return arr[int(k)] if f==c else arr[f]*(c-k)+arr[c]*(k-f)
    med = pct(st, 0.5); q1 = pct(st, 0.25); q3 = pct(st, 0.75)
    iqr = q3-q1; uf = q3+1.5*iqr
    std = math.sqrt(sum((t-mean)**2 for t in totals)/n) if n else 0
    stores.sort(key=lambda s: -s["total_loss_qty"])
    for i, s in enumerate(stores, 1):
        s["rank"] = i
        s["share_of_system_pct"] = (s["total_loss_qty"]/sys_total*100) if sys_total else 0
        s["vs_mean_pct"] = ((s["total_loss_qty"]-mean)/mean*100) if mean else 0
        s["vs_median_pct"] = ((s["total_loss_qty"]-med)/med*100) if med else 0
        s["z_score"] = ((s["total_loss_qty"]-mean)/std) if std else 0
        s["percentile"] = ((n-i+1)/n*100) if n else 0
        out = (iqr>0 and s["total_loss_qty"]>uf) or (std>0 and s["z_score"]>=2)
        attn = (s["total_loss_qty"]>med and s["latest_mom_pct"] is not None and s["latest_mom_pct"]>50)
        s["status"] = "异常" if out else ("需关注" if attn else "正常")
    return {"mean": mean, "median": med, "q1": q1, "q3": q3, "iqr": iqr, "upper_fence": uf, "std": std,
            "n": n, "sys_total_qty": sys_total}

stats_all = add_stats_usd(stores_all)
stats_by_spec = {sp: add_stats_qty(stores_by_spec[sp]) for sp in SPECS}

# ===== system monthly across stores (ALL = USD) =====
sys_monthly_usd = [sum(s["monthly_usd"][i] for s in stores_all) for i in range(len(months_all))]
sys_monthly_sales = [sum(s["sales_monthly"][i] for s in stores_all) for i in range(len(months_all))]
sys_monthly_intensity = [(u/s*1000.0) if s>0 else 0.0 for u, s in zip(sys_monthly_usd, sys_monthly_sales)]
def mom_series(xs):
    o=[None]
    for i in range(1,len(xs)):
        p=xs[i-1]
        o.append(None if p==0 else (xs[i]-p)/p*100.0)
    return o
sys_mom_usd = mom_series(sys_monthly_usd)

# ===== non-store rollup =====
non_store_rec = [r for r in records if not r["is_store"]]
non_stores = []
ns_groups = defaultdict(list)
for r in non_store_rec:
    ns_groups[(r["dept_id"], r["store_name"])].append(r)
for (dept_id, dept_name), g in ns_groups.items():
    m_usd = defaultdict(float)
    for r in g:
        m_usd[r["ny_month"]] += r["loss_usd"]
    monthly_usd = [m_usd.get(m, 0.0) for m in months_all]
    non_stores.append({
        "dept_id": dept_id, "shop_no": "NON-STORE", "store_name": dept_name,
        "area": "非门店",
        "total_loss_usd": sum(monthly_usd),
        "record_count": len(g),
        "monthly_usd": monthly_usd,
        "first_month": next((m for m, v in zip(months_all, monthly_usd) if v > 0), None),
        "last_active_month": next((m for m, v in zip(reversed(months_all), reversed(monthly_usd)) if v > 0), None),
        "top_operator": max(
            (r["operator"] for r in g),
            key=lambda op: sum(rr["loss_usd"] for rr in g if rr["operator"] == op),
            default=None),
    })

# ===== write benchmark + matrix =====
BENCH_CSV  = os.path.join(OUT_DIR, "store_benchmark.csv")
MATRIX_CSV = os.path.join(OUT_DIR, "store_month_matrix.csv")
SPEC_CSV   = os.path.join(OUT_DIR, "spec_summary.csv")

bench_fields = ["rank","dept_id","shop_no","store_name","area",
                "total_loss_usd","total_sales","intensity_usd_per_1k_orders",
                "record_count","active_months","first_month","last_active_month",
                "share_of_system_pct","vs_mean_pct","vs_median_pct","z_score","percentile",
                "latest_month_value_usd","latest_mom_pct","worst_month","worst_month_value_usd",
                "top_operator","top_operator_share_pct","status"] + months_all
with open(BENCH_CSV, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(bench_fields)
    for s in stores_all:
        row = [s["rank"], s["dept_id"], s["shop_no"], s["store_name"], s["area"],
               f"{s['total_loss_usd']:.2f}", s["total_sales"],
               "" if s["intensity_total"] is None else f"{s['intensity_total']:.4f}",
               s["record_count"], s["active_months"], s["first_month"] or "", s["last_active_month"] or "",
               f"{s['share_of_system_pct']:.4f}", f"{s['vs_mean_pct']:.4f}", f"{s['vs_median_pct']:.4f}",
               f"{s['z_score']:.4f}", f"{s['percentile']:.2f}",
               f"{s['latest_month_value_usd']:.2f}",
               "" if s["latest_mom_pct"] is None else f"{s['latest_mom_pct']:.4f}",
               s["worst_month"] or "", f"{s['worst_month_value_usd']:.2f}",
               s["top_operator"] or "",
               "" if s["top_operator_share_pct"] is None else f"{s['top_operator_share_pct']:.4f}",
               s["status"]]
        row.extend(f"{v:.2f}" for v in s["monthly_usd"])
        w.writerow(row)
    for s in non_stores:
        row = ["NS", s["dept_id"], s["shop_no"], s["store_name"], s["area"],
               f"{s['total_loss_usd']:.2f}", 0, "",
               s["record_count"], 0, s["first_month"] or "", s["last_active_month"] or "",
               "","","","","","","","","",s["top_operator"] or "","","非门店"]
        row.extend(f"{v:.2f}" for v in s["monthly_usd"])
        w.writerow(row)
print(f"wrote {BENCH_CSV}")

with open(MATRIX_CSV, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["dept_id","shop_no","store_name","area"] + months_all + ["Total_USD"])
    for s in stores_all:
        w.writerow([s["dept_id"], s["shop_no"], s["store_name"], s["area"],
                    *[f"{v:.2f}" for v in s["monthly_usd"]],
                    f"{s['total_loss_usd']:.2f}"])
    col_t_usd = [sum(s["monthly_usd"][i] for s in stores_all) for i in range(len(months_all))]
    w.writerow(["TOTAL","TOTAL","TOTAL","TOTAL", *[f"{v:.2f}" for v in col_t_usd],
                f"{sum(col_t_usd):.2f}"])
    for s in non_stores:
        w.writerow([s["dept_id"], "NON-STORE", "非门店:"+s["store_name"], "非门店",
                    *[f"{v:.2f}" for v in s["monthly_usd"]],
                    f"{s['total_loss_usd']:.2f}"])
print(f"wrote {MATRIX_CSV}")

with open(SPEC_CSV, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["spec_mid","category","label","name","unit","cost_per_unit","total_records",
                "total_loss_qty","total_loss_usd","store_count_with_loss"])
    for sp, meta in SPECS.items():
        srecs = [r for r in records if r["spec_mid"] == sp and r["is_store"]]
        total_qty = sum(r["loss_qty"] for r in srecs)
        total_usd = sum(r["loss_usd"] for r in srecs)
        sc = len({r["dept_id"] for r in srecs})
        w.writerow([sp, meta["cat"], meta["label_cn"], meta["name"], meta["unit_label"],
                    f"{meta['cost_per_unit']:.6f}",
                    len(srecs), f"{total_qty:.2f}", f"{total_usd:.2f}", sc])
print(f"wrote {SPEC_CSV}")

# ===== reconciliation =====
total_rec_usd = sum(r["loss_usd"] for r in records if r["is_store"])
total_store_usd = sum(s["total_loss_usd"] for s in stores_all)
reconciliation = "PASS" if abs(total_rec_usd - total_store_usd) < 0.01 else "FAIL"

# ===== dashboard payload =====
specs_meta = []
for k, v in SPECS.items():
    srecs = [r for r in records if r["spec_mid"] == k and r["is_store"]]
    has_data = len(srecs) > 0
    specs_meta.append({
        "mid": k, "name": v["name"], "label_cn": v["label_cn"],
        "cat": v["cat"], "cat_label": v["cat_label"],
        "spec_cost": v["spec_cost"], "cg_dly_ratio": v["cg_dly_ratio"],
        "dly_use_ratio": v["dly_use_ratio"],
        "use_unit_mid": v["use_unit_mid"], "unit_label": v["unit_label"],
        "cost_per_unit": v["cost_per_unit"],
        "has_data": has_data,
        "record_count": len(srecs),
        "total_loss_qty": sum(r["loss_qty"] for r in srecs),
        "total_loss_usd": sum(r["loss_usd"] for r in srecs),
    })

payload = {
    "meta": {
        "specs": specs_meta,
        "categories": [{"id": cid, "label": clabel} for cid, clabel in CATEGORIES],
        "primary_spec": "ALL",
        "period_start": months_all[0] if months_all else "",
        "period_end":   months_all[-1] if months_all else "",
        "months": months_all,
        "areas": sorted({s["area"] for s in stores_all}),
        "generated": datetime.now(NY).strftime("%Y-%m-%d"),
        "timezone": "America/New_York (DST-aware via zoneinfo)",
        "reconciliation": reconciliation,
        "has_usd": True,
        "dst_drift_count": len(dst_drift),
        "record_count": len([r for r in records if r["is_store"]]),
        "non_store_record_count": len(non_store_rec),
        "store_count": len(stores_all),
        "non_store_count": len(non_stores),
        "spec_count": len(SPECS),
        "spec_with_data_count": sum(1 for s in specs_meta if s["has_data"]),
        "grand_total_usd": sum(s["total_loss_usd"] for s in stores_all),
        "system_monthly_usd": sys_monthly_usd,
        "system_monthly_sales": sys_monthly_sales,
        "system_monthly_intensity": sys_monthly_intensity,
        "system_mom_pct": sys_mom_usd,
        "system_latest_mom_pct": sys_mom_usd[-1] if sys_mom_usd else None,
        "stats_all": stats_all,
        "stats_by_spec": stats_by_spec,
    },
    "stores_all": stores_all,
    "stores_by_spec": stores_by_spec,
    "stores_by_cat": stores_by_cat,
    "non_stores": non_stores,
}
PAYLOAD = os.path.join(OUT_DIR, "dashboard_payload.json")
with open(PAYLOAD, "w", encoding="utf-8") as f:
    json.dump(payload, f, ensure_ascii=False, indent=2)
print(f"wrote {PAYLOAD}")

# ===== summary =====
print("\n" + "="*78)
print("BUILD V2 SUMMARY")
print("="*78)
print(f"Specs covered     : {len(SPECS)} total, {len(specs_with_data)} with records, {len(SPECS)-len(specs_with_data)} empty")
print(f"Records (store)   : {len([r for r in records if r['is_store']])}")
print(f"Records (non-store): {len(non_store_rec)}")
print(f"Stores            : {len(stores_all)}")
print(f"Months            : {months_all[0]} → {months_all[-1]} ({len(months_all)} months)")
print(f"Grand loss (USD)  : ${stats_all['sys_total_usd']:,.2f}")
print(f"Reconciliation    : {reconciliation}")
print()
print("Per-category USD totals:")
cat_totals = defaultdict(float)
cat_counts = defaultdict(int)
for r in records:
    if r["is_store"]:
        cat_totals[r["category"]] += r["loss_usd"]
        cat_counts[r["category"]] += 1
for cid, clabel in CATEGORIES:
    print(f"  {cid:<10} {clabel:<26} USD=${cat_totals.get(cid, 0):>11,.2f}  records={cat_counts.get(cid, 0):>5}")

print("\nTop 10 stores by USD across all specs:")
for s in stores_all[:10]:
    intensity_str = f"${s['intensity_total']:.2f}" if s['intensity_total'] is not None else "—"
    print(f"  #{s['rank']:>2} {s['store_name']:<22} USD=${s['total_loss_usd']:>9,.2f} orders={s['total_sales']:>9,} intensity(USD/1k)={intensity_str:>8} status={s['status']}")
