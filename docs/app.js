/* 정책·경제 일정 — 빌드 도구 없이 도는 단일 페이지.
   docs/data/*.json 을 읽어 레일 / 달력 / 표 세 뷰를 그린다. */

const CATEGORIES = {
  MONETARY: "통화정책", INDICATOR: "경제지표", REALESTATE: "부동산",
  FISCAL: "재정·예산", ASSEMBLY: "국회", FINANCE: "금융·감독",
  MARKET: "시장일정", GLOBAL: "해외", CUSTOM: "직접입력",
};
const DOW = ["일", "월", "화", "수", "목", "금", "토"];
const DAY = 86400000;

const state = {
  events: [],
  changedIds: new Set(),
  cursor: new Date(),
  hidden: new Set(),
  query: "",
  minImportance: 0,
  hideCancelled: true,
};

const $ = (id) => document.getElementById(id);
const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const today = () => { const d = new Date(); d.setHours(0, 0, 0, 0); return d; };
const color = (cat) => `var(--c-${cat in CATEGORIES ? cat : "CUSTOM"})`;
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

function dday(dateStr) {
  const diff = Math.round((new Date(dateStr + "T00:00:00") - today()) / DAY);
  if (diff === 0) return "D-DAY";
  return diff > 0 ? `D-${diff}` : `D+${-diff}`;
}

/* ── 데이터 ─────────────────────────────────────── */
async function load() {
  try {
    const [events, changes, runs] = await Promise.all([
      fetch("data/events.json").then((r) => r.json()),
      fetch("data/changes.json").then((r) => r.json()).catch(() => ({ changes: [] })),
      fetch("data/runs.json").then((r) => r.json()).catch(() => ({ runs: [] })),
    ]);

    state.events = events.events || [];
    const cutoff = Date.now() - 7 * DAY;
    for (const c of changes.changes || []) {
      if (c.type !== "NEW" && new Date(c.detected_at).getTime() > cutoff) state.changedIds.add(c.id);
    }

    const last = (runs.runs || [])[0];
    $("stamp-updated").textContent = (events.generated_at || "").replace("T", " ").slice(0, 16) || "기록 없음";
    $("stamp-count").textContent = state.events.length.toLocaleString("ko-KR");
    $("stamp-sources").textContent = last ? last.sources.filter((s) => s.status === "OK").length : "–";
    render();
  } catch (err) {
    $("grid").outerHTML = `<div class="empty"><b>일정을 불러오지 못했습니다.</b>
      data/events.json 이 아직 없다면 저장소에서 “일정 수집” 워크플로를 한 번 실행하세요.</div>`;
    console.error(err);
  }
}

function visible() {
  const q = state.query.trim().toLowerCase();
  return state.events.filter((e) => {
    if (state.hidden.has(e.category)) return false;
    if (e.importance < state.minImportance) return false;
    if (state.hideCancelled && e.status === "CANCELLED") return false;
    if (q && !`${e.title} ${e.agency} ${(e.tags || []).join(" ")}`.toLowerCase().includes(q)) return false;
    return true;
  });
}

/* ── 레일 ───────────────────────────────────────── */
function renderRail(events) {
  const rail = $("rail");
  rail.querySelectorAll(".rail-tick, .rail-month, .rail-now").forEach((n) => n.remove());

  const start = today().getTime() - 30 * DAY;
  const span = 120 * DAY;
  const pos = (t) => ((t - start) / span) * 100;

  const now = document.createElement("div");
  now.className = "rail-now";
  now.style.left = pos(today().getTime()) + "%";
  rail.appendChild(now);

  for (let i = 0; i <= 4; i++) {
    const d = new Date(start + i * 30 * DAY);
    const label = document.createElement("div");
    label.className = "rail-month";
    label.style.left = pos(d.getTime()) + "%";
    label.textContent = `${d.getMonth() + 1}월`;
    rail.appendChild(label);
  }

  for (const e of events) {
    const t = new Date(e.date + "T00:00:00").getTime();
    if (t < start || t > start + span) continue;
    const tick = document.createElement("button");
    tick.className = "rail-tick";
    tick.style.left = pos(t) + "%";
    tick.style.height = `${10 + e.importance * 12}px`;
    tick.style.setProperty("--tick", color(e.category));
    tick.style.opacity = e.status === "CANCELLED" ? ".3" : "1";
    tick.title = `${e.date} ${e.title}`;
    tick.setAttribute("aria-label", `${e.date} ${e.title}`);
    tick.onclick = () => openDrawer(e);
    rail.appendChild(tick);
  }
}

/* ── 카테고리 칩 ─────────────────────────────────── */
function renderChips() {
  const box = $("chips");
  if (box.childElementCount) return;
  for (const [key, label] of Object.entries(CATEGORIES)) {
    const chip = document.createElement("button");
    chip.className = "chip";
    chip.style.setProperty("--dot", color(key));
    chip.textContent = label;
    chip.setAttribute("aria-pressed", "true");
    chip.onclick = () => {
      const on = chip.getAttribute("aria-pressed") === "true";
      chip.setAttribute("aria-pressed", String(!on));
      on ? state.hidden.add(key) : state.hidden.delete(key);
      render();
    };
    box.appendChild(chip);
  }
}

