"""state.json → 정적 대시보드(docs/index.html) 생성.

외부 라이브러리·CDN 없이 단일 HTML로 렌더링하므로 GitHub Pages나
로컬 파일 열기 모두에서 동작한다.
"""
import json

_TEMPLATE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>아파트 실거래가 모니터</title>
<style>
  :root {
    --bg: #f6f7f9; --card: #fff; --ink: #1c2230; --sub: #6b7280;
    --line: #e5e7eb; --up: #dc2626; --down: #2563eb; --accent: #0f766e;
  }
  * { box-sizing: border-box; }
  body { margin: 0; padding: 24px; background: var(--bg); color: var(--ink);
         font-family: "Apple SD Gothic Neo", "Pretendard", "Malgun Gothic", sans-serif; }
  h1 { font-size: 22px; margin: 0 0 4px; }
  .sub { color: var(--sub); font-size: 13px; margin-bottom: 20px; }
  .cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
           gap: 14px; margin-bottom: 24px; }
  .card { background: var(--card); border: 1px solid var(--line); border-radius: 12px;
          padding: 16px 18px; }
  .card h3 { margin: 0 0 2px; font-size: 15px; }
  .card .band { color: var(--sub); font-size: 12px; margin-bottom: 10px; }
  .card .price { font-size: 22px; font-weight: 700; }
  .card .meta { font-size: 12px; color: var(--sub); margin-top: 6px; }
  .diff-up { color: var(--up); font-weight: 600; }
  .diff-down { color: var(--down); font-weight: 600; }
  .section { background: var(--card); border: 1px solid var(--line);
             border-radius: 12px; padding: 18px; margin-bottom: 24px; }
  .section h2 { font-size: 16px; margin: 0 0 12px; }
  svg text { font-family: inherit; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th, td { padding: 8px 10px; text-align: right; border-bottom: 1px solid var(--line); }
  th:first-child, td:first-child, th:nth-child(2), td:nth-child(2) { text-align: left; }
  th { color: var(--sub); font-weight: 600; font-size: 12px; }
  tr.cancelled td { color: #9ca3af; text-decoration: line-through; }
  .badge { display: inline-block; padding: 1px 7px; border-radius: 99px;
           font-size: 11px; background: #fee2e2; color: #b91c1c; text-decoration: none; }
  select { padding: 6px 10px; border: 1px solid var(--line); border-radius: 8px;
           font-size: 13px; margin-bottom: 12px; }
  .legend { font-size: 12px; color: var(--sub); margin-top: 8px; }
</style>
</head>
<body>
<h1>🏠 아파트 실거래가 모니터</h1>
<div class="sub">마지막 갱신: __LAST_RUN__ · 누적 기록 __TOTAL__건</div>

<div class="cards" id="cards"></div>

<div class="section">
  <h2>가격 추이</h2>
  <select id="groupSel"></select>
  <div id="chart"></div>
</div>

<div class="section">
  <h2>거래 내역</h2>
  <table>
    <thead><tr><th>계약일</th><th>단지</th><th>전용(㎡)</th><th>층</th>
               <th>거래금액</th><th>직전대비</th><th>비고</th></tr></thead>
    <tbody id="rows"></tbody>
  </table>
</div>

<script>
const DEALS = __DEALS__;

function fmtMoney(man) {
  const sign = man < 0 ? "-" : ""; man = Math.abs(man);
  const eok = Math.floor(man / 10000), rest = man % 10000;
  if (eok && rest) return sign + eok + "억 " + rest.toLocaleString();
  if (eok) return sign + eok + "억";
  return sign + rest.toLocaleString() + "만";
}
const groupKey = d => d.apt_nm + " " + Math.floor(d.area) + "㎡";

// 그룹별 정렬된 유효 거래
const groups = {};
DEALS.slice().sort((a,b) => a.date.localeCompare(b.date)).forEach(d => {
  (groups[groupKey(d)] = groups[groupKey(d)] || []).push(d);
});
const activeOf = g => g.filter(d => !d.cancelled);

// ---- 요약 카드
const cardsEl = document.getElementById("cards");
Object.entries(groups).forEach(([key, g]) => {
  const act = activeOf(g);
  if (!act.length) return;
  const last = act[act.length - 1], prev = act[act.length - 2];
  let diffHtml = "<span class='meta'>직전 거래 없음</span>";
  if (prev) {
    const diff = last.amount - prev.amount, pct = (diff / prev.amount * 100).toFixed(1);
    diffHtml = diff > 0 ? `<span class="diff-up">▲ ${fmtMoney(diff)} (+${pct}%)</span>`
             : diff < 0 ? `<span class="diff-down">▼ ${fmtMoney(-diff)} (${pct}%)</span>`
             : "<span>― 보합</span>";
  }
  cardsEl.insertAdjacentHTML("beforeend", `
    <div class="card">
      <h3>${last.apt_nm}</h3>
      <div class="band">전용 ${Math.floor(last.area)}㎡대 · ${last.umd_nm} · 기록 ${act.length}건</div>
      <div class="price">${fmtMoney(last.amount)}원</div>
      <div>${diffHtml}</div>
      <div class="meta">최근 계약 ${last.date} · ${last.floor || "?"}층</div>
    </div>`);
});

// ---- 가격 추이 차트 (inline SVG)
const sel = document.getElementById("groupSel");
Object.keys(groups).filter(k => activeOf(groups[k]).length >= 1)
  .forEach(k => sel.insertAdjacentHTML("beforeend",
    `<option value="${k}">${k} (${activeOf(groups[k]).length}건)</option>`));

function drawChart(key) {
  const data = activeOf(groups[key] || []);
  const el = document.getElementById("chart");
  if (!data.length) { el.innerHTML = "<div class='legend'>데이터 없음</div>"; return; }
  const W = 860, H = 300, P = {l: 70, r: 20, t: 16, b: 40};
  const xs = data.map(d => new Date(d.date).getTime());
  const ys = data.map(d => d.amount);
  const x0 = Math.min(...xs), x1 = Math.max(...xs) || x0 + 1;
  const yMin = Math.min(...ys), yMax = Math.max(...ys);
  const pad = Math.max((yMax - yMin) * 0.15, yMax * 0.02, 500);
  const y0 = yMin - pad, y1 = yMax + pad;
  const X = t => xs.length > 1 && x1 > x0
    ? P.l + (t - x0) / (x1 - x0) * (W - P.l - P.r) : (P.l + W - P.r) / 2;
  const Y = v => H - P.b - (v - y0) / (y1 - y0) * (H - P.t - P.b);
  let s = `<svg viewBox="0 0 ${W} ${H}" style="width:100%;max-width:${W}px">`;
  for (let i = 0; i <= 4; i++) {
    const v = y0 + (y1 - y0) * i / 4, y = Y(v);
    s += `<line x1="${P.l}" y1="${y}" x2="${W - P.r}" y2="${y}" stroke="#e5e7eb"/>`
       + `<text x="${P.l - 8}" y="${y + 4}" text-anchor="end" font-size="11" fill="#6b7280">${fmtMoney(Math.round(v))}</text>`;
  }
  if (data.length > 1) {
    const pts = data.map(d => `${X(new Date(d.date).getTime())},${Y(d.amount)}`).join(" ");
    s += `<polyline points="${pts}" fill="none" stroke="#0f766e" stroke-width="2"/>`;
  }
  data.forEach(d => {
    const cx = X(new Date(d.date).getTime()), cy = Y(d.amount);
    s += `<circle cx="${cx}" cy="${cy}" r="4" fill="#0f766e">`
       + `<title>${d.date} · ${d.floor || "?"}층 · ${fmtMoney(d.amount)}원</title></circle>`;
  });
  const labelStep = Math.max(1, Math.ceil(data.length / 8));
  data.forEach((d, i) => {
    if (i % labelStep) return;
    s += `<text x="${X(new Date(d.date).getTime())}" y="${H - P.b + 18}" text-anchor="middle" font-size="11" fill="#6b7280">${d.date.slice(2)}</text>`;
  });
  s += "</svg>";
  el.innerHTML = s + `<div class="legend">점 위에 마우스를 올리면 층·금액이 표시됩니다. 해제 거래는 제외.</div>`;
}
sel.addEventListener("change", () => drawChart(sel.value));
if (sel.options.length) { sel.value = sel.options[0].value; drawChart(sel.value); }

// ---- 거래 테이블
const rowsEl = document.getElementById("rows");
DEALS.slice().sort((a,b) => b.date.localeCompare(a.date)).forEach(d => {
  const g = activeOf(groups[groupKey(d)]);
  const idx = g.findIndex(x => x.date === d.date && x.amount === d.amount && x.floor === d.floor);
  let diff = "—";
  if (!d.cancelled && idx > 0) {
    const dv = d.amount - g[idx - 1].amount;
    const pct = (dv / g[idx - 1].amount * 100).toFixed(1);
    diff = dv > 0 ? `<span class="diff-up">+${fmtMoney(dv)} (+${pct}%)</span>`
         : dv < 0 ? `<span class="diff-down">${fmtMoney(dv)} (${pct}%)</span>` : "보합";
  }
  rowsEl.insertAdjacentHTML("beforeend", `
    <tr class="${d.cancelled ? "cancelled" : ""}">
      <td>${d.date}</td><td>${d.apt_nm}</td><td>${d.area}</td>
      <td>${d.floor || "?"}</td><td><b>${fmtMoney(d.amount)}</b></td>
      <td>${diff}</td>
      <td>${d.cancelled ? '<span class="badge">해제</span>' : (d.dealing_gbn || "")}</td>
    </tr>`);
});
</script>
</body>
</html>
"""


def render_dashboard(state, cfg, out_path):
    deals = sorted(state.get("deals", {}).values(), key=lambda d: d["date"])
    html = (_TEMPLATE
            .replace("__LAST_RUN__", state.get("last_run", "-"))
            .replace("__TOTAL__", str(len(deals)))
            .replace("__DEALS__", json.dumps(deals, ensure_ascii=False)))
    out_path.write_text(html, encoding="utf-8")
