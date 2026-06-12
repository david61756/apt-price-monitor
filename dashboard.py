"""state.json → 정적 대시보드(docs/index.html) 생성.

외부 라이브러리·CDN 없이 단일 HTML로 렌더링하므로 GitHub Pages나
로컬 파일 열기 모두에서 동작한다.

탭 구성:
  - 대시보드: 단지·평형별 요약 카드 / 가격 추이 차트 / 거래 내역(단지별 필터)
  - 단지 관리: config.yaml의 관심 단지를 폼으로 편집해 GitHub API로 직접 커밋
"""
import json
from pathlib import Path

_SGG_PATH = Path(__file__).resolve().parent / "sgg_codes.json"

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
  .sub { color: var(--sub); font-size: 13px; margin-bottom: 16px; }
  .tabs { display: flex; gap: 8px; margin-bottom: 18px; }
  .tabs button { padding: 9px 18px; border: 1px solid var(--line); border-radius: 99px;
                 background: var(--card); font-size: 14px; cursor: pointer; color: var(--sub); }
  .tabs button.active { background: var(--accent); border-color: var(--accent);
                        color: #fff; font-weight: 600; }
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
  tr.grp td { background: #f0fdfa; color: var(--accent); font-weight: 700;
              text-align: left; text-decoration: none; font-size: 13px; }
  .badge { display: inline-block; padding: 1px 7px; border-radius: 99px;
           font-size: 11px; background: #fee2e2; color: #b91c1c; text-decoration: none; }
  select, input[type=text], input[type=password] {
    padding: 7px 10px; border: 1px solid var(--line); border-radius: 8px;
    font-size: 13px; background: #fff; }
  .legend { font-size: 12px; color: var(--sub); margin-top: 8px; }
  .toolbar { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; margin-bottom: 12px; }
  .toolbar .cnt { font-size: 12px; color: var(--sub); }
  /* 단지 관리 */
  .cfg-row { display: grid; grid-template-columns: 1.2fr 1fr 1.2fr 0.7fr auto;
             gap: 8px; align-items: start; padding: 10px 0; border-bottom: 1px dashed var(--line); }
  .cfg-row input { width: 100%; }
  .cfg-head { font-size: 12px; color: var(--sub); font-weight: 600; padding-bottom: 4px; }
  .hint { font-size: 11px; margin-top: 3px; min-height: 14px; }
  .hint.ok { color: var(--accent); } .hint.err { color: var(--up); }
  button.btn { padding: 9px 16px; border-radius: 8px; border: 1px solid var(--line);
               background: #fff; font-size: 13px; cursor: pointer; }
  button.btn.primary { background: var(--accent); border-color: var(--accent);
                       color: #fff; font-weight: 600; }
  button.btn.danger { color: var(--up); }
  .save-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
               gap: 10px; margin: 12px 0; }
  .save-grid label { font-size: 12px; color: var(--sub); display: block; margin-bottom: 4px; }
  .save-grid input { width: 100%; }
  #saveStatus { margin-top: 12px; font-size: 13px; white-space: pre-wrap; }
  .note { font-size: 12px; color: var(--sub); background: #f9fafb; border: 1px solid var(--line);
          border-radius: 8px; padding: 10px 12px; margin-top: 14px; line-height: 1.7; }
</style>
</head>
<body>
<h1>🏠 아파트 실거래가 모니터</h1>
<div class="sub">마지막 갱신: __LAST_RUN__ · 누적 기록 __TOTAL__건</div>

<div class="tabs">
  <button id="tabBtnDash" class="active" onclick="showTab('dash')">📊 대시보드</button>
  <button id="tabBtnManage" onclick="showTab('manage')">⚙️ 단지 관리</button>
</div>

<div id="tab-dash">
  <div class="cards" id="cards"></div>

  <div class="section">
    <h2>가격 추이</h2>
    <select id="groupSel"></select>
    <div id="chart"></div>
  </div>

  <div class="section">
    <h2>거래 내역</h2>
    <div class="toolbar">
      <select id="aptSel"></select>
      <span class="cnt" id="rowCnt"></span>
    </div>
    <table>
      <thead><tr><th>계약일</th><th>단지</th><th>전용(㎡)</th><th>층</th>
                 <th>거래금액</th><th>직전대비</th><th>비고</th></tr></thead>
      <tbody id="rows"></tbody>
    </table>
  </div>
</div>

<div id="tab-manage" style="display:none">
  <div class="section">
    <h2>관심 단지 편집</h2>
    <div class="cfg-row cfg-head" style="border-bottom:1px solid var(--line)">
      <div>표시 이름</div><div>지역 (시군구명 또는 코드 5자리)</div>
      <div>단지명 키워드 (쉼표 구분)</div><div>전용면적 ㎡ (쉼표)</div><div></div>
    </div>
    <div id="cfgRows"></div>
    <div style="margin-top:12px">
      <button class="btn" onclick="addCfgRow()">＋ 단지 추가</button>
    </div>
  </div>

  <div class="section">
    <h2>GitHub에 저장</h2>
    <div class="save-grid">
      <div><label>저장소 소유자(아이디)</label><input type="text" id="ghOwner"></div>
      <div><label>저장소 이름</label><input type="text" id="ghRepo"></div>
      <div><label>GitHub 토큰 (repo·workflow 권한)</label><input type="password" id="ghToken" placeholder="ghp_..."></div>
    </div>
    <button class="btn primary" onclick="saveToGitHub()">💾 GitHub에 저장 (config.yaml 커밋)</button>
    <button class="btn" onclick="runNow()">▶ 모니터링 지금 실행</button>
    <button class="btn" onclick="copyYaml()">📋 YAML 복사</button>
    <a class="btn" id="editLink" style="text-decoration:none;display:inline-block" target="_blank">✏️ GitHub에서 직접 편집</a>
    <div id="saveStatus"></div>
    <div class="note">
      · 저장하면 config.yaml이 GitHub에 바로 커밋되고, <b>다음 자동 실행(매일 09:00 KST)부터 반영</b>됩니다.
        바로 반영하려면 "모니터링 지금 실행"을 누르세요 (1~2분 후 이 페이지 새로고침).<br>
      · 토큰은 이 브라우저(localStorage)에만 저장되며 저장소에는 올라가지 않습니다.
        공용 PC에서는 입력하지 마세요.<br>
      · 지역명이 모호하면(예: 고성군) 시도명을 포함하거나 법정동코드 5자리를 직접 입력하세요.
        입력란 아래에 변환된 코드가 즉시 표시됩니다.
    </div>
  </div>
</div>

<script>
const DEALS = __DEALS__;
const CONFIG = __CONFIG__;
const SGG = __SGG__;

// ============================== 공통 유틸 ==============================
function fmtMoney(man) {
  const sign = man < 0 ? "-" : ""; man = Math.abs(man);
  const eok = Math.floor(man / 10000), rest = man % 10000;
  if (eok && rest) return sign + eok + "억 " + rest.toLocaleString();
  if (eok) return sign + eok + "억";
  return sign + rest.toLocaleString() + "만";
}
const groupKey = d => d.apt_nm + " " + Math.floor(d.area) + "㎡";

function showTab(name) {
  document.getElementById("tab-dash").style.display = name === "dash" ? "" : "none";
  document.getElementById("tab-manage").style.display = name === "manage" ? "" : "none";
  document.getElementById("tabBtnDash").classList.toggle("active", name === "dash");
  document.getElementById("tabBtnManage").classList.toggle("active", name === "manage");
}

// 그룹별(단지+면적대) 정렬된 거래
const groups = {};
DEALS.slice().sort((a,b) => a.date.localeCompare(b.date)).forEach(d => {
  (groups[groupKey(d)] = groups[groupKey(d)] || []).push(d);
});
const activeOf = g => g.filter(d => !d.cancelled);

// ============================== 요약 카드 ==============================
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

// ============================== 가격 추이 차트 ==============================
const sel = document.getElementById("groupSel");
Object.keys(groups).sort().filter(k => activeOf(groups[k]).length >= 1)
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

// ============================== 거래 내역 (단지별 분류) ==============================
const aptSel = document.getElementById("aptSel");
const aptNames = [...new Set(DEALS.map(d => d.apt_nm))].sort();
aptSel.insertAdjacentHTML("beforeend", `<option value="__all__">전체 단지 (최신순)</option>`);
aptSel.insertAdjacentHTML("beforeend", `<option value="__grouped__">전체 단지 (단지별 묶음)</option>`);
aptNames.forEach(n => {
  const cnt = DEALS.filter(d => d.apt_nm === n).length;
  aptSel.insertAdjacentHTML("beforeend", `<option value="${n}">${n} (${cnt}건)</option>`);
});

function rowHtml(d) {
  const g = activeOf(groups[groupKey(d)]);
  const idx = g.findIndex(x => x.date === d.date && x.amount === d.amount && x.floor === d.floor);
  let diff = "—";
  if (!d.cancelled && idx > 0) {
    const dv = d.amount - g[idx - 1].amount;
    const pct = (dv / g[idx - 1].amount * 100).toFixed(1);
    diff = dv > 0 ? `<span class="diff-up">+${fmtMoney(dv)} (+${pct}%)</span>`
         : dv < 0 ? `<span class="diff-down">${fmtMoney(dv)} (${pct}%)</span>` : "보합";
  }
  return `
    <tr class="${d.cancelled ? "cancelled" : ""}">
      <td>${d.date}</td><td>${d.apt_nm}</td><td>${d.area}</td>
      <td>${d.floor || "?"}</td><td><b>${fmtMoney(d.amount)}</b></td>
      <td>${diff}</td>
      <td>${d.cancelled ? '<span class="badge">해제</span>' : (d.dealing_gbn || "")}</td>
    </tr>`;
}

function renderTable() {
  const mode = aptSel.value;
  const rowsEl = document.getElementById("rows");
  rowsEl.innerHTML = "";
  let shown = 0;
  if (mode === "__grouped__") {
    aptNames.forEach(n => {
      const list = DEALS.filter(d => d.apt_nm === n)
                        .sort((a,b) => b.date.localeCompare(a.date));
      const act = list.filter(d => !d.cancelled);
      const latest = act.length ? ` · 최신 ${fmtMoney(act[0].amount)}원 (${act[0].date})` : "";
      rowsEl.insertAdjacentHTML("beforeend",
        `<tr class="grp"><td colspan="7">📍 ${n} — ${list.length}건${latest}</td></tr>`);
      list.forEach(d => rowsEl.insertAdjacentHTML("beforeend", rowHtml(d)));
      shown += list.length;
    });
  } else {
    const list = DEALS.filter(d => mode === "__all__" || d.apt_nm === mode)
                      .sort((a,b) => b.date.localeCompare(a.date));
    list.forEach(d => rowsEl.insertAdjacentHTML("beforeend", rowHtml(d)));
    shown = list.length;
  }
  document.getElementById("rowCnt").textContent = `${shown}건 표시`;
}
aptSel.addEventListener("change", renderTable);
renderTable();

// ============================== 단지 관리 탭 ==============================
// 시군구명 → 법정동코드 (lawd.py와 동일 로직)
function resolveLawd(region) {
  region = region.trim().split(/\\s+/).join(" ");
  if (!region) return {err: "지역을 입력하세요"};
  if (/^\\d{5}$/.test(region)) return {code: region, name: "코드 직접 지정"};
  if (SGG[region]) return {code: SGG[region], name: region};
  const q = region.split(" ");
  const cands = [];
  for (const [name, code] of Object.entries(SGG)) {
    const nt = name.split(" ");
    let i = 0, ok = true;
    for (const qt of q) {
      while (i < nt.length && !nt[i].includes(qt)) i++;
      if (i === nt.length) { ok = false; break; }
      i++;
    }
    if (ok) cands.push({name, code});
  }
  if (cands.length === 1) return cands[0];
  if (!cands.length) return {err: "일치하는 시군구 없음"};
  return {err: "여러 곳 일치: " + cands.slice(0, 4).map(c => c.name).join(", ")};
}

function addCfgRow(c) {
  c = c || {name: "", region: "", match: [], areas: []};
  const region = c.region || c.lawd_cd || "";
  const div = document.createElement("div");
  div.className = "cfg-row";
  div.innerHTML = `
    <div><input type="text" class="f-name" value="${(c.name||"").replace(/"/g,'&quot;')}" placeholder="예: 송도더샵 (전용 84)"></div>
    <div><input type="text" class="f-region" value="${String(region).replace(/"/g,'&quot;')}" placeholder="예: 인천 연수구">
         <div class="hint f-hint"></div></div>
    <div><input type="text" class="f-match" value="${(c.match||[]).join(", ").replace(/"/g,'&quot;')}" placeholder="예: 송도더샵 (비우면 표시이름으로 매칭)"></div>
    <div><input type="text" class="f-areas" value="${(c.areas||[]).join(", ")}" placeholder="예: 84 (비우면 전체)"></div>
    <div><button class="btn danger" onclick="this.closest('.cfg-row').remove()">삭제</button></div>`;
  const regionInput = div.querySelector(".f-region");
  const hint = div.querySelector(".f-hint");
  const update = () => {
    if (!regionInput.value.trim()) { hint.textContent = ""; return; }
    const r = resolveLawd(regionInput.value);
    hint.className = "hint f-hint " + (r.err ? "err" : "ok");
    hint.textContent = r.err ? "⚠ " + r.err : `✓ ${r.name} (${r.code})`;
  };
  regionInput.addEventListener("input", update);
  update();
  document.getElementById("cfgRows").appendChild(div);
}
(CONFIG.complexes || []).forEach(addCfgRow);

function gatherCfg() {
  const complexes = [], errors = [];
  document.querySelectorAll("#cfgRows .cfg-row").forEach((row, i) => {
    const name = row.querySelector(".f-name").value.trim();
    const region = row.querySelector(".f-region").value.trim();
    const match = row.querySelector(".f-match").value.split(",").map(s => s.trim()).filter(Boolean);
    const areas = row.querySelector(".f-areas").value.split(",").map(s => s.trim()).filter(Boolean);
    if (!name && !region) return; // 빈 행 무시
    if (!name) errors.push(`${i + 1}번째 행: 표시 이름이 비어 있습니다`);
    const r = resolveLawd(region);
    if (r.err) errors.push(`${i + 1}번째 행(${name || "?"}): ${r.err}`);
    if (areas.some(a => !/^\\d+$/.test(a)))
      errors.push(`${i + 1}번째 행(${name || "?"}): 전용면적은 숫자만 입력하세요`);
    const entry = {name, match, areas: areas.map(Number)};
    if (/^\\d{5}$/.test(region)) entry.lawd_cd = region; else entry.region = region;
    complexes.push(entry);
  });
  if (!complexes.length) errors.push("단지가 하나도 없습니다");
  return {complexes, errors};
}

function yamlStr(s) { return '"' + String(s).replace(/\\\\/g, "\\\\\\\\").replace(/"/g, '\\\\"') + '"'; }
function buildYaml(complexes) {
  const opt = CONFIG.options || {};
  let out = "# 관심 단지 설정 — 대시보드 '단지 관리' 탭에서 생성됨\\n";
  out += "# region: 시군구명(자동 변환) / lawd_cd: 법정동코드 5자리 직접 지정\\n";
  out += "# match: 단지명 부분일치 키워드 / areas: 전용면적 ㎡ 정수 대역(생략 시 전체)\\n\\n";
  out += "complexes:\\n";
  for (const c of complexes) {
    out += `  - name: ${yamlStr(c.name)}\\n`;
    if (c.lawd_cd) out += `    lawd_cd: ${yamlStr(c.lawd_cd)}\\n`;
    else out += `    region: ${yamlStr(c.region)}\\n`;
    if (c.match.length) out += `    match: [${c.match.map(yamlStr).join(", ")}]\\n`;
    if (c.areas.length) out += `    areas: [${c.areas.join(", ")}]\\n`;
  }
  out += `\\noptions:\\n  months_back: ${opt.months_back ?? 1}\\n`;
  out += `  notify_cancellations: ${opt.notify_cancellations ?? true}\\n`;
  return out;
}

// GitHub 연동
const ownerEl = document.getElementById("ghOwner");
const repoEl = document.getElementById("ghRepo");
const tokenEl = document.getElementById("ghToken");
(function initRepoFields() {
  let owner = localStorage.getItem("gh_owner") || "";
  let repo = localStorage.getItem("gh_repo") || "";
  if (location.hostname.endsWith(".github.io")) {
    owner = location.hostname.split(".")[0];
    repo = location.pathname.split("/").filter(Boolean)[0] || repo;
  }
  ownerEl.value = owner; repoEl.value = repo;
  tokenEl.value = localStorage.getItem("gh_token") || "";
  updateEditLink();
})();
function updateEditLink() {
  document.getElementById("editLink").href =
    `https://github.com/${ownerEl.value}/${repoEl.value}/edit/main/config.yaml`;
}
ownerEl.addEventListener("input", updateEditLink);
repoEl.addEventListener("input", updateEditLink);

function setStatus(msg, ok) {
  const el = document.getElementById("saveStatus");
  el.textContent = msg;
  el.style.color = ok ? "var(--accent)" : "var(--up)";
}

async function gh(path, opts = {}) {
  const r = await fetch(`https://api.github.com/repos/${ownerEl.value}/${repoEl.value}/${path}`, {
    ...opts,
    headers: {Authorization: `Bearer ${tokenEl.value.trim()}`,
              Accept: "application/vnd.github+json", ...(opts.headers || {})},
  });
  if (!r.ok) {
    const t = await r.text();
    throw new Error(`GitHub API ${r.status}: ${t.slice(0, 200)}`);
  }
  return r.status === 204 ? null : r.json();
}

function persistFields() {
  localStorage.setItem("gh_owner", ownerEl.value);
  localStorage.setItem("gh_repo", repoEl.value);
  localStorage.setItem("gh_token", tokenEl.value.trim());
}

async function saveToGitHub() {
  const {complexes, errors} = gatherCfg();
  if (errors.length) { setStatus("입력 오류:\\n· " + errors.join("\\n· "), false); return; }
  if (!ownerEl.value || !repoEl.value || !tokenEl.value.trim()) {
    setStatus("저장소 소유자/이름/토큰을 모두 입력하세요", false); return;
  }
  persistFields();
  setStatus("저장 중...", true);
  try {
    const yaml = buildYaml(complexes);
    const cur = await gh("contents/config.yaml?ref=main");
    const bytes = new TextEncoder().encode(yaml);
    let bin = ""; bytes.forEach(b => bin += String.fromCharCode(b));
    await gh("contents/config.yaml", {method: "PUT", body: JSON.stringify({
      message: "config: 대시보드에서 관심단지 수정",
      content: btoa(bin), sha: cur.sha, branch: "main"})});
    setStatus(`✅ 저장 완료 (단지 ${complexes.length}개). 다음 자동 실행부터 반영됩니다.\\n` +
              `바로 반영하려면 "모니터링 지금 실행"을 누르세요.`, true);
  } catch (e) { setStatus("❌ 저장 실패: " + e.message, false); }
}

async function runNow() {
  if (!ownerEl.value || !repoEl.value || !tokenEl.value.trim()) {
    setStatus("저장소 소유자/이름/토큰을 모두 입력하세요", false); return;
  }
  persistFields();
  setStatus("실행 요청 중...", true);
  try {
    await gh("actions/workflows/monitor.yml/dispatches",
             {method: "POST", body: JSON.stringify({ref: "main"})});
    setStatus("✅ 실행 요청 완료. 1~2분 후 이 페이지를 새로고침하면 결과가 반영됩니다.", true);
  } catch (e) { setStatus("❌ 실행 요청 실패: " + e.message, false); }
}

function copyYaml() {
  const {complexes, errors} = gatherCfg();
  if (errors.length) { setStatus("입력 오류:\\n· " + errors.join("\\n· "), false); return; }
  navigator.clipboard.writeText(buildYaml(complexes))
    .then(() => setStatus("📋 YAML이 복사되었습니다. config.yaml에 붙여넣으세요.", true))
    .catch(() => setStatus("복사 실패 — 'GitHub에서 직접 편집'을 이용하세요.", false));
}
</script>
</body>
</html>
"""


def render_dashboard(state, cfg, out_path):
    deals = sorted(state.get("deals", {}).values(), key=lambda d: d["date"])
    config_pub = {
        "complexes": [
            {"name": c["name"],
             **({"region": c["region"]} if c.get("region") else {"lawd_cd": c["lawd_cd"]}),
             "match": c.get("match") or [],
             "areas": c.get("areas") or []}
            for c in cfg.get("complexes", [])
        ],
        "options": cfg.get("options") or {},
    }
    sgg = json.loads(_SGG_PATH.read_text(encoding="utf-8"))
    html = (_TEMPLATE
            .replace("__LAST_RUN__", state.get("last_run", "-"))
            .replace("__TOTAL__", str(len(deals)))
            .replace("__DEALS__", json.dumps(deals, ensure_ascii=False))
            .replace("__CONFIG__", json.dumps(config_pub, ensure_ascii=False))
            .replace("__SGG__", json.dumps(sgg, ensure_ascii=False)))
    out_path.write_text(html, encoding="utf-8")
