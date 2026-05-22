"""V2 dashboard builder — consumes /app/output/dashboard_payload.json.

New capabilities vs v1:
- Spec selector (4 milk variants + ALL aggregate).
- Metric toggle: mL / USD / 损耗强度 (mL per 1k orders).
- Multi-spec stacked breakdown bar.
- Sales intensity now first-class (no longer disabled).
- DST-aware: payload was bucketed via zoneinfo America/New_York; we surface that in the header.
"""
import json, os
from datetime import datetime

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT_DIR = os.path.join(REPO_ROOT, "output")
DOCS_DATA = os.path.join(REPO_ROOT, "docs", "data")

with open(os.path.join(OUT_DIR, "dashboard_payload.json"), encoding="utf-8") as f:
    payload = json.load(f)

# Inject build_meta into payload so the dashboard footer can show freshness.
# build_meta.json is written by pipeline/refresh.sh after this script runs;
# read it here if a previous build deposited one (best-effort, optional).
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
<title>门店脱脂奶过期销毁损耗分析看板</title>
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
    <h1>Luckin USA 牛奶过期销毁损耗分析看板</h1>
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
      <option value="ml">报损量 (mL)</option>
      <option value="usd">报损金额 (USD)</option>
      <option value="intensity">损耗强度 (mL / 1k 单)</option>
    </select>
  </div>
  <div><label>月份起</label><select id="fMonthFrom"></select></div>
  <div><label>月份止</label><select id="fMonthTo"></select></div>
  <div><label>门店</label><select id="fStore"></select></div>
  <div><label>排序</label>
    <select id="fSort">
      <option value="metric_desc">按当前指标（高→低）</option>
      <option value="metric_asc">按当前指标（低→高）</option>
      <option value="latest_desc">按最新月</option>
      <option value="mom_desc">按最新月环比</option>
    </select>
  </div>
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
    <div class="chart-wrap tall"><canvas id="chartRank"></canvas></div>
    <div class="note" id="rankCaveat"></div>
  </section>

  <section id="secPareto"><h2>门店损耗帕累托（累计占比）</h2>
    <div class="chart-wrap"><canvas id="chartPareto"></canvas></div>
  </section>

  <section id="secSpecMix"><h2>门店 × 规格 构成</h2>
    <div class="chart-wrap"><canvas id="chartSpecMix"></canvas></div>
    <div class="note">堆叠条形图：每家门店的损耗按规格拆分（脱脂 / 全脂 / 减脂），帮助识别哪种牛奶产生的过期销毁更多。</div>
  </section>

  <section id="secLeague"><h2>门店对标榜单</h2>
    <div style="overflow-x:auto"><table class="league" id="tblLeague"></table></div>
  </section>

  <section id="secTrend"><h2>月度趋势</h2>
    <div class="chart-wrap"><canvas id="chartTrend"></canvas></div>
  </section>

  <section id="secHeat"><h2>门店 × 月份 热力矩阵</h2>
    <div style="overflow-x:auto" id="heatWrap"></div>
    <div class="legend"><span>低</span><span class="swatch"></span><span>高（颜色越深表示报损量越大；·=该月未开业或为零）</span></div>
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
        <h3>规格构成</h3>
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
  （tenant=LKUS，specific_reason_code=015「过期销毁」）；门店主数据来自 <code>luckyus_opshop.t_shop_info</code>；
  销量参考来自 <code>luckyus_sales_order.t_order_store_fact</code>（hourly→月汇总）；
  单位成本来自 <code>luckyus_scm_purchase.t_goods_spec_cost_detail</code>。<br>
  8th &amp; Broadway 的 Jan-Apr 2026 已与门店导出的 xlsx 文件逐月对账（差异 = 0）。<br>
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
const SPEC_COLORS = {
  "GS07788-01": PALETTE.primary,
  "GS07786-01": PALETTE.gold,
  "GS07785-01": PALETTE.teal,
  "GS07786-02": PALETTE.amber,
};

const state = {
  spec: "ALL",
  metric: "ml",   // ml | usd | intensity
  monthFrom: DATA.meta.months[0],
  monthTo:   DATA.meta.months[DATA.meta.months.length - 1],
  selectedStore: null,
  sort: "metric_desc",
};

