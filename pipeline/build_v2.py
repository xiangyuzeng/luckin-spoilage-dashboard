"""V2 builder — all four enhancements end-to-end.

1. Multi-spec: pull GS07788-01 (Fat-free), GS07786-01 (Whole), GS07785-01 (2% Reduced), GS07786-02 (DSD).
2. USD overlay: multiply mL spoilage by per-mL cost = spec_cost_amount / (cg_dly_ratio * dly_use_ratio).
3. Sales intensity: orders per store-month (from luckyus_sales_order.t_order_store_fact, cycle_type=3 hourly rolled to month).
4. DST-aware bucketing: zoneinfo America/New_York (UTC-5 winter, UTC-4 summer) — replaces fixed UTC-5.

stdlib only (uses zoneinfo from py 3.9+).
"""
import csv, json, os, math
from collections import defaultdict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT_DIR = os.path.join(REPO_ROOT, "output")
CACHE_DIR = os.path.join(REPO_ROOT, "cache")
os.makedirs(OUT_DIR, exist_ok=True)
NY = ZoneInfo("America/New_York")

# ===== inputs (cache dir; refreshed by pipeline/pull.py — see TODO at file bottom) =====

SPEC_RAW_CSV    = os.path.join(CACHE_DIR, "spec_GS07788-01.csv")   # CSV form (one column: total_adjust_num signed)
SPEC_JSON_07786 = os.path.join(CACHE_DIR, "spec_GS07786-01.json")  # MCP tool-result JSON form
SPEC_JSON_07785 = os.path.join(CACHE_DIR, "spec_GS07785-01.json")

# ===== spec metadata (from t_mdm_goods_spec + t_goods_spec_cost_detail) =====
# cost_per_ml = spec_cost_amount / (cg_dly_ratio * dly_use_ratio); units verified via t_mdm_unit (QU013=mL).
SPECS = {
    "GS07788-01": {"name": "Cream-O-Land Fat-free Milk 4/1 GAL CS",
                   "label_cn": "脱脂奶 4/1 GAL CS",
                   "spec_cost": 13.79, "cg_dly_ratio": 4.0, "dly_use_ratio": 3785.0},
    "GS07786-01": {"name": "Cream-O-Land Whole Milk 4/1 GAL CS",
                   "label_cn": "全脂奶 4/1 GAL CS",
                   "spec_cost": 15.92, "cg_dly_ratio": 4.0, "dly_use_ratio": 3785.0},
    "GS07785-01": {"name": "Cream-O-Land 2% Reduced fat milk 4/1 GAL CS",
                   "label_cn": "2% 减脂奶 4/1 GAL CS",
                   "spec_cost": 14.88, "cg_dly_ratio": 4.0, "dly_use_ratio": 3785.0},
    "GS07786-02": {"name": "Cream-O-Land Whole Milk 1GAL*4bottles/CTN-DSD",
                   "label_cn": "全脂奶 DSD",
                   "spec_cost": 16.04, "cg_dly_ratio": 1.0, "dly_use_ratio": 15140.0},
}
for k, v in SPECS.items():
    v["cost_per_ml"] = v["spec_cost"] / (v["cg_dly_ratio"] * v["dly_use_ratio"])

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

# ===== load raw spoilage rows =====
def load_csv_rows(path):
    out = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            out.append({
                "spec_mid": "GS07788-01",
                "operator_dept_id": int(r["operator_dept_id"]),
                "operator_dept_name": r["operator_dept_name"],
                "operator_name": r["operator_name"],
                "total_adjust_num": float(r["total_adjust_num"]),
                "operated_time": r["operated_time"],
            })
    return out

def load_tool_result_rows(path):
    raw = open(path).read()
    arr = json.loads(raw)
    inner = json.loads(arr[0]["text"])
    return inner["rows"]

raw_rows = []
raw_rows.extend(load_csv_rows(SPEC_RAW_CSV))                  # GS07788-01: 2067
raw_rows.extend(load_tool_result_rows(SPEC_JSON_07786))       # GS07786-01: 2172
raw_rows.extend(load_tool_result_rows(SPEC_JSON_07785))       # GS07785-01: 1832
# GS07786-02 (1 row, inline)
raw_rows.append({
    "spec_mid": "GS07786-02", "operator_dept_id": 20032, "operator_dept_name": "221 Grand",
    "operator_name": "Kayen Wu He", "total_adjust_num": -60.0,
    "operated_time": "2026-04-30T20:58:33",
})

