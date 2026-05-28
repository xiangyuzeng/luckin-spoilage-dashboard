"""V3 dashboard builder — consumes output/dashboard_payload.json (44-SKU edition).

New vs v2:
- 44 SKUs across 9 categories (was 4 milk variants).
- Spec dropdown grouped via <optgroup>; SKUs with zero records appear greyed.
- ALL view: USD-only metric, stacked by category (9 colors), not by SKU.
- Per-spec view: native unit (mL / g / 个) from payload meta.
- Category-level drilling: a "category" pseudo-spec rolls up SKUs within a cat.
- Per-category color palette (HSL family per category).
"""
import json, os

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT_DIR = os.path.join(REPO_ROOT, "output")
DOCS_DATA = os.path.join(REPO_ROOT, "docs", "data")

with open(os.path.join(OUT_DIR, "dashboard_payload.json"), encoding="utf-8") as f:
    payload = json.load(f)

# Best-effort build_meta injection (refresh.sh writes this after build).
_build_meta_path = os.path.join(DOCS_DATA, "build_meta.json")
if os.path.exists(_build_meta_path):
    try:
        payload["meta"]["build_meta"] = json.load(open(_build_meta_path, encoding="utf-8"))
    except Exception:
        pass

HTML_TEMPLATE = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=1200,initial-scale=1">
<title>门店物料过期销毁损耗分析看板</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  :root {
    --primary:#0365C0; --navy:#1A365D; --teal:#00A5A5; --gold:#DCBD23;
    --red:#C0392B; --amber:#E67E22; --green:#27AE60;
    --bg:#F5F7FB; --card:#fff; --ink:#1F2937; --muted:#6B7280; --line:#E5E7EB;
  }
  * { box-sizing:border-box; }
  html,body { margin:0; padding:0; background:var(--bg); color:var(--ink);
    font-family:Arial,"Helvetica Neue",Helvetica,"PingFang SC","Microsoft YaHei",sans-serif; }
  header.bar { background:linear-gradient(135deg,var(--primary),var(--navy)); color:#fff;
    padding:22px 28px; display:flex; justify-content:space-between; align-items:center; box-shadow:0 2px 8px rgba(0,0,0,.08); }
  header.bar h1 { margin:0; font-size:22px; letter-spacing:.5px; }
  header.bar .sub { margin-top:6px; font-size:13px; opacity:.92; }
  .pill { display:inline-block; padding:4px 10px; border-radius:999px; font-size:12px; font-weight:700; }
  .pill.pass { background:var(--green); color:#fff; }
  .pill.fail { background:var(--red); color:#fff; }
  .pill.info { background:rgba(255,255,255,.18); color:#fff; margin-right:6px; }

  .toolbar { position:sticky; top:0; z-index:50; background:#fff; border-bottom:1px solid var(--line);
    padding:12px 28px; display:flex; flex-wrap:wrap; gap:14px; align-items:center; box-shadow:0 1px 3px rgba(0,0,0,.04); }
  .toolbar label { font-size:12px; color:var(--muted); margin-right:4px; }
  .toolbar select, .toolbar button {
    font-size:13px; padding:6px 10px; border:1px solid var(--line); border-radius:6px; background:#fff; color:var(--ink); }
  .toolbar button { background:var(--primary); color:#fff; border-color:var(--primary); cursor:pointer; }
  .toolbar button:hover { filter:brightness(1.05); }
  .toolbar .group { display:flex; gap:6px; align-items:center; padding:4px 8px; background:var(--bg); border-radius:6px; }
  .toolbar .group label { margin-right:0; }
  .toolbar select option:disabled { color:#9aa0a6; font-style:italic; }
  .metric-note { font-size:11px; color:var(--muted); margin-left:6px; max-width:260px; line-height:1.4; }
  .gran-loading { font-size:11px; color:var(--primary); margin-left:6px; }
  .axis-warn { font-size:11px; color:var(--amber); margin-left:6px; }

  main { padding:22px 28px 60px; }
  section { background:var(--card); border-radius:12px; box-shadow:0 2px 6px rgba(0,0,0,.04); padding:20px 22px; margin-bottom:22px; }
  section h2 { margin:0 0 14px; font-size:16px; color:var(--navy); display:flex; align-items:center; gap:10px; }
  section h2 .tag { font-size:11px; background:var(--bg); color:var(--muted); padding:2px 8px; border-radius:999px; }
  .note { font-size:12px; color:var(--muted); margin-top:8px; }

  .kpis { display:grid; grid-template-columns:repeat(7,1fr); gap:14px; }
  @media (max-width:1180px) { .kpis { grid-template-columns:repeat(4,1fr); } }
  .kpi { background:#fff; border:1px solid var(--line); border-radius:10px; padding:14px; }
  .kpi .label { font-size:12px; color:var(--muted); }
  .kpi .value { font-size:22px; font-weight:700; color:var(--navy); margin-top:4px; }
  .kpi .sub { font-size:11px; color:var(--muted); margin-top:4px; }
  .kpi.accent .value { color:var(--primary); }

  .alert-strip { display:flex; gap:12px; flex-wrap:wrap; }
  .alert-card { padding:12px 14px; border-radius:10px; border-left:4px solid; background:#FFFBF1; flex:1 1 320px; }
  .alert-card.s-yc { border-left-color:var(--red); background:#FDECEA; }
  .alert-card.s-xz { border-left-color:var(--amber); background:#FFF6E5; }
  .alert-card .title { font-weight:700; color:var(--navy); }
  .alert-card .why { font-size:12px; color:var(--muted); margin-top:4px; }

  .chart-wrap { position:relative; height:380px; }
  .chart-wrap.tall { height:560px; }

  .empty-state { padding:60px 20px; text-align:center; color:var(--muted); font-size:14px;
    background:repeating-linear-gradient(45deg,#FAFBFE,#FAFBFE 10px,#F2F4F8 10px,#F2F4F8 20px);
    border-radius:8px; border:1px dashed var(--line); }

  table.league { width:100%; border-collapse:collapse; font-size:13px; }
  table.league th, table.league td { padding:10px 8px; border-bottom:1px solid var(--line); text-align:right; }
  table.league th:first-child, table.league td:first-child,
  table.league th:nth-child(2), table.league td:nth-child(2),
  table.league th:nth-child(3), table.league td:nth-child(3) { text-align:left; }
  table.league th { color:var(--muted); font-weight:600; cursor:pointer; user-select:none; background:#FAFBFE; }
  table.league th:hover { color:var(--primary); }
  table.league tr.outlier td { background:#FDECEA; }
  table.league tr.attn td { background:#FFF6E5; }
  table.league tr:hover td { background:#EEF4FB; }
  .status-pill { display:inline-block; padding:2px 8px; font-size:11px; border-radius:999px; font-weight:700; color:#fff; }
  .status-pill.s-yc { background:var(--red); }
  .status-pill.s-xz { background:var(--amber); }
  .status-pill.s-zc { background:var(--green); }
  .sparkline { display:inline-block; vertical-align:middle; }

  table.heatmap { border-collapse:collapse; font-size:12px; }
  table.heatmap th, table.heatmap td { padding:6px 10px; border:1px solid var(--line); text-align:right; }
  table.heatmap th { background:#FAFBFE; color:var(--muted); font-weight:600; }
  table.heatmap th:first-child, table.heatmap td:first-child { text-align:left; }
  table.heatmap tr.total td, table.heatmap td.total { font-weight:700; }
  .legend { display:flex; align-items:center; gap:8px; font-size:12px; color:var(--muted); margin-top:10px; }
  .legend .swatch { width:80px; height:12px; border-radius:3px; background:linear-gradient(90deg,#EAF2FB,#0365C0); }

  .drill-grid { display:grid; grid-template-columns:1fr 1fr; gap:18px; }
  .drill-grid .panel { border:1px solid var(--line); border-radius:10px; padding:14px; }
  .drill-grid h3 { margin:0 0 8px; font-size:14px; color:var(--navy); }
  .drill-kpis { display:grid; grid-template-columns:repeat(3,1fr); gap:10px; }
  .drill-kpis .kpi { padding:10px; }
  .drill-kpis .kpi .value { font-size:18px; }
  .op-table { width:100%; border-collapse:collapse; font-size:12px; margin-top:8px; }
  .op-table th, .op-table td { padding:6px 8px; border-bottom:1px solid var(--line); text-align:right; }
  .op-table th:first-child, .op-table td:first-child { text-align:left; }

  footer { color:var(--muted); font-size:12px; padding:14px 28px 40px; line-height:1.6; }

  @media print {
    @page { size:Letter landscape; margin:.4in; }
    body { background:#fff; }
    .toolbar { display:none; }
    section { box-shadow:none; border:1px solid var(--line); page-break-inside:avoid; }
    .chart-wrap { height:300px; }
    .chart-wrap.tall { height:500px; }
    header.bar { background:var(--primary) !important; -webkit-print-color-adjust:exact; print-color-adjust:exact; }
    .status-pill,.pill { -webkit-print-color-adjust:exact; print-color-adjust:exact; }
  }
</style>
</head>
<body>
<header class="bar">
  <div>
    <h1>Luckin USA 物料过期销毁损耗分析看板</h1>
    <div class="sub">
      <span id="hdrSpec"></span> · <span id="hdrPeriod"></span> ·
      <span class="pill info" id="tzBadge"></span>
      <span class="pill info" id="usdBadge">USD 成本已计入</span>
      <span class="pill info" id="intBadge">含销量参考</span>
    </div>
  </div>
  <div><span id="reconPill" class="pill pass">对账 PASS</span></div>
</header>

<div class="toolbar">
  <div class="group">
    <label>规格</label>
    <select id="fSpec"></select>
  </div>
  <div class="group">
    <label>指标</label>
    <select id="fMetric">
      <option value="usd">报损金额 (USD)</option>
      <option value="qty">报损量 (单位随规格)</option>
      <option value="intensity">损耗强度 (USD / 1k 单)</option>
    </select>
    <span id="metricNote" class="metric-note"></span>
  </div>
  <div class="group">
    <label>时间粒度</label>
    <select id="fGran">
      <option value="month">月</option>
      <option value="week">周</option>
      <option value="day">天</option>
    </select>
    <span id="granLoading" class="gran-loading"></span>
  </div>
  <div><label>起</label><select id="fMonthFrom"></select></div>
  <div><label>止</label><select id="fMonthTo"></select></div>
  <div><label>门店</label><select id="fStore"></select></div>
  <div><label>排序</label>
    <select id="fSort">
      <option value="metric_desc">按当前指标（高→低）</option>
      <option value="metric_asc">按当前指标（低→高）</option>
      <option value="latest_desc">按最新期</option>
      <option value="mom_desc">按最新期环比</option>
    </select>
  </div>
  <span id="axisWarn" class="axis-warn"></span>
  <button id="btnExportCsv">导出当前 CSV</button>
  <button id="btnPrint">打印 / 导出 PDF</button>
</div>

<main>
  <section id="secKpi"><h2>关键指标 <span class="tag" id="kpiScope"></span></h2>
    <div class="kpis" id="kpiGrid"></div>
  </section>

  <section id="secAlerts" style="display:none"><h2>需关注门店</h2>
    <div class="alert-strip" id="alertStrip"></div>
  </section>

  <section id="secRank"><h2>门店损耗排名 <span class="tag">主图</span></h2>
    <div id="rankBody"><div class="chart-wrap tall"><canvas id="chartRank"></canvas></div></div>
    <div class="note" id="rankCaveat"></div>
  </section>

  <section id="secPareto"><h2>门店损耗帕累托（累计占比）</h2>
    <div id="paretoBody"><div class="chart-wrap"><canvas id="chartPareto"></canvas></div></div>
  </section>

  <section id="secSpecMix"><h2 id="specMixTitle">门店 × 品类 构成</h2>
    <div id="specMixBody"><div class="chart-wrap"><canvas id="chartSpecMix"></canvas></div></div>
    <div class="note" id="specMixNote">堆叠条形图：每家门店的 USD 损耗按品类（奶/咖啡豆/糖浆/烘焙/…）拆分，识别哪些品类驱动门店总损耗。选择单一规格时仅显示该规格的损耗。</div>
  </section>

  <section id="secLeague"><h2>门店对标榜单</h2>
    <div id="leagueBody" style="overflow-x:auto"><table class="league" id="tblLeague"></table></div>
  </section>

  <section id="secTrend"><h2>月度趋势</h2>
    <div id="trendBody"><div class="chart-wrap"><canvas id="chartTrend"></canvas></div></div>
  </section>

  <section id="secHeat"><h2>门店 × 月份 热力矩阵</h2>
    <div id="heatBody" style="overflow-x:auto"><div id="heatWrap"></div></div>
    <div class="legend"><span>低</span><span class="swatch"></span><span>高（颜色越深表示损耗越大；·=该月未开业或为零）</span></div>
  </section>

  <section id="secNonStore"><h2>非门店调整记录 <span class="tag">参考</span></h2>
    <div class="note">下列为后台/总部部门的库存调整，不计入门店损耗排名。</div>
    <div style="overflow-x:auto" id="nonStoreWrap"></div>
  </section>

  <section id="secDrill"><h2>门店明细 <span class="tag" id="drillStoreLabel"></span></h2>
    <div class="drill-grid">
      <div class="panel">
        <h3>门店关键指标</h3>
        <div class="drill-kpis" id="drillKpis"></div>
        <div class="note" id="drillNote"></div>
      </div>
      <div class="panel">
        <h3>月度报损</h3>
        <div class="chart-wrap" style="height:280px"><canvas id="chartDrillMonthly"></canvas></div>
      </div>
      <div class="panel">
        <h3 id="drillSpecTitle">品类构成</h3>
        <div class="chart-wrap" style="height:240px"><canvas id="chartDrillSpec"></canvas></div>
      </div>
      <div class="panel">
        <h3>操作人构成</h3>
        <table class="op-table" id="tblOperators"></table>
      </div>
    </div>
  </section>
</main>

<footer>
  数据来源：直接读取 SCM 源库 <code>luckyus_scm_shopstock.t_shop_spec_stock_change_record</code>
  （tenant=LKUS，specific_reason_code=015「过期销毁」）；
  规格、单位、成本来自 <code>t_mdm_goods_spec</code> + <code>t_goods_spec_cost_detail</code>；
  门店主数据来自 <code>luckyus_opshop.t_shop_info</code>；
  销量参考来自 <code>luckyus_sales_order.t_order_store_fact</code>（hourly→月汇总）。<br>
  说明：单位非统一（mL / g / 个），跨规格比较默认采用 USD 金额。<br>
  周期：<span id="ftrPeriod"></span> · 生成日期：<span id="ftrGen"></span> ·
  时区：<span id="ftrTz"></span> · DST drift: <span id="ftrDst"></span> 行 ·
  对账状态：<span id="ftrRecon"></span><br>
  自动刷新：<span id="ftrBuild">—</span><br>
  本看板为只读分析，未修改任何源数据。
</footer>

<script>
const DATA = __PAYLOAD__;

const fmtN = (v, dp=1) => (v==null || isNaN(v)) ? "—" :
  v.toLocaleString("en-US", {minimumFractionDigits:dp, maximumFractionDigits:dp});
const fmt0 = v => fmtN(v, 0);
const fmtUsd = v => "$" + fmtN(v, 2);
const fmtPct = (v, dp=1) => (v==null || isNaN(v)) ? "—" : (v>=0?"+":"") + v.toFixed(dp) + "%";
const fmtPctU = (v, dp=1) => (v==null || isNaN(v)) ? "—" : v.toFixed(dp) + "%";
const PALETTE = { primary:"#0365C0", navy:"#1A365D", teal:"#00A5A5", gold:"#DCBD23",
                  red:"#C0392B", amber:"#E67E22", green:"#27AE60" };
const STATUS_COLOR = {"异常":PALETTE.red, "需关注":PALETTE.amber, "正常":PALETTE.primary};
const STATUS_CLASS = {"异常":"s-yc", "需关注":"s-xz", "正常":"s-zc"};

// Category base hues (HSL). Within each category, SKUs get a lightness fan.
const CATEGORY_HUE = {
  dairy:     {h:210, s:65},   // blue family — milk
  coffee:    {h: 25, s:55},   // brown family — coffee beans
  bakery:    {h: 40, s:75},   // gold family — bakery
  syrup:     {h:330, s:60},   // pink/magenta — syrups
  sauce:     {h: 15, s:65},   // red-orange — sauces
  powder:    {h:160, s:50},   // teal-green — powders
  seasoning: {h:280, s:45},   // purple — seasoning
  beverage:  {h:190, s:65},   // cyan — beverages
  other:     {h:  0, s: 0},   // grey — other
};

// Per-spec color: hue from category, lightness fanned by SKU index within category.
const SPEC_COLORS = (() => {
  const out = {}; const byCat = {};
  DATA.meta.specs.forEach(sp => {
    (byCat[sp.cat] = byCat[sp.cat] || []).push(sp.mid);
  });
  Object.entries(byCat).forEach(([cat, list]) => {
    const base = CATEGORY_HUE[cat] || CATEGORY_HUE.other;
    list.forEach((mid, i) => {
      const span = list.length > 1 ? (60 / (list.length - 1)) : 0;
      const l = 35 + (i * span);  // 35% → 95% lightness fan
      out[mid] = `hsl(${base.h}, ${base.s}%, ${Math.min(l, 70)}%)`;
    });
  });
  return out;
})();
const CATEGORY_COLORS = Object.fromEntries(Object.entries(CATEGORY_HUE).map(([k,v]) => [k, `hsl(${v.h}, ${v.s}%, 45%)`]));

const SPECS_BY_MID = Object.fromEntries(DATA.meta.specs.map(sp => [sp.mid, sp]));
const SPEC_IDX_BY_MID = Object.fromEntries(DATA.meta.specs.map((sp, i) => [sp.mid, i]));

const state = {
  spec: "ALL",
  metric: "usd",
  gran: "month",
  monthFrom: DATA.meta.months[0],
  monthTo:   DATA.meta.months[DATA.meta.months.length - 1],
  selectedStore: null,
  sort: "metric_desc",
};

// ============================================================================
// Granularity layer — month is the default and uses the precomputed payload
// arrays directly (no fetch). Week/day lazy-load data/events.json on first
// switch and derive bucketed series from it. All caches keyed by gran are
// memoized; cleared if EVENTS reloads.
// ============================================================================

let EVENTS = null;                 // { stores_index, rows: [[date,store,spec,usd,qty], ...] }
let storeIdxByKey = null;          // "dept_id|shop_no" → idx into EVENTS.stores_index
const _allBucketsCache = {};       // gran → sorted bucket list (string)
const _seriesCache = new Map();    // key: "slice|storeIdx|gran|metric" → series aligned to _allBucketsCache[gran]
const _eventsLoadPromise = { value: null };

function clearSeriesCache() { _seriesCache.clear(); for (const k of Object.keys(_allBucketsCache)) delete _allBucketsCache[k]; }

// ISO 8601 week key for a "YYYY-MM-DD" date.
function isoWeekKey(date) {
  const [y, m, d] = date.split("-").map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d));
  const dow = (dt.getUTCDay() + 6) % 7;  // Mon=0..Sun=6
  dt.setUTCDate(dt.getUTCDate() - dow + 3);  // Thursday of current week
  const isoYear = dt.getUTCFullYear();
  const jan4 = new Date(Date.UTC(isoYear, 0, 4));
  const jan4Dow = (jan4.getUTCDay() + 6) % 7;
  jan4.setUTCDate(jan4.getUTCDate() - jan4Dow + 3);  // Thursday of week 1
  const weekNum = 1 + Math.round((dt - jan4) / (7 * 86400000));
  return `${isoYear}-W${String(weekNum).padStart(2, "0")}`;
}
// Inverse: Monday of a "YYYY-Www" key → "YYYY-MM-DD".
function isoWeekMonday(weekKey) {
  const m = /^(\d{4})-W(\d{2})$/.exec(weekKey);
  if (!m) return null;
  const isoYear = +m[1], weekNum = +m[2];
  const jan4 = new Date(Date.UTC(isoYear, 0, 4));
  const jan4Dow = (jan4.getUTCDay() + 6) % 7;
  const mondayWeek1 = new Date(jan4);
  mondayWeek1.setUTCDate(jan4.getUTCDate() - jan4Dow);
  const monday = new Date(mondayWeek1);
  monday.setUTCDate(mondayWeek1.getUTCDate() + (weekNum - 1) * 7);
  return monday.toISOString().slice(0, 10);
}
function isoWeekRangeLabel(weekKey) {
  const mon = isoWeekMonday(weekKey);
  if (!mon) return weekKey;
  const monDt = new Date(mon + "T00:00:00Z");
  const sunDt = new Date(monDt);
  sunDt.setUTCDate(monDt.getUTCDate() + 6);
  return `${monDt.toISOString().slice(5,10)}–${sunDt.toISOString().slice(5,10)}`;
}
function dateToBucket(date, gran) {
  if (gran === "day") return date;
  if (gran === "month") return date.slice(0, 7);
  return isoWeekKey(date);
}
// All bucket keys present in the dataset for a given granularity, sorted lexicographically.
function getAllBuckets(gran) {
  if (gran === "month") return DATA.meta.months;
  if (_allBucketsCache[gran]) return _allBucketsCache[gran];
  if (!EVENTS) return DATA.meta.months;
  const set = new Set();
  for (const r of EVENTS.rows) set.add(dateToBucket(r[0], gran));
  const list = [...set].sort();
  _allBucketsCache[gran] = list;
  return list;
}
function bucketLabel(key, gran) {
  if (gran === "week") return `${key.slice(0,4)}-${key.slice(5)} (${isoWeekRangeLabel(key)})`;
  return key;
}
function bucketShort(key, gran) {
  if (gran === "week") return key.slice(0,4) + "-" + key.slice(5);  // YYYY-Wxx
  return key;
}

// Memoized series builder: returns an array aligned to getAllBuckets(gran).
// storeIdx === null → sum across all stores. slice is "ALL" | "CAT:<id>" | "<spec_mid>".
function seriesFor(slice, storeIdx, gran, metric) {
  const k = `${slice}|${storeIdx === null ? "_" : storeIdx}|${gran}|${metric}`;
  if (_seriesCache.has(k)) return _seriesCache.get(k);
  const buckets = getAllBuckets(gran);
  const idxOf = Object.fromEntries(buckets.map((b, i) => [b, i]));
  const series = new Array(buckets.length).fill(0);
  if (!EVENTS) { _seriesCache.set(k, series); return series; }
  let specPred;
  if (slice === "ALL") {
    specPred = () => true;
  } else if (slice.startsWith("CAT:")) {
    const cat = slice.slice(4);
    specPred = sp => DATA.meta.specs[sp]?.cat === cat;
  } else {
    const target = SPEC_IDX_BY_MID[slice];
    if (target === undefined) { _seriesCache.set(k, series); return series; }
    specPred = sp => sp === target;
  }
  const useQty = metric === "qty";
  for (const r of EVENTS.rows) {
    const s = r[1], sp = r[2];
    if (storeIdx !== null && s !== storeIdx) continue;
    if (!specPred(sp)) continue;
    const b = dateToBucket(r[0], gran);
    const i = idxOf[b];
    if (i === undefined) continue;
    series[i] += useQty ? r[4] : r[3];
  }
  _seriesCache.set(k, series);
  return series;
}

// Fetch events.json once. Promise-memoized so concurrent gran switches share one fetch.
function ensureEvents() {
  if (EVENTS) return Promise.resolve(EVENTS);
  if (_eventsLoadPromise.value) return _eventsLoadPromise.value;
  const note = document.getElementById("granLoading");
  if (note) note.textContent = "正在加载事件级数据…";
  _eventsLoadPromise.value = fetch("data/events.json", { cache: "force-cache" })
    .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
    .then(json => {
      EVENTS = json;
      storeIdxByKey = {};
      EVENTS.stores_index.forEach((s, i) => { storeIdxByKey[`${s.dept_id}|${s.shop_no}`] = i; });
      // Live reconciliation against payload — month totals must agree.
      const monthIdx = Object.fromEntries(DATA.meta.months.map((m, i) => [m, i]));
      const ev = new Array(DATA.meta.months.length).fill(0);
      EVENTS.rows.forEach(r => { const i = monthIdx[r[0].slice(0, 7)]; if (i !== undefined) ev[i] += r[3]; });
      DATA.meta.system_monthly_usd.forEach((v, i) => {
        if (Math.abs(v - ev[i]) > 0.05) {
          console.warn(`events reconciliation: month ${DATA.meta.months[i]}: events=$${ev[i].toFixed(2)} payload=$${v.toFixed(2)}`);
        }
      });
      if (note) note.textContent = "";
      return EVENTS;
    })
    .catch(err => {
      console.error("events.json fetch failed:", err);
      if (note) note.textContent = "事件数据加载失败，已回退到月维度";
      state.gran = "month";
      const fG = document.getElementById("fGran");
      if (fG) fG.value = "month";
      throw err;
    });
  return _eventsLoadPromise.value;
}

// Active axis domain for current granularity.
function axisDomain() { return getAllBuckets(state.gran); }

// Default time window when switching granularity (avoid 365-bar charts).
function defaultWindowForGran(gran) {
  const domain = gran === "month" ? DATA.meta.months : getAllBuckets(gran);
  if (!domain.length) return [DATA.meta.months[0], DATA.meta.months.at(-1)];
  if (gran === "month") return [domain[0], domain.at(-1)];
  if (gran === "week") return [domain[Math.max(0, domain.length - 16)], domain.at(-1)];
  return [domain[Math.max(0, domain.length - 30)], domain.at(-1)];  // day
}
function clampToDomain(b, domain, fallback) {
  return domain.includes(b) ? b : fallback;
}

// Human-readable granularity label.
function granLabelCn() { return state.gran === "month" ? "月" : (state.gran === "week" ? "周" : "天"); }
// "12 个月" but "16 周" / "30 天" — 周/天 already function as measure words.
function granCountLabel(n) {
  if (state.gran === "month") return `${n} 个月`;
  return `${n} ${granLabelCn()}`;
}
function periodOverPeriodLabel() {
  return state.gran === "month" ? "环比" : (state.gran === "week" ? "周环比" : "日环比");
}

const storeKey = s => `${s.dept_id}|${s.shop_no}`;

function currentSpec() {
  if (state.spec === "ALL") return null;
  if (state.spec.startsWith("CAT:")) return null;
  return SPECS_BY_MID[state.spec] || null;
}
function currentCategory() {
  return state.spec.startsWith("CAT:") ? state.spec.slice(4) : null;
}

// Pick dataset based on spec selection.
function activeStoresAll() {
  if (state.spec === "ALL") return DATA.stores_all;
  if (state.spec.startsWith("CAT:")) {
    const cat = state.spec.slice(4);
    return DATA.stores_by_cat[cat] || [];
  }
  return DATA.stores_by_spec[state.spec] || [];
}

// effectiveMetric enforces two constraints:
//   1. ALL / category views can only use USD (units mix across SKUs) — qty → usd.
//   2. Intensity requires monthly sales as denominator (not available sub-month) —
//      intensity → usd when gran != month, with a UI note set elsewhere.
function effectiveMetric() {
  let m = state.metric;
  if (m === "qty" && (state.spec === "ALL" || state.spec.startsWith("CAT:"))) m = "usd";
  if (m === "intensity" && state.gran !== "month") m = "usd";
  return m;
}

// monthlyArr returns the FULL-domain series for store s, aligned to:
//   - DATA.meta.months when gran === "month"
//   - getAllBuckets(state.gran) otherwise (derived from EVENTS.rows)
// Month path stays on precomputed payload arrays — instant, no fetch.
function monthlyArr(s) {
  const m = effectiveMetric();
  if (state.gran === "month") {
    if (m === "usd") return s.monthly_usd || [];
    if (m === "intensity") return s.intensity_monthly || [];
    return s.monthly_qty || s.monthly_usd || [];
  }
  // week / day — derive from EVENTS for the active spec slice.
  if (!EVENTS || !storeIdxByKey) return [];
  const sidx = storeIdxByKey[`${s.dept_id}|${s.shop_no}`];
  if (sidx === undefined) return [];
  return seriesFor(state.spec, sidx, state.gran, m);
}
function totalValue(s) {
  const m = effectiveMetric();
  if (m === "usd") return s.total_loss_usd || 0;
  if (m === "intensity") return s.intensity_total || 0;
  return s.total_loss_qty || s.total_loss_usd || 0;
}

function metricLabel() {
  const m = effectiveMetric();
  if (m === "usd") return "报损金额 (USD)";
  if (m === "intensity")
    return state.spec === "ALL" || state.spec.startsWith("CAT:")
      ? "损耗强度 (USD/千单)" : "损耗强度 (mL or g per 1k orders)";
  const sp = currentSpec();
  const u = sp?.unit_label || "qty";
  return `报损量 (${u})`;
}
function metricFmt(v) {
  if (v == null || isNaN(v)) return "—";
  const m = effectiveMetric();
  if (m === "usd") return fmtUsd(v);
  if (m === "intensity") return fmtN(v, 1);
  return fmtN(v, 0);
}
function metricUnit() {
  const m = effectiveMetric();
  if (m === "usd") return "USD";
  if (m === "intensity") return state.spec === "ALL" || state.spec.startsWith("CAT:") ? "USD/千单" : "qty/千单";
  const sp = currentSpec();
  return sp?.unit_label || "qty";
}

function initToolbar() {
  const fSpec = document.getElementById("fSpec");
  // Grouped <optgroup> per category
  const byCat = {};
  DATA.meta.specs.forEach(sp => (byCat[sp.cat] = byCat[sp.cat] || []).push(sp));
  let html = `<option value="ALL">全部规格（USD 合计）</option>`;
  DATA.meta.categories.forEach(({id, label}) => {
    const list = byCat[id] || [];
    if (!list.length) return;
    html += `<optgroup label="${label}（${list.length} 个）">`;
    html += `<option value="CAT:${id}">▣ ${label} · 整品类合计</option>`;
    list.forEach(sp => {
      const empty = !sp.has_data;
      const tag = empty ? "（暂无数据）" : "";
      html += `<option value="${sp.mid}" ${empty ? "disabled" : ""}>${sp.label_cn}（${sp.mid}）${tag}</option>`;
    });
    html += `</optgroup>`;
  });
  fSpec.innerHTML = html;
  fSpec.value = state.spec;
  fSpec.onchange = () => { state.spec = fSpec.value; state.selectedStore = null;
    document.getElementById("fStore").value = ""; render(); };

  const fMet = document.getElementById("fMetric");
  fMet.value = state.metric;
  fMet.onchange = () => { state.metric = fMet.value; render(); };

  const fMF = document.getElementById("fMonthFrom");
  const fMT = document.getElementById("fMonthTo");
  // Populate from/to from the active axis domain. Called again when gran changes.
  function repopulateWindow() {
    const domain = axisDomain();
    if (!domain.length) return;
    const opts = domain.map(b => `<option value="${b}">${state.gran === "week" ? bucketLabel(b, "week") : b}</option>`).join("");
    fMF.innerHTML = opts;
    fMT.innerHTML = opts;
    state.monthFrom = clampToDomain(state.monthFrom, domain, domain[0]);
    state.monthTo   = clampToDomain(state.monthTo,   domain, domain.at(-1));
    fMF.value = state.monthFrom;
    fMT.value = state.monthTo;
  }
  repopulateWindow();
  fMF.onchange = () => { state.monthFrom = fMF.value; render(); };
  fMT.onchange = () => { state.monthTo = fMT.value; render(); };

  const fGran = document.getElementById("fGran");
  fGran.value = state.gran;
  fGran.onchange = async () => {
    const prev = state.gran;
    const next = fGran.value;
    if (prev === next) return;
    // Optimistic UI: if next != month and EVENTS not loaded, fetch first.
    if (next !== "month") {
      try { await ensureEvents(); }
      catch { fGran.value = "month"; return; }
    }
    state.gran = next;
    // Reset window to a sensible default for the new granularity.
    const [f, t] = defaultWindowForGran(next);
    state.monthFrom = f; state.monthTo = t;
    // If intensity was selected, fall back to USD with a note (effectiveMetric handles it).
    repopulateWindow();
    updateMetricAvailability();
    render();
  };

  const fS = document.getElementById("fStore");
  fS.innerHTML = `<option value="">（全部 / 系统视图）</option>` +
    DATA.stores_all.map(s => `<option value="${storeKey(s)}">${s.store_name} (${s.shop_no})</option>`).join("");
  fS.onchange = () => { state.selectedStore = fS.value || null; render(); };

  document.getElementById("fSort").onchange = (e) => { state.sort = e.target.value; render(); };
  document.getElementById("btnPrint").onclick = () => window.print();
  document.getElementById("btnExportCsv").onclick = exportCurrentCsv;
}

// Window-filtered buckets in the ACTIVE axis (month/week/day).
function activeMonths() { return activeBuckets(); }
function activeBuckets() {
  const all = axisDomain();
  let i1 = all.indexOf(state.monthFrom);
  let i2 = all.indexOf(state.monthTo);
  if (i1 < 0) i1 = 0;
  if (i2 < 0) i2 = all.length - 1;
  return all.slice(Math.min(i1, i2), Math.max(i1, i2) + 1);
}

// Sync the metric dropdown's disabled state + inline note when gran changes.
function updateMetricAvailability() {
  const fMet = document.getElementById("fMetric");
  if (!fMet) return;
  const intensityOpt = fMet.querySelector('option[value="intensity"]');
  const note = document.getElementById("metricNote");
  const monthOnly = state.gran !== "month";
  if (intensityOpt) intensityOpt.disabled = monthOnly;
  if (note) note.textContent = monthOnly && state.metric === "intensity"
    ? "损耗强度需月度销量分母，仅月维度可用 — 已回退到 USD"
    : (monthOnly ? "（损耗强度仅月维度可用）" : "");
}

function storeView(s, months) {
  const domain = axisDomain();
  const idx = months.map(m => domain.indexOf(m));
  const arr = monthlyArr(s);
  const mView = idx.map(i => i >= 0 ? (arr[i] || 0) : 0);
  const total = mView.reduce((a,b)=>a+b, 0);
  let lastIdx = -1;
  for (let i = mView.length - 1; i >= 0; i--) if (mView[i] > 0) { lastIdx = i; break; }
  let latestMom = null, latestValue = 0;
  if (lastIdx >= 0) {
    latestValue = mView[lastIdx];
    if (lastIdx >= 1 && mView[lastIdx-1] > 0) {
      latestMom = (latestValue - mView[lastIdx-1]) / mView[lastIdx-1] * 100;
    }
  }
  const active = mView.filter(v => v > 0).length;
  return Object.assign({}, s, {
    monthly_view: mView,
    total_view: total,
    active_view: active,
    latest_view: latestValue,
    latest_mom_view: latestMom,
    last_active_idx_view: lastIdx,
  });
}

function sortStores(stores) {
  const cmp = {
    metric_desc: (a,b) => b.total_view - a.total_view,
    metric_asc:  (a,b) => a.total_view - b.total_view,
    latest_desc: (a,b) => b.latest_view - a.latest_view,
    mom_desc:    (a,b) => (b.latest_mom_view ?? -Infinity) - (a.latest_mom_view ?? -Infinity),
  };
  return stores.slice().sort(cmp[state.sort] || cmp.metric_desc);
}

let chartRank, chartPareto, chartSpecMix, chartTrend, chartDrillMonthly, chartDrillSpec;

function showEmpty(targetSelector, html) {
  const el = document.querySelector(targetSelector);
  if (el) el.innerHTML = `<div class="empty-state">${html}</div>`;
}
function restoreCanvas(targetSelector, canvasHtml) {
  const el = document.querySelector(targetSelector);
  if (el && !el.querySelector("canvas")) el.innerHTML = canvasHtml;
}

function renderKpis(months, stores) {
  const domain = axisDomain();
  const sysTotal = stores.reduce((a,s)=>a + s.total_view, 0);
  const recCount = stores.reduce((a,s)=>a + s.record_count, 0);
  const mean = stores.length ? sysTotal / stores.length : 0;
  const top = stores.slice().sort((a,b)=>b.total_view - a.total_view)[0];
  let latestMom = null;
  if (months.length >= 2) {
    const sysM = months.map(m => stores.reduce((a,s)=>a + (monthlyArr(s)[domain.indexOf(m)]||0), 0));
    const prev = sysM[sysM.length - 2], cur = sysM[sysM.length - 1];
    if (prev) latestMom = (cur - prev) / prev * 100;
  }
  let scope;
  if (state.spec === "ALL") scope = "全部规格";
  else if (state.spec.startsWith("CAT:")) {
    const cat = DATA.meta.categories.find(c => c.id === state.spec.slice(4));
    scope = cat ? cat.label : state.spec;
  } else {
    const sp = currentSpec();
    scope = sp ? `${sp.label_cn}（${sp.mid}）` : state.spec;
  }
  document.getElementById("kpiScope").textContent =
    `${scope} · ${months[0]} → ${months[months.length-1]} · 粒度：${granLabelCn()} · 指标：${metricLabel()}`;
  const cells = [
    {label:"系统总" + metricLabel(), value: metricFmt(sysTotal), sub:"单位：" + metricUnit()},
    {label:"覆盖门店数", value: stores.length, sub:`记录数 ${recCount}`},
    {label:"店均", value: metricFmt(mean), sub:"= 系统总 / 门店数"},
    {label:"最高门店", value: top ? top.store_name : "—",
      sub: top ? `${metricFmt(top.total_view)} · 占 ${fmtPctU(sysTotal ? top.total_view/sysTotal*100 : 0)}` : "",
      accent: true},
    {label:"统计周期", value: `${months[0]} → ${months[months.length-1]}`, sub: granCountLabel(months.length)},
    {label:"过期销毁记录数", value: recCount, sub:"reason = 015"},
    {label:"系统最新" + periodOverPeriodLabel(), value: fmtPct(latestMom), sub: months[months.length-1] || ""},
  ];
  document.getElementById("kpiGrid").innerHTML = cells.map(c => `
    <div class="kpi ${c.accent ? "accent" : ""}">
      <div class="label">${c.label}</div>
      <div class="value">${c.value}</div>
      <div class="sub">${c.sub || ""}</div>
    </div>`).join("");
}

function renderAlerts(stores) {
  const flagged = stores.filter(s => s.status && s.status !== "正常");
  const sec = document.getElementById("secAlerts");
  if (!flagged.length) { sec.style.display = "none"; return; }
  sec.style.display = "";
  document.getElementById("alertStrip").innerHTML = flagged.map(s => {
    const reason = s.status === "异常"
      ? `统计离群：总量 ${metricFmt(s.total_view)}（z=${(s.z_score??0).toFixed(2)}）`
      : `最新${periodOverPeriodLabel()} ${fmtPct(s.latest_mom_view ?? s.latest_mom_pct)}，且总量高于中位数`;
    const cls = STATUS_CLASS[s.status];
    return `<div class="alert-card ${cls}">
      <div class="title">${s.store_name} <span class="status-pill ${cls}">${s.status}</span></div>
      <div class="why">${reason}</div>
    </div>`;
  }).join("");
}

function renderRank(stores) {
  restoreCanvas("#rankBody", `<div class="chart-wrap tall"><canvas id="chartRank"></canvas></div>`);
  if (!stores.length) {
    showEmpty("#rankBody", "当前规格暂无门店损耗记录");
    return;
  }
  const sysTotal = stores.reduce((a,s)=>a + s.total_view, 0) || 1;
  const arr = stores.slice().sort((a,b)=>b.total_view - a.total_view);
  const labels = arr.map(s => s.store_name);
  const data   = arr.map(s => s.total_view);
  const colors = arr.map(s => STATUS_COLOR[s.status] || PALETTE.primary);
  const vals = arr.map(s => s.total_view);
  const mean = vals.length ? vals.reduce((a,b)=>a+b,0) / vals.length : 0;
  const sortedV = vals.slice().sort((a,b)=>a-b);
  const median = sortedV.length ? sortedV[Math.floor((sortedV.length-1)/2)] : 0;
  if (chartRank) chartRank.destroy();
  chartRank = new Chart(document.getElementById("chartRank"), {
    type: "bar",
    data: { labels, datasets: [{ label: metricLabel(), data, backgroundColor: colors, borderRadius: 4 }] },
    options: {
      indexAxis: "y", maintainAspectRatio: false,
      onClick: (evt, els) => {
        if (!els.length) return;
        const s = arr[els[0].index];
        state.selectedStore = storeKey(s);
        document.getElementById("fStore").value = state.selectedStore;
        render();
        document.getElementById("secDrill").scrollIntoView({behavior:"smooth"});
      },
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: {
          label: ctx => {
            const s = arr[ctx.dataIndex];
            const pct = sysTotal ? s.total_view / sysTotal * 100 : 0;
            return [
              `${metricFmt(s.total_view)} (占系统 ${fmtPctU(pct)})`,
              `较店均 ${fmtPct(mean ? (s.total_view-mean)/mean*100 : 0)}`,
              `状态: ${s.status||"—"} · 活跃 ${granCountLabel(s.active_view)}`
            ];
          }
        }}
      },
      scales: {
        x: { ticks: { callback: v => v.toLocaleString() }, grid: { color: "#F0F2F7" } },
        y: { grid: { display: false } }
      }
    },
    plugins: [{
      id:"refLines",
      afterDraw(c) {
        const {ctx, chartArea, scales} = c;
        if (!chartArea) return;
        const xMean = scales.x.getPixelForValue(mean);
        const xMed  = scales.x.getPixelForValue(median);
        ctx.save(); ctx.setLineDash([6,4]); ctx.lineWidth = 1.5;
        ctx.strokeStyle = PALETTE.teal;
        ctx.beginPath(); ctx.moveTo(xMean, chartArea.top); ctx.lineTo(xMean, chartArea.bottom); ctx.stroke();
        ctx.fillStyle = PALETTE.teal; ctx.font = "11px Arial";
        ctx.fillText("店均 " + metricFmt(mean), xMean + 4, chartArea.top + 12);
        ctx.strokeStyle = PALETTE.gold;
        ctx.beginPath(); ctx.moveTo(xMed, chartArea.top + 18); ctx.lineTo(xMed, chartArea.bottom); ctx.stroke();
        ctx.fillStyle = PALETTE.gold;
        ctx.fillText("中位数 " + metricFmt(median), xMed + 4, chartArea.top + 30);
        ctx.restore();
      }
    }, {
      id:"barLabels",
      afterDatasetsDraw(c) {
        const meta = c.getDatasetMeta(0);
        const {ctx} = c;
        ctx.save(); ctx.font = "11px Arial"; ctx.fillStyle = "#1F2937"; ctx.textBaseline = "middle";
        meta.data.forEach((bar, i) => {
          const s = arr[i];
          const pct = sysTotal ? s.total_view / sysTotal * 100 : 0;
          ctx.fillText(`${metricFmt(s.total_view)} · ${fmtPctU(pct)}`, bar.x + 6, bar.y);
        });
        ctx.restore();
      }
    }]
  });
  const parts = [];
  if (state.metric === "intensity" && state.gran === "month")
    parts.push("强度口径：每千笔订单产生的过期销毁；销量数据来自 t_order_store_fact，cycle_type=hour 汇总。");
  if (state.metric === "intensity" && state.gran !== "month")
    parts.push("损耗强度需月度销量分母，仅月维度可用；当前已回退到 USD。");
  if (effectiveMetric() === "usd" || effectiveMetric() === "qty")
    parts.push(`绝对量口径会受门店开业时间影响（新店活跃期数少）；切换至「损耗强度」并选择月维度可看销量平准化后的对比。`);
  document.getElementById("rankCaveat").textContent = parts.join(" ");
}

function renderPareto(stores) {
  restoreCanvas("#paretoBody", `<div class="chart-wrap"><canvas id="chartPareto"></canvas></div>`);
  if (!stores.length) {
    showEmpty("#paretoBody", "暂无数据");
    return;
  }
  const sorted = stores.slice().sort((a,b)=>b.total_view - a.total_view);
  const total = sorted.reduce((a,s)=>a+s.total_view, 0) || 1;
  const labels = sorted.map(s=>s.store_name);
  const bars = sorted.map(s=>s.total_view);
  let cum = 0; const line = sorted.map(s => { cum += s.total_view; return cum/total*100; });
  if (chartPareto) chartPareto.destroy();
  chartPareto = new Chart(document.getElementById("chartPareto"), {
    data: { labels, datasets: [
      { type:"bar",  label: metricLabel(), data: bars, backgroundColor: PALETTE.primary, yAxisID:"y", borderRadius:4 },
      { type:"line", label:"累计占比%", data: line, borderColor: PALETTE.gold, backgroundColor: PALETTE.gold, yAxisID:"y2", tension:.2, pointRadius:3 }
    ]},
    options: { maintainAspectRatio:false,
      plugins: { legend:{position:"top"},
        tooltip: { callbacks: { label: ctx => ctx.dataset.yAxisID === "y2"
          ? `累计 ${ctx.parsed.y.toFixed(1)}%` : metricFmt(ctx.parsed.y) }}
      },
      scales: {
        y:  { position:"left",  beginAtZero:true, ticks:{ callback: v => v.toLocaleString() } },
        y2: { position:"right", beginAtZero:true, max:100, ticks:{ callback: v => v+"%" }, grid:{display:false} }
      }
    },
    plugins: [{
      id:"p80",
      afterDraw(c) {
        const {ctx, chartArea, scales} = c;
        if (!chartArea || !scales.y2) return;
        const y = scales.y2.getPixelForValue(80);
        ctx.save(); ctx.setLineDash([4,4]); ctx.strokeStyle = PALETTE.red;
        ctx.beginPath(); ctx.moveTo(chartArea.left, y); ctx.lineTo(chartArea.right, y); ctx.stroke();
        ctx.fillStyle = PALETTE.red; ctx.font = "11px Arial";
        ctx.fillText("80%", chartArea.left + 4, y - 4);
        ctx.restore();
      }
    }]
  });
}

function renderSpecMix() {
  // Stacks USD across stores by CATEGORY when ALL view, or by SKU within a category.
  restoreCanvas("#specMixBody", `<div class="chart-wrap"><canvas id="chartSpecMix"></canvas></div>`);
  const stores = DATA.stores_all.slice().sort((a,b)=>b.total_loss_usd - a.total_loss_usd);
  if (!stores.length) { showEmpty("#specMixBody", "暂无数据"); return; }
  const labels = stores.map(s => s.store_name);
  let datasets, title, note;

  if (state.spec === "ALL") {
    // Stack by category
    title = "门店 × 品类 构成";
    note = "堆叠条形图：每家门店的 USD 损耗按 9 个品类拆分（颜色 = 品类）。";
    datasets = DATA.meta.categories.map(({id, label}) => ({
      label, backgroundColor: CATEGORY_COLORS[id] || PALETTE.primary,
      data: stores.map(s => (s.cat_breakdown && s.cat_breakdown[id]?.usd) || 0),
    })).filter(ds => ds.data.some(v => v > 0));
  } else if (state.spec.startsWith("CAT:")) {
    const cat = state.spec.slice(4);
    title = `门店 × 规格 构成（${DATA.meta.categories.find(c=>c.id===cat)?.label || cat}）`;
    note = "堆叠条形图：选中品类内每个 SKU 的 USD 损耗分布。";
    const skusInCat = DATA.meta.specs.filter(sp => sp.cat === cat && sp.has_data);
    datasets = skusInCat.map(sp => ({
      label: sp.label_cn, backgroundColor: SPEC_COLORS[sp.mid] || PALETTE.primary,
      data: stores.map(s => (s.spec_breakdown && s.spec_breakdown[sp.mid]?.usd) || 0),
    })).filter(ds => ds.data.some(v => v > 0));
  } else {
    // Single-spec: bar of that one SKU's USD per store
    title = "门店 × 当前规格 构成";
    note = "选中单一规格时，柱条仅显示该规格在每家门店的 USD 损耗。";
    const sp = currentSpec();
    datasets = [{
      label: sp ? sp.label_cn : state.spec,
      backgroundColor: sp ? SPEC_COLORS[sp.mid] : PALETTE.primary,
      data: stores.map(s => (s.spec_breakdown && s.spec_breakdown[state.spec]?.usd) || 0),
    }];
  }
  document.getElementById("specMixTitle").textContent = title;
  document.getElementById("specMixNote").textContent = note;
  if (chartSpecMix) chartSpecMix.destroy();
  chartSpecMix = new Chart(document.getElementById("chartSpecMix"), {
    type: "bar",
    data: { labels, datasets },
    options: { indexAxis:"y", maintainAspectRatio:false,
      plugins: { legend: { position: "top", labels: {boxWidth:14, font:{size:11}} },
        tooltip: { callbacks: { label: ctx => `${ctx.dataset.label}: ${fmtUsd(ctx.parsed.x)}` } }
      },
      scales: {
        x: { stacked:true, ticks:{ callback: v => "$"+v.toLocaleString() } },
        y: { stacked:true, grid:{ display:false } }
      }
    }
  });
}

let leagueSort = { key: "total_view", dir: -1 };
function renderLeague(months, stores) {
  const tbl = document.getElementById("tblLeague");
  if (!stores.length) {
    document.getElementById("leagueBody").innerHTML = `<div class="empty-state">暂无数据</div>`;
    return;
  }
  document.getElementById("leagueBody").innerHTML = `<table class="league" id="tblLeague"></table>`;
  const tbl2 = document.getElementById("tblLeague");
  const sysTotal = stores.reduce((a,s)=>a + s.total_view, 0) || 1;
  const totals = stores.map(s=>s.total_view).sort((a,b)=>a-b);
  const median = totals.length ? totals[Math.floor((totals.length-1)/2)] : 0;
  const mean = stores.length ? sysTotal/stores.length : 0;
  const arr = stores.slice();
  arr.sort((a,b) => {
    const ka = a[leagueSort.key], kb = b[leagueSort.key];
    const va = (ka==null) ? -Infinity : ka;
    const vb = (kb==null) ? -Infinity : kb;
    if (va < vb) return -1 * leagueSort.dir;
    if (va > vb) return  1 * leagueSort.dir;
    return 0;
  });
  const hdr = [
    ["rank","排名"], ["store_name","门店"], ["area","区域"],
    ["total_view",metricLabel()], ["share","占系统%"],
    ["total_loss_usd","累计 USD"], ["intensity_total","总强度"],
    ["active_view",`活跃${granLabelCn()}`],
    ["spark","趋势"], ["latest_mom_view",`最新${periodOverPeriodLabel()}`], ["status","状态"],
  ];
  const sortKeyMap = { rank:"rank", store_name:"store_name", area:"area",
    total_view:"total_view", share:"total_view",
    total_loss_usd:"total_loss_usd", intensity_total:"intensity_total",
    active_view:"active_view",
    latest_mom_view:"latest_mom_view", status:"status", spark:"total_view" };
  tbl2.innerHTML = `
    <thead><tr>${hdr.map(h => `<th data-k="${h[0]}">${h[1]}</th>`).join("")}</tr></thead>
    <tbody>${arr.map(s => {
      const share = s.total_view/sysTotal*100;
      const cls = s.status === "异常" ? "outlier" : (s.status === "需关注" ? "attn" : "");
      const pcls = STATUS_CLASS[s.status] || "s-zc";
      const intensityStr = s.intensity_total == null ? "—" : fmtN(s.intensity_total, 1);
      return `<tr class="${cls}" data-dk="${storeKey(s)}">
        <td>${s.rank}</td>
        <td>${s.store_name}</td>
        <td>${s.area}</td>
        <td>${metricFmt(s.total_view)}</td>
        <td>${fmtPctU(share)}</td>
        <td>${fmtUsd(s.total_loss_usd)}</td>
        <td>${intensityStr}</td>
        <td>${s.active_view}</td>
        <td>${sparkline(s.monthly_view)}</td>
        <td style="color:${(s.latest_mom_view??0)>=0?PALETTE.red:PALETTE.green}">${fmtPct(s.latest_mom_view)}</td>
        <td><span class="status-pill ${pcls}">${s.status||"—"}</span></td>
      </tr>`;
    }).join("")}</tbody>`;
  tbl2.querySelectorAll("th").forEach(th => {
    th.onclick = () => {
      const target = sortKeyMap[th.dataset.k] || "total_view";
      if (leagueSort.key === target) leagueSort.dir *= -1;
      else { leagueSort.key = target; leagueSort.dir = (typeof arr[0]?.[target] === "number") ? -1 : 1; }
      renderLeague(months, stores);
    };
  });
  tbl2.querySelectorAll("tbody tr").forEach(tr => {
    tr.onclick = () => {
      state.selectedStore = tr.dataset.dk;
      document.getElementById("fStore").value = tr.dataset.dk;
      render();
      document.getElementById("secDrill").scrollIntoView({behavior:"smooth"});
    };
  });
}

function sparkline(values) {
  const w = 110, h = 24, pad = 2;
  if (!values.length) return "";
  const max = Math.max(...values), min = Math.min(...values);
  const span = max - min || 1;
  const pts = values.map((v, i) => {
    const x = pad + (i * (w - 2*pad)) / Math.max(values.length - 1, 1);
    const y = h - pad - ((v - min) / span) * (h - 2*pad);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  return `<svg class="sparkline" width="${w}" height="${h}">
    <polyline points="${pts}" fill="none" stroke="${PALETTE.primary}" stroke-width="1.5"/>
  </svg>`;
}

function renderTrend(months, stores) {
  restoreCanvas("#trendBody", `<div class="chart-wrap"><canvas id="chartTrend"></canvas></div>`);
  if (!stores.length) { showEmpty("#trendBody", "暂无数据"); return; }
  if (chartTrend) chartTrend.destroy();
  const domain = axisDomain();
  const sysSeries = months.map(m => stores.reduce((a,s)=>a + (monthlyArr(s)[domain.indexOf(m)]||0), 0));
  const meanSeries = sysSeries.map(v => stores.length ? v / stores.length : 0);
  const datasets = [
    { label:"系统合计", data: sysSeries, borderColor: PALETTE.navy, backgroundColor: PALETTE.navy,
      borderWidth:3, tension:.25, pointRadius:4 },
    { label:"店均参考", data: meanSeries, borderColor: PALETTE.teal, backgroundColor: "rgba(0,165,165,.10)",
      borderDash:[6,4], fill:true, tension:.25, pointRadius:0 },
  ];
  stores.forEach((s, i) => {
    const view = months.map(m => monthlyArr(s)[domain.indexOf(m)] || 0);
    datasets.push({
      label: s.store_name, data: view,
      borderColor: hueColor(i), backgroundColor: hueColor(i),
      borderWidth: state.selectedStore === storeKey(s) ? 3 : 1.2,
      tension:.25, pointRadius: state.selectedStore === storeKey(s) ? 4 : 2,
      hidden: state.selectedStore && state.selectedStore !== storeKey(s) && stores.length > 1,
    });
  });
  // Rotate / thin x-axis labels when there are many buckets (week/day views).
  const labels = months.map(m => state.gran === "week" ? bucketShort(m, "week") : m);
  const xTickCfg = months.length > 14
    ? { maxRotation: 60, minRotation: 45, autoSkip: true, maxTicksLimit: 16, font: { size: 10 } }
    : { autoSkip: false };
  chartTrend = new Chart(document.getElementById("chartTrend"), {
    type: "line",
    data: { labels, datasets },
    options: { maintainAspectRatio:false,
      plugins: { legend:{ position:"top", labels:{ boxWidth:14, font:{ size:11 } } },
        tooltip:{ callbacks:{
          title: ctx => state.gran === "week" ? `${months[ctx[0].dataIndex]} (${isoWeekRangeLabel(months[ctx[0].dataIndex])})` : months[ctx[0].dataIndex],
          label: ctx => `${ctx.dataset.label}: ${metricFmt(ctx.parsed.y)}`
        } } },
      scales: { x: { ticks: xTickCfg },
                y: { beginAtZero:true, ticks:{ callback: v => v.toLocaleString() } } }
    }
  });
}
function hueColor(i) {
  const palette = [PALETTE.primary, PALETTE.gold, PALETTE.red, PALETTE.green, PALETTE.amber,
                   "#8E44AD","#16A085","#2C3E50","#D35400","#3498DB","#9B59B6","#1ABC9C",
                   "#F39C12","#34495E","#E91E63","#795548","#607D8B","#FF5722","#009688"];
  return palette[i % palette.length];
}

function renderHeat(months, stores) {
  const wrap = document.getElementById("heatWrap");
  if (!wrap) { document.getElementById("heatBody").innerHTML = `<div id="heatWrap"></div>`; }
  if (!stores.length) { document.getElementById("heatBody").innerHTML = `<div class="empty-state">暂无数据</div>`; return; }
  // Too-wide guard: 60+ columns is unreadable on most screens.
  const axisWarn = document.getElementById("axisWarn");
  if (axisWarn) {
    axisWarn.textContent = months.length > 60
      ? `当前 ${granLabelCn()}维度共 ${months.length} 列，热力图过宽 — 建议缩小起/止范围。`
      : "";
  }
  const wrap2 = document.getElementById("heatWrap") || (() => {
    document.getElementById("heatBody").innerHTML = `<div id="heatWrap"></div>`;
    return document.getElementById("heatWrap");
  })();
  const domain = axisDomain();
  const cells = stores.flatMap(s => months.map(m => monthlyArr(s)[domain.indexOf(m)] || 0));
  const maxV = Math.max(...cells, 1);
  const cellColor = v => {
    if (v === 0) return "#FAFBFE";
    const t = v / maxV;
    const r = Math.round(234 + (3 - 234) * t);
    const g = Math.round(242 + (101 - 242) * t);
    const b = Math.round(251 + (192 - 251) * t);
    return `rgb(${r},${g},${b})`;
  };
  const colTotals = months.map(m => stores.reduce((a,s)=>a + (monthlyArr(s)[domain.indexOf(m)] || 0), 0));
  const grand = colTotals.reduce((a,b)=>a+b, 0);
  const sorted = stores.slice().sort((a,b)=>b.total_view - a.total_view);
  const colHeader = m => state.gran === "week" ? bucketShort(m, "week") : m;
  let html = `<table class="heatmap"><thead><tr><th>门店</th>${months.map(m=>`<th title="${bucketLabel(m, state.gran)}">${colHeader(m)}</th>`).join("")}<th>总计</th></tr></thead><tbody>`;
  sorted.forEach(s => {
    const row = months.map(m => monthlyArr(s)[domain.indexOf(m)] || 0);
    const rowT = row.reduce((a,b)=>a+b, 0);
    html += `<tr><td>${s.store_name}</td>${row.map(v =>
      `<td style="background:${cellColor(v)}; color:${v/maxV>.55?'#fff':'#1F2937'}">${v===0?'·':metricFmt(v)}</td>`).join("")}<td class="total">${metricFmt(rowT)}</td></tr>`;
  });
  html += `<tr class="total"><td>合计</td>${colTotals.map(v=>`<td>${metricFmt(v)}</td>`).join("")}<td>${metricFmt(grand)}</td></tr>`;
  html += `</tbody></table>`;
  wrap2.innerHTML = html;
}

function renderNonStores(months) {
  const sec = document.getElementById("secNonStore");
  if (!DATA.non_stores || !DATA.non_stores.length) { sec.style.display = "none"; return; }
  let html = `<table class="league"><thead><tr><th>部门名称</th><th>dept_id</th>
    <th>报损金额 (USD)</th><th>记录数</th><th>首月</th><th>末月</th><th>主操作人</th></tr></thead><tbody>`;
  DATA.non_stores.forEach(s => {
    html += `<tr><td>${s.store_name}</td><td>${s.dept_id}</td>
      <td>${fmtUsd(s.total_loss_usd)}</td><td>${s.record_count}</td>
      <td>${s.first_month||"—"}</td><td>${s.last_active_month||"—"}</td>
      <td>${s.top_operator||"—"}</td></tr>`;
  });
  html += `</tbody></table>`;
  document.getElementById("nonStoreWrap").innerHTML = html;
}

function renderDrill(months, stores) {
  const dk = state.selectedStore;
  const target = dk ? stores.find(s => storeKey(s) === dk)
                    : stores.slice().sort((a,b)=>b.total_view - a.total_view)[0];
  document.getElementById("drillStoreLabel").textContent = target ? `${target.store_name} (${target.shop_no})` : "—";
  if (!target) {
    document.getElementById("drillKpis").innerHTML = `<div class="empty-state" style="grid-column:1/-1">暂无数据</div>`;
    return;
  }
  const sysTotal = stores.reduce((a,s)=>a+s.total_view, 0) || 1;
  const mean = stores.length ? sysTotal / stores.length : 0;
  let worstM = "—", worstV = 0;
  target.monthly_view.forEach((v, i) => { if (v > worstV) { worstV = v; worstM = months[i]; } });
  const k = [
    {label:"总" + metricLabel(), value: metricFmt(target.total_view), sub:`活跃 ${granCountLabel(target.active_view)}`},
    {label:"占系统%", value: fmtPctU(sysTotal ? target.total_view/sysTotal*100 : 0), sub:`排名 #${target.rank||"—"}`},
    {label:"较店均", value: fmtPct(mean ? (target.total_view-mean)/mean*100 : 0), sub:`店均 ${metricFmt(mean)}`},
    {label:"累计 USD", value: fmtUsd(target.total_loss_usd), sub: state.spec==="ALL" ? "全部规格" : ""},
    {label:"总订单", value: fmtN(target.total_sales,0), sub:"窗口期总订单数"},
    {label:"损耗强度", value: target.intensity_total==null?"—":fmtN(target.intensity_total,1), sub: (state.spec==="ALL"||state.spec.startsWith("CAT:"))?"USD/千单":"qty/千单"},
    {label:"最新" + granLabelCn(), value: metricFmt(target.latest_view), sub: months[target.last_active_idx_view] || "—"},
    {label:"最新" + periodOverPeriodLabel(), value: fmtPct(target.latest_mom_view), sub:`较上一有数据${granLabelCn()}`},
    {label:"最糟" + granLabelCn(), value: worstM, sub: metricFmt(worstV)},
  ];
  document.getElementById("drillKpis").innerHTML = k.map(c => `
    <div class="kpi">
      <div class="label">${c.label}</div>
      <div class="value">${c.value}</div>
      <div class="sub">${c.sub}</div>
    </div>`).join("");
  document.getElementById("drillNote").textContent =
    `主操作人：${target.top_operator || "—"}（占该店 ${fmtPctU(target.top_operator_share_pct||0)}）· z=${(target.z_score??0).toFixed(2)} · 百分位 ${fmtN(target.percentile,0)}`;

  if (chartDrillMonthly) chartDrillMonthly.destroy();
  const drillLabels = months.map(m => state.gran === "week" ? bucketShort(m, "week") : m);
  const drillTickCfg = months.length > 14
    ? { maxRotation: 60, minRotation: 45, autoSkip: true, maxTicksLimit: 16, font: { size: 10 } }
    : { autoSkip: false };
  chartDrillMonthly = new Chart(document.getElementById("chartDrillMonthly"), {
    type: "bar",
    data: { labels: drillLabels, datasets: [
      { label: metricLabel(), data: target.monthly_view, backgroundColor: PALETTE.primary, borderRadius:4 }
    ]},
    options: { maintainAspectRatio:false,
      plugins:{ legend:{display:false}, tooltip:{ callbacks:{
        title: ctx => state.gran === "week" ? `${months[ctx[0].dataIndex]} (${isoWeekRangeLabel(months[ctx[0].dataIndex])})` : months[ctx[0].dataIndex],
        label: ctx => metricFmt(ctx.parsed.y) }}},
      scales: { x:{ ticks: drillTickCfg },
                y:{ beginAtZero:true, ticks:{ callback: v => v.toLocaleString() } } }
    }
  });

  // Drill donut: prefer category breakdown for ALL view; SKU breakdown for category drill;
  // operators-only for single SKU view.
  if (chartDrillSpec) chartDrillSpec.destroy();
  const all = DATA.stores_all.find(s => storeKey(s) === storeKey(target));
  let donutTitle, donutLabels, donutValues, donutColors;
  if (state.spec === "ALL" && all && all.cat_breakdown) {
    donutTitle = "品类构成";
    const entries = Object.entries(all.cat_breakdown).sort((a,b)=>b[1].usd-a[1].usd);
    donutLabels = entries.map(([k]) => DATA.meta.categories.find(c=>c.id===k)?.label || k);
    donutValues = entries.map(([_, v]) => v.usd);
    donutColors = entries.map(([k]) => CATEGORY_COLORS[k] || PALETTE.primary);
  } else if (state.spec.startsWith("CAT:") && all && all.spec_breakdown) {
    const cat = state.spec.slice(4);
    donutTitle = "规格构成（当前品类）";
    const entries = Object.entries(all.spec_breakdown)
      .filter(([k]) => SPECS_BY_MID[k]?.cat === cat)
      .sort((a,b)=>b[1].usd-a[1].usd);
    donutLabels = entries.map(([k]) => SPECS_BY_MID[k]?.label_cn || k);
    donutValues = entries.map(([_, v]) => v.usd);
    donutColors = entries.map(([k]) => SPEC_COLORS[k] || PALETTE.primary);
  } else if (all && all.spec_breakdown && all.spec_breakdown[state.spec]) {
    donutTitle = "当前规格 vs 该店其他规格";
    const sel = all.spec_breakdown[state.spec];
    const otherUsd = (all.total_loss_usd || 0) - (sel.usd || 0);
    donutLabels = [SPECS_BY_MID[state.spec]?.label_cn || state.spec, "该店其他规格"];
    donutValues = [sel.usd, Math.max(otherUsd, 0)];
    donutColors = [SPEC_COLORS[state.spec] || PALETTE.primary, "#CBD5E1"];
  } else {
    donutTitle = "品类构成";
    donutLabels = []; donutValues = []; donutColors = [];
  }
  document.getElementById("drillSpecTitle").textContent = donutTitle;
  if (donutValues.length && donutValues.some(v => v > 0)) {
    chartDrillSpec = new Chart(document.getElementById("chartDrillSpec"), {
      type: "doughnut",
      data: { labels: donutLabels, datasets: [{ data: donutValues, backgroundColor: donutColors }] },
      options: { maintainAspectRatio:false,
        plugins:{ legend:{ position:"right", labels:{font:{size:11}} },
          tooltip:{ callbacks:{ label: ctx => `${ctx.label}: ${fmtUsd(ctx.parsed)}` } } }
      }
    });
  }

  const ops = target.operators || [];
  const opUnit = effectiveMetric() === "usd" ? "USD" : metricUnit();
  document.getElementById("tblOperators").innerHTML = `
    <thead><tr><th>操作人</th><th>记录数</th><th>${opUnit}</th><th>占该店%</th></tr></thead>
    <tbody>${ops.map(o => `
      <tr><td>${o.name}</td><td>${o.count}</td><td>${effectiveMetric()==="usd"?fmtUsd(o.qty):fmtN(o.qty,0)}</td><td>${fmtPctU(o.share_pct)}</td></tr>
    `).join("")}</tbody>`;
}

function exportCurrentCsv() {
  const months = activeMonths();
  const stores = sortStores(activeStoresAll().map(s => storeView(s, months)));
  const headers = ["rank","dept_id","shop_no","store_name","area",
                   `total_${effectiveMetric()}`, "total_loss_usd", "total_sales", "intensity_per_1k",
                   `active_${state.gran === "month" ? "months" : (state.gran === "week" ? "weeks" : "days")}`,
                   "record_count","status","spec_scope", ...months];
  const sysTotal = stores.reduce((a,s)=>a+s.total_view, 0) || 1;
  const rows = stores.map((s,i) => {
    const base = [i+1, s.dept_id, s.shop_no, s.store_name, s.area,
                  s.total_view.toFixed(2),
                  (s.total_loss_usd||0).toFixed(2),
                  s.total_sales||0,
                  s.intensity_total == null ? "" : s.intensity_total.toFixed(4),
                  s.active_view, s.record_count, s.status||"", state.spec];
    return base.concat(s.monthly_view.map(v => v.toFixed(2)));
  });
  // Prepend a header note row that records the granularity / metric / window.
  const note = [`# spoilage export — gran=${state.gran} · metric=${effectiveMetric()} · spec=${state.spec} · window=${state.monthFrom}..${state.monthTo}`];
  const csv = [note, headers, ...rows].map(r => r.map(c => {
    const x = String(c);
    return /[,"\n]/.test(x) ? `"${x.replace(/"/g,'""')}"` : x;
  }).join(",")).join("\n");
  const blob = new Blob([csv], {type:"text/csv;charset=utf-8;"});
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  const safeFrom = state.monthFrom.replace(/[^A-Za-z0-9_-]/g, "");
  const safeTo   = state.monthTo.replace(/[^A-Za-z0-9_-]/g, "");
  a.href = url; a.download = `spoilage_${state.spec.replace(/[^A-Za-z0-9_-]/g,"")}_${state.gran}_${effectiveMetric()}_${safeFrom}_${safeTo}.csv`;
  a.click(); URL.revokeObjectURL(url);
}

function render() {
  updateMetricAvailability();
  const months = activeMonths();
  let stores = activeStoresAll().map(s => storeView(s, months));
  stores = sortStores(stores);
  const ranked = stores.slice().sort((a,b)=>b.total_view - a.total_view);
  ranked.forEach((s, i) => { s.rank = i + 1; });
  renderKpis(months, stores);
  renderAlerts(stores);
  renderRank(stores);
  renderPareto(stores);
  renderSpecMix();
  renderLeague(months, stores);
  renderTrend(months, stores);
  renderHeat(months, stores);
  renderNonStores(months);
  renderDrill(months, stores);
}

// header / footer
const withData = DATA.meta.specs.filter(sp => sp.has_data).length;
document.getElementById("hdrSpec").textContent = `${DATA.meta.spec_count} 种规格 / ${DATA.meta.categories.length} 个品类（${withData} 个有记录）`;
document.getElementById("hdrPeriod").textContent = `周期：${DATA.meta.period_start} → ${DATA.meta.period_end}`;
document.getElementById("tzBadge").textContent = "时区：" + DATA.meta.timezone;
document.getElementById("ftrPeriod").textContent = `${DATA.meta.period_start} → ${DATA.meta.period_end}`;
document.getElementById("ftrGen").textContent = DATA.meta.generated;
document.getElementById("ftrTz").textContent = DATA.meta.timezone;
document.getElementById("ftrDst").textContent = DATA.meta.dst_drift_count;
document.getElementById("ftrRecon").textContent = DATA.meta.reconciliation;
if (DATA.meta.build_meta) {
  const bm = DATA.meta.build_meta;
  document.getElementById("ftrBuild").textContent =
    `最近一次构建 ${bm.build_time} · commit ${(bm.git_commit||"").slice(0,8)} · 输入行数 ${bm.rows}`;
}
document.getElementById("reconPill").textContent = `对账 ${DATA.meta.reconciliation}`;
document.getElementById("reconPill").className = "pill " + (DATA.meta.reconciliation === "PASS" ? "pass" : "fail");

initToolbar();
render();
</script>
</body>
</html>
"""

html = HTML_TEMPLATE.replace("__PAYLOAD__", json.dumps(payload, ensure_ascii=False))
HTML = os.path.join(OUT_DIR, "dashboard.html")
with open(HTML, "w", encoding="utf-8") as f:
    f.write(html)
print(f"wrote {HTML}  ({os.path.getsize(HTML):,} bytes)")
print(f"stores_all={len(payload['stores_all'])}  non_stores={len(payload['non_stores'])}  "
      f"months={len(payload['meta']['months'])}  specs={len(payload['meta']['specs'])}  "
      f"specs_with_data={payload['meta']['spec_with_data_count']}")