const storeKey = s => `${s.dept_id}|${s.shop_no}`;

// pick which dataset to show (per-spec or aggregate)
function activeStoresAll() {
  return state.spec === "ALL" ? DATA.stores_all : (DATA.stores_by_spec[state.spec] || []);
}

// metric extractor: returns the right monthly array given current state
function monthlyArr(s) {
  if (state.metric === "usd") return s.monthly_usd;
  if (state.metric === "intensity") return s.intensity_monthly || [];
  return s.monthly_ml;
}
function metricLabel() {
  if (state.metric === "usd") return "报损金额 (USD)";
  if (state.metric === "intensity") return "损耗强度 (mL/千单)";
  return "报损量 (mL)";
}
function metricFmt(v) {
  if (v == null || isNaN(v)) return "—";
  if (state.metric === "usd") return fmtUsd(v);
  if (state.metric === "intensity") return fmtN(v, 1);
  return fmtN(v, 0);
}
function metricUnit() {
  return state.metric === "usd" ? "USD" : (state.metric === "intensity" ? "mL/千单" : "mL");
}

function initToolbar() {
  const fSpec = document.getElementById("fSpec");
  fSpec.innerHTML = `<option value="ALL">全部规格（合计）</option>` +
    DATA.meta.specs.filter(sp => (DATA.stores_by_spec[sp.mid] || []).length > 0)
      .map(sp => `<option value="${sp.mid}">${sp.label_cn}（${sp.mid}）</option>`).join("");
  fSpec.value = state.spec;
  fSpec.onchange = () => { state.spec = fSpec.value; state.selectedStore = null;
    document.getElementById("fStore").value = ""; render(); };

  const fMet = document.getElementById("fMetric");
  fMet.value = state.metric;
  fMet.onchange = () => { state.metric = fMet.value; render(); };

  const fMF = document.getElementById("fMonthFrom");
  const fMT = document.getElementById("fMonthTo");
  fMF.innerHTML = DATA.meta.months.map(m => `<option value="${m}">${m}</option>`).join("");
  fMT.innerHTML = DATA.meta.months.map(m => `<option value="${m}">${m}</option>`).join("");
  fMT.value = state.monthTo;
  fMF.onchange = () => { state.monthFrom = fMF.value; render(); };
  fMT.onchange = () => { state.monthTo = fMT.value; render(); };

  const fS = document.getElementById("fStore");
  fS.innerHTML = `<option value="">（全部 / 系统视图）</option>` +
    DATA.stores_all.map(s => `<option value="${storeKey(s)}">${s.store_name} (${s.shop_no})</option>`).join("");
  fS.onchange = () => { state.selectedStore = fS.value || null; render(); };

  document.getElementById("fSort").onchange = (e) => { state.sort = e.target.value; render(); };
  document.getElementById("btnPrint").onclick = () => window.print();
  document.getElementById("btnExportCsv").onclick = exportCurrentCsv;
}

function activeMonths() {
  const all = DATA.meta.months;
  const i1 = all.indexOf(state.monthFrom);
  const i2 = all.indexOf(state.monthTo);
  return all.slice(Math.min(i1, i2), Math.max(i1, i2) + 1);
}