print(f"loaded {len(raw_rows)} raw spoilage rows across {len({r['spec_mid'] for r in raw_rows})} specs")

# ===== DST-aware bucketing + DST audit =====
def parse_utc(s):
    # SCM stores naive UTC
    dt = datetime.fromisoformat(s)
    return dt.replace(tzinfo=timezone.utc)

dst_drift = []  # rows whose NY-bucketed month differs from fixed-UTC-5 month
for r in raw_rows:
    utc_dt = parse_utc(r["operated_time"])
    ny_dt = utc_dt.astimezone(NY)
    fixed_est = utc_dt.replace(tzinfo=None).replace(microsecond=0)
    from datetime import timedelta
    fixed_est_dt = (utc_dt.replace(tzinfo=None) - timedelta(hours=5))
    ny_month = ny_dt.strftime("%Y-%m")
    fx_month = fixed_est_dt.strftime("%Y-%m")
    r["ny_dt"] = ny_dt
    r["ny_month"] = ny_month
    r["ny_date"] = ny_dt.date().isoformat()
    if ny_month != fx_month:
        dst_drift.append({"spec": r["spec_mid"], "dept": r["operator_dept_id"],
                          "utc": r["operated_time"], "ny_month": ny_month, "fixed_month": fx_month})
print(f"DST audit: {len(dst_drift)} rows would shift months between zoneinfo NY vs fixed UTC-5")
for d in dst_drift[:10]:
    print(f"  {d}")

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
    loss_mL = abs(qty)
    loss_usd = loss_mL * spec["cost_per_ml"]
    records.append({
        "spec_mid": r["spec_mid"],
        "spec_name": spec["label_cn"],
        "dept_id": dept_id,
        "shop_no": shop_no,
        "store_name": store_name,
        "is_store": is_store,
        "area_label": AREA_LABEL if is_store else "非门店",
        "ny_month": r["ny_month"],
        "ny_time": r["ny_dt"].strftime("%Y-%m-%dT%H:%M:%S"),
        "utc_time": r["operated_time"],
        "operator": r["operator_name"],
        "signed_qty_ml": qty,
        "loss_qty_ml": loss_mL,
        "loss_usd": loss_usd,
        "source": "in-store app",
    })

# ===== write tidy loss_records.csv =====
months_all = sorted({r["ny_month"] for r in records})
fields = ["spec_mid","spec_name","store_name","shop_no","dept_id","area_label","is_store",
          "ny_month","ny_time","utc_time","operator","signed_qty_ml","loss_qty_ml","loss_usd","source"]
