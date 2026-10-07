const app = document.getElementById("app");

const state = {
  user: null,
  view: "dashboard",
  params: {},
  employee: null,
  level: null,
};

const NAV = {
  corporate_safety_head: [
    ["dashboard", "Dashboard"], ["units", "Units"], ["employees", "Employees"],
    ["progress", "Learning Progress"], ["analytics", "Analytics"], ["reports", "Reports"],
    ["logs", "Activity Logs"], ["profile", "Profile"],
  ],
  function_safety_unit_head: [
    ["dashboard", "Dashboard"], ["unit", "My Unit"], ["employees", "Employees"],
    ["progress", "Learning Progress"], ["attention", "At-Risk Employees"],
    ["reports", "Reports"], ["profile", "Profile"],
  ],
  operator_workman: [
    ["dashboard", "Dashboard"], ["learning", "My Learning"], ["roadmap", "Learning Roadmap"],
    ["assessments", "My Assessments"], ["progress", "My Progress"], ["profile", "Profile"],
  ],
};

const ROLE_LABEL = {
  corporate_safety_head: "Corporate Safety Head",
  function_safety_unit_head: "Function Safety Unit Head",
  operator_workman: "Operator / Workman",
};

/* ------------------------------------------------------------------ helpers */

function esc(v) {
  return String(v ?? "").replace(/[&<>'"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[c]));
}
function pct(v) { return Math.max(0, Math.min(100, Number(v || 0))); }
function levelLabel(n) { return `Level ${String(n).padStart(2, "0")}`; }
function fmtDay(v) { return v ? String(v).replace("T", " ").slice(0, 16) : "-"; }
function statusClass(s) { return String(s || "").split(" ")[0]; }

function badge(status) {
  return `<span class="status ${esc(statusClass(status))}">${esc(status)}</span>`;
}
function bar(value, tone = "") {
  return `<div class="bar ${tone}"><span style="width:${pct(value)}%"></span></div>`;
}
function kpiGrid(items) {
  return `<section class="grid kpis">${items.map(i => `
    <div class="card kpi ${i.tone ? "kpi-" + i.tone : ""}">
      <div class="label">${esc(i.label)}</div>
      <div class="value">${esc(i.value)}</div>
      ${i.hint ? `<div class="hint">${esc(i.hint)}</div>` : ""}
    </div>`).join("")}</section>`;
}
function emptyState(msg, hint = "") {
  return `<div class="empty"><strong>${esc(msg)}</strong>${hint ? `<p>${esc(hint)}</p>` : ""}</div>`;
}
function sectionTitle(title, sub = "") {
  return `<div class="section-title"><h2>${esc(title)}</h2>${sub ? `<p class="subtle">${esc(sub)}</p>` : ""}</div>`;
}

async function api(path, options = {}) {
  let res;
  try {
    res = await fetch(path, { credentials: "same-origin", headers: { "Content-Type": "application/json" }, ...options });
  } catch {
    const e = new Error("Network error. Check your connection and try again.");
    e.code = "NETWORK";
    throw e;
  }
  const data = await res.json().catch(() => ({}));
  if (res.status === 401) {
    state.user = null;
    const e = new Error(data.message || "Session expired. Please login again.");
    e.code = data.error || "SESSION_EXPIRED";
    renderLogin(e.code === "AUTH_REQUIRED" ? "" : e.message);
    throw e;
  }
  if (!res.ok) {
    const e = new Error(data.message || "Request failed.");
    e.code = data.error || "REQUEST_FAILED";
    e.status = res.status;
    throw e;
  }
  return data;
}

async function run(fn) {
  try {
    await fn();
  } catch (err) {
    if (err && (err.code === "AUTH_REQUIRED" || err.code === "SESSION_EXPIRED")) return;
    renderError(err);
  }
}

/* ------------------------------------------------------------------ login */

function renderLogin(message = "") {
  app.innerHTML = `
    <main class="login-page">
      <section class="login-card">
        <div class="brand"><strong>MILL LMS</strong><span>Safety &amp; Production Learning</span></div>
        <h1>Secure Employee Access</h1>
        <p class="subtle">Login with your Employee ID. Access is granted by your server-side role and unit assignment.</p>
        ${message ? `<div class="notice error">${esc(message)}</div>` : ""}
        <form id="loginForm">
          <label>Employee ID<input id="employeeId" autocomplete="username" value="EMP001" required></label>
          <label>Password<input id="password" type="password" autocomplete="current-password" value="demo123" required></label>
          <button type="submit">Login</button>
        </form>
        <div class="demo">
          <strong>Demo access &mdash; password <em>demo123</em></strong>
          <div class="chips">
            <button type="button" class="chip" data-emp="CORP001">CORP001 Corporate</button>
            <button type="button" class="chip" data-emp="RMLH001">RMLH001 Unit Head</button>
            <button type="button" class="chip" data-emp="EMP001">EMP001 Operator</button>
          </div>
        </div>
      </section>
    </main>`;
  document.querySelectorAll("[data-emp]").forEach(b => b.addEventListener("click", () => {
    document.getElementById("employeeId").value = b.dataset.emp;
    document.getElementById("password").value = "demo123";
  }));
  document.getElementById("loginForm").addEventListener("submit", async e => {
    e.preventDefault();
    try {
      const data = await api("/api/login", {
        method: "POST",
        body: JSON.stringify({ employee_id: document.getElementById("employeeId").value.trim(), password: document.getElementById("password").value }),
      });
      state.user = data.user;
      state.view = "dashboard";
      state.params = {};
      state.employee = null;
      await renderApp();
    } catch (err) {
      if (err.code !== "AUTH_REQUIRED" && err.code !== "SESSION_EXPIRED") renderLogin(err.message);
    }
  });
}

/* ------------------------------------------------------------------ shell */

function go(view, params = {}, extra = {}) {
  state.view = view;
  state.params = params;
  Object.assign(state, extra);
  renderApp();
}

async function renderApp() {
  if (!state.user) {
    try { state.user = (await api("/api/me")).user; } catch { return; }
  }
  const role = state.user.role;
  const items = NAV[role] || [];
  const nav = items.map(([key, label]) =>
    `<button class="${state.view === key ? "active" : ""}" data-view="${key}">${esc(label)}</button>`).join("");
  app.innerHTML = `
    <div class="shell role-${role === "operator_workman" ? "operator" : "manager"}">
      <aside class="sidebar">
        <div class="brand"><strong>MILL LMS</strong><span>Safety &amp; Production</span></div>
        <div class="scope">
          <span>${esc(ROLE_LABEL[role] || role)}</span>
          <strong>${esc(state.user.unit_code || "All Units")}</strong>
        </div>
        <nav class="nav">${nav}</nav>
        <div class="userbox">
          <strong>${esc(state.user.name)}</strong>
          <span>${esc(state.user.employee_id)}</span>
          <button class="secondary" id="logoutBtn">Logout</button>
        </div>
      </aside>
      <main class="main" id="main"></main>
    </div>`;
  document.querySelectorAll("[data-view]").forEach(btn =>
    btn.addEventListener("click", () => go(btn.dataset.view)));
  document.getElementById("logoutBtn").addEventListener("click", async () => {
    try { await api("/api/logout", { method: "POST", body: "{}" }); } catch { /* session already gone */ }
    state.user = null;
    renderLogin("You have been logged out securely.");
  });
  await dispatch();
}

async function dispatch() {
  const role = state.user.role;
  const views = role === "corporate_safety_head" ? corporateViews()
    : role === "function_safety_unit_head" ? unitHeadViews()
      : operatorViews();
  const fn = views[state.view] || views.dashboard;
  await run(() => fn(normalizeParams(state.params)));
}

function corporateViews() {
  return {
    dashboard: corpDashboard, units: unitsView, unit: unitDetailView, employees: employeesView,
    progress: progressView, analytics: analyticsView, reports: reportsView, logs: logsView,
    profile: profileView, employee: employeeView, learning: () => go("dashboard"),
  };
}
function unitHeadViews() {
  return {
    dashboard: headDashboard, unit: myUnitView, employees: employeesView, progress: progressView,
    attention: attentionView, reports: reportsView, profile: profileView, employee: employeeView,
    units: () => go("dashboard"), analytics: () => go("dashboard"), logs: () => go("dashboard"),
  };
}
function operatorViews() {
  return {
    dashboard: operatorDashboard, learning: learningView, roadmap: roadmapView,
    assessments: assessmentsView, progress: myProgressView, profile: profileView,
    units: () => go("dashboard"), employees: () => go("dashboard"), employee: () => go("dashboard"),
  };
}

function main() { return document.getElementById("main"); }
function setMain(html) { main().innerHTML = html; window.scrollTo({ top: 0, behavior: "instant" }); }

/* ------------------------------------------------------------------ shared components */

function topbar(title, sub = "", right = "") {
  return `<div class="topbar"><div><h1>${esc(title)}</h1>${sub ? `<p class="subtle">${sub}</p>` : ""}</div><div class="topbar-actions">${right}</div></div>`;
}

function kpisFor(k, unitScope) {
  const items = unitScope
    ? [
        { label: "Total Employees", value: k.total_employees },
        { label: "Active Employees", value: k.active_employees },
        { label: "Completion", value: `${k.overall_completion_percent}%` },
        { label: "Average Score", value: `${k.average_score}%` },
        { label: "Completed Training", value: k.completed_training },
        { label: "Pending Training", value: k.pending_training },
        { label: "At-Risk", value: k.at_risk, tone: k.at_risk ? "warn" : "" },
        { label: "Not Started", value: k.not_started, tone: k.not_started ? "warn" : "" },
      ]
    : [
        { label: "Total Employees", value: k.total_employees },
        { label: "Total Units", value: k.total_units },
        { label: "Overall Completion", value: `${k.overall_completion_percent}%` },
        { label: "Average Score", value: `${k.average_score}%` },
        { label: "On Track", value: k.on_track, tone: "good" },
        { label: "Needs Attention", value: k.needs_attention, tone: "warn" },
        { label: "Inactive", value: k.inactive, tone: "bad" },
      ];
  return kpiGrid(items);
}

function employeeTable(rows, opts = {}) {
  const showUnit = opts.showUnit !== false;
  if (!rows || !rows.length) return emptyState(opts.empty || "No employees match these filters.", opts.emptyHint || "");
  const head = ["Employee ID", "Employee Name"];
  if (showUnit) head.push("Unit");
  head.push("Current Level", "Progress", "Score", "Last Activity", "Status", "Action");
  return `<div class="table-wrap"><table>
    <thead><tr>${head.map(h => `<th>${h}</th>`).join("")}</tr></thead>
    <tbody>${rows.map(e => `<tr>
      <td><strong>${esc(e.employee_id)}</strong></td>
      <td>${esc(e.name)}</td>
      ${showUnit ? `<td>${esc(e.unit_code)}</td>` : ""}
      <td>${levelLabel(e.current_level)}</td>
      <td class="num">${e.progress_percent}% ${bar(e.progress_percent, e.progress_percent >= 66 ? "" : e.progress_percent >= 33 ? "warn" : "bad")}</td>
      <td class="num">${e.average_score}%</td>
      <td>${fmtDay(e.last_activity)}</td>
      <td>${badge(e.training_status)}</td>
      <td><button class="secondary small" data-emp="${esc(e.employee_id)}">View</button></td>
    </tr>`).join("")}</tbody></table></div>`;
}

function bindEmployeeButtons(then) {
  document.querySelectorAll("[data-emp]").forEach(b => b.addEventListener("click", () => {
    state.employee = b.dataset.emp;
    go("employee");
    if (then) then();
  }));
}

function filterBar(defs) {
  return `<div class="filters">
    ${defs.filter(d => d.type !== "hidden").map(d => {
      if (d.type === "search") {
        return `<label class="grow">${esc(d.label)}<input data-filter="${d.id}" type="search" placeholder="${esc(d.placeholder || "")}" value="${esc(d.value || "")}"></label>`;
      }
      return `<label>${esc(d.label)}<select data-filter="${d.id}">
        ${d.options.map(o => `<option value="${esc(o)}" ${String(d.value || "") === String(o) ? "selected" : ""}>${esc(o)}</option>`).join("")}
      </select></label>`;
    }).join("")}
    <button class="secondary" id="clearFilters">Reset</button>
  </div>`;
}

function bindFilters(render) {
  document.querySelectorAll("[data-filter]").forEach(el => {
    const apply = () => {
      state.params = normalizeParams({ ...state.params, [el.dataset.filter]: el.value });
      render();
    };
    el.addEventListener("change", apply);
    if (el.tagName === "INPUT") el.addEventListener("keyup", e => { if (e.key === "Enter") apply(); });
  });
  const clear = document.getElementById("clearFilters");
  if (clear) clear.addEventListener("click", () => { state.params = {}; render(); });
}

function qs(params) {
  const p = Object.entries(params).filter(([, v]) => v !== "" && v != null);
  return p.length ? "?" + p.map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`).join("&") : "";
}

/* ------------------------------------------------------------------ charts */

function barChart(items, valueKey, labelKey, suffix = "%", maxOverride) {
  if (!items.length) return emptyState("No data available for this chart.");
  const max = maxOverride || Math.max(100, ...items.map(i => Number(i[valueKey] || 0)));
  return `<div class="chart bars">${items.map(i => `
    <div class="bar-row">
      <span class="bar-label">${esc(i[labelKey])}</span>
      <div class="bar-track"><span style="width:${Math.round(pct(Number(i[valueKey]) / max * 100))}%"></span></div>
      <span class="bar-value">${esc(i[valueKey])}${suffix}</span>
    </div>`).join("")}</div>`;
}

function donut(dist) {
  const colors = { "ON TRACK": "#268a57", "NEEDS ATTENTION": "#e0a80f", "INACTIVE": "#b83b45", "COMPLETED": "#2d6cdf" };
  const entries = Object.entries(dist);
  const total = entries.reduce((a, [, v]) => a + v, 0);
  let acc = 0;
  const stops = entries.map(([k, v]) => {
    const start = total ? (acc / total) * 100 : 0;
    acc += v;
    const end = total ? (acc / total) * 100 : 0;
    return `${colors[k] || "#94a3ab"} ${start}% ${end}%`;
  });
  return `<div class="donut-wrap">
    <div class="donut" style="background:conic-gradient(${stops.join(",")})">
      <div class="donut-hole"><strong>${total}</strong><span>Employees</span></div>
    </div>
    <ul class="legend">${entries.map(([k, v]) => `<li><i style="background:${colors[k] || "#94a3ab"}"></i>${esc(k)} <strong>${total ? Math.round((v / total) * 100) : 0}%</strong><span>${v}</span></li>`).join("")}</ul>
  </div>`;
}

function funnelChart(rows) {
  if (!rows || !rows.length) return emptyState("No training data available.");
  const totals = rows.map(r => r.completed + r.in_progress + r.locked);
  const max = Math.max(1, ...totals);
  return `<div class="funnel">${rows.map(r => `
    <div class="funnel-col" title="Level ${r.level}: ${r.completed} completed, ${r.in_progress} in progress, ${r.locked} locked">
      <div class="funnel-stack" style="height:${Math.round(((r.completed + r.in_progress + r.locked) / max) * 160)}px">
        <span class="seg locked" style="flex:${Math.max(0, r.locked)}"></span>
        <span class="seg progress" style="flex:${Math.max(0, r.in_progress)}"></span>
        <span class="seg done" style="flex:${Math.max(0, r.completed)}"></span>
      </div>
      <span class="funnel-label">${String(r.level).padStart(2, "0")}</span>
      <span class="funnel-value">${r.completed}</span>
    </div>`).join("")}</div>
    <div class="legend inline">
      <li><i class="seg-dot done"></i>Completed</li>
      <li><i class="seg-dot progress"></i>In progress</li>
      <li><i class="seg-dot locked"></i>Locked / not started</li>
    </div>`;
}

function roadmapHtml(nodes, opts = {}) {
  const clickable = opts.clickable !== false;
  return `<section class="roadmap">${nodes.map(n => {
    const mark = n.state === "COMPLETED" ? "✓" : n.state === "CURRENT" ? "●" : "🔒";
    const label = n.state === "COMPLETED" ? "Completed" : n.state === "CURRENT" ? "Current" : "Locked";
    return `<button class="level ${n.state}" ${clickable && n.state !== "LOCKED" ? `data-level="${n.level_number}"` : "disabled"}
      aria-label="${label} ${levelLabel(n.level_number)}">
      <span class="mark">${mark}</span>
      <strong>${levelLabel(n.level_number)}</strong>
      <span class="lvl-title">${esc(String(n.title).replace(/^Level \d+ - /, ""))}</span>
      <span class="lvl-state">${label}</span>
    </button>`;
  }).join("")}</section>`;
}

/* ------------------------------------------------------------------ corporate */

async function corpDashboard() {
  const d = await api("/api/corporate/dashboard");
  setMain(`
    ${topbar("Corporate Safety Dashboard", "Organization-wide safety training visibility across all 8 units.",
      `<button class="secondary" data-nav="reports">Reports</button>`)}
    ${kpisFor(d.kpis, false)}
    <div class="split-2">
      <section class="card">
        ${sectionTitle("Unit Performance", "Completion percentage by unit")}
        ${barChart(d.units, "completion_percent", "unit_code")}
      </section>
      <section class="card">
        ${sectionTitle("Learner Status Distribution", "All operators and workmen")}
        ${donut(d.kpis.status_distribution)}
      </section>
    </div>
    ${sectionTitle("Units", "Select a unit to open its training dashboard")}
    <section class="grid cards">${d.units.map(u => unitCard(u)).join("")}</section>
    ${sectionTitle("Employees Needing Attention", "At-risk and inactive learners")}
    ${employeeTable(d.employees.filter(e => e.training_status === "NEEDS ATTENTION" || e.training_status === "INACTIVE").slice(0, 8),
      { empty: "All employees are on track." })}
    <div class="split-2">
      <section class="card">
        ${sectionTitle("Average Score by Unit")}
        ${barChart(d.units, "average_score", "unit_code")}
      </section>
      <section class="card">
        ${sectionTitle("Status Distribution by Unit", "On track vs needs attention vs inactive")}
        ${d.units.map(u => `<div class="mini-row"><span>${u.unit_code}</span>
          <div class="stackbar">
            <span class="on" style="width:${share(u, "on_track", u.employee_count)}%"></span>
            <span class="att" style="width:${share(u, "at_risk", u.employee_count)}%"></span>
            <span class="off" style="width:${share(u, "inactive", u.employee_count)}%"></span>
          </div><em>${u.employee_count}</em></div>`).join("")}
      </section>
    </div>`);
  document.querySelectorAll("[data-unit]").forEach(b => b.addEventListener("click", () => go("unit", { unit: b.dataset.unit })));
  document.querySelectorAll("[data-nav]").forEach(b => b.addEventListener("click", () => go(b.dataset.nav)));
  bindEmployeeButtons();
}

function share(u, key, total) { return total ? Math.round((u[key] / total) * 100) : 0; }

function unitCard(u) {
  const tone = u.completion_percent >= 60 ? "" : u.completion_percent >= 30 ? "warn" : "bad";
  return `<article class="card unit-card">
    <div class="unit-head"><h3>${esc(u.unit_code)}</h3>${badge(u.at_risk > 0 ? "NEEDS ATTENTION" : "ON TRACK")}</div>
    <p class="subtle">${esc(u.unit_name)}</p>
    <div class="unit-grid">
      <div><span>Employees</span><strong>${u.employee_count}</strong></div>
      <div><span>Completion</span><strong>${u.completion_percent}%</strong></div>
      <div><span>Avg Score</span><strong>${u.average_score}%</strong></div>
      <div><span>At Risk</span><strong>${u.at_risk}</strong></div>
    </div>
    ${bar(u.completion_percent, tone)}
    <button class="secondary" data-unit="${esc(u.unit_code)}">View Unit</button>
  </article>`;
}

async function unitsView() {
  const d = await api("/api/units");
  setMain(`
    ${topbar("Units", "Centralized unit master with live training performance.")}
    <div class="table-wrap"><table>
      <thead><tr><th>Unit Code</th><th>Unit Name</th><th>Safety Head</th><th>Employees</th><th>Active</th><th>Completion</th><th>Avg Score</th><th>Status</th><th>Action</th></tr></thead>
      <tbody>${d.units.map(u => `<tr>
        <td><strong>${esc(u.unit_code)}</strong></td>
        <td>${esc(u.unit_name)}</td>
        <td>${esc(u.safety_head ? `${u.safety_head.name} (${u.safety_head.employee_id})` : "-")}</td>
        <td class="num">${u.employee_count}</td>
        <td class="num">${u.active_employees}</td>
        <td class="num">${u.completion_percent}% ${bar(u.completion_percent, u.completion_percent >= 60 ? "" : "warn")}</td>
        <td class="num">${u.average_score}%</td>
        <td>${badge(u.status)}</td>
        <td><button class="secondary small" data-unit="${esc(u.unit_code)}">View Unit</button></td>
      </tr>`).join("")}</tbody></table></div>`);
  document.querySelectorAll("[data-unit]").forEach(b => b.addEventListener("click", () => go("unit", { unit: b.dataset.unit })));
}

async function unitDetailView(params) {
  const code = params.unit || params.code;
  const d = await api(`/api/units/${encodeURIComponent(code)}${qs({ status: params.status, q: params.q, level: params.level })}`);
  const k = d.kpis;
  setMain(`
    ${topbar(`${d.unit.unit_code} - Safety Training Dashboard`, `${esc(d.unit.name || d.unit.unit_name)} &middot; Safety Head: ${esc(d.unit.safety_head ? d.unit.safety_head.name : "-")}`,
      `<button class="secondary" id="backToUnits">Back to Units</button>`)}
    ${kpisFor(k, true)}
    <div class="split-2">
      <section class="card">${sectionTitle("Learner Status", d.unit.unit_code)}${donut(k.status_distribution)}</section>
      <section class="card">${sectionTitle("Level Completion", "Completed learners per level")}${funnelChart((await api(`/api/units/${encodeURIComponent(code)}/progress`)).funnel)}</section>
    </div>
    ${sectionTitle("Employee Progress", `${d.employees.length} employees in scope`)}
    ${filterBar([
      { id: "status", label: "Training Status", options: ["All", "ON TRACK", "NEEDS ATTENTION", "INACTIVE", "COMPLETED"], value: params.status === "All" ? "" : params.status },
      { id: "level", label: "Current Level", options: ["All", ...Array.from({ length: 16 }, (_, i) => String(i + 1))], value: params.level },
      { id: "q", label: "Search", type: "search", placeholder: "Employee ID or name", value: params.q },
    ])}
    ${employeeTable(d.employees, { showUnit: false, empty: "No employees match these filters." })}
    ${sectionTitle("At-Risk Employees", "Requires supervisor follow-up")}
    ${employeeTable(d.at_risk, { showUnit: false, empty: "No at-risk employees in this unit." })}`);
  document.getElementById("backToUnits").addEventListener("click", () => go("units"));
  bindFilters(() => run(() => unitDetailView(state.params)));
  bindEmployeeButtons();
}

async function headDashboard() {
  const d = await api("/api/unit/dashboard");
  const attention = d.employees.filter(e => e.training_status === "NEEDS ATTENTION" || e.training_status === "INACTIVE");
  setMain(`
    ${topbar(`${d.unit.unit_code} - Safety Training Dashboard`, "Function Safety Unit Head view. Only your assigned unit is accessible.",
      `<button class="secondary" data-nav="attention">At-Risk Employees (${attention.length})</button>`)}
    ${kpisFor(d.kpis, true)}
    <div class="split-2">
      <section class="card">${sectionTitle("Learner Status", d.unit.unit_name)}${donut(d.kpis.status_distribution)}</section>
      <section class="card">${sectionTitle("Completion Snapshot")}
        ${barChart([{ label: "Completion", value: d.kpis.overall_completion_percent }, { label: "Average Score", value: d.kpis.average_score }, { label: "On Track", value: d.kpis.total_employees ? Math.round((d.kpis.on_track / d.kpis.total_employees) * 100) : 0 }], "value", "label")}
        <p class="subtle">On track ${d.kpis.on_track} &middot; Needs attention ${d.kpis.needs_attention} &middot; Inactive ${d.kpis.inactive} &middot; Not started ${d.kpis.not_started}</p>
      </section>
    </div>
    ${sectionTitle("Employee Progress", "Select an employee to view full learning progress")}
    ${employeeTable(d.employees, { showUnit: false, empty: "No employees in this unit." })}`);
  document.querySelectorAll("[data-nav]").forEach(b => b.addEventListener("click", () => go(b.dataset.nav)));
  bindEmployeeButtons();
}

async function myUnitView(params) {
  const p = { status: params.status, level: params.level, q: params.q };
  const [d, prog] = await Promise.all([
    api(`/api/unit/dashboard${qs(p)}`),
    api("/api/unit/progress"),
  ]);
  setMain(`
    ${topbar(`${d.unit.unit_code} - My Unit`, `${esc(d.unit.unit_name)} &middot; Function Safety Head: ${esc(d.unit.safety_head ? `${d.unit.safety_head.name} (${d.unit.safety_head.employee_id})` : "-")}`)}
    <section class="card unit-master">
      <div class="kv"><span>Unit Code</span><strong>${esc(d.unit.unit_code)}</strong></div>
      <div class="kv"><span>Unit Name</span><strong>${esc(d.unit.unit_name)}</strong></div>
      <div class="kv"><span>Safety Head</span><strong>${esc(d.unit.safety_head ? d.unit.safety_head.name : "-")}</strong></div>
      <div class="kv"><span>Employees</span><strong>${d.kpis.total_employees}</strong></div>
      <div class="kv"><span>Active</span><strong>${d.kpis.active_employees}</strong></div>
      <div class="kv"><span>Completion</span><strong>${d.kpis.overall_completion_percent}%</strong></div>
      <div class="kv"><span>Average Score</span><strong>${d.kpis.average_score}%</strong></div>
      <div class="kv"><span>Unit Status</span><strong>${esc(d.unit.status)}</strong></div>
    </section>
    <div class="split-2">
      <section class="card">${sectionTitle("Level Completion Funnel", "Completed learners per level")}${funnelChart(prog.funnel)}</section>
      <section class="card">${sectionTitle("Learner Status")}${donut(d.kpis.status_distribution)}</section>
    </div>
    ${sectionTitle("Employees", `${d.employees.length} in scope`)}
    ${filterBar([
      { id: "status", label: "Training Status", options: ["All", "ON TRACK", "NEEDS ATTENTION", "INACTIVE", "COMPLETED"], value: params.status === "All" ? "" : params.status },
      { id: "level", label: "Current Level", options: ["All", ...Array.from({ length: 16 }, (_, i) => String(i + 1))], value: params.level },
      { id: "q", label: "Search", type: "search", placeholder: "Employee ID or name", value: params.q },
    ])}
    ${employeeTable(d.employees, { showUnit: false })}`);
  bindFilters(() => run(() => myUnitView(state.params)));
  bindEmployeeButtons();
}

async function employeesView(params) {
  const isCorp = state.user.role === "corporate_safety_head";
  const unitOpts = ["All Units", "RML", "RST", "RMU", "RMF", "SAN", "SRS", "SVSM", "RTL-S"];
  const d = await api(`/api/employees${qs({ unit: isCorp ? params.unit : "", status: params.status, q: params.q, level: params.level, min_progress: params.min_progress })}`);
  setMain(`
    ${topbar("Employees", isCorp
      ? "Server-side filtered employee progress across all units."
      : `Employees of your assigned unit only (${state.user.unit_code}). Other units are denied by the backend.`)}
    ${filterBar([
      isCorp ? { id: "unit", label: "Unit", options: unitOpts, value: params.unit || "All Units" } : { id: "unit", label: "Unit", type: "hidden" },
      { id: "status", label: "Training Status", options: ["All", "ON TRACK", "NEEDS ATTENTION", "INACTIVE", "COMPLETED"], value: params.status === "All" ? "" : params.status },
      { id: "level", label: "Current Level", options: ["All", ...Array.from({ length: 16 }, (_, i) => String(i + 1))], value: params.level },
      { id: "min_progress", label: "Min Progress %", options: ["All", "0", "25", "50", "75", "90"], value: params.min_progress },
      { id: "q", label: "Search", type: "search", placeholder: "Employee ID or name", value: params.q },
    ])}
    ${employeeTable(d.employees, { showUnit: isCorp })}`);
  bindFilters(() => run(() => employeesView(normalizeParams(state.params))));
  bindEmployeeButtons();
}

function normalizeParams(p) {
  const out = { ...p };
  if (out.unit === "All Units") out.unit = "";
  if (out.status === "All") out.status = "";
  if (out.level === "All") out.level = "";
  if (out.min_progress === "All") out.min_progress = "";
  if (out.unit === "") delete out.unit;
  return out;
}

async function attentionView(params) {
  const d = await api(`/api/at-risk${qs({ unit: params.unit })}`);
  setMain(`
    ${topbar("At-Risk Employees", d.unit ? `Unit ${esc(d.unit)} only.` : "All units, ranked by risk reason.")}
    ${d.count ? `<div class="table-wrap"><table>
      <thead><tr><th>Employee ID</th><th>Name</th><th>Unit</th><th>Level</th><th>Progress</th><th>Score</th><th>Status</th><th>Reason</th><th>Action</th></tr></thead>
      <tbody>${d.employees.map(e => `<tr>
        <td><strong>${esc(e.employee_id)}</strong></td><td>${esc(e.name)}</td><td>${esc(e.unit_code)}</td>
        <td>${levelLabel(e.current_level)}</td><td class="num">${e.progress_percent}%</td><td class="num">${e.average_score}%</td>
        <td>${badge(e.training_status)}</td><td class="reason">${esc(e.reason)}</td>
        <td><button class="secondary small" data-emp="${esc(e.employee_id)}">View</button></td>
      </tr>`).join("")}</tbody></table></div>`
      : emptyState("No employees currently need attention.", "Everyone in scope is on track or completed.")}`);
  bindEmployeeButtons();
}

async function progressView(params) {
  const isCorp = state.user.role === "corporate_safety_head";
  const d = await api(isCorp ? "/api/analytics" : "/api/unit/progress");
  const funnel = isCorp ? d.level_funnel : d.funnel;
  let body = "";
  if (isCorp) {
    const employees = (await api(`/api/employees${qs({ unit: params.unit, status: params.status, q: params.q })}`)).employees;
    body = `
      <section class="card">${sectionTitle("Level Completion Funnel", "Completed learners at each of the 16 levels")}${funnelChart(funnel)}</section>
      <div class="split-2">
        <section class="card">${sectionTitle("Completion by Unit")}${barChart(d.unit_comparison, "completion_percent", "unit_code")}</section>
        <section class="card">${sectionTitle("Average Score by Unit")}${barChart(d.unit_comparison, "average_score", "unit_code")}</section>
      </div>
      ${sectionTitle("Employee Learning Progress")}
      ${filterBar([
        { id: "unit", label: "Unit", options: ["All Units", "RML", "RST", "RMU", "RMF", "SAN", "SRS", "SVSM", "RTL-S"], value: params.unit || "All Units" },
        { id: "status", label: "Training Status", options: ["All", "ON TRACK", "NEEDS ATTENTION", "INACTIVE", "COMPLETED"], value: params.status },
        { id: "q", label: "Search", type: "search", placeholder: "Employee ID or name", value: params.q },
      ])}
      ${employeeTable(employees, { showUnit: true })}`;
  } else {
    body = `
      <section class="card">${sectionTitle("Level Completion Funnel", `Completed learners at each of the 16 levels for ${state.user.unit_code}`)}${funnelChart(funnel)}</section>
      ${sectionTitle("Employee Learning Progress")}
      ${employeeTable(d.employees, { showUnit: false })}`;
  }
  setMain(`
    ${topbar("Learning Progress", isCorp ? "Organization-wide level completion funnel and unit comparison." : `Level completion funnel for ${esc(state.user.unit_code)}.`)}
    ${body}`);
  if (isCorp) bindFilters(() => run(() => progressView(state.params)));
  bindEmployeeButtons();
}

async function analyticsView() {
  const d = await api("/api/analytics");
  setMain(`
    ${topbar("Analytics", "Corporate Safety Head only. Generated " + fmtDay(d.generated_at))}
    <div class="split-2">
      <section class="card">${sectionTitle("Unit Comparison", "Completion percentage")}${barChart(d.unit_comparison, "completion_percent", "unit_code")}</section>
      <section class="card">${sectionTitle("Learner Status Distribution")}${donut(d.status_distribution)}</section>
    </div>
    <div class="split-2">
      <section class="card">${sectionTitle("Average Score by Unit")}${barChart(d.unit_comparison, "average_score", "unit_code")}</section>
      <section class="card">${sectionTitle("Score Bands", "Employees grouped by average assessment score")}${barChart(d.score_bands, "count", "band", "", Math.max(1, ...d.score_bands.map(b => b.count)))}</section>
    </div>
    ${sectionTitle("At-Risk Employees", `${d.at_risk.length} require follow-up`)}
    ${employeeTable(d.at_risk, { empty: "No at-risk employees." })}`);
  bindEmployeeButtons();
}

async function reportsView(params) {
  const isCorp = state.user.role === "corporate_safety_head";
  const p = normalizeParams({ ...params });
  const data = await api(`/api/reports${qs(p)}`);
  const unitOpts = ["All Units", "RML", "RST", "RMU", "RMF", "SAN", "SRS", "SVSM", "RTL-S"];
  setMain(`
    ${topbar("Reports", "Filter, preview and export training data.", `<button class="warning" id="csvBtn">Download CSV</button>`)}
    <section class="card">
      <div class="filters">
        ${isCorp ? `<label>Unit<select data-filter="unit">${unitOpts.map(o => `<option ${((p.unit || "All Units") === o) ? "selected" : ""}>${o}</option>`).join("")}</select></label>` : `<label>Unit<input value="${esc(state.user.unit_code)}" disabled></label>`}
        <label>Status<select data-filter="status">${["All", "ON TRACK", "NEEDS ATTENTION", "INACTIVE", "COMPLETED"].map(o => `<option ${((p.status || "All") === o) ? "selected" : ""}>${o}</option>`).join("")}</select></label>
        <label>Level<select data-filter="level">${["All", ...Array.from({ length: 16 }, (_, i) => String(i + 1))].map(o => `<option ${((p.level || "All") === o) ? "selected" : ""}>${o}</option>`).join("")}</select></label>
        <label>Report Scope<select data-filter="scope">${[["employee", "Employee summary"], ["module", "Module detail"]].map(([v, l]) => `<option value="${v}" ${(p.scope || "employee") === v ? "selected" : ""}>${l}</option>`).join("")}</select></label>
        <label>From<input type="date" data-filter="from" value="${esc(p.from || "")}"></label>
        <label>To<input type="date" data-filter="to" value="${esc(p.to || "")}"></label>
        <button class="secondary" id="clearFilters">Reset</button>
      </div>
    </section>
    ${kpiGrid([
      { label: "Rows", value: data.summary.rows },
      { label: "Average Progress", value: `${data.summary.average_progress}%` },
      { label: "Average Score", value: `${data.summary.average_score}%` },
      { label: "On Track", value: data.summary.status_counts["ON TRACK"] },
      { label: "Needs Attention", value: data.summary.status_counts["NEEDS ATTENTION"] },
      { label: "Inactive", value: data.summary.status_counts["INACTIVE"] },
      { label: "Completed", value: data.summary.status_counts["COMPLETED"] },
    ])}
    ${data.rows.length ? `<div class="table-wrap"><table>
      <thead><tr>${data.header.map(h => `<th>${esc(String(h).replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase()))}</th>`).join("")}</tr></thead>
      <tbody>${data.rows.slice(0, 300).map(r => `<tr>${data.header.map(h => `<td>${esc(r[h])}</td>`).join("")}</tr>`).join("")}</tbody>
    </table></div>
    ${data.rows.length > 300 ? `<p class="subtle">Showing first 300 of ${data.rows.length} rows. Use CSV export for the full report.</p>` : ""}`
      : emptyState("No report data matches these filters.", "Adjust the filters and generate again.")}
    <p class="subtle">Generated ${fmtDay(data.generated_at)} &middot; Scope: ${esc(data.filters.scope)} &middot; Unit: ${esc(data.filters.unit || "All")}</p>`);
  bindFilters(() => run(() => reportsView(normalizeParams(state.params))));
  document.getElementById("csvBtn").addEventListener("click", async () => {
    const res = await fetch(`/api/reports${qs({ ...normalizeParams(state.params), format: "csv" })}`, { credentials: "same-origin" });
    const blob = await res.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "mill_lms_report.csv";
    document.body.appendChild(a);
    a.click();
    a.remove();
  });
}

async function logsView(params) {
  const d = await api(`/api/audit-logs${qs({ action: params.action, employee_id: params.employee_id, limit: 200 })}`);
  setMain(`
    ${topbar("Activity Logs", "Audit trail of login, learning, assessment and access events. Corporate Safety Head only.")}
    <div class="filters">
      <label>Action<select data-filter="action">${["All", ...d.actions].map(o => `<option ${((params.action || "All") === o) ? "selected" : ""}>${o}</option>`).join("")}</select></label>
      <label>Employee ID<input data-filter="employee_id" value="${esc(params.employee_id || "")}" placeholder="e.g. EMP001"></label>
      <button class="secondary" id="clearFilters">Reset</button>
    </div>
    ${d.logs.length ? `<div class="table-wrap"><table>
      <thead><tr><th>Time</th><th>Employee</th><th>Action</th><th>Level</th><th>Metadata</th><th>IP</th></tr></thead>
      <tbody>${d.logs.map(l => `<tr>
        <td>${fmtDay(l.timestamp)}</td>
        <td>${esc(l.employee_id || "System")}</td>
        <td><span class="action ${esc(l.action)}">${esc(l.action)}</span></td>
        <td>${l.level_number ? levelLabel(l.level_number) : "-"}</td>
        <td class="mono">${esc(l.metadata || "{}")}</td>
        <td>${esc(l.ip_address || "-")}</td>
      </tr>`).join("")}</tbody></table></div>` : emptyState("No activity logs match this filter.")}`);
  const normalize = p => {
    const out = { ...p };
    if (out.action === "All") out.action = "";
    return out;
  };
  bindFilters(() => run(() => logsView(normalize(state.params))));
}

async function employeeView() {
  if (!state.employee) return go("dashboard");
  const d = await api(`/api/employees/${encodeURIComponent(state.employee)}`);
  const s = d.summary;
  setMain(`
    <button class="secondary small back" id="backBtn">&larr; Back</button>
    ${topbar(d.profile.name, `${esc(d.profile.employee_id)} &middot; ${esc(d.profile.unit_code)} ${esc(d.profile.unit_name || "")} &middot; Operator / Workman`, badge(s.training_status))}
    ${kpiGrid([
      { label: "Overall Progress", value: `${s.progress_percent}%` },
      { label: "Completed Levels", value: `${s.completed_levels} / 16` },
      { label: "Current Level", value: levelLabel(s.current_level) },
      { label: "Average Score", value: `${s.average_score}%` },
      { label: "Assessment Attempts", value: s.total_attempts },
      { label: "Failed Assessments", value: s.failed_assessments, tone: s.failed_assessments ? "warn" : "" },
      { label: "Last Activity", value: fmtDay(s.last_activity) },
    ])}
    ${s.risk_reasons.length
      ? `<div class="notice error"><strong>${esc(s.training_status)}:</strong> ${esc(s.risk_reasons.join(" · "))}</div>`
      : `<div class="notice ok"><strong>On track.</strong> No risk indicators detected for this employee.</div>`}
    <div class="split-2">
      <section class="card">
        ${sectionTitle("Learning Roadmap")}
        ${roadmapHtml(d.roadmap, { clickable: false })}
      </section>
      <section class="card">
        ${sectionTitle("Employee Profile")}
        <div class="kv"><span>Name</span><strong>${esc(d.profile.name)}</strong></div>
        <div class="kv"><span>Employee ID</span><strong>${esc(d.profile.employee_id)}</strong></div>
        <div class="kv"><span>Unit</span><strong>${esc(d.profile.unit_code)}</strong></div>
        <div class="kv"><span>Role</span><strong>Operator / Workman</strong></div>
        <div class="kv"><span>Account Status</span><strong>${esc(d.profile.status)}</strong></div>
        <div class="kv"><span>Last Login</span><strong>${fmtDay(d.profile.last_login)}</strong></div>
        ${sectionTitle("Activity Timeline")}
        ${d.activity.length ? `<ul class="timeline">${d.activity.slice(0, 12).map(a => `<li><strong>${esc(a.action)}</strong> ${a.level_number ? levelLabel(a.level_number) : ""}<span>${fmtDay(a.timestamp)}</span></li>`).join("")}</ul>`
        : `<p class="subtle">No recorded activity yet.</p>`}
      </section>
    </div>
    ${sectionTitle("Training History", "Module level completion record")}
    ${d.training_history.length ? `<div class="table-wrap"><table>
      <thead><tr><th>Module</th><th>Attempt</th><th>Score</th><th>Status</th><th>Started</th><th>Completed</th></tr></thead>
      <tbody>${d.training_history.map(h => `<tr>
        <td>${esc(h.module)}</td><td class="num">${h.attempts}</td>
        <td class="num">${h.score ?? "-"}</td><td>${badge(h.status)}</td>
        <td>${fmtDay(h.started_at)}</td><td>${fmtDay(h.completed_date)}</td>
      </tr>`).join("")}</tbody></table></div>` : emptyState("No training history yet.")}
    ${sectionTitle("Assessment Attempts", "Every submitted MCQ attempt")}
    ${d.assessment_attempts.length ? `<div class="table-wrap"><table>
      <thead><tr><th>Level</th><th>Module</th><th>Attempt</th><th>Score</th><th>Result</th><th>Submitted</th></tr></thead>
      <tbody>${d.assessment_attempts.map(a => `<tr>
        <td>${levelLabel(a.level_number)}</td><td>${esc(a.module)}</td><td class="num">${a.attempt_no}</td>
        <td class="num">${a.score}%</td><td>${badge(a.passed ? "PASSED" : "FAILED")}</td><td>${fmtDay(a.submitted_at)}</td>
      </tr>`).join("")}</tbody></table></div>` : emptyState("No assessment attempts recorded.")}`);
  document.getElementById("backBtn").addEventListener("click", () => {
    state.employee = null;
    go(state.user.role === "corporate_safety_head" ? "employees" : "employees");
  });
}

/* ------------------------------------------------------------------ profile */

async function profileView() {
  const me = (await api("/api/me")).user;
  const isOp = me.role === "operator_workman";
  let summary = null;
  if (isOp) summary = (await api("/api/my-profile")).summary;
  setMain(`
    ${topbar("Profile", "Your account and access scope.")}
    <div class="split-2">
      <section class="card">
        ${sectionTitle("Account")}
        <div class="kv"><span>Name</span><strong>${esc(me.name)}</strong></div>
        <div class="kv"><span>Employee ID</span><strong>${esc(me.employee_id)}</strong></div>
        <div class="kv"><span>Role</span><strong>${esc(ROLE_LABEL[me.role])}</strong></div>
        <div class="kv"><span>Unit</span><strong>${esc(me.unit_code || "All Units")}</strong></div>
        <div class="kv"><span>Unit Name</span><strong>${esc(me.unit_name || "Organization wide")}</strong></div>
        <div class="kv"><span>Account Status</span><strong>${esc(me.status)}</strong></div>
        <div class="kv"><span>Last Login</span><strong>${fmtDay(me.last_login)}</strong></div>
      </section>
      <section class="card">
        ${sectionTitle("Access Scope")}
        <p>${me.role === "corporate_safety_head"
          ? "You can view all 8 units, all employees, analytics, reports and audit logs."
          : me.role === "function_safety_unit_head"
            ? `You can view only unit <strong>${esc(me.unit_code)}</strong>. Every other unit is blocked by the backend.`
            : "You can view only your own profile, roadmap, assessments and progress."}</p>
        ${summary ? kpiGrid([
          { label: "Progress", value: `${summary.progress_percent}%` },
          { label: "Completed", value: `${summary.completed_levels} / 16` },
          { label: "Average Score", value: `${summary.average_score}%` },
          { label: "Status", value: summary.training_status },
        ]) : ""}
        <div class="notice">Sessions expire after 8 hours. All actions are recorded in the audit log.</div>
        <button id="profileLogout">Logout</button>
      </section>
    </div>`);
  document.getElementById("profileLogout").addEventListener("click", async () => {
    try { await api("/api/logout", { method: "POST", body: "{}" }); } catch { /* ignore */ }
    state.user = null;
    renderLogin("You have been logged out securely.");
  });
}

/* ------------------------------------------------------------------ operator */

async function operatorDashboard() {
  const d = await api("/api/my-profile");
  const s = d.summary;
  const current = d.roadmap.find(x => x.state === "CURRENT") || d.roadmap[d.roadmap.length - 1];
  const doneCount = s.completed_levels;
  setMain(`
    <div class="welcome">
      <div>
        <h1>Welcome, ${esc(d.profile.name)}</h1>
        <p class="subtle">Employee ID: ${esc(d.profile.employee_id)} &middot; Unit: ${esc(d.profile.unit_code)} &middot; Role: Operator / Workman</p>
      </div>
      <button class="warning big" id="continueTop">Continue ${levelLabel(current.level_number)} &rarr;</button>
    </div>
    ${kpiGrid([
      { label: "Current Level", value: levelLabel(s.current_level) },
      { label: "Overall Progress", value: `${s.progress_percent}%` },
      { label: "Completed", value: `${doneCount} / 16` },
      { label: "Average Score", value: `${s.average_score}%` },
    ])}
    ${sectionTitle("Production / Safety Learning Roadmap", "Complete each level to unlock the next one")}
    ${roadmapHtml(d.roadmap)}
    <section class="grid cards wide-cards">
      <article class="card action-card">
        <h2>Current Module</h2>
        <p class="big-level">${levelLabel(current.level_number)}</p>
        <p class="subtle">${esc(String(current.title).replace(/^Level \d+ - /, ""))}</p>
        <button class="warning big" id="continueCard">Continue Learning &rarr;</button>
      </article>
      <article class="card">
        <h2>Training Progress</h2>
        <div class="progress-split">
          <div><span>Completed</span><strong>${s.completed_levels}</strong></div>
          <div><span>In Progress</span><strong>${s.in_progress_levels}</strong></div>
          <div><span>Locked</span><strong>${s.locked_levels}</strong></div>
        </div>
        <p class="subtle">Progress: ${s.progress_percent}%</p>
        ${bar(s.progress_percent)}
      </article>
    </section>`);
  document.getElementById("continueTop").addEventListener("click", () => go("learning", {}, { level: current.level_number }));
  document.getElementById("continueCard").addEventListener("click", () => go("learning", {}, { level: current.level_number }));
  document.querySelectorAll("[data-level]").forEach(b =>
    b.addEventListener("click", () => go("learning", {}, { level: Number(b.dataset.level) })));
}

async function roadmapView() {
  const d = await api("/api/my-roadmap");
  const current = d.roadmap.find(x => x.state === "CURRENT");
  setMain(`
    ${topbar("Learning Roadmap", "16 sequential levels. A level unlocks only after the previous one is passed.")}
    <section class="roadmap-full">
      ${d.roadmap.map(n => {
        const mark = n.state === "COMPLETED" ? "✓" : n.state === "CURRENT" ? "●" : "🔒";
        const label = n.state === "COMPLETED" ? "Completed" : n.state === "CURRENT" ? "Current" : "Locked";
        return `<div class="road-row ${n.state}">
          <span class="road-mark">${mark}</span>
          <div class="road-body">
            <strong>${levelLabel(n.level_number)} &mdash; ${esc(String(n.title).replace(/^Level \d+ - /, ""))}</strong>
            <span>${n.state === "LOCKED"
              ? `Complete ${levelLabel(n.level_number - 1)} to unlock this level.`
              : n.state === "COMPLETED"
                ? `Score ${n.score ?? "-"}% · ${n.attempts} attempt${n.attempts === 1 ? "" : "s"}`
                : "Your current level — start now."}</span>
          </div>
          <span class="road-state">${label}</span>
          ${n.state !== "LOCKED" ? `<button class="secondary small" data-level="${n.level_number}">Open</button>` : `<button class="secondary small" disabled>Locked</button>`}
        </div>`;
      }).join("")}
    </section>
    ${current ? `<div class="notice info">Next action: open <strong>${levelLabel(current.level_number)}</strong>, read the content, watch the video, then pass the MCQ.</div>` : ""}`);
  document.querySelectorAll("[data-level]").forEach(b =>
    b.addEventListener("click", () => go("learning", {}, { level: Number(b.dataset.level) })));
}

async function learningView(params) {
  if (!state.level) {
    const d = await api("/api/my-roadmap");
    const current = d.roadmap.find(x => x.state === "CURRENT");
    state.level = current ? current.level_number : 1;
  }
  const level = state.level;
  const m = await api(`/api/my-module/${level}`);
  const p = m.progress;
  const canAssess = p.content_completed && p.video_completed;
  const nextLevel = level < 16 ? level + 1 : null;
  setMain(`
    <button class="secondary small back" id="roadmapBack">&larr; Learning Roadmap</button>
    ${topbar(m.title, esc(m.description), badge(m.state))}
    <div class="module-layout">
      <section class="card module-main">
        <div class="step ${p.content_completed ? "done" : ""}">
          <div class="step-head"><span class="step-num">1</span><h2>Learning Content</h2><span class="step-state">${p.content_completed ? "Completed" : "Pending"}</span></div>
          <p>${esc(m.content.content)}</p>
          <div class="doc-chip">SOP Document: ${esc(String(m.content.document_url).split("/").pop())}</div>
          <button id="contentBtn" class="${p.content_completed ? "secondary" : ""}" ${p.content_completed ? "disabled" : ""}>
            ${p.content_completed ? "✓ Content Completed" : "Mark Content As Read"}
          </button>
        </div>

        <div class="step ${p.video_completed ? "done" : ""}">
          <div class="step-head"><span class="step-num">2</span><h2>Training Video</h2><span class="step-state">${p.video_completed ? "Completed" : p.video_started ? `${p.video_progress}%` : "Pending"}</span></div>
          <div class="player">
            <div class="player-screen">
              <span class="player-title">${esc(m.title)}</span>
              <span class="player-dur">${Math.floor(m.video.duration_seconds / 60)} min ${m.video.duration_seconds % 60} sec</span>
            </div>
            <div class="player-bar"><span id="videoBar" style="width:${pct(p.video_progress)}%"></span></div>
            <div class="player-meta"><span id="videoPct">${p.video_progress}% watched</span>
              <button id="videoBtn" class="small ${p.video_completed ? "secondary" : "warning"}" ${!p.content_completed ? "disabled" : ""}>
                ${p.video_completed ? "✓ Video Completed" : p.video_started ? "Resume Video" : "Play Video"}
              </button>
            </div>
          </div>
          ${!p.content_completed ? `<p class="hint">Complete Step 1 to unlock the training video.</p>` : ""}
        </div>

        <div class="step ${p.assessment_completed && p.status === "COMPLETED" ? "done" : ""}">
          <div class="step-head"><span class="step-num">3</span><h2>MCQ Assessment</h2><span class="step-state">${p.status === "COMPLETED" ? "Passed" : p.attempts ? `Attempt ${p.attempts}` : "Pending"}</span></div>
          <p>Required pass score: <strong>${m.assessment.pass_percentage}%</strong> &middot; Attempts used: <strong>${p.attempts} / ${m.assessment.attempt_limit}</strong></p>
          <div id="assessmentZone">${assessmentZone(m)}</div>
        </div>
      </section>

      <aside class="card module-side">
        <h2>Progress Check</h2>
        <ul class="checklist">
          <li class="${p.content_completed ? "ok" : "current"}"><span>${p.content_completed ? "✓" : "●"}</span> Learning content</li>
          <li class="${p.video_completed ? "ok" : p.content_completed ? "current" : "locked"}"><span>${p.video_completed ? "✓" : p.content_completed ? "●" : "🔒"}</span> Training video</li>
          <li class="${p.status === "COMPLETED" ? "ok" : canAssess ? "current" : "locked"}"><span>${p.status === "COMPLETED" ? "✓" : canAssess ? "●" : "🔒"}</span> MCQ assessment</li>
        </ul>
        <div class="kv"><span>Last Score</span><strong>${p.score ?? "-"}</strong></div>
        <div class="kv"><span>Attempts</span><strong>${p.attempts}</strong></div>
        <div class="kv"><span>Module State</span><strong>${esc(m.state)}</strong></div>
        ${nextLevel ? `<div class="notice">${p.status === "COMPLETED"
          ? `Level ${String(nextLevel).padStart(2, "0")} is now unlocked.`
          : `Pass this assessment to unlock Level ${String(nextLevel).padStart(2, "0")}.`}</div>` : `<div class="notice ok">Final level. Passing completes your roadmap.</div>`}
      </aside>
    </div>`);

  document.getElementById("roadmapBack").addEventListener("click", () => go("roadmap"));
  const contentBtn = document.getElementById("contentBtn");
  if (contentBtn && !p.content_completed) {
    contentBtn.addEventListener("click", async () => {
      contentBtn.disabled = true;
      contentBtn.textContent = "Saving...";
      await api(`/api/my-module/${level}/content-complete`, { method: "POST", body: "{}" });
      go("learning", {}, { level });
    });
  }
  const videoBtn = document.getElementById("videoBtn");
  if (videoBtn && !p.video_completed && p.content_completed) {
    videoBtn.addEventListener("click", () => playVideo(level, videoBtn));
  }
  bindAssessment(level, m);
}

function assessmentZone(m) {
  const p = m.progress;
  if (p.status === "COMPLETED") {
    return `<div class="result ok"><strong>✓ Assessment passed with ${p.score}%.</strong>
      <p>This level is complete. ${m.level_number < 16 ? `Level ${String(m.level_number + 1).padStart(2, "0")} is unlocked.` : "You have completed the full roadmap."}</p>
      ${m.level_number < 16 ? `<button class="warning" id="nextLevelBtn">Continue to Level ${String(m.level_number + 1).padStart(2, "0")} &rarr;</button>` : ""}</div>`;
  }
  if (p.attempts >= m.assessment.attempt_limit) {
    return `<div class="result error"><strong>Attempt limit reached.</strong><p>${p.attempts} of ${m.assessment.attempt_limit} attempts used. Contact your supervisor to reset this module.</p></div>`;
  }
  if (!p.content_completed || !p.video_completed) {
    return `<div class="result warn"><strong>Assessment locked.</strong><p>${!p.content_completed ? "Complete the learning content first." : "Watch the training video to the end first."}</p></div>`;
  }
  return `<div class="result" id="assessmentIntro">
      <p>${p.attempts ? `Previous attempt${p.attempts > 1 ? "s" : ""}: ${p.attempts}. Last score: ${p.score}%. ` : ""}Pass mark is ${m.assessment.pass_percentage}%.</p>
      <button class="warning" id="startAssessment">${p.attempts ? "Retake Assessment" : "Start Assessment"}</button>
    </div>`;
}

function quizForm(m) {
  return `<form id="assessmentForm" class="quiz">
    ${m.questions.map((q, i) => `<fieldset class="options">
      <legend><span class="qnum">Q${i + 1}</span> ${esc(q.question)}</legend>
      ${["a", "b", "c", "d"].map(letter => `<label class="option">
        <input type="radio" name="q${q.id}" value="${letter.toUpperCase()}" required>
        <span>${esc(q[`option_${letter}`])}</span>
      </label>`).join("")}
    </fieldset>`).join("")}
    <div class="quiz-actions">
      <button class="warning" type="submit">Submit Assessment</button>
      <span class="subtle">You cannot change answers after submission.</span>
    </div>
    <div id="assessmentResult"></div>
  </form>`;
}

function bindAssessment(level, m) {
  const start = document.getElementById("startAssessment");
  if (start) {
    start.addEventListener("click", async () => {
      try {
        await api(`/api/my-module/${level}/assessment-start`, { method: "POST", body: "{}" });
        document.getElementById("assessmentZone").innerHTML = quizForm(m);
        bindAssessment(level, m);
        document.querySelector(".quiz").scrollIntoView({ behavior: "smooth", block: "start" });
      } catch (err) {
        document.getElementById("assessmentZone").innerHTML = `<div class="result error"><strong>${esc(err.code === "MODULE_LOCKED" ? "Module locked" : "Cannot start")}</strong><p>${esc(err.message)}</p></div>`;
      }
    });
  }
  const next = document.getElementById("nextLevelBtn");
  if (next) next.addEventListener("click", () => go("learning", {}, { level: Math.min(16, level + 1) }));
  const form = document.getElementById("assessmentForm");
  if (form) {
    form.addEventListener("submit", async e => {
      e.preventDefault();
      const fd = new FormData(form);
      const answers = {};
      m.questions.forEach(q => { answers[q.id] = fd.get(`q${q.id}`); });
      const btn = form.querySelector("button[type=submit]");
      btn.disabled = true;
      btn.textContent = "Scoring...";
      try {
        const r = await api(`/api/my-module/${level}/assessment-submit`, { method: "POST", body: JSON.stringify({ answers }) });
        const zone = document.getElementById("assessmentResult");
        zone.innerHTML = r.passed
          ? `<div class="result ok"><strong>✓ Passed with ${r.score}%.</strong>
              <p>${r.next_unlocked ? `Level ${String(r.next_unlocked).padStart(2, "0")} is now unlocked.` : "Roadmap complete."}</p>
              ${r.next_unlocked ? `<button class="warning" id="nextLevelBtn">Continue to Level ${String(r.next_unlocked).padStart(2, "0")} &rarr;</button>` : ""}</div>`
          : `<div class="result error"><strong>Failed. You scored ${r.score}%. Required: ${r.pass_percentage}%.</strong>
              <p>Attempts used: ${r.attempts} of ${r.attempt_limit}. Review the content and video, then retake.</p>
              <button class="secondary" id="retryBtn">Retake Assessment</button></div>`;
        zone.scrollIntoView({ behavior: "smooth", block: "center" });
        const retry = document.getElementById("retryBtn");
        if (retry) retry.addEventListener("click", () => go("learning", {}, { level }));
        const nb = document.getElementById("nextLevelBtn");
        if (nb) nb.addEventListener("click", () => go("learning", {}, { level: r.next_unlocked }));
      } catch (err) {
        document.getElementById("assessmentResult").innerHTML = `<div class="result error"><strong>${esc(err.code)}</strong><p>${esc(err.message)}</p></div>`;
        btn.disabled = false;
        btn.textContent = "Submit Assessment";
      }
    });
  }
}

function playVideo(level, btn) {
  btn.disabled = true;
  btn.textContent = "Playing...";
  let pctValue = Number(document.getElementById("videoBar").style.width.replace("%", "")) || 0;
  const step = async () => {
    pctValue = Math.min(100, pctValue + 5);
    const barEl = document.getElementById("videoBar");
    const pctEl = document.getElementById("videoPct");
    if (!barEl) return;
    barEl.style.width = pctValue + "%";
    pctEl.textContent = pctValue + "% watched";
    try {
      const r = await api(`/api/my-module/${level}/video-progress`, { method: "POST", body: JSON.stringify({ percent: pctValue }) });
      if (r.video_completed) { setTimeout(() => go("learning", {}, { level }), 350); return; }
      setTimeout(step, 320);
    } catch (err) {
      renderError(err);
    }
  };
  setTimeout(step, 250);
}

async function assessmentsView() {
  const d = await api("/api/my-assessments");
  setMain(`
    ${topbar("My Assessments", `Pass mark ${d.pass_percentage}% · Attempt limit ${d.attempt_limit} per module.`)}
    ${d.pending.length ? `${sectionTitle("Pending Assessment")}
      <div class="table-wrap"><table>
        <thead><tr><th>Level</th><th>Module</th><th>Attempts Used</th><th>Last Score</th><th>Status</th><th>Action</th></tr></thead>
        <tbody>${d.pending.map(x => `<tr>
          <td>${levelLabel(x.level_number)}</td><td>${esc(x.module)}</td><td class="num">${x.attempts}</td>
          <td class="num">${x.score ?? "-"}</td><td>${badge(x.status)}</td>
          <td><button class="warning small" data-level="${x.level_number}">Open</button></td>
        </tr>`).join("")}</tbody></table></div>` : ""}
    ${sectionTitle("Assessment History", "Every submitted attempt")}
    ${d.history.length ? `<div class="table-wrap"><table>
      <thead><tr><th>Level</th><th>Module</th><th>Attempt</th><th>Score</th><th>Required</th><th>Result</th><th>Submitted</th></tr></thead>
      <tbody>${d.history.map(h => `<tr>
        <td>${levelLabel(h.level_number)}</td><td>${esc(h.module)}</td><td class="num">${h.attempt_no}</td>
        <td class="num">${h.score}%</td><td class="num">${h.pass_percentage}%</td>
        <td>${badge(h.status)}</td><td>${fmtDay(h.submitted_at)}</td>
      </tr>`).join("")}</tbody></table></div>` : emptyState("No assessment attempts yet.", "Complete content and video, then start your first assessment.")}`);
  document.querySelectorAll("[data-level]").forEach(b =>
    b.addEventListener("click", () => go("learning", {}, { level: Number(b.dataset.level) })));
}

async function myProgressView() {
  const d = await api("/api/my-progress");
  const s = d.summary;
  setMain(`
    ${topbar("My Progress", "Your complete training record.")}
    ${kpiGrid([
      { label: "Overall Progress", value: `${s.progress_percent}%` },
      { label: "Completed Levels", value: `${s.completed_levels} / 16` },
      { label: "Current Level", value: levelLabel(s.current_level) },
      { label: "Average Score", value: `${s.average_score}%` },
      { label: "Assessment Attempts", value: s.total_attempts },
      { label: "Status", value: s.training_status },
    ])}
    ${s.risk_reasons.length ? `<div class="notice error">${esc(s.risk_reasons.join(" · "))}</div>` : ""}
    <div class="split-2">
      <section class="card">${sectionTitle("Roadmap")}${roadmapHtml(d.roadmap)}</section>
      <section class="card">${sectionTitle("Progress Bar")}${bar(s.progress_percent)}
        <div class="progress-split">
          <div><span>Completed</span><strong>${s.completed_levels}</strong></div>
          <div><span>In Progress</span><strong>${s.in_progress_levels}</strong></div>
          <div><span>Locked</span><strong>${s.locked_levels}</strong></div>
        </div>
        <div class="kv"><span>Last Activity</span><strong>${fmtDay(s.last_activity)}</strong></div>
        <div class="kv"><span>Failed Assessments</span><strong>${s.failed_assessments}</strong></div>
      </section>
    </div>
    ${sectionTitle("Module Record")}
    <div class="table-wrap"><table>
      <thead><tr><th>Level</th><th>Module</th><th>Status</th><th>Content</th><th>Video</th><th>Score</th><th>Attempts</th><th>Completed</th></tr></thead>
      <tbody>${d.modules.map(m => `<tr>
        <td>${levelLabel(m.level_number)}</td><td>${esc(String(m.title).replace(/^Level \d+ - /, ""))}</td>
        <td>${badge(m.status)}</td>
        <td>${m.content_completed ? "✓" : "-"}</td>
        <td>${m.video_completed ? "✓" : m.video_progress ? m.video_progress + "%" : "-"}</td>
        <td class="num">${m.score ?? "-"}</td><td class="num">${m.attempts}</td>
        <td>${fmtDay(m.completed_at)}</td>
      </tr>`).join("")}</tbody>
    </table></div>`);
  document.querySelectorAll("[data-level]").forEach(b =>
    b.addEventListener("click", () => go("learning", {}, { level: Number(b.dataset.level) })));
}

/* ------------------------------------------------------------------ errors */

function renderError(err) {
  const code = (err && err.code) || "ERROR";
  const target = document.getElementById("main");
  if (!target) return renderLogin(err && err.message);
  const map = {
    MODULE_LOCKED: ["🔒", "Module Locked", "warn"],
    FORBIDDEN: ["", "Access Denied", "error"],
    UNIT_FORBIDDEN: ["", "Access Denied", "error"],
    EMPLOYEE_FORBIDDEN: ["", "Access Denied", "error"],
    NOT_FOUND: ["", "Not Found", "warn"],
    NETWORK: ["", "Connection Problem", "error"],
    SERVER_ERROR: ["", "Server Error", "error"],
    ATTEMPT_LIMIT_REACHED: ["", "Attempt Limit Reached", "warn"],
    CONTENT_REQUIRED: ["", "Step Incomplete", "warn"],
    VIDEO_REQUIRED: ["", "Step Incomplete", "warn"],
    TOO_MANY_ATTEMPTS: ["", "Too Many Attempts", "warn"],
  };
  const [icon, title, tone] = map[code] || ["", "Something Went Wrong", "warn"];
  const retryable = code === "NETWORK" || code === "SERVER_ERROR";
  const backView = state.user && state.user.role === "operator_workman" ? "roadmap" : "dashboard";
  target.innerHTML = `
    <div class="error-page ${tone}">
      <div class="error-icon">${icon || "!"}</div>
      <h1>${esc(title)}</h1>
      <p class="error-code">${esc(code)}</p>
      <p>${esc((err && err.message) || "Unexpected error.")}</p>
      <div class="error-actions">
        <button id="errBack" class="secondary">&larr; Back to ${backView === "roadmap" ? "Roadmap" : "Dashboard"}</button>
        ${retryable ? `<button id="errRetry" class="warning">Retry</button>` : ""}
      </div>
    </div>`;
  document.getElementById("errBack").addEventListener("click", () => go(backView));
  const retry = document.getElementById("errRetry");
  if (retry) retry.addEventListener("click", () => dispatch());
}

/* ------------------------------------------------------------------ boot */

(async function boot() {
  try {
    state.user = (await api("/api/me")).user;
    await renderApp();
  } catch (err) {
    if (err && (err.code === "AUTH_REQUIRED" || err.code === "SESSION_EXPIRED")) return;
    if (err && ["FORBIDDEN", "UNIT_FORBIDDEN", "EMPLOYEE_FORBIDDEN", "MODULE_LOCKED", "NOT_FOUND", "NETWORK", "SERVER_ERROR"].includes(err.code)) {
      return renderLogin(err.message);
    }
    renderLogin("");
  }
})();