function storeView(s, months) {
  const idx = months.map(m => DATA.meta.months.indexOf(m));
  const arr = monthlyArr(s);
  const mView = idx.map(i => arr[i] || 0);
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

function renderKpis(months, stores) {
  const sysTotal = stores.reduce((a,s)=>a + s.total_view, 0);
  const recCount = stores.reduce((a,s)=>a + s.record_count, 0);
  const mean = stores.length ? sysTotal / stores.length : 0;
  const top = stores.slice().sort((a,b)=>b.total_view - a.total_view)[0];
  let latestMom = null;
  if (months.length >= 2) {
    const sysM = months.map(m => stores.reduce((a,s)=>a + (monthlyArr(s)[DATA.meta.months.indexOf(m)]||0), 0));
    const prev = sysM[sysM.length - 2], cur = sysM[sysM.length - 1];
    if (prev) latestMom = (cur - prev) / prev * 100;
  }
  const specLabel = state.spec === "ALL" ? "全部规格" : (DATA.meta.specs.find(sp=>sp.mid===state.spec)?.label_cn || state.spec);
  document.getElementById("kpiScope").textContent =
    `${specLabel} · ${months[0]} → ${months[months.length-1]} · 指标：${metricLabel()}`;
  const cells = [
    {label:"系统总" + metricLabel(), value: metricFmt(sysTotal), sub:"单位：" + metricUnit()},
    {label:"覆盖门店数", value: stores.length, sub:`记录数 ${recCount}`},
    {label:"店均", value: metricFmt(mean), sub:"= 系统总 / 门店数"},
    {label:"最高门店", value: top ? top.store_name : "—",
      sub: top ? `${metricFmt(top.total_view)} · 占 ${fmtPctU(sysTotal ? top.total_view/sysTotal*100 : 0)}` : "",
      accent: true},
    {label:"统计周期", value: `${months[0]} → ${months[months.length-1]}`, sub: `${months.length} 个月`},
    {label:"过期销毁记录数", value: recCount, sub:"reason = 015"},
    {label:"系统最新月环比", value: fmtPct(latestMom), sub: months[months.length-1] || ""},
  ];
  document.getElementById("kpiGrid").innerHTML = cells.map(c => `
    <div class="kpi ${c.accent ? "accent" : ""}">
      <div class="label">${c.label}</div>
      <div class="value">${c.value}</div>
      <div class="sub">${c.sub || ""}</div>
    </div>`).join("");
}

function renderAlerts(stores) {
  const flagged = stores.filter(s => s.status !== "正常");
  const sec = document.getElementById("secAlerts");
  if (!flagged.length) { sec.style.display = "none"; return; }
  sec.style.display = "";
  document.getElementById("alertStrip").innerHTML = flagged.map(s => {
    const reason = s.status === "异常"
      ? `统计离群：总量 ${fmtN(s.total_loss_ml,0)} mL（z=${(s.z_score??0).toFixed(2)}）`
      : `最新月环比 ${fmtPct(s.latest_mom_pct)}，且总量高于中位数`;
    const cls = STATUS_CLASS[s.status];
    return `<div class="alert-card ${cls}">
      <div class="title">${s.store_name} <span class="status-pill ${cls}">${s.status}</span></div>
      <div class="why">${reason}</div>
    </div>`;
  }).join("");
}

function renderRank(stores) {
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
              `状态: ${s.status} · 活跃 ${s.active_view} 月`
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
  if (state.metric === "intensity")
    parts.push("强度口径：每千笔订单产生的过期销毁 mL；销量数据来自 t_order_store_fact，cycle_type=hour 汇总。");
  if (state.metric === "ml" || state.metric === "usd")
    parts.push("绝对量口径会受门店开业时间影响（新店活跃月少）；切换至「损耗强度」可看销量平准化后的对比。");
  document.getElementById("rankCaveat").textContent = parts.join(" ");
}

function renderPareto(stores) {
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

function renderSpecMix(months) {
  // Stacked bar of each store by spec. Only meaningful when state.spec="ALL".
  // We always render it (when not ALL it just shows the single spec).
  // Use mL by default; switch to USD if metric is usd.
  const useUsd = state.metric === "usd";
  const stores = DATA.stores_all.slice().sort((a,b)=>b.total_loss_ml - a.total_loss_ml);
  const labels = stores.map(s => s.store_name);
  const specList = DATA.meta.specs.filter(sp => (DATA.stores_by_spec[sp.mid]||[]).length > 0);
  const datasets = specList.map(sp => ({
    label: sp.label_cn,
    backgroundColor: SPEC_COLORS[sp.mid] || PALETTE.primary,
    data: stores.map(s => {
      const b = s.spec_breakdown && s.spec_breakdown[sp.mid];
      if (!b) return 0;
      return useUsd ? b.usd : b.ml;
    }),
  }));
  if (chartSpecMix) chartSpecMix.destroy();
  chartSpecMix = new Chart(document.getElementById("chartSpecMix"), {
    type: "bar",
    data: { labels, datasets },
    options: { indexAxis:"y", maintainAspectRatio:false,
      plugins: { legend: { position: "top" },
        tooltip: { callbacks: { label: ctx => `${ctx.dataset.label}: ${useUsd ? fmtUsd(ctx.parsed.x) : fmtN(ctx.parsed.x,0)+' mL'}` } }
      },
      scales: {
        x: { stacked:true, ticks:{ callback: v => v.toLocaleString() } },
        y: { stacked:true, grid:{ display:false } }
      }
    }
  });
}

let leagueSort = { key: "total_view", dir: -1 };
function renderLeague(months, stores) {
  const tbl = document.getElementById("tblLeague");
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
    ["active_view","活跃月"],
    ["spark","趋势"], ["latest_mom_view","最新月环比"], ["status","状态"],
  ];
  const sortKeyMap = { rank:"rank", store_name:"store_name", area:"area",
    total_view:"total_view", share:"total_view",
    total_loss_usd:"total_loss_usd", intensity_total:"intensity_total",
    active_view:"active_view",
    latest_mom_view:"latest_mom_view", status:"status", spark:"total_view" };
  tbl.innerHTML = `
    <thead><tr>${hdr.map(h => `<th data-k="${h[0]}">${h[1]}</th>`).join("")}</tr></thead>
    <tbody>${arr.map(s => {
      const share = s.total_view/sysTotal*100;
      const cls = s.status === "异常" ? "outlier" : (s.status === "需关注" ? "attn" : "");
      const pcls = STATUS_CLASS[s.status];
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
        <td><span class="status-pill ${pcls}">${s.status}</span></td>
      </tr>`;
    }).join("")}</tbody>`;
  tbl.querySelectorAll("th").forEach(th => {
    th.onclick = () => {
      const target = sortKeyMap[th.dataset.k] || "total_view";
      if (leagueSort.key === target) leagueSort.dir *= -1;
      else { leagueSort.key = target; leagueSort.dir = (typeof arr[0]?.[target] === "number") ? -1 : 1; }
      renderLeague(months, stores);
    };
  });
  tbl.querySelectorAll("tbody tr").forEach(tr => {
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
  if (chartTrend) chartTrend.destroy();
  const sysSeries = months.map(m => stores.reduce((a,s)=>a + (monthlyArr(s)[DATA.meta.months.indexOf(m)]||0), 0));
  const meanSeries = sysSeries.map(v => stores.length ? v / stores.length : 0);
  const datasets = [
    { label:"系统合计", data: sysSeries, borderColor: PALETTE.navy, backgroundColor: PALETTE.navy,
      borderWidth:3, tension:.25, pointRadius:4 },
    { label:"店均参考", data: meanSeries, borderColor: PALETTE.teal, backgroundColor: "rgba(0,165,165,.10)",
      borderDash:[6,4], fill:true, tension:.25, pointRadius:0 },
  ];
  stores.forEach((s, i) => {
    const view = months.map(m => monthlyArr(s)[DATA.meta.months.indexOf(m)] || 0);
    datasets.push({
      label: s.store_name, data: view,
      borderColor: hueColor(i), backgroundColor: hueColor(i),
      borderWidth: state.selectedStore === storeKey(s) ? 3 : 1.2,
      tension:.25, pointRadius: state.selectedStore === storeKey(s) ? 4 : 2,
      hidden: state.selectedStore && state.selectedStore !== storeKey(s) && stores.length > 1,
    });
  });
  chartTrend = new Chart(document.getElementById("chartTrend"), {
    type: "line",
    data: { labels: months, datasets },
    options: { maintainAspectRatio:false,
      plugins: { legend:{ position:"top", labels:{ boxWidth:14, font:{ size:11 } } },
        tooltip:{ callbacks:{ label: ctx => `${ctx.dataset.label}: ${metricFmt(ctx.parsed.y)}` } } },
      scales: { y:{ beginAtZero:true, ticks:{ callback: v => v.toLocaleString() } } }
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
  const cells = stores.flatMap(s => months.map(m => monthlyArr(s)[DATA.meta.months.indexOf(m)] || 0));
  const maxV = Math.max(...cells, 1);
  const cellColor = v => {
    if (v === 0) return "#FAFBFE";
    const t = v / maxV;
    const r = Math.round(234 + (3 - 234) * t);
    const g = Math.round(242 + (101 - 242) * t);
    const b = Math.round(251 + (192 - 251) * t);
    return `rgb(${r},${g},${b})`;
  };
  const colTotals = months.map(m => stores.reduce((a,s)=>a + (monthlyArr(s)[DATA.meta.months.indexOf(m)] || 0), 0));
  const grand = colTotals.reduce((a,b)=>a+b, 0);
  const sorted = stores.slice().sort((a,b)=>b.total_view - a.total_view);
  let html = `<table class="heatmap"><thead><tr><th>门店</th>${months.map(m=>`<th>${m}</th>`).join("")}<th>总计</th></tr></thead><tbody>`;
  sorted.forEach(s => {
    const row = months.map(m => monthlyArr(s)[DATA.meta.months.indexOf(m)] || 0);
    const rowT = row.reduce((a,b)=>a+b, 0);
    html += `<tr><td>${s.store_name}</td>${row.map(v =>
      `<td style="background:${cellColor(v)}; color:${v/maxV>.55?'#fff':'#1F2937'}">${v===0?'·':metricFmt(v)}</td>`).join("")}<td class="total">${metricFmt(rowT)}</td></tr>`;
  });
  html += `<tr class="total"><td>合计</td>${colTotals.map(v=>`<td>${metricFmt(v)}</td>`).join("")}<td>${metricFmt(grand)}</td></tr>`;
  html += `</tbody></table>`;
  wrap.innerHTML = html;
}

function renderNonStores(months) {
  const sec = document.getElementById("secNonStore");
  if (!DATA.non_stores || !DATA.non_stores.length) { sec.style.display = "none"; return; }
  let html = `<table class="league"><thead><tr><th>部门名称</th><th>dept_id</th><th>报损量 (mL)</th>
    <th>报损金额 (USD)</th><th>记录数</th><th>首月</th><th>末月</th><th>主操作人</th></tr></thead><tbody>`;
  DATA.non_stores.forEach(s => {
    html += `<tr><td>${s.store_name}</td><td>${s.dept_id}</td><td>${fmtN(s.total_loss_ml,0)}</td>
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
  if (!target) return;
  const sysTotal = stores.reduce((a,s)=>a+s.total_view, 0) || 1;
  const mean = stores.length ? sysTotal / stores.length : 0;
  let worstM = "—", worstV = 0;
  target.monthly_view.forEach((v, i) => { if (v > worstV) { worstV = v; worstM = months[i]; } });
  const k = [
    {label:"总" + metricLabel(), value: metricFmt(target.total_view), sub:`活跃 ${target.active_view} 月`},
    {label:"占系统%", value: fmtPctU(sysTotal ? target.total_view/sysTotal*100 : 0), sub:`排名 #${target.rank}`},
    {label:"较店均", value: fmtPct(mean ? (target.total_view-mean)/mean*100 : 0), sub:`店均 ${metricFmt(mean)}`},
    {label:"累计 USD", value: fmtUsd(target.total_loss_usd), sub:"全部规格"},
    {label:"总订单", value: fmtN(target.total_sales,0), sub:"窗口期总订单数"},
    {label:"损耗强度", value: target.intensity_total==null?"—":fmtN(target.intensity_total,1), sub:"mL/千单"},
    {label:"最新月", value: metricFmt(target.latest_view), sub: months[target.last_active_idx_view] || "—"},
    {label:"最新月环比", value: fmtPct(target.latest_mom_view), sub:"较上一有数据月"},
    {label:"最糟月份", value: worstM, sub: metricFmt(worstV)},
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
  chartDrillMonthly = new Chart(document.getElementById("chartDrillMonthly"), {
    type: "bar",
    data: { labels: months, datasets: [
      { label: metricLabel(), data: target.monthly_view, backgroundColor: PALETTE.primary, borderRadius:4 }
    ]},
    options: { maintainAspectRatio:false,
      plugins:{ legend:{display:false}, tooltip:{ callbacks:{ label: ctx => metricFmt(ctx.parsed.y) }}},
      scales: { y:{ beginAtZero:true, ticks:{ callback: v => v.toLocaleString() } } }
    }
  });

  // spec breakdown donut — use ALL aggregate spec_breakdown
  const all = DATA.stores_all.find(s => storeKey(s) === storeKey(target));
  if (chartDrillSpec) chartDrillSpec.destroy();
  if (all && all.spec_breakdown) {
    const useUsd = state.metric === "usd";
    const entries = Object.entries(all.spec_breakdown);
    const labels = entries.map(([k]) => DATA.meta.specs.find(sp=>sp.mid===k)?.label_cn || k);
    const dataVals = entries.map(([_, v]) => useUsd ? v.usd : v.ml);
    const colors = entries.map(([k]) => SPEC_COLORS[k] || PALETTE.primary);
    chartDrillSpec = new Chart(document.getElementById("chartDrillSpec"), {
      type: "doughnut",
      data: { labels, datasets: [{ data: dataVals, backgroundColor: colors }] },
      options: { maintainAspectRatio:false,
        plugins:{ legend:{ position:"right", labels:{font:{size:11}} },
          tooltip:{ callbacks:{ label: ctx => `${ctx.label}: ${useUsd ? fmtUsd(ctx.parsed) : fmtN(ctx.parsed,0)+' mL'}` } } }
      }
    });
  }

  const ops = target.operators || [];
  document.getElementById("tblOperators").innerHTML = `
    <thead><tr><th>操作人</th><th>记录数</th><th>报损量 (mL)</th><th>占该店%</th></tr></thead>
    <tbody>${ops.map(o => `
      <tr><td>${o.name}</td><td>${o.count}</td><td>${fmtN(o.qty,0)}</td><td>${fmtPctU(o.share_pct)}</td></tr>
    `).join("")}</tbody>`;
}