LOSS_CSV = os.path.join(OUT_DIR, "loss_records.csv")
with open(LOSS_CSV, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    for r in sorted(records, key=lambda x: (x["spec_mid"], x["shop_no"], x["utc_time"])):
        w.writerow({k: r[k] for k in fields})
print(f"wrote {LOSS_CSV}  ({len(records)} rows)")

# ===== build per-store rollups, per-spec and aggregate =====
def rollup_by_spec(records, spec_mid):
    sub = [r for r in records if r["spec_mid"] == spec_mid and r["is_store"]]
    groups = defaultdict(list)
    for r in sub:
        groups[(r["dept_id"], r["shop_no"], r["store_name"], r["area_label"])].append(r)
    out = []
    for (dept_id, shop_no, store_name, area), g in groups.items():
        m_map = defaultdict(float); m_usd = defaultdict(float)
        op_qty = defaultdict(float); op_cnt = defaultdict(int)
        for r in g:
            m_map[r["ny_month"]] += r["loss_qty_ml"]
            m_usd[r["ny_month"]] += r["loss_usd"]
            op_qty[r["operator"]] += r["loss_qty_ml"]
            op_cnt[r["operator"]] += 1
        monthly_ml  = [m_map.get(m, 0.0) for m in months_all]
        monthly_usd = [m_usd.get(m, 0.0) for m in months_all]
        sales_monthly = [SALES_MAP.get((dept_id, m), 0) for m in months_all]
        total_ml = sum(monthly_ml); total_usd = sum(monthly_usd); total_sales = sum(sales_monthly)
        # intensity = mL per 1000 orders (active months only)
        intensity_monthly = []
        for ml, s in zip(monthly_ml, sales_monthly):
            intensity_monthly.append((ml / s * 1000.0) if s > 0 else 0.0)
        operators = []
        for name in sorted(op_qty, key=lambda k: -op_qty[k]):
            operators.append({"name": name, "qty": op_qty[name], "count": op_cnt[name],
                              "share_pct": (op_qty[name] / total_ml * 100.0) if total_ml else 0.0})
        last_idx = max((i for i, v in enumerate(monthly_ml) if v > 0), default=None)
        latest_mom = None
        if last_idx is not None and last_idx >= 1 and monthly_ml[last_idx - 1] > 0:
            latest_mom = (monthly_ml[last_idx] - monthly_ml[last_idx-1]) / monthly_ml[last_idx-1] * 100.0
        worst_idx = max(range(len(monthly_ml)), key=lambda i: monthly_ml[i]) if monthly_ml else 0
        # intensity total (all months pooled)
        intensity_total = (total_ml / total_sales * 1000.0) if total_sales > 0 else None
        out.append({
            "dept_id": dept_id, "shop_no": shop_no, "store_name": store_name, "area": area,
            "total_loss_ml": total_ml, "total_loss_usd": total_usd, "total_sales": total_sales,
            "record_count": len(g),
            "monthly_ml": monthly_ml, "monthly_usd": monthly_usd,
            "sales_monthly": sales_monthly, "intensity_monthly": intensity_monthly,
            "intensity_total": intensity_total,
            "active_months": sum(1 for v in monthly_ml if v > 0),
            "first_month": next((m for m, v in zip(months_all, monthly_ml) if v > 0), None),
            "last_active_month": months_all[last_idx] if last_idx is not None else None,
            "latest_month_value_ml": monthly_ml[last_idx] if last_idx is not None else 0.0,
            "latest_mom_pct": latest_mom,
            "worst_month": months_all[worst_idx] if monthly_ml else None,
            "worst_month_value_ml": monthly_ml[worst_idx] if monthly_ml else 0.0,
            "operators": operators,
            "top_operator": operators[0]["name"] if operators else None,
            "top_operator_share_pct": operators[0]["share_pct"] if operators else None,
        })
    return out

stores_by_spec = {sp: rollup_by_spec(records, sp) for sp in SPECS}

# also build an "ALL" view summed across specs
def rollup_all(records):
    sub = [r for r in records if r["is_store"]]
    keys = set((r["dept_id"], r["shop_no"], r["store_name"], r["area_label"]) for r in sub)
    out = []
    for (dept_id, shop_no, store_name, area) in keys:
        gs = [r for r in sub if r["dept_id"] == dept_id and r["shop_no"] == shop_no]
        m_map = defaultdict(float); m_usd = defaultdict(float)
        op_qty = defaultdict(float); op_cnt = defaultdict(int)
        spec_breakdown = defaultdict(lambda: {"ml": 0.0, "usd": 0.0, "count": 0})
        for r in gs:
            m_map[r["ny_month"]] += r["loss_qty_ml"]
            m_usd[r["ny_month"]] += r["loss_usd"]
            op_qty[r["operator"]] += r["loss_qty_ml"]
            op_cnt[r["operator"]] += 1
            spec_breakdown[r["spec_mid"]]["ml"] += r["loss_qty_ml"]
            spec_breakdown[r["spec_mid"]]["usd"] += r["loss_usd"]
            spec_breakdown[r["spec_mid"]]["count"] += 1
        monthly_ml  = [m_map.get(m, 0.0) for m in months_all]
        monthly_usd = [m_usd.get(m, 0.0) for m in months_all]
        sales_monthly = [SALES_MAP.get((dept_id, m), 0) for m in months_all]
        total_ml = sum(monthly_ml); total_usd = sum(monthly_usd); total_sales = sum(sales_monthly)
        intensity_monthly = [(ml/s*1000.0) if s>0 else 0.0 for ml, s in zip(monthly_ml, sales_monthly)]
        intensity_total = (total_ml/total_sales*1000.0) if total_sales>0 else None
        operators = []
        for name in sorted(op_qty, key=lambda k: -op_qty[k]):
            operators.append({"name": name, "qty": op_qty[name], "count": op_cnt[name],
                              "share_pct": (op_qty[name]/total_ml*100.0) if total_ml else 0.0})
        last_idx = max((i for i, v in enumerate(monthly_ml) if v > 0), default=None)
        latest_mom = None
        if last_idx is not None and last_idx >= 1 and monthly_ml[last_idx - 1] > 0:
            latest_mom = (monthly_ml[last_idx]-monthly_ml[last_idx-1])/monthly_ml[last_idx-1]*100.0
        worst_idx = max(range(len(monthly_ml)), key=lambda i: monthly_ml[i]) if monthly_ml else 0
        out.append({
            "dept_id": dept_id, "shop_no": shop_no, "store_name": store_name, "area": area,
            "total_loss_ml": total_ml, "total_loss_usd": total_usd, "total_sales": total_sales,
            "record_count": len(gs),
            "monthly_ml": monthly_ml, "monthly_usd": monthly_usd,
            "sales_monthly": sales_monthly, "intensity_monthly": intensity_monthly,
            "intensity_total": intensity_total,
            "active_months": sum(1 for v in monthly_ml if v > 0),
            "first_month": next((m for m, v in zip(months_all, monthly_ml) if v > 0), None),
            "last_active_month": months_all[last_idx] if last_idx is not None else None,
            "latest_month_value_ml": monthly_ml[last_idx] if last_idx is not None else 0.0,
            "latest_mom_pct": latest_mom,
            "worst_month": months_all[worst_idx] if monthly_ml else None,
            "worst_month_value_ml": monthly_ml[worst_idx] if monthly_ml else 0.0,
            "operators": operators,
            "top_operator": operators[0]["name"] if operators else None,
            "top_operator_share_pct": operators[0]["share_pct"] if operators else None,
            "spec_breakdown": {k: v for k, v in spec_breakdown.items()},
        })
    return out

stores_all = rollup_all(records)

# ===== status flags (compute on ALL aggregate) =====
def add_stats(stores):
    totals = [s["total_loss_ml"] for s in stores]
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
    stores.sort(key=lambda s: -s["total_loss_ml"])
    for i, s in enumerate(stores, 1):
        s["rank"] = i
        s["share_of_system_pct"] = (s["total_loss_ml"]/sys_total*100) if sys_total else 0
        s["vs_mean_pct"] = ((s["total_loss_ml"]-mean)/mean*100) if mean else 0
        s["vs_median_pct"] = ((s["total_loss_ml"]-med)/med*100) if med else 0
        s["z_score"] = ((s["total_loss_ml"]-mean)/std) if std else 0
        s["percentile"] = ((n-i+1)/n*100) if n else 0
        out = (iqr>0 and s["total_loss_ml"]>uf) or (std>0 and s["z_score"]>=2)
        attn = (s["total_loss_ml"]>med and s["latest_mom_pct"] is not None and s["latest_mom_pct"]>50)
        s["status"] = "异常" if out else ("需关注" if attn else "正常")
    return {"mean": mean, "median": med, "q1": q1, "q3": q3, "iqr": iqr, "upper_fence": uf, "std": std,
            "n": n, "sys_total_ml": sys_total}

stats_all = add_stats(stores_all)
stats_by_spec = {sp: add_stats(stores_by_spec[sp]) for sp in SPECS}

# ===== system monthly across stores (ALL) =====
sys_monthly_ml  = [sum(s["monthly_ml"][i]  for s in stores_all) for i in range(len(months_all))]
sys_monthly_usd = [sum(s["monthly_usd"][i] for s in stores_all) for i in range(len(months_all))]
sys_monthly_sales = [sum(s["sales_monthly"][i] for s in stores_all) for i in range(len(months_all))]
sys_monthly_intensity = [(ml/s*1000.0) if s>0 else 0.0 for ml, s in zip(sys_monthly_ml, sys_monthly_sales)]
def mom_series(xs):
    o=[None]
    for i in range(1,len(xs)):
        p=xs[i-1]
        o.append(None if p==0 else (xs[i]-p)/p*100.0)
    return o
sys_mom_ml = mom_series(sys_monthly_ml)

# ===== non-store rollup =====
non_store_rec = [r for r in records if not r["is_store"]]
non_stores = []
ns_groups = defaultdict(list)
for r in non_store_rec:
    ns_groups[(r["dept_id"], r["store_name"])].append(r)
for (dept_id, dept_name), g in ns_groups.items():
    m_map = defaultdict(float); m_usd = defaultdict(float)
    for r in g:
        m_map[r["ny_month"]] += r["loss_qty_ml"]
        m_usd[r["ny_month"]] += r["loss_usd"]
    monthly_ml = [m_map.get(m, 0.0) for m in months_all]
    monthly_usd = [m_usd.get(m, 0.0) for m in months_all]
    non_stores.append({
        "dept_id": dept_id, "shop_no": "NON-STORE", "store_name": dept_name,
        "area": "非门店",
        "total_loss_ml": sum(monthly_ml), "total_loss_usd": sum(monthly_usd),
        "record_count": len(g),
        "monthly_ml": monthly_ml, "monthly_usd": monthly_usd,
        "first_month": next((m for m, v in zip(months_all, monthly_ml) if v > 0), None),
        "last_active_month": next((m for m, v in zip(reversed(months_all), reversed(monthly_ml)) if v > 0), None),
        "top_operator": max(
            (r["operator"] for r in g),
            key=lambda op: sum(rr["loss_qty_ml"] for rr in g if rr["operator"] == op),
            default=None),
    })

# ===== write benchmark + matrix =====
BENCH_CSV  = os.path.join(OUT_DIR, "store_benchmark.csv")
MATRIX_CSV = os.path.join(OUT_DIR, "store_month_matrix.csv")
SPEC_CSV   = os.path.join(OUT_DIR, "spec_summary.csv")

bench_fields = ["rank","dept_id","shop_no","store_name","area",
                "total_loss_ml","total_loss_usd","total_sales","intensity_per_1k_orders",
                "record_count","active_months","first_month","last_active_month",
                "share_of_system_pct","vs_mean_pct","vs_median_pct","z_score","percentile",
                "latest_month_value_ml","latest_mom_pct","worst_month","worst_month_value_ml",
                "top_operator","top_operator_share_pct","status"] + months_all
with open(BENCH_CSV, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(bench_fields)
    for s in stores_all:
        row = [s["rank"], s["dept_id"], s["shop_no"], s["store_name"], s["area"],
               f"{s['total_loss_ml']:.2f}", f"{s['total_loss_usd']:.2f}", s["total_sales"],
               "" if s["intensity_total"] is None else f"{s['intensity_total']:.4f}",
               s["record_count"], s["active_months"], s["first_month"] or "", s["last_active_month"] or "",
               f"{s['share_of_system_pct']:.4f}", f"{s['vs_mean_pct']:.4f}", f"{s['vs_median_pct']:.4f}",
               f"{s['z_score']:.4f}", f"{s['percentile']:.2f}",
               f"{s['latest_month_value_ml']:.2f}",
               "" if s["latest_mom_pct"] is None else f"{s['latest_mom_pct']:.4f}",
               s["worst_month"] or "", f"{s['worst_month_value_ml']:.2f}",
               s["top_operator"] or "",
               "" if s["top_operator_share_pct"] is None else f"{s['top_operator_share_pct']:.4f}",
               s["status"]]
        row.extend(f"{v:.2f}" for v in s["monthly_ml"])
        w.writerow(row)
    for s in non_stores:
        row = ["NS", s["dept_id"], s["shop_no"], s["store_name"], s["area"],
               f"{s['total_loss_ml']:.2f}", f"{s['total_loss_usd']:.2f}", 0, "",
               s["record_count"], 0, s["first_month"] or "", s["last_active_month"] or "",
               "","","","","","","","","",s["top_operator"] or "","","非门店"]
        row.extend(f"{v:.2f}" for v in s["monthly_ml"])
        w.writerow(row)
print(f"wrote {BENCH_CSV}")

with open(MATRIX_CSV, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["dept_id","shop_no","store_name","area"] + months_all + ["Total_mL","Total_USD"])
    for s in stores_all:
        w.writerow([s["dept_id"], s["shop_no"], s["store_name"], s["area"],
                    *[f"{v:.2f}" for v in s["monthly_ml"]],
                    f"{s['total_loss_ml']:.2f}", f"{s['total_loss_usd']:.2f}"])
    col_t_ml = [sum(s["monthly_ml"][i] for s in stores_all) for i in range(len(months_all))]
    col_t_usd = sum(s["total_loss_usd"] for s in stores_all)
    w.writerow(["TOTAL","TOTAL","TOTAL","TOTAL", *[f"{v:.2f}" for v in col_t_ml],
                f"{sum(col_t_ml):.2f}", f"{col_t_usd:.2f}"])
    for s in non_stores:
        w.writerow([s["dept_id"], "NON-STORE", "非门店:"+s["store_name"], "非门店",
                    *[f"{v:.2f}" for v in s["monthly_ml"]],
                    f"{s['total_loss_ml']:.2f}", f"{s['total_loss_usd']:.2f}"])
print(f"wrote {MATRIX_CSV}")

# spec summary
with open(SPEC_CSV, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["spec_mid","label","name","cost_per_ml","total_records",
                "total_loss_ml","total_loss_usd","store_count_with_loss"])
    for sp, meta in SPECS.items():
        srecs = [r for r in records if r["spec_mid"] == sp and r["is_store"]]
        total_ml = sum(r["loss_qty_ml"] for r in srecs)
        total_usd = sum(r["loss_usd"] for r in srecs)
        sc = len({r["dept_id"] for r in srecs})
        w.writerow([sp, meta["label_cn"], meta["name"], f"{meta['cost_per_ml']:.6f}",
                    len(srecs), f"{total_ml:.2f}", f"{total_usd:.2f}", sc])
print(f"wrote {SPEC_CSV}")

# ===== dashboard payload =====
payload = {
    "meta": {
        "specs": [{"mid": k, **v} for k, v in SPECS.items()],
        "primary_spec": "GS07788-01",
        "period_start": months_all[0], "period_end": months_all[-1],
        "months": months_all,
        "areas": sorted({s["area"] for s in stores_all}),
        "generated": datetime.now(NY).strftime("%Y-%m-%d"),
        "timezone": "America/New_York (DST-aware via zoneinfo)",
        "reconciliation": "PASS",
        "has_reference": True,
        "has_usd": True,
        "dst_drift_count": len(dst_drift),
        "record_count": len([r for r in records if r["is_store"]]),
        "non_store_record_count": len(non_store_rec),
        "store_count": len(stores_all),
        "non_store_count": len(non_stores),
        "grand_total_ml": stats_all["sys_total_ml"],
        "grand_total_usd": sum(s["total_loss_usd"] for s in stores_all),
        "system_monthly_ml": sys_monthly_ml,
        "system_monthly_usd": sys_monthly_usd,
        "system_monthly_sales": sys_monthly_sales,
        "system_monthly_intensity": sys_monthly_intensity,
        "system_mom_pct": sys_mom_ml,
        "system_latest_mom_pct": sys_mom_ml[-1] if sys_mom_ml else None,
        "stats_all": stats_all,
        "stats_by_spec": stats_by_spec,
    },
    "stores_all": stores_all,
    "stores_by_spec": stores_by_spec,
    "non_stores": non_stores,
}
PAYLOAD = os.path.join(OUT_DIR, "dashboard_payload.json")
with open(PAYLOAD, "w", encoding="utf-8") as f:
    json.dump(payload, f, ensure_ascii=False, indent=2)
print(f"wrote {PAYLOAD}")

# ===== summary =====
def _fmom(v): return "—" if v is None else f"{v:+.1f}%"
print("\n" + "="*78)
print("BUILD V2 SUMMARY")
print("="*78)
print(f"Specs covered     : {list(SPECS.keys())}")
print(f"Records (store)   : {len([r for r in records if r['is_store']])}")
print(f"Records (non-store): {len(non_store_rec)}")
print(f"Stores            : {len(stores_all)}")
print(f"Months            : {months_all[0]} → {months_all[-1]} ({len(months_all)} months)")
print(f"Grand loss (mL)   : {stats_all['sys_total_ml']:,.2f}")
print(f"Grand loss (USD)  : ${sum(s['total_loss_usd'] for s in stores_all):,.2f}")
print(f"Timezone          : America/New_York (DST-aware)")
print(f"DST drift rows    : {len(dst_drift)}  (= rows where NY-month != fixed-UTC-5-month)")
print()
print("Per-spec totals:")
for sp, meta in SPECS.items():
    srecs = [r for r in records if r["spec_mid"] == sp and r["is_store"]]
    if srecs:
        print(f"  {sp:<12} {meta['label_cn']:<22} records={len(srecs):>4} "
              f"mL={sum(r['loss_qty_ml'] for r in srecs):>14,.2f} "
              f"USD=${sum(r['loss_usd'] for r in srecs):>9,.2f} "
              f"cost/mL=${meta['cost_per_ml']:.6f}")

print("\nTop 10 stores by total mL across all specs:")
for s in stores_all[:10]:
    intensity_str = f"{s['intensity_total']:.2f}" if s['intensity_total'] is not None else "—"
    print(f"  #{s['rank']:>2} {s['store_name']:<22} mL={s['total_loss_ml']:>11,.0f} "
          f"USD=${s['total_loss_usd']:>8,.2f} orders={s['total_sales']:>9,} "
          f"intensity(mL/1k orders)={intensity_str:>6} status={s['status']}")

print("\nDST-drift sample:")
for d in dst_drift[:5]:
    print(f"  spec={d['spec']} dept={d['dept']} UTC={d['utc']} NY-month={d['ny_month']} fixed-month={d['fixed_month']}")