/* ── 달력 ───────────────────────────────────────── */
function renderCalendar(events) {
  const grid = $("grid");
  const y = state.cursor.getFullYear();
  const m = state.cursor.getMonth();
  $("month-label").textContent = `${y}. ${String(m + 1).padStart(2, "0")}`;

  const byDate = new Map();
  for (const e of events) {
    if (!byDate.has(e.date)) byDate.set(e.date, []);
    byDate.get(e.date).push(e);
  }

  const first = new Date(y, m, 1);
  const lead = first.getDay();
  const days = new Date(y, m + 1, 0).getDate();
  const todayIso = iso(today());

  let html = DOW.map((d, i) => `<div class="dow${i === 0 ? " sun" : ""}">${d}</div>`).join("");
  for (let i = 0; i < lead; i++) html += `<div class="cell void"></div>`;

  for (let d = 1; d <= days; d++) {
    const key = iso(new Date(y, m, d));
    const list = (byDate.get(key) || []).sort((a, b) => b.importance - a.importance);
    const isHoliday = list.some((e) => (e.tags || []).includes("공휴일"));
    const cls = ["cell", key === todayIso ? "today" : "", isHoliday ? "holiday" : ""].join(" ");

    const pills = list.slice(0, 3).map((e) => `
      <button class="pill ${e.status === "TENTATIVE" ? "tentative" : ""} ${e.status === "CANCELLED" ? "cancelled" : ""}"
              style="--dot:${color(e.category)}" data-id="${e.id}" title="${esc(e.title)}">
        ${e.importance === 3 ? '<span class="star">★</span> ' : ""}${esc(e.title)}
      </button>`).join("");
    const more = list.length > 3 ? `<div class="more">+${list.length - 3}건</div>` : "";

    html += `<div class="${cls}" role="gridcell"><div class="daynum">${d}</div>${pills}${more}</div>`;
  }
  grid.innerHTML = html;

  grid.querySelectorAll(".pill").forEach((btn) => {
    btn.onclick = () => openDrawer(state.events.find((e) => e.id === btn.dataset.id));
  });
}

/* ── 표 ─────────────────────────────────────────── */
function renderTable(events) {
  const from = new Date(today().getTime() - 14 * DAY);
  const rows = events
    .filter((e) => new Date(e.date + "T00:00:00") >= from)
    .sort((a, b) => a.date.localeCompare(b.date) || b.importance - a.importance)
    .slice(0, 200);

  $("table-count").textContent = `${rows.length}건 (2주 전부터)`;

  if (!rows.length) {
    $("table-wrap").innerHTML = `<div class="empty"><b>조건에 맞는 일정이 없습니다.</b>필터를 넓히거나 검색어를 지워보세요.</div>`;
    return;
  }

  const body = rows.map((e) => {
    const past = new Date(e.date + "T00:00:00") < today();
    const diff = Math.round((new Date(e.date + "T00:00:00") - today()) / DAY);
    const badges = [
      e.status === "TENTATIVE" ? '<span class="badge tentative">잠정</span>' : "",
      e.status === "CANCELLED" ? '<span class="badge cancelled">취소</span>' : "",
      state.changedIds.has(e.id) ? '<span class="badge changed">변경</span>' : "",
    ].join("");
    return `<tr class="${past ? "past" : ""}" data-id="${e.id}" style="cursor:pointer">
      <td class="num">${e.date.slice(5)} <span style="color:var(--ink-3)">${DOW[new Date(e.date + "T00:00:00").getDay()]}</span></td>
      <td class="num"><span class="dday ${diff >= 0 && diff <= 7 ? "soon" : ""}">${dday(e.date)}</span></td>
      <td><span class="tag" style="--dot:${color(e.category)}">${CATEGORIES[e.category] || e.category}</span></td>
      <td>${esc(e.agency)}</td>
      <td>${esc(e.title)}${badges}</td>
      <td class="num">${"★".repeat(e.importance)}</td>
      <td class="num">${e.time || "-"}</td>
    </tr>`;
  }).join("");

  $("table-wrap").innerHTML = `<table>
    <thead><tr><th>날짜</th><th>D-day</th><th>분류</th><th>기관</th><th>이벤트</th><th>중요도</th><th>시각</th></tr></thead>
    <tbody>${body}</tbody></table>`;

  $("table-wrap").querySelectorAll("tbody tr").forEach((tr) => {
    tr.onclick = () => openDrawer(state.events.find((e) => e.id === tr.dataset.id));
  });
}