function exportCurrentCsv() {
  const months = activeMonths();
  const stores = sortStores(activeStoresAll().map(s => storeView(s, months)));
  const headers = ["rank","dept_id","shop_no","store_name","area",
                   `total_${state.metric}`, "total_loss_ml", "total_loss_usd", "total_sales", "intensity_per_1k",
                   "active_months","record_count","status","spec_scope", ...months];
  const sysTotal = stores.reduce((a,s)=>a+s.total_view, 0) || 1;
  const rows = stores.map((s,i) => {
    const base = [i+1, s.dept_id, s.shop_no, s.store_name, s.area,
                  s.total_view.toFixed(2),
                  s.total_loss_ml.toFixed(2),
                  s.total_loss_usd.toFixed(2),
                  s.total_sales,
                  s.intensity_total == null ? "" : s.intensity_total.toFixed(4),
                  s.active_view, s.record_count, s.status, state.spec];
    return base.concat(s.monthly_view.map(v => v.toFixed(2)));
  });
  const csv = [headers, ...rows].map(r => r.map(c => {
    const x = String(c);
    return /[,"\n]/.test(x) ? `"${x.replace(/"/g,'""')}"` : x;
  }).join(",")).join("\n");
  const blob = new Blob([csv], {type:"text/csv;charset=utf-8;"});
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = `spoilage_${state.spec}_${state.metric}_${state.monthFrom}_${state.monthTo}.csv`;
  a.click(); URL.revokeObjectURL(url);
}

function render() {
  const months = activeMonths();
  let stores = activeStoresAll().map(s => storeView(s, months));
  stores = sortStores(stores);
  const ranked = stores.slice().sort((a,b)=>b.total_view - a.total_view);
  ranked.forEach((s, i) => { s.rank = i + 1; });
  renderKpis(months, stores);
  renderAlerts(stores);
  renderRank(stores);
  renderPareto(stores);
  renderSpecMix(months);
  renderLeague(months, stores);
  renderTrend(months, stores);
  renderHeat(months, stores);
  renderNonStores(months);
  renderDrill(months, stores);
}

// header / footer
document.getElementById("hdrSpec").textContent = "规格：" + DATA.meta.specs.filter(sp => (DATA.stores_by_spec[sp.mid]||[]).length>0).map(sp=>sp.label_cn).join(" / ");
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
      f"months={len(payload['meta']['months'])}  specs={len(payload['meta']['specs'])}")
