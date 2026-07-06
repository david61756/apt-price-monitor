"""state.json → 정적 대시보드(docs/index.html) 생성.

외부 라이브러리·CDN 없이 단일 HTML로 렌더링하므로 GitHub Pages나
로컬 파일 열기 모두에서 동작한다.

탭 구성:
  - 대시보드: 단지·평형별 요약 카드 / 가격 추이 차트 / 거래 내역(단지별 필터)
  - 단지 관리: config.yaml의 관심 단지를 폼으로 편집해 GitHub API로 직접 커밋
"""
import json
from pathlib import Path

from matching import matching_complex_name
from quotes import quote_in_config

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
  .tabs { display: flex; gap: 8px; margin-bottom: 18px; flex-wrap: wrap; }
  .tabs button { padding: 9px 18px; border: 1px solid var(--line); border-radius: 99px;
                 background: var(--card); font-size: 14px; cursor: pointer; color: var(--sub);
                 white-space: nowrap; }
  .tabs button.active { background: var(--accent); border-color: var(--accent);
                        color: #fff; font-weight: 600; }
  .cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
           gap: 14px; margin-bottom: 24px; }
  .region-head { grid-column: 1 / -1; display: flex; align-items: center; gap: 8px;
                 font-size: 14px; font-weight: 700; color: var(--accent);
                 margin: 10px 0 -2px; padding-bottom: 6px; border-bottom: 2px solid var(--line); }
  .region-head:first-child { margin-top: 0; }
  /* 카드 순서 편집 UI */
  .ord-bar { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-bottom: 12px; }
  .ord-bar .ord-hint { font-size: 11px; color: var(--sub); }
  .ord-status { font-size: 12px; color: var(--accent); font-weight: 600; }
  .region-head .reg-move { display: none; }
  .region-head .reg-move button { border: 1px solid var(--line); background: #fff; border-radius: 6px;
                 cursor: pointer; font-size: 11px; line-height: 1; padding: 2px 7px; }
  body.editorder .region-head .reg-move { display: inline-flex; gap: 4px; }
  body.editorder #cards .card, body.editorder #qCards .card { cursor: grab; }
  .card.dragover { outline: 2px dashed var(--accent); outline-offset: 2px; }
  .card { background: var(--card); border: 1px solid var(--line); border-radius: 12px;
          padding: 16px 18px; }
  .card h3 { margin: 0 0 2px; font-size: 15px; }
  .card .band { color: var(--sub); font-size: 12px; margin-bottom: 10px; }
  .card .price { font-size: 22px; font-weight: 700; }
  .card .meta { font-size: 12px; color: var(--sub); margin-top: 6px; }
  .card .pyeong { font-size: 12px; color: var(--accent); font-weight: 600; margin-top: 4px; }
  /* 요약 카드: 클릭 시 가격추이·거래내역을 해당 단지로 필터(다시 클릭 시 해제). 매매·호가 공통 */
  #cards .card, #qCards .card { cursor: pointer; transition: box-shadow .12s, border-color .12s; }
  #cards .card:hover, #qCards .card:hover { border-color: #94a3b8; }
  #cards .card.sel, #qCards .card.sel { border-color: var(--accent); box-shadow: 0 0 0 2px var(--accent) inset; background: #f0fdfa; }
  #cards .card .selhint, #qCards .card .selhint { font-size: 11px; color: #94a3b8; margin-top: 8px; }
  #cards .card.sel .selhint, #qCards .card.sel .selhint { color: var(--accent); }
  .diff-up { color: var(--up); font-weight: 600; }
  .diff-down { color: var(--down); font-weight: 600; }
  .section { background: var(--card); border: 1px solid var(--line);
             border-radius: 12px; padding: 18px; margin-bottom: 24px; }
  .section h2 { font-size: 16px; margin: 0 0 12px; }
  svg text { font-family: inherit; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  /* 모바일: 표를 가로 스크롤(컬럼 글자단위 줄바꿈 방지), 탭/여백 축소 */
  @media (max-width: 640px) {
    body { padding: 14px; }
    .tabs button { padding: 8px 13px; font-size: 13px; }
    table { display: block; overflow-x: auto; white-space: nowrap; }
    .cfg-row { grid-template-columns: 1fr; gap: 6px; }
  }
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
  .cfg-row { display: grid; grid-template-columns: 1.1fr 0.9fr 1fr 0.6fr 0.95fr auto;
             gap: 8px; align-items: start; padding: 10px 0; border-bottom: 1px dashed var(--line); }
  .cfg-row input { width: 100%; }
  .naver-cell { display: flex; gap: 4px; }
  .naver-cell input { min-width: 0; }
  .naver-cell .btn { padding: 9px 10px; white-space: nowrap; }
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
  .warn { background: #fffbeb; border: 1px solid #fcd34d; border-radius: 12px;
          padding: 14px 16px; margin-bottom: 20px; font-size: 13px; color: #92400e; line-height: 1.7; }
  .warn b { color: #b45309; }
  .warn code { background: #fef3c7; padding: 1px 5px; border-radius: 4px; }
  .warn a { color: #b45309; }
</style>
</head>
<body>
<h1>🏠 아파트 실거래가 모니터</h1>
<div class="sub">매매 갱신: __LAST_RUN__ · 관심단지 __WATCHED__곳 · 표시 거래 __TOTAL__건<span id="quotesRunHdr"></span></div>

<div id="warnBanner"></div>

<div class="tabs">
  <button id="tabBtnDash" class="active" onclick="showTab('dash')">📊 매매 실거래</button>
  <button id="tabBtnQuotes" onclick="showTab('quotes')">🏷️ 호가</button>
  <button id="tabBtnManage" onclick="showTab('manage')">⚙️ 단지 관리</button>
</div>

<div id="tab-dash">
  <div class="ord-bar">
    <button class="btn ord-edit-btn" type="button" onclick="toggleOrderEdit()">🔀 순서 편집</button>
    <button class="btn primary" type="button" onclick="saveCardOrder()">💾 순서 저장(로컬 공유)</button>
    <button class="btn" type="button" onclick="resetCardOrder()">🔄 공유순서 불러오기</button>
    <span class="ord-status"></span>
    <span class="ord-hint">편집 켜고 카드 드래그(같은 지역 내)·지역 ▲▼로 변경 후 저장. 자동저장: <code>python3 order_server.py</code> 실행 후 <code>localhost:8787</code> 접속(저장 시 자동 커밋·공유). Pages접속 시엔 클립보드→<code>bash save_order.sh</code></span>
  </div>
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

<div id="tab-quotes" style="display:none">
  <div id="quotesEmpty" class="section" style="display:none">
    <h2>🏷️ 호가 데이터가 아직 없습니다</h2>
    <div class="legend" style="line-height:1.8">
      네이버페이 부동산 호가는 로그인된 브라우저 세션으로 수집합니다.
      <code>python quotes_monitor.py</code> 를 한 번 실행하면 이 탭에 매물 호가가 채워집니다.
      (단지별 <code>naver_id</code> 설정과 <code>.env</code>의 네이버 세션이 필요 — README 참고)<br>
      ⚠ 호가는 <b>과거 조회(백필)가 불가능</b>합니다. 수집을 시작한 날부터의 스냅샷만 쌓입니다.
    </div>
  </div>
  <div id="quotesBody">
    <div id="qWarnBanner"></div>
    <div class="ord-bar">
      <button class="btn ord-edit-btn" type="button" onclick="toggleOrderEdit()">🔀 순서 편집</button>
      <button class="btn primary" type="button" onclick="saveCardOrder()">💾 순서 저장(로컬 공유)</button>
      <button class="btn" type="button" onclick="resetCardOrder()">🔄 공유순서 불러오기</button>
      <span class="ord-status"></span>
      <span class="ord-hint">지역/단지 순서는 매매·호가 탭 공통입니다.</span>
    </div>
    <div class="cards" id="qCards"></div>
    <div class="section">
      <h2>호가 추이 <span class="legend" id="qTrackSince"></span></h2>
      <select id="qGroupSel"></select>
      <div id="qChart"></div>
    </div>
    <div class="section">
      <h2>현재 호가 <span class="legend">(동일세대 묶음 — 클릭하면 중개사별 펼침)</span></h2>
      <div class="toolbar">
        <select id="qAptSel"></select>
        <label style="font-size:12px;color:var(--sub)">
          <input type="checkbox" id="qShowGone"> 내려간 매물 포함</label>
        <span class="cnt" id="qRowCnt"></span>
      </div>
      <table>
        <thead><tr><th>확인일</th><th>단지</th><th>전용(㎡)</th><th>동·층</th>
                   <th>호가</th><th>직전대비</th><th>비고</th></tr></thead>
        <tbody id="qRows"></tbody>
      </table>
    </div>
    <div class="section">
      <h2>호가 변동·소멸 이력 <span class="legend">(최신순)</span></h2>
      <table>
        <thead><tr><th>날짜</th><th>단지</th><th>동·층</th><th>전용</th>
                   <th>변동</th><th>비고</th></tr></thead>
        <tbody id="qHistory"></tbody>
      </table>
    </div>
  </div>
</div>

<div id="tab-manage" style="display:none">
  <div class="section">
    <h2>관심 단지 편집</h2>
    <div class="cfg-row cfg-head" style="border-bottom:1px solid var(--line)">
      <div>표시 이름</div><div>지역 (시군구명 또는 코드 5자리)</div>
      <div>단지명 키워드 (쉼표 구분)</div><div>전용면적 ㎡ (쉼표)</div>
      <div>네이버 단지번호 (호가)</div><div></div>
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
    </div>
    <button class="btn primary" onclick="copyYaml()">📋 YAML 복사</button>
    <a class="btn" id="editLink" style="text-decoration:none;display:inline-block" target="_blank">✏️ GitHub에서 직접 편집</a>
    <div id="saveStatus"></div>
    <div class="note">
      · 단지를 편집한 뒤 <b>"✏️ GitHub에서 직접 편집"</b>으로 config.yaml을 저장하면(또는 <b>"📋 YAML 복사"</b> 후 붙여넣기),
        내 Mac이 변경을 감지해 <b>자동으로 데이터를 갱신</b>합니다(최대 15분, Mac이 켜져 있어야 함).<br>
      · 갱신 후 <b>2~3분 뒤</b> 이 페이지를 <b>새로고침</b>하면 결과가 보입니다
        (GitHub Pages 갱신에 약간 시간이 걸리며, 안 보이면 Shift+새로고침으로 캐시를 비우세요).
        바로 받으려면 터미널에서 <code>bash run_quotes.sh</code> 실행.<br>
      · 단지명(match)은 <b>실제 등록명과 정확히 일치</b>해야 합니다(괄호·'촌' 등 포함).
        헷갈리면 로컬에서 <code>python search.py "지역명" 키워드</code> 로 실제 단지명·전용면적을 확인하세요.<br>
      · <b>네이버 단지번호(호가)</b>가 비어 있으면 그 단지는 <b>호가가 수집되지 않습니다</b>.
        직접 입력하거나 <b>🔍 찾기</b>를 눌러 자동 조회하세요(실패 시 새 탭이 열리니 주소의 번호를 복사).<br>
    </div>
  </div>
</div>

<script>
const DEALS = __DEALS__;
const CONFIG = __CONFIG__;
const REGION_MAP = __REGION_MAP__;
const SGG = __SGG__;
const WARNINGS = __WARNINGS__;
const QUOTES = __QUOTES__;
const QUOTES_META = __QUOTES_META__;
// 카드 지역별 그룹핑: config 단지명 → 지역 라벨
const regionOf = c => REGION_MAP[c] || "기타 지역";

// ============================== 공통 유틸 ==============================
function fmtMoney(man) {
  const sign = man < 0 ? "-" : ""; man = Math.abs(man);
  const eok = Math.floor(man / 10000), rest = man % 10000;
  if (eok && rest) return sign + eok + "억 " + rest.toLocaleString();
  if (eok) return sign + eok + "억";
  return sign + rest.toLocaleString() + "만";
}
const groupKey = d => d.apt_nm + " " + Math.floor(d.area) + "㎡";
// 전용면적 표시: 소수 2자리까지, 불필요한 0 제거 (74.1285 → 74.13, 73 → 73)
const fmtArea = a => (+a || 0).toFixed(2).replace(/\\.?0+$/, "");

// HTML 이스케이프 — 외부 문자열(네이버 단지명·중개사명 등)을 innerHTML에 넣기 전 적용(XSS 방지)
function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g,
    c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
}

function showTab(name) {
  for (const t of ["dash", "quotes", "manage"]) {
    document.getElementById("tab-" + t).style.display = name === t ? "" : "none";
  }
  document.getElementById("tabBtnDash").classList.toggle("active", name === "dash");
  document.getElementById("tabBtnQuotes").classList.toggle("active", name === "quotes");
  document.getElementById("tabBtnManage").classList.toggle("active", name === "manage");
}

// 매칭 0건 단지 경고 배너
(function renderWarnings() {
  if (!WARNINGS.length) return;
  const items = WARNINGS.map(w =>
    `<li><b>${esc(w.name)}</b> — 지역 <code>${esc(w.region)}</code>, ` +
    `단지명 <code>${esc((w.match||[]).join(", ")) || "(없음)"}</code>` +
    (w.areas && w.areas.length ? `, 전용 <code>${esc(w.areas.join(", "))}㎡</code>` : "") +
    `</li>`).join("");
  document.getElementById("warnBanner").innerHTML = `
    <div class="warn">
      ⚠ <b>아래 ${WARNINGS.length}개 단지는 매칭된 거래가 0건</b>입니다.
      단지명(match)이 실제 등록명과 다르거나, 전용면적(areas)이 실제와 다를 수 있습니다.
      <ul style="margin:8px 0 4px">${items}</ul>
      해결: <b>⚙️ 단지 관리</b> 탭에서 값을 수정하거나, 로컬에서
      <code>python search.py "지역명" 키워드</code> 로 실제 단지명·전용면적을 확인하세요.
      (실거래 신고가 없으면 일시적으로 0건일 수도 있습니다.)
    </div>`;
})();

// 그룹별(단지+면적대) 정렬된 거래
const groups = {};
DEALS.slice().sort((a,b) => a.date.localeCompare(b.date)).forEach(d => {
  (groups[groupKey(d)] = groups[groupKey(d)] || []).push(d);
});
const activeOf = g => g.filter(d => !d.cancelled);

// ============================== 요약 카드 ==============================
// 단지(config)별 현재 최저호가 — 매매 카드에 함께 구분 표시
const askMinByComplex = {};
QUOTES.filter(q => q.status === "active").forEach(q => {
  if (askMinByComplex[q.complex] == null || q.price < askMinByComplex[q.complex])
    askMinByComplex[q.complex] = q.price;
});

const cardsEl = document.getElementById("cards");
let __cardRegion = null;
Object.entries(groups)
  .filter(([key, g]) => activeOf(g).length)
  .sort((a, b) => {
    const la = activeOf(a[1]).slice(-1)[0], lb = activeOf(b[1]).slice(-1)[0];
    return regionOf(la.complex).localeCompare(regionOf(lb.complex))
        || String(la.apt_nm).localeCompare(String(lb.apt_nm));
  })
  .forEach(([key, g]) => {
  const act = activeOf(g);
  const last = act[act.length - 1], prev = act[act.length - 2];
  const __region = regionOf(last.complex);
  if (__region !== __cardRegion) {
    __cardRegion = __region;
    cardsEl.insertAdjacentHTML("beforeend", `<div class="region-head" data-region="${esc(__region)}"><span>📍 ${esc(__region)}</span>` +
      `<span class="reg-move"><button type="button" data-regmove="-1">▲</button>` +
      `<button type="button" data-regmove="1">▼</button></span></div>`);
  }
  let diffHtml = "<span class='meta'>직전 거래 없음</span>";
  if (prev) {
    const diff = last.amount - prev.amount, pct = (diff / prev.amount * 100).toFixed(1);
    diffHtml = diff > 0 ? `<span class="diff-up">▲ ${fmtMoney(diff)} (+${pct}%)</span>`
             : diff < 0 ? `<span class="diff-down">▼ ${fmtMoney(-diff)} (${pct}%)</span>`
             : "<span>― 보합</span>";
  }
  // 같은 단지의 현재 최저호가(있으면) — 실거래와 구분해 표시
  const ask = askMinByComplex[last.complex];
  let askHtml = "";
  if (ask != null) {
    const gap = ask - last.amount, p = (gap / last.amount * 100).toFixed(1);
    const cls = gap > 0 ? "diff-up" : gap < 0 ? "diff-down" : "";
    askHtml = `<div class="meta">🏷️ 현재 최저호가 <b>${fmtMoney(ask)}</b>`
      + ` <span class="${cls}">(${gap >= 0 ? "+" : ""}${p}%)</span></div>`;
  }
  // 평단가(만원/평) — 면적 다른 단지 비교용 핵심 지표
  const pyeong = last.area ? Math.round(last.amount * 3.3058 / last.area) : 0;
  const pyeongHtml = pyeong ? `<div class="pyeong">평단가 ${pyeong.toLocaleString()}만/평</div>` : "";
  // #2 신고가/신저가 배지 — 추적기간 내 최신 거래가 최고/최저일 때(표본 5건 이상에서만)
  const amts = act.map(d => d.amount);
  const isHigh = act.length >= 5 && last.amount === Math.max(...amts);
  const isLow = act.length >= 5 && last.amount === Math.min(...amts);
  const recBadge = isHigh ? `<span class="badge" style="background:#fee2e2;color:#b91c1c">🔺 신고가</span>`
                 : isLow ? `<span class="badge" style="background:#dbeafe;color:#1d4ed8">🔻 신저가</span>` : "";
  // #1 표본 부족 경고 — 거래 5건 미만이면 등락/호가갭이 불안정함을 고지
  const thinHtml = act.length < 5
    ? `<div class="meta" style="color:#b45309">⚠ 실거래 표본 ${act.length}건 · 추세·갭은 참고용</div>` : "";
  cardsEl.insertAdjacentHTML("beforeend", `
    <div class="card" data-key="${esc(key)}" data-apt="${esc(last.apt_nm)}" data-complex="${esc(last.complex)}" data-region="${esc(__region)}">
      <h3>${esc(last.apt_nm)} ${recBadge}</h3>
      <div class="band">전용 ${Math.floor(last.area)}㎡대 · ${esc(last.umd_nm)} · 기록 ${act.length}건</div>
      <div class="price">${fmtMoney(last.amount)}원 <span class="meta">실거래</span></div>
      <div>${diffHtml}</div>
      ${pyeongHtml}
      ${askHtml}
      ${thinHtml}
      <div class="meta">최근 계약 ${last.date} · ${last.floor || "?"}층</div>
      <div class="selhint">▸ 클릭하면 이 단지로 차트·내역 보기</div>
    </div>`);
});

// 카드 클릭 → 가격추이(차트)·거래내역(표)을 해당 단지로 필터. 같은 카드 재클릭 시 해제(토글).
let selCardKey = null;
function clearCardSel() {
  selCardKey = null;
  cardsEl.querySelectorAll(".card.sel").forEach(c => c.classList.remove("sel"));
}
cardsEl.addEventListener("click", e => {
  const card = e.target.closest(".card");
  if (!card) return;
  const key = card.dataset.key, apt = card.dataset.apt;
  if (selCardKey === key) {                         // 토글 해제 → 기본(전체)로 복귀
    clearCardSel();
    if (sel.options.length) { sel.value = sel.options[0].value; drawChart(sel.value); }
    aptSel.value = "__all__"; renderTable();
    return;
  }
  selCardKey = key;
  cardsEl.querySelectorAll(".card").forEach(c => c.classList.toggle("sel", c === card));
  if ([...sel.options].some(o => o.value === key)) { sel.value = key; drawChart(key); }
  aptSel.value = apt; renderTable();
  document.getElementById("chart").scrollIntoView({ behavior: "smooth", block: "center" });
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
  const W = 880, H = 330, P = {l: 78, r: 58, t: 26, b: 42};
  const xs = data.map(d => new Date(d.date).getTime());
  const ys = data.map(d => d.amount);
  const x0 = Math.min(...xs), x1 = Math.max(...xs) || x0 + 1;
  const yMin = Math.min(...ys), yMax = Math.max(...ys);
  const pad = Math.max((yMax - yMin) * 0.18, yMax * 0.03, 500);
  const y0 = yMin - pad, y1 = yMax + pad;
  const X = t => xs.length > 1 && x1 > x0
    ? P.l + (t - x0) / (x1 - x0) * (W - P.l - P.r) : (P.l + W - P.r) / 2;
  const Y = v => H - P.b - (v - y0) / (y1 - y0) * (H - P.t - P.b);
  const pts = data.map(d => [X(new Date(d.date).getTime()), Y(d.amount)]);
  let s = `<svg viewBox="0 0 ${W} ${H}" style="width:100%;max-width:${W}px">`;
  s += `<defs><linearGradient id="gradDeal" x1="0" y1="0" x2="0" y2="1">`
     + `<stop offset="0" stop-color="#0f766e" stop-opacity="0.20"/>`
     + `<stop offset="1" stop-color="#0f766e" stop-opacity="0"/></linearGradient></defs>`;
  for (let i = 0; i <= 4; i++) {
    const v = y0 + (y1 - y0) * i / 4, y = Y(v);
    s += `<line x1="${P.l}" y1="${y}" x2="${W - P.r}" y2="${y}" stroke="#eef2f7"/>`
       + `<text x="${P.l - 8}" y="${y + 4}" text-anchor="end" font-size="11" fill="#9ca3af">${fmtMoney(Math.round(v))}</text>`;
  }
  if (pts.length > 1) {
    const poly = pts.map(p => p.join(",")).join(" ");
    s += `<polygon points="${pts[0][0]},${H - P.b} ${poly} ${pts[pts.length - 1][0]},${H - P.b}" fill="url(#gradDeal)"/>`;
    s += `<polyline points="${poly}" fill="none" stroke="#0f766e" stroke-width="2.5" stroke-linejoin="round"/>`;
  }
  data.forEach((d, i) => {
    s += `<circle cx="${pts[i][0]}" cy="${pts[i][1]}" r="3.5" fill="#0f766e">`
       + `<title>${d.date} · ${d.floor || "?"}층 · ${fmtMoney(d.amount)}원</title></circle>`;
  });
  // 최고·최저 지점 라벨 (표본 3건 이상)
  if (data.length >= 3 && yMax !== yMin) {
    const mi = ys.indexOf(yMax), ni = ys.indexOf(yMin);
    s += `<text x="${pts[mi][0]}" y="${pts[mi][1] - 9}" text-anchor="middle" font-size="10" fill="#dc2626">최고 ${fmtMoney(yMax)}</text>`;
    s += `<text x="${pts[ni][0]}" y="${pts[ni][1] + 16}" text-anchor="middle" font-size="10" fill="#2563eb">최저 ${fmtMoney(yMin)}</text>`;
  }
  // 최신 거래 강조 + 값 배지
  const last = data[data.length - 1], lx = pts[pts.length - 1][0], ly = pts[pts.length - 1][1];
  s += `<circle cx="${lx}" cy="${ly}" r="5.5" fill="#0f766e" stroke="#fff" stroke-width="2"/>`;
  const lbl = fmtMoney(last.amount) + "원", bw = lbl.length * 7 + 16;
  let bx = lx + 10; if (bx + bw > W - 2) bx = lx - 10 - bw;
  const by = Math.min(Math.max(ly - 11, P.t), H - P.b - 22);
  s += `<rect x="${bx}" y="${by}" width="${bw}" height="22" rx="6" fill="#0f766e"/>`
     + `<text x="${bx + bw / 2}" y="${by + 15}" text-anchor="middle" font-size="12" fill="#fff" font-weight="700">${lbl}</text>`;
  let lastLx = -999;
  data.forEach((d, i) => {
    if (i !== data.length - 1 && pts[i][0] - lastLx < 60) return;
    lastLx = pts[i][0];
    s += `<text x="${pts[i][0]}" y="${H - P.b + 18}" text-anchor="middle" font-size="11" fill="#9ca3af">${d.date.slice(2)}</text>`;
  });
  s += "</svg>";
  el.innerHTML = s + `<div class="legend"><span style="color:#0f766e">●</span> 실거래 추이 · 최신가 강조 · 점에 마우스를 올리면 층·금액. 해제 거래 제외.</div>`;
}
sel.addEventListener("change", () => { clearCardSel(); drawChart(sel.value); });
if (sel.options.length) { sel.value = sel.options[0].value; drawChart(sel.value); }

// ============================== 거래 내역 (단지별 분류) ==============================
const aptSel = document.getElementById("aptSel");
const aptNames = [...new Set(DEALS.map(d => d.apt_nm))].sort();
aptSel.insertAdjacentHTML("beforeend", `<option value="__all__">전체 단지 (최신순)</option>`);
aptSel.insertAdjacentHTML("beforeend", `<option value="__grouped__">전체 단지 (단지별 묶음)</option>`);
aptNames.forEach(n => {
  const cnt = DEALS.filter(d => d.apt_nm === n).length;
  aptSel.insertAdjacentHTML("beforeend", `<option value="${esc(n)}">${esc(n)} (${cnt}건)</option>`);
});

function rowHtml(d) {
  const g = activeOf(groups[groupKey(d)]);
  const idx = g.indexOf(d);     // 객체 참조로 조회(동일 값 중복 행에서도 정확)
  let diff = "—";
  if (!d.cancelled && idx > 0) {
    const dv = d.amount - g[idx - 1].amount;
    const pct = (dv / g[idx - 1].amount * 100).toFixed(1);
    diff = dv > 0 ? `<span class="diff-up">+${fmtMoney(dv)} (+${pct}%)</span>`
         : dv < 0 ? `<span class="diff-down">${fmtMoney(dv)} (${pct}%)</span>` : "보합";
  }
  return `
    <tr class="${d.cancelled ? "cancelled" : ""}">
      <td>${d.date}</td><td>${esc(d.apt_nm)}</td><td>${fmtArea(d.area)}</td>
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
        `<tr class="grp"><td colspan="7">📍 ${esc(n)} — ${list.length}건${latest}</td></tr>`);
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
aptSel.addEventListener("change", () => { clearCardSel(); renderTable(); });
renderTable();

// ============================== 호가 탭 ==============================
(function quotesTab() {
  const hasQuotes = QUOTES.length > 0;
  document.getElementById("quotesEmpty").style.display = hasQuotes ? "none" : "";
  document.getElementById("quotesBody").style.display = hasQuotes ? "" : "none";
  // 헤더에 호가 마지막 수집 시각 표시 (가격 변동이 없어도 '언제 수집했는지' 보이도록)
  if (QUOTES_META.last_run) {
    document.getElementById("quotesRunHdr").textContent =
      " · 호가 수집: " + QUOTES_META.last_run.slice(0, 16).replace("T", " ");
  }
  if (QUOTES_META.tracking_since) {
    document.getElementById("qTrackSince").textContent =
      "· 호가 추적 시작 " + QUOTES_META.tracking_since;
  }
  if (!hasQuotes) return;

  const runDate = (QUOTES_META.last_run || "").slice(0, 10);
  const dayMs = 86400000;
  const isRecent = iso => runDate && iso &&
    (new Date(runDate) - new Date(iso.slice(0, 10))) <= 7 * dayMs;
  const byComplex = {};
  QUOTES.forEach(q => (byComplex[q.complex] = byComplex[q.complex] || []).push(q));
  const complexNames = Object.keys(byComplex).sort();
  const activeIn = list => list.filter(q => q.status === "active");
  // 매매 최신가 (같은 config 단지)
  const dealLatest = {};
  DEALS.filter(d => !d.cancelled).forEach(d => {
    const c = dealLatest[d.complex];
    if (!c || d.date > c.date) dealLatest[d.complex] = d;
  });

  // ---- ① 요약 카드 (config 단지별)
  const qCardsEl = document.getElementById("qCards");
  let __qRegion = null;
  complexNames
    .filter(name => activeIn(byComplex[name]).length)
    .sort((a, b) => regionOf(a).localeCompare(regionOf(b)) || a.localeCompare(b))
    .forEach(name => {
    const act = activeIn(byComplex[name]);
    const __region = regionOf(name);
    if (__region !== __qRegion) {
      __qRegion = __region;
      qCardsEl.insertAdjacentHTML("beforeend", `<div class="region-head" data-region="${esc(__region)}"><span>📍 ${esc(__region)}</span>` +
      `<span class="reg-move"><button type="button" data-regmove="-1">▲</button>` +
      `<button type="button" data-regmove="1">▼</button></span></div>`);
    }
    const prices = act.map(q => q.price);
    const minP = Math.min(...prices);
    const maxP = Math.max(...prices);
    // #4 호가 범위(최저~최고) — 매도자 기대 분포
    const rangeHtml = maxP > minP
      ? `<div class="meta">호가 범위 ${fmtMoney(minP)} ~ ${fmtMoney(maxP)}</div>` : "";
    // #3 평단가(최저호가 기준) — 매매 카드와 동일 지표
    const cheap = act.reduce((a, b) => b.price < a.price ? b : a);
    const pyq = cheap.area ? Math.round(minP * 3.3058 / cheap.area) : 0;
    const pyeongQHtml = pyq ? `<div class="pyeong">최저호가 평단가 ${pyq.toLocaleString()}만/평</div>` : "";
    const newCnt = act.filter(q => isRecent(q.first_seen)).length;
    const cutCnt = act.filter(q => q.price_history && q.price_history.length >= 2 &&
      q.price_history[q.price_history.length - 1].price < q.price_history[q.price_history.length - 2].price).length;
    let gapHtml = "";
    const dl = dealLatest[name];
    if (dl) {
      const gap = minP - dl.amount, pct = (gap / dl.amount * 100).toFixed(1);
      const cls = gap > 0 ? "diff-up" : gap < 0 ? "diff-down" : "";
      gapHtml = `<div class="meta">최근 실거래 ${fmtMoney(dl.amount)} (${dl.date})` +
        ` → 최저호가 <span class="${cls}">${gap >= 0 ? "+" : ""}${fmtMoney(gap)} (${pct > 0 ? "+" : ""}${pct}%)</span></div>`;
    } else {
      gapHtml = `<div class="meta">실거래 기록 없음</div>`;
    }
    const badge = (newCnt ? `🆕${newCnt} ` : "") + (cutCnt ? `🔻${cutCnt}` : "");
    qCardsEl.insertAdjacentHTML("beforeend", `
      <div class="card" data-name="${esc(name)}" data-complex="${esc(name)}" data-region="${esc(__region)}">
        <h3>${esc(name)}</h3>
        <div class="band">활성 매물 ${act.length}건 ${badge ? "· " + badge : ""}</div>
        <div class="price">${fmtMoney(minP)}원 <span class="meta">최저호가</span></div>
        ${rangeHtml}
        ${pyeongQHtml}
        ${gapHtml}
        <div class="selhint">▸ 클릭하면 이 단지로 호가추이·목록 보기</div>
      </div>`);
  });

  // ---- ② 호가 추이 차트 (config 단지별: 일별 최저/평균 호가 + 실거래 오버레이)
  const qSel = document.getElementById("qGroupSel");
  complexNames.forEach(n => {
    if (activeIn(byComplex[n]).length || byComplex[n].length)
      qSel.insertAdjacentHTML("beforeend", `<option value="${esc(n)}">${esc(n)}</option>`);
  });
  function priceAsOf(q, d) {
    let p = null;
    for (const h of (q.price_history || [])) { if (h.date <= d) p = h.price; else break; }
    return p;
  }
  function drawQChart(name) {
    const list = byComplex[name] || [];
    const el = document.getElementById("qChart");
    const dates = new Set();
    list.forEach(q => (q.price_history || []).forEach(h => dates.add(h.date)));
    if (runDate) dates.add(runDate);
    const xdates = [...dates].sort();
    // 일별 최저/평균 호가
    const series = xdates.map(d => {
      const ps = [];
      list.forEach(q => {
        const born = (q.first_seen || "").slice(0, 10);
        const gone = q.gone_date;
        if (born && born > d) return;
        if (gone && gone <= d) return;
        const p = priceAsOf(q, d);
        if (p != null) ps.push(p);
      });
      return ps.length ? { d, min: Math.min(...ps), avg: ps.reduce((a, b) => a + b, 0) / ps.length } : null;
    }).filter(Boolean);
    const deals = DEALS.filter(d => d.complex === name && !d.cancelled);
    if (!series.length && !deals.length) { el.innerHTML = "<div class='legend'>데이터 없음</div>"; return; }
    const W = 880, H = 330, P = { l: 78, r: 58, t: 26, b: 42 };
    const allT = series.map(s => new Date(s.d).getTime())
      .concat(deals.map(d => new Date(d.date).getTime()));
    const allV = series.flatMap(s => [s.min, s.avg]).concat(deals.map(d => d.amount));
    const x0 = Math.min(...allT), x1 = Math.max(...allT) || x0 + 1;
    const vMin = Math.min(...allV), vMax = Math.max(...allV);
    const pad = Math.max((vMax - vMin) * 0.18, vMax * 0.03, 500);
    const y0 = vMin - pad, y1 = vMax + pad;
    const X = t => x1 > x0 ? P.l + (t - x0) / (x1 - x0) * (W - P.l - P.r) : (P.l + W - P.r) / 2;
    const Y = v => H - P.b - (v - y0) / (y1 - y0) * (H - P.t - P.b);
    let s = `<svg viewBox="0 0 ${W} ${H}" style="width:100%;max-width:${W}px">`;
    s += `<defs><linearGradient id="gradQ" x1="0" y1="0" x2="0" y2="1">`
       + `<stop offset="0" stop-color="#0f766e" stop-opacity="0.18"/>`
       + `<stop offset="1" stop-color="#0f766e" stop-opacity="0"/></linearGradient></defs>`;
    for (let i = 0; i <= 4; i++) {
      const v = y0 + (y1 - y0) * i / 4, y = Y(v);
      s += `<line x1="${P.l}" y1="${y}" x2="${W - P.r}" y2="${y}" stroke="#eef2f7"/>`
        + `<text x="${P.l - 8}" y="${y + 4}" text-anchor="end" font-size="11" fill="#9ca3af">${fmtMoney(Math.round(v))}</text>`;
    }
    const mpts = series.map(s2 => [X(new Date(s2.d).getTime()), Y(s2.min)]);
    if (mpts.length > 1) {
      const poly = mpts.map(p => p.join(",")).join(" ");
      s += `<polygon points="${mpts[0][0]},${H - P.b} ${poly} ${mpts[mpts.length - 1][0]},${H - P.b}" fill="url(#gradQ)"/>`;
      s += `<polyline points="${poly}" fill="none" stroke="#0f766e" stroke-width="2.5" stroke-linejoin="round"/>`;
      const apoly = series.map(s2 => `${X(new Date(s2.d).getTime())},${Y(s2.avg)}`).join(" ");
      s += `<polyline points="${apoly}" fill="none" stroke="#94a3b8" stroke-width="1.8" stroke-dasharray="4 3"/>`;
    }
    series.forEach((s2, i) => {
      s += `<circle cx="${mpts[i][0]}" cy="${mpts[i][1]}" r="3.5" fill="#0f766e">`
        + `<title>${s2.d} · 최저호가 ${fmtMoney(s2.min)}원</title></circle>`;
    });
    deals.forEach(d => {
      const cx = X(new Date(d.date).getTime()), cy = Y(d.amount);
      s += `<circle cx="${cx}" cy="${cy}" r="4.5" fill="none" stroke="#dc2626" stroke-width="2">`
        + `<title>실거래 ${d.date} · ${fmtMoney(d.amount)}원</title></circle>`;
    });
    if (mpts.length) {     // 최신 최저호가 강조 + 값 배지
      const last = series[series.length - 1], lx = mpts[mpts.length - 1][0], ly = mpts[mpts.length - 1][1];
      s += `<circle cx="${lx}" cy="${ly}" r="5.5" fill="#0f766e" stroke="#fff" stroke-width="2"/>`;
      const lbl = fmtMoney(last.min) + "원", bw = lbl.length * 7 + 16;
      let bx = lx + 10; if (bx + bw > W - 2) bx = lx - 10 - bw;
      const by = Math.min(Math.max(ly - 11, P.t), H - P.b - 22);
      s += `<rect x="${bx}" y="${by}" width="${bw}" height="22" rx="6" fill="#0f766e"/>`
        + `<text x="${bx + bw / 2}" y="${by + 15}" text-anchor="middle" font-size="12" fill="#fff" font-weight="700">${lbl}</text>`;
    }
    let lastLabelX = -999;
    series.forEach((s2, i) => {
      const lx = X(new Date(s2.d).getTime());
      if (i !== series.length - 1 && lx - lastLabelX < 60) return;
      lastLabelX = lx;
      s += `<text x="${lx}" y="${H - P.b + 18}" text-anchor="middle" font-size="11" fill="#9ca3af">${s2.d.slice(2)}</text>`;
    });
    s += "</svg>";
    el.innerHTML = s + `<div class="legend"><b style="color:#0f766e">▬</b> 최저호가 · <span style="color:#94a3b8">┄</span> 평균호가 · <span style="color:#dc2626">○</span> 실거래(체결) · 최신 최저호가 강조. 점에 마우스를 올리면 상세.</div>`;
  }
  qSel.addEventListener("change", () => { clearQCardSel(); drawQChart(qSel.value); });
  if (qSel.options.length) { qSel.value = qSel.options[0].value; drawQChart(qSel.value); }

  // ---- ③ 현재 호가 목록 (unit_key 묶음)
  const qAptSel = document.getElementById("qAptSel");
  qAptSel.insertAdjacentHTML("beforeend", `<option value="__all__">전체 단지 (최신순)</option>`);
  qAptSel.insertAdjacentHTML("beforeend", `<option value="__grouped__">전체 단지 (단지별 묶음)</option>`);
  complexNames.forEach(n => {
    const cnt = activeIn(byComplex[n]).length;
    qAptSel.insertAdjacentHTML("beforeend", `<option value="${esc(n)}">${esc(n)} (활성 ${cnt})</option>`);
  });
  function qChangeBadge(q) {
    const h = q.price_history || [];
    if (h.length < 2) return "";
    const dv = h[h.length - 1].price - h[h.length - 2].price;
    const pct = (dv / h[h.length - 2].price * 100).toFixed(1);
    return dv < 0 ? `<span class="diff-down">${fmtMoney(dv)} (${pct}%)</span>`
         : dv > 0 ? `<span class="diff-up">+${fmtMoney(dv)} (+${pct}%)</span>` : "보합";
  }
  function statusNote(q) {   // 비고용: 상태 배지(없으면 빈 문자열)
    if (q.status === "gone") return `<span class="badge">내려감</span>`;
    const b = [];
    if (isRecent(q.first_seen)) b.push(`<span class="badge" style="background:#dcfce7;color:#15803d">신규</span>`);
    if (q.relisted_count || q.relist_of) b.push(`<span class="badge" style="background:#e0e7ff;color:#4338ca">재등록</span>`);
    return b.join(" ");
  }
  function qReps(list) {
    // unit_key로 묶고 대표(최저가→확인일 최신→article_no) 선택
    const groups = {};
    list.forEach(q => {
      const k = q.unit_key_confident ? q.unit_key : "solo:" + q.article_no;
      (groups[k] = groups[k] || []).push(q);
    });
    return Object.values(groups).map(g => {
      g.sort((a, b) => a.price - b.price ||
        (b.confirm_ymd || "").localeCompare(a.confirm_ymd || "") ||
        a.article_no.localeCompare(b.article_no));
      return g;
    }).sort((a, b) => a[0].price - b[0].price);
  }
  // 매매 거래내역과 동일한 형식: 확인일 | 단지 | 전용 | 동·층 | 호가 | 직전대비 | 비고
  function renderQTable() {
    const mode = qAptSel.value;
    const showGone = document.getElementById("qShowGone").checked;
    const tbody = document.getElementById("qRows");
    tbody.innerHTML = "";
    let shown = 0;
    const filt = list => (list || []).filter(q => showGone || q.status === "active");
    const byDate = groups => groups.slice().sort((a, b) =>     // 최신순(확인일 desc), 동률 시 저가순
      (b[0].confirm_ymd || "").localeCompare(a[0].confirm_ymd || "") || a[0].price - b[0].price);

    function emitReps(groups) {
      groups.forEach(group => {
        const rep = group[0], n = group.length;
        const dongFloor = `${rep.building_name !== "?" ? esc(rep.building_name) + "동 " : ""}${esc(rep.floor_self) || "?"}층`;
        const dupBadge = n > 1 ? ` <span class="badge" style="background:#f1f5f9;color:#475569;cursor:pointer">+${n - 1}곳</span>` : "";
        const note = [statusNote(rep), rep.direction ? esc(rep.direction) + "향" : "", esc(rep.realtor)]
          .filter(Boolean).join(" · ") + dupBadge;
        tbody.insertAdjacentHTML("beforeend", `
          <tr class="${rep.status === "gone" ? "cancelled" : ""}" ${n > 1 ? `style="cursor:pointer" onclick="this.nextElementSibling.style.display=this.nextElementSibling.style.display==='none'?'':'none'"` : ""}>
            <td>${fmtYmd(rep.confirm_ymd)}</td><td>${esc(rep.complex)}</td>
            <td>${fmtArea(rep.area)}</td><td>${dongFloor}</td>
            <td><b>${fmtMoney(rep.price)}</b></td><td>${qChangeBadge(rep) || "—"}</td>
            <td>${note}</td>
          </tr>`);
        if (n > 1) {
          const inner = group.slice(1).map(q =>
            `<div style="padding:2px 0">· ${fmtMoney(q.price)}원 — ${esc(q.realtor) || "?"} (${fmtYmd(q.confirm_ymd)}) ${qChangeBadge(q)}</div>`).join("");
          tbody.insertAdjacentHTML("beforeend",
            `<tr style="display:none"><td></td><td colspan="6" style="color:var(--sub);font-size:12px">${inner}</td></tr>`);
        }
        shown += n;
      });
    }

    if (mode === "__grouped__") {                       // 단지별 묶음(헤더 + 행)
      complexNames.forEach(name => {
        const groups = byDate(qReps(filt(byComplex[name])));
        if (!groups.length) return;
        const minP = Math.min(...groups.map(g => g[0].price));
        tbody.insertAdjacentHTML("beforeend",
          `<tr class="grp"><td colspan="7">📍 ${esc(name)} — 활성 ${activeIn(byComplex[name]).length}건 · 최저 ${fmtMoney(minP)}원</td></tr>`);
        emitReps(groups);
      });
    } else {                                            // 전체(최신순) 또는 특정 단지
      const list = mode === "__all__" ? QUOTES : (byComplex[mode] || []);
      emitReps(byDate(qReps(filt(list))));
    }
    document.getElementById("qRowCnt").textContent = `${shown}건`;
  }
  function fmtYmd(s) { return s && s.length === 8 ? `${s.slice(2, 4)}.${s.slice(4, 6)}.${s.slice(6)}` : "-"; }
  qAptSel.addEventListener("change", () => { clearQCardSel(); renderQTable(); });
  document.getElementById("qShowGone").addEventListener("change", renderQTable);
  renderQTable();

  // 호가 카드 클릭 → 호가추이·목록을 해당 단지로 필터(재클릭 시 해제, 토글)
  let selQCard = null;
  function clearQCardSel() {
    selQCard = null;
    qCardsEl.querySelectorAll(".card.sel").forEach(c => c.classList.remove("sel"));
  }
  qCardsEl.addEventListener("click", e => {
    const card = e.target.closest(".card");
    if (!card) return;
    const name = card.dataset.name;
    if (selQCard === name) {                          // 토글 해제 → 전체로 복귀
      clearQCardSel();
      if (qSel.options.length) { qSel.value = qSel.options[0].value; drawQChart(qSel.value); }
      qAptSel.value = "__all__"; renderQTable();
      return;
    }
    selQCard = name;
    qCardsEl.querySelectorAll(".card").forEach(c => c.classList.toggle("sel", c === card));
    if ([...qSel.options].some(o => o.value === name)) { qSel.value = name; drawQChart(name); }
    qAptSel.value = name; renderQTable();
    document.getElementById("qChart").scrollIntoView({ behavior: "smooth", block: "center" });
  });

  // ---- ④ 호가 변동·소멸 이력
  const hist = [];
  QUOTES.forEach(q => {
    const h = q.price_history || [];
    for (let i = 1; i < h.length; i++) {
      hist.push({ date: h[i].date, q, kind: "change", from: h[i - 1].price, to: h[i].price });
    }
    if (q.status === "gone" && q.gone_date) hist.push({ date: q.gone_date, q, kind: "gone" });
  });
  hist.sort((a, b) => b.date.localeCompare(a.date));
  const hb = document.getElementById("qHistory");
  hist.slice(0, 200).forEach(e => {
    const q = e.q;
    const dongFloor = `${q.building_name !== "?" ? esc(q.building_name) + "동 " : ""}${esc(q.floor_self) || "?"}층`;
    let change, note;
    if (e.kind === "gone") {
      change = `<span style="color:#9ca3af">${fmtMoney(q.price)} → 내려감</span>`;
      note = `<span class="badge">소멸</span>`;
    } else {
      const dv = e.to - e.from, pct = (dv / e.from * 100).toFixed(1);
      const cls = dv < 0 ? "diff-down" : "diff-up";
      change = `${fmtMoney(e.from)} → <b>${fmtMoney(e.to)}</b> <span class="${cls}">(${dv > 0 ? "+" : ""}${fmtMoney(dv)}, ${pct > 0 ? "+" : ""}${pct}%)</span>`;
      note = dv < 0 ? "🔻 인하" : "🔺 인상";
    }
    hb.insertAdjacentHTML("beforeend", `
      <tr><td>${e.date}</td><td>${esc(q.apt_nm)}</td><td>${dongFloor}</td>
          <td>${q.area}</td><td>${change}</td><td>${note}</td></tr>`);
  });
  if (!hist.length) hb.insertAdjacentHTML("beforeend",
    `<tr><td colspan="6" class="legend">아직 변동·소멸 이력이 없습니다 (스냅샷이 2회 이상 쌓이면 표시).</td></tr>`);

  // ---- ⑤ 경고 배너 (조회 실패/0건 의심 단지)
  const stale = complexNames.filter(n => activeIn(byComplex[n]).length === 0);
  if (stale.length) {
    document.getElementById("qWarnBanner").innerHTML =
      `<div class="warn">⚠ 활성 호가 0건인 단지: <b>${stale.map(esc).join(", ")}</b>. ` +
      `세션 만료·매물 소진·naver_id 오류일 수 있습니다. <code>python quotes_monitor.py</code> 재실행 또는 네이버 재로그인 후 세션 갱신을 확인하세요.</div>`;
  }
})();

// ============================== 카드 순서(지역·단지) 편집·저장 ==============================
// 순서는 order.json으로 공유(모든 기기). 저장(커밋)은 로컬에서만: '순서 저장' → 클립보드 → `bash save_order.sh`.
const CARD_ORDER = { regions: [], complexes: [] };
let __editOrder = false;

function __seedRegions() {
  return [...document.querySelectorAll("#cards .region-head, #qCards .region-head")]
    .map(h => h.dataset.region).filter((v, i, a) => v && a.indexOf(v) === i);
}
function __seedComplexes() {
  const out = [];
  document.querySelectorAll("#cards .card, #qCards .card").forEach(c => {
    const k = c.dataset.complex;
    if (k && !out.includes(k)) out.push(k);
  });
  return out;
}
const __rankR = r => { const i = CARD_ORDER.regions.indexOf(r); return i < 0 ? 9999 : i; };
const __rankC = c => { const i = CARD_ORDER.complexes.indexOf(c); return i < 0 ? 9999 : i; };

function applyOrder(id) {
  const el = document.getElementById(id);
  if (!el) return;
  const heads = {}, cards = {};
  [...el.children].forEach(n => {
    if (n.classList && n.classList.contains("region-head")) heads[n.dataset.region] = n;
    else if (n.dataset && n.dataset.region) (cards[n.dataset.region] = cards[n.dataset.region] || []).push(n);
  });
  Object.keys(heads).sort((a, b) => __rankR(a) - __rankR(b) || a.localeCompare(b)).forEach(r => {
    el.appendChild(heads[r]);
    (cards[r] || []).sort((a, b) => __rankC(a.dataset.complex) - __rankC(b.dataset.complex)
        || String(a.dataset.complex).localeCompare(String(b.dataset.complex)))
      .forEach(c => el.appendChild(c));
  });
}
function applyOrderAll() { applyOrder("cards"); applyOrder("qCards"); }

function __setOrderStatus(msg) { document.querySelectorAll(".ord-status").forEach(e => e.textContent = msg); }
function markOrderDirty() {
  localStorage.setItem("card_order", JSON.stringify(CARD_ORDER));
  __setOrderStatus("● 변경됨 — 저장 필요");
}

async function loadCardOrder() {
  const cached = localStorage.getItem("card_order");
  if (cached) {
    try { const o = JSON.parse(cached); CARD_ORDER.regions = o.regions || []; CARD_ORDER.complexes = o.complexes || []; } catch (e) {}
  } else {
    try {
      const r = await fetch("order.json?_=" + Date.now());
      if (r.ok) { const o = await r.json(); CARD_ORDER.regions = o.regions || []; CARD_ORDER.complexes = o.complexes || []; }
    } catch (e) {}
  }
  applyOrderAll();
}

function toggleOrderEdit() {
  __editOrder = !__editOrder;
  document.body.classList.toggle("editorder", __editOrder);
  document.querySelectorAll(".ord-edit-btn").forEach(b => b.textContent = __editOrder ? "✅ 편집 끝" : "🔀 순서 편집");
  document.querySelectorAll("#cards .card, #qCards .card").forEach(c => c.draggable = __editOrder);
  if (__editOrder) {
    if (!CARD_ORDER.regions.length) CARD_ORDER.regions = __seedRegions();
    if (!CARD_ORDER.complexes.length) CARD_ORDER.complexes = __seedComplexes();
    __setOrderStatus("편집 중 — 드래그/▲▼로 변경 후 '순서 저장'");
  }
}

function moveRegion(region, dir) {
  if (!CARD_ORDER.regions.length) CARD_ORDER.regions = __seedRegions();
  const arr = CARD_ORDER.regions, i = arr.indexOf(region), j = i + dir;
  if (i < 0 || j < 0 || j >= arr.length) return;
  [arr[i], arr[j]] = [arr[j], arr[i]];
  applyOrderAll(); markOrderDirty();
}

let __dragEl = null;
document.addEventListener("dragstart", e => {
  const c = e.target.closest && e.target.closest(".card");
  if (!c || !__editOrder) return;
  __dragEl = c; e.dataTransfer.effectAllowed = "move";
});
document.addEventListener("dragover", e => {
  if (!__editOrder || !__dragEl) return;
  const over = e.target.closest && e.target.closest(".card");
  if (!over || over === __dragEl || over.dataset.region !== __dragEl.dataset.region) return;
  e.preventDefault(); over.classList.add("dragover");
});
document.addEventListener("dragleave", e => {
  const over = e.target.closest && e.target.closest(".card");
  if (over) over.classList.remove("dragover");
});
document.addEventListener("drop", e => {
  if (!__editOrder || !__dragEl) return;
  const over = e.target.closest && e.target.closest(".card");
  document.querySelectorAll(".card.dragover").forEach(c => c.classList.remove("dragover"));
  if (!over || over === __dragEl || over.dataset.region !== __dragEl.dataset.region) { __dragEl = null; return; }
  e.preventDefault();
  if (!CARD_ORDER.complexes.length) CARD_ORDER.complexes = __seedComplexes();
  const arr = CARD_ORDER.complexes;
  const from = arr.indexOf(__dragEl.dataset.complex), to = arr.indexOf(over.dataset.complex);
  if (from >= 0 && to >= 0) { arr.splice(to, 0, arr.splice(from, 1)[0]); applyOrderAll(); markOrderDirty(); }
  __dragEl = null;
});
document.addEventListener("dragend", () => {
  document.querySelectorAll(".card.dragover").forEach(c => c.classList.remove("dragover"));
  __dragEl = null;
});
document.addEventListener("click", e => {
  const b = e.target.closest && e.target.closest("[data-regmove]");
  if (!b) return;
  const head = b.closest(".region-head");
  if (head) moveRegion(head.dataset.region, parseInt(b.dataset.regmove, 10));
});

function saveCardOrder() {
  if (!CARD_ORDER.regions.length) CARD_ORDER.regions = __seedRegions();
  if (!CARD_ORDER.complexes.length) CARD_ORDER.complexes = __seedComplexes();
  const json = JSON.stringify({ regions: CARD_ORDER.regions, complexes: CARD_ORDER.complexes }, null, 1);
  localStorage.setItem("card_order", JSON.stringify(CARD_ORDER));
  // 로컬 서버(order_server.py)로 접속했으면 자동 저장(커밋·푸시)
  const isLocal = ["localhost", "127.0.0.1"].includes(location.hostname);
  if (isLocal) {
    __setOrderStatus("저장 중…");
    fetch("/save-order", { method: "POST", headers: { "Content-Type": "application/json" }, body: json })
      .then(r => r.json())
      .then(o => __setOrderStatus((o.ok ? "✅ " : "❌ ") + o.msg + (o.ok ? " — 다른 기기는 '🔄 공유순서 불러오기'" : "")))
      .catch(() => __setOrderStatus("❌ 로컬 서버 응답 없음 — `python3 order_server.py` 실행 확인"));
    return;
  }
  // GitHub Pages 등: 클립보드 폴백 → 로컬에서 bash save_order.sh
  const done = () => __setOrderStatus("📋 복사됨 — 로컬 터미널에서 `bash save_order.sh` 실행 → 모든 기기 공유");
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(json).then(done).catch(() => __showOrderJson(json));
  } else { __showOrderJson(json); }
}
function __showOrderJson(json) {
  __setOrderStatus("아래 JSON을 docs/order.json 에 저장(복사)하세요");
  let ta = document.getElementById("ordJsonBox");
  if (!ta) {
    ta = document.createElement("textarea");
    ta.id = "ordJsonBox";
    ta.style.cssText = "width:100%;height:120px;margin-top:8px;font-size:11px";
    const c = document.getElementById("cards");
    c.parentNode.insertBefore(ta, c.nextSibling);
  }
  ta.value = json; ta.focus(); ta.select();
}
function resetCardOrder() {
  localStorage.removeItem("card_order");
  __setOrderStatus("공유 순서를 불러옵니다…");
  location.reload();
}

loadCardOrder();

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
    <div><div class="naver-cell">
           <input type="text" class="f-naver" value="${(c.naver_id||"").replace(/"/g,'&quot;')}" placeholder="예: 166117 (호가 수집용)">
           <button class="btn" type="button" onclick="lookupNaverId(this)" title="네이버에서 단지번호 찾기">🔍 찾기</button>
         </div><div class="hint f-naver-hint"></div></div>
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

// 단지번호 조회용 검색어: 단지명 키워드(첫 항목) 우선, 없으면 표시이름에서 '전용…'·괄호 제거
function naverQuery(row) {
  const match = (row.querySelector(".f-match").value || "").split(",")[0].trim();
  if (match) return match;
  return (row.querySelector(".f-name").value || "")
           .replace(/\\s*전용.*$/, "").replace(/\\s*\\(.*$/, "").trim();
}

// 정적 페이지에서 네이버는 CORS로 직접 호출 불가 → 공개 프록시 경유(best-effort).
// m.land 검색은 단지 상세(/complex/info/{번호})로 리다이렉트되므로 최종 URL/본문에서 번호를 추출.
async function fetchNaverId(targetUrl) {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), 12000);
  try {
    const r = await fetch("https://api.allorigins.win/get?url=" + encodeURIComponent(targetUrl),
                          {signal: ctrl.signal});
    if (!r.ok) return null;
    const d = await r.json();
    const hay = ((d && d.status && d.status.url) ? d.status.url + " " : "") +
                ((d && d.contents) ? d.contents : "");
    const m = hay.match(/complex(?:es)?\\/(?:info\\/)?(\\d{3,})/);
    return m ? m[1] : null;
  } finally {
    clearTimeout(t);
  }
}

// 🔍 찾기: naver_lookup.py와 동일한 m.land 리다이렉트 방식으로 단지번호 자동 조회.
// 프록시 실패 시 브라우저가 직접 리다이렉트를 따라가도록 새 탭으로 폴백.
async function lookupNaverId(btn) {
  const row = btn.closest(".cfg-row");
  const input = row.querySelector(".f-naver");
  const hint = row.querySelector(".f-naver-hint");
  const q = naverQuery(row);
  if (!q) {
    hint.className = "hint f-naver-hint err";
    hint.textContent = "⚠ 표시 이름이나 단지명 키워드를 먼저 입력하세요";
    return;
  }
  const searchUrl = "https://m.land.naver.com/search/result/" + encodeURIComponent(q);
  hint.className = "hint f-naver-hint";
  hint.textContent = "조회 중… (" + q + ")";
  btn.disabled = true;
  try {
    const id = await fetchNaverId(searchUrl);
    if (id) {
      input.value = id;
      hint.className = "hint f-naver-hint ok";
      hint.textContent = "✓ 단지번호 " + id + " (네이버에서 한 번 더 확인 권장)";
      return;
    }
    throw new Error("not found");
  } catch (e) {
    window.open(searchUrl, "_blank", "noopener");
    hint.className = "hint f-naver-hint err";
    hint.innerHTML = "자동 조회 실패 — 새 탭 주소의 <code>…/complex/info/<b>번호</b></code> 에서 번호를 복사해 입력하세요";
  } finally {
    btn.disabled = false;
  }
}

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
    const naverEl = row.querySelector(".f-naver");      // 호가 단지번호 보존(편집 UI엔 없지만 유지)
    if (naverEl && naverEl.value.trim()) entry.naver_id = naverEl.value.trim();
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
    if (c.naver_id) out += `    naver_id: ${yamlStr(c.naver_id)}\\n`;
  }
  out += `\\noptions:\\n  months_back: ${opt.months_back ?? 1}\\n`;
  out += `  notify_cancellations: ${opt.notify_cancellations ?? true}\\n`;
  // 호가 수집 옵션(naver:) 보존
  const nv = CONFIG.naver || {};
  const tt = (nv.trade_types && nv.trade_types.length) ? nv.trade_types : ["A1"];
  out += `\\nnaver:\\n  trade_types: [${tt.map(yamlStr).join(", ")}]\\n`;
  out += `  notify: ${nv.notify ?? true}\\n`;
  return out;
}

// GitHub 연동
const ownerEl = document.getElementById("ghOwner");
const repoEl = document.getElementById("ghRepo");
(function initRepoFields() {
  let owner = localStorage.getItem("gh_owner") || "";
  let repo = localStorage.getItem("gh_repo") || "";
  if (location.hostname.endsWith(".github.io")) {
    owner = location.hostname.split(".")[0];
    repo = location.pathname.split("/").filter(Boolean)[0] || repo;
  }
  ownerEl.value = owner; repoEl.value = repo;
  localStorage.setItem("gh_owner", owner); localStorage.setItem("gh_repo", repo);
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


def render_dashboard(state, cfg, out_path, quotes_state=None):
    complexes = cfg.get("complexes", [])
    all_deals = sorted(state.get("deals", {}).values(), key=lambda d: d["date"])

    # 현재 config에 매칭되는 거래만 표시 (관심단지에서 빠진 옛 단지 데이터는 숨김).
    # 거래의 complex 이름도 현재 config 기준으로 다시 태깅(단지명 변경 대응).
    visible, counts = [], {c["name"]: 0 for c in complexes}
    for d in all_deals:
        name = matching_complex_name(d, complexes)
        if name is not None:
            visible.append({**d, "complex": name})
            counts[name] += 1

    # 매칭 0건 단지 → 경고 배너
    warnings = []
    for c in complexes:
        if counts.get(c["name"], 0) == 0:
            ref = c.get("region") or c.get("lawd_cd")
            warnings.append({
                "name": c["name"], "region": ref,
                "match": c.get("match") or [], "areas": c.get("areas") or [],
            })

    # 호가: 현재 config에 매칭되는 매물만 표시 (관심단지에서 빠진 매물 숨김)
    qs = quotes_state or {}
    visible_quotes = [q for q in qs.get("quotes", {}).values()
                      if quote_in_config(q, complexes) is not None]
    quotes_meta = {
        "tracking_since": qs.get("tracking_since", ""),
        "last_run": qs.get("last_run", ""),
    }

    config_pub = {
        "complexes": [
            {"name": c["name"],
             **({"region": c["region"]} if c.get("region") else {"lawd_cd": c["lawd_cd"]}),
             "match": c.get("match") or [],
             "areas": c.get("areas") or [],
             **({"naver_id": c["naver_id"]} if c.get("naver_id") else {})}
            for c in complexes
        ],
        "options": cfg.get("options") or {},
        "naver": cfg.get("naver") or {},
    }
    sgg = json.loads(_SGG_PATH.read_text(encoding="utf-8"))

    # 데이터를 JS로 주입할 때 '<'를 \\u003c로 이스케이프 → </script> breakout(XSS) 차단
    def _js(obj):
        return json.dumps(obj, ensure_ascii=False).replace("<", "\\u003c")

    # 카드 지역별 그룹핑용: config 단지명 → 지역 라벨(시군구)
    region_map = {c["name"]: (c.get("region") or c.get("lawd_cd") or "기타 지역")
                  for c in complexes}
    subs = {
        "LAST_RUN": state.get("last_run", "-"),
        "TOTAL": str(len(visible)),
        "WATCHED": str(len(complexes)),
        "DEALS": _js(visible),
        "WARNINGS": _js(warnings),
        "CONFIG": _js(config_pub),
        "REGION_MAP": _js(region_map),
        "SGG": _js(sgg),
        "QUOTES": _js(visible_quotes),
        "QUOTES_META": _js(quotes_meta),
    }
    # 단일 패스 치환: 데이터 안에 우연히 __TOKEN__ 문자열이 있어도 재치환되지 않음.
    # 대문자/언더스코어 placeholder만 매칭 → JS의 __all__/__grouped__ 같은 소문자 센티넬은 안전.
    import re
    html = re.sub(r"__([A-Z_]+)__",
                  lambda m: subs.get(m.group(1), m.group(0)), _TEMPLATE)
    out_path.write_text(html, encoding="utf-8")