/* ── 상세 패널 ───────────────────────────────────── */
function openDrawer(e) {
  if (!e) return;
  const statusText = { CONFIRMED: "확정", TENTATIVE: "잠정", CANCELLED: "취소" }[e.status] || e.status;
  $("drawer-body").innerHTML = `
    <span class="tag" style="--dot:${color(e.category)}">${CATEGORIES[e.category] || e.category}</span>
    <h3>${esc(e.title)}</h3>
    <p style="color:var(--ink-2);margin:0">${esc(e.description) || "설명 없음"}</p>
    <dl>
      <dt>날짜</dt><dd>${e.date}${e.end_date ? ` ~ ${e.end_date}` : ""} (${dday(e.date)})</dd>
      <dt>시각</dt><dd>${e.time || "미정 · 종일"}</dd>
      <dt>기관</dt><dd>${esc(e.agency)}</dd>
      <dt>상태</dt><dd>${statusText}</dd>
      <dt>중요도</dt><dd>${"★".repeat(e.importance)}</dd>
      <dt>출처</dt><dd>${e.source_url ? `<a href="${esc(e.source_url)}" target="_blank" rel="noopener">원문 열기</a>` : esc(e.source_id)}</dd>
      <dt>수집</dt><dd class="num" style="font-size:12px">${(e.last_seen_at || "").slice(0, 16).replace("T", " ")}</dd>
    </dl>
    ${e.locked ? '<p style="font-size:12px;color:var(--ink-2)">직접 입력한 일정입니다. 자동 수집이 덮어쓰지 않습니다.</p>' : ""}`;
  $("drawer").dataset.open = "true";
  $("drawer-close").focus();
}
const closeDrawer = () => { $("drawer").dataset.open = "false"; };

/* ── 내보내기 ───────────────────────────────────── */
function download(name, mime, text) {
  const url = URL.createObjectURL(new Blob(["\ufeff" + text], { type: mime }));
  const a = document.createElement("a");
  a.href = url; a.download = name; a.click();
  URL.revokeObjectURL(url);
}

function toICS(events) {
  const stamp = new Date().toISOString().replace(/[-:]|\.\d{3}/g, "");
  const fold = (s) => s.replace(/[\\;,]/g, (c) => "\\" + c).replace(/\n/g, "\\n");
  const lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//kr-policy-calendar//KO", "CALSCALE:GREGORIAN", "X-WR-CALNAME:정책·경제 일정"];
  for (const e of events) {
    if (e.status === "CANCELLED") continue;
    const d = e.date.replace(/-/g, "");
    const end = new Date(new Date((e.end_date || e.date) + "T00:00:00").getTime() + DAY);
    lines.push("BEGIN:VEVENT", `UID:${e.id}@kr-policy-calendar`, `DTSTAMP:${stamp}`,
      `DTSTART;VALUE=DATE:${d}`, `DTEND;VALUE=DATE:${iso(end).replace(/-/g, "")}`,
      `SUMMARY:${fold((e.status === "TENTATIVE" ? "[잠정] " : "") + e.title)}`,
      `DESCRIPTION:${fold(`${e.agency} · ${CATEGORIES[e.category] || e.category}\n${e.description || ""}`)}`,
      e.source_url ? `URL:${e.source_url}` : "", "END:VEVENT");
  }
  lines.push("END:VCALENDAR");
  return lines.filter(Boolean).join("\r\n");
}

function toCSV(events) {
  const head = ["날짜", "요일", "분류", "기관", "이벤트", "중요도", "상태", "시각", "출처"];
  const cell = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
  const rows = events.map((e) => [
    e.date, DOW[new Date(e.date + "T00:00:00").getDay()], CATEGORIES[e.category] || e.category,
    e.agency, e.title, e.importance, e.status, e.time || "", e.source_url || "",
  ].map(cell).join(","));
  return [head.map(cell).join(","), ...rows].join("\r\n");
}

/* ── 렌더 & 바인딩 ───────────────────────────────── */
function render() {
  const events = visible();
  renderChips();
  renderRail(events);
  renderCalendar(events);
  renderTable(events);
}

function bind() {
  $("prev").onclick = () => { state.cursor.setMonth(state.cursor.getMonth() - 1); render(); };
  $("next").onclick = () => { state.cursor.setMonth(state.cursor.getMonth() + 1); render(); };
  $("today").onclick = () => { state.cursor = new Date(); render(); };
  $("q").oninput = (e) => { state.query = e.target.value; render(); };
  $("importance").onchange = (e) => { state.minImportance = +e.target.value; render(); };
  $("hide-cancelled").onchange = (e) => { state.hideCancelled = e.target.checked; render(); };
  $("drawer-close").onclick = closeDrawer;
  $("export-ics").onclick = () => download("policy-calendar.ics", "text/calendar", toICS(visible()));
  $("export-csv").onclick = () => download("policy-calendar.csv", "text/csv", toCSV(visible()));
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeDrawer(); });
}

bind();
load();
