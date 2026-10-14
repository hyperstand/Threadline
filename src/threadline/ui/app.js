"use strict";

/*
 * Threadline UI (M9): four screens over the existing API, no build step.
 *
 * Document text, questions, and tool output are untrusted. They are only written as DOM
 * text (textContent or text nodes), never through innerHTML. The page's Content-Security-Policy
 * also blocks inline scripts as a second line of defence.
 */

const STATUS_CLASSES = new Set([
  "confirmed", "contradicted", "unknown", "observed", "unverified", "source_backed",
  "completed", "insufficient_evidence", "failed", "running", "queued", "cancelled",
  "indexed", "processing", "pending", "archived",
]);

function el(tag, attrs, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "text") node.textContent = String(value);
    else if (key === "class") node.className = String(value);
    else if (key.startsWith("on") && typeof value === "function") node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? "" : String(value));
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

function badge(status) {
  const name = status === null || status === undefined ? "unknown" : String(status);
  const cls = STATUS_CLASSES.has(name) ? name : "neutral";
  return el("span", { class: `badge ${cls}`, text: name.replace(/_/g, " ") });
}

function simulatedBadge() {
  return el("span", { class: "badge simulated", text: "simulated" });
}

function setMessage(node, text, isError = false) {
  node.textContent = text;
  node.className = isError ? "message error" : "message";
}

function messageBlock(text, isError = false) {
  return el("p", {
    class: isError ? "message error" : "message",
    role: isError ? "alert" : "status",
    text,
  });
}

function fmtTime(value) {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString();
}

function short(value, length = 12) {
  return value ? String(value).slice(0, length) : "";
}

function summarize(meta) {
  const text = JSON.stringify(meta || {});
  return text.length > 160 ? `${text.slice(0, 157)}…` : text;
}

function countBy(items, key) {
  return items.reduce((acc, item) => {
    acc[item[key]] = (acc[item[key]] || 0) + 1;
    return acc;
  }, {});
}

function errorText(detail, status) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item) => item.msg || JSON.stringify(item)).join("; ");
  return `HTTP ${status}`;
}

async function api(path, options = {}) {
  const headers = { Accept: "application/json", ...(options.headers || {}) };
  const response = await fetch(path, { ...options, headers });
  const text = await response.text();
  let body = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch (_error) {
      body = text;
    }
  }
  if (!response.ok) {
    const detail = body && typeof body === "object" ? body.detail : undefined;
    throw new Error(errorText(detail, response.status));
  }
  return body;
}

function table(headers, rows) {
  return el(
    "div",
    { class: "table-wrap" },
    el(
      "table",
      {},
      el("thead", {}, el("tr", {}, headers.map((h) => el("th", { scope: "col", text: h })))),
      el("tbody", {}, rows),
    ),
  );
}

function field(label, control, hint) {
  return el(
    "label",
    { class: "field" },
    el("span", { class: "field-label", text: label }),
    control,
    hint ? el("span", { class: "hint", text: hint }) : null,
  );
}

function card(title, ...children) {
  return el("section", { class: "card" }, el("h2", { text: title }), ...children);
}

function listOf(items) {
  if (!items || items.length === 0) return el("p", { class: "muted", text: "None." });
  return el("ul", { class: "items" }, items.map((item) => el("li", { text: String(item) })));
}

function countsLine(counts) {
  return el(
    "p",
    { class: "counts" },
    ["confirmed", "contradicted", "unknown"].flatMap((status) => [badge(status), ` ${counts[status] || 0}   `]),
  );
}

/* ---------- Library: upload and list documents ---------- */

async function documentTable() {
  const docs = await api("/api/v1/documents");
  if (docs.length === 0) return messageBlock("No documents yet. Upload a runbook to start.");
  return table(
    ["Source", "Type", "Status", "System", "Environment", "Content hash", "Added"],
    docs.map((doc) =>
      el(
        "tr",
        {},
        el("td", { text: doc.source_name }),
        el("td", { text: doc.media_type }),
        el("td", {}, badge(doc.status)),
        el("td", { text: doc.system_scope || "—" }),
        el("td", { text: doc.environment_scope || "—" }),
        el("td", { class: "mono", text: short(doc.content_hash) }),
        el("td", { text: fmtTime(doc.created_at) }),
      ),
    ),
  );
}

async function renderLibrary() {
  const message = el("div", { class: "message", role: "status" });
  const file = el("input", { type: "file", name: "file", required: true, accept: ".pdf,.docx,.md,.txt" });
  const system = el("input", { type: "text", name: "system_scope", maxlength: 255, autocomplete: "off" });
  const environment = el("input", { type: "text", name: "environment_scope", maxlength: 255, autocomplete: "off" });
  const submit = el("button", { type: "submit", text: "Upload and index" });
  const listing = el("div", {}, messageBlock("Loading documents…"));

  const form = el(
    "form",
    {
      class: "card",
      onsubmit: async (event) => {
        event.preventDefault();
        const chosen = file.files && file.files[0];
        if (!chosen) {
          setMessage(message, "Choose a file first.", true);
          return;
        }
        const body = new FormData();
        body.append("file", chosen);
        if (system.value.trim()) body.append("system_scope", system.value.trim());
        if (environment.value.trim()) body.append("environment_scope", environment.value.trim());

        submit.disabled = true;
        setMessage(message, "Uploading and indexing…");
        try {
          const doc = await api("/api/v1/documents", { method: "POST", body });
          setMessage(message, `${doc.source_name}: ${doc.status}`);
          form.reset();
        } catch (error) {
          setMessage(message, `Upload failed: ${error.message}`, true);
        } finally {
          submit.disabled = false;
        }
        try {
          listing.replaceChildren(await documentTable());
        } catch (error) {
          listing.replaceChildren(messageBlock(`Could not load documents: ${error.message}`, true));
        }
      },
    },
    field("Document", file, "PDF, DOCX, Markdown, or plain text."),
    field("System (optional)", system, "Documents scoped to a system are only confirmed for that system."),
    field("Environment (optional)", environment, "Without a scope, a document's applicability is unknown."),
    el("div", {}, submit),
    message,
  );

  documentTable()
    .then((node) => listing.replaceChildren(node))
    .catch((error) => listing.replaceChildren(messageBlock(`Could not load documents: ${error.message}`, true)));

  return el(
    "section",
    {},
    el("h1", { text: "Library" }),
    form,
    card("Indexed documents", listing),
  );
}

/* ---------- Workspace: ask an investigation question ---------- */

async function renderWorkspace() {
  const message = el("div", { class: "message", role: "status" });
  const question = el("textarea", { name: "question", rows: 3, maxlength: 4000, required: true });
  const system = el("input", { type: "text", name: "target_system", maxlength: 255, required: true, autocomplete: "off" });
  const environment = el("input", { type: "text", name: "target_environment", maxlength: 255, required: true, autocomplete: "off" });
  const mode = el(
    "select",
    { name: "mode" },
    el("option", { value: "live", text: "Live (read-only Goose when configured)" }),
    el("option", { value: "document_only", text: "Documents only" }),
  );
  const submit = el("button", { type: "submit", text: "Investigate" });

  const form = el(
    "form",
    {
      class: "card",
      onsubmit: async (event) => {
        event.preventDefault();
        submit.disabled = true;
        setMessage(message, "Running investigation…");
        try {
          const run = await api("/api/v1/investigations", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              question: question.value.trim(),
              target_system: system.value.trim(),
              target_environment: environment.value.trim(),
              mode: mode.value,
            }),
          });
          message.replaceChildren(
            el("div", { class: "row" }, "Status:", badge(run.status)),
            el("p", { text: run.summary || "No summary was produced." }),
            el("a", { href: `#report/${encodeURIComponent(run.id)}`, text: "Open report →" }),
          );
        } catch (error) {
          setMessage(message, `Investigation could not run: ${error.message}`, true);
        } finally {
          submit.disabled = false;
        }
      },
    },
    field("Question", question, "Answers cite only the documents and observations they rely on."),
    el(
      "div",
      { class: "two-up" },
      field("Target system", system),
      field("Target environment", environment),
    ),
    field("Mode", mode, "Documents only skips live evidence collection."),
    el("div", {}, submit),
    message,
  );

  return el(
    "section",
    {},
    el("h1", { text: "Workspace" }),
    form,
  );
}

/* ---------- History: list past investigations ---------- */

async function investigationTable() {
  const items = await api("/api/v1/investigations?limit=50");
  if (items.length === 0) return messageBlock("No investigations yet. Ask a question in Workspace.");
  return table(
    ["Started", "Question", "Target", "Status", "Summary"],
    items.map((item) =>
      el(
        "tr",
        {},
        el("td", { text: fmtTime(item.started_at) }),
        el("td", {}, el("a", { href: `#report/${encodeURIComponent(item.id)}`, text: item.question })),
        el("td", { text: `${item.target_system || "?"} / ${item.target_environment || "?"}` }),
        el("td", {}, badge(item.status)),
        el("td", { text: item.summary || "" }),
      ),
    ),
  );
}

async function renderHistory() {
  const listing = el("div", {}, messageBlock("Loading…"));
  const load = async () => {
    listing.replaceChildren(messageBlock("Loading…"));
    try {
      listing.replaceChildren(await investigationTable());
    } catch (error) {
      listing.replaceChildren(messageBlock(`Could not load history: ${error.message}`, true));
    }
  };
  load();

  return el(
    "section",
    {},
    el(
      "div",
      { class: "toolbar" },
      el("h1", { text: "History" }),
      el("button", { type: "button", class: "secondary", text: "Refresh", onclick: load }),
    ),
    listing,
  );
}

/* ---------- Report: one investigation in full ---------- */

function referenceMeta(ref) {
  const parts = [];
  if (ref.version) parts.push(`version ${short(ref.version, 12)}`);
  if (ref.page_number !== null && ref.page_number !== undefined) parts.push(`page ${ref.page_number}`);
  if (ref.section_path) parts.push(ref.section_path);
  return parts.join(" · ");
}

function auditCard(investigationId) {
  const body = el("div", {}, el("p", { class: "muted", text: "Workflow steps, tool calls, and verification results recorded for this run." }));
  const loadButton = el("button", {
    type: "button",
    class: "secondary",
    text: "Load audit trail",
    onclick: async (event) => {
      const button = event.currentTarget;
      button.disabled = true;
      try {
        const data = await api(`/api/v1/investigations/${encodeURIComponent(investigationId)}/audit-events`);
        body.replaceChildren(auditTable(data.events));
      } catch (error) {
        body.replaceChildren(messageBlock(`Could not load audit events: ${error.message}`, true));
      }
    },
  });
  return card("Audit trail", loadButton, body);
}

function auditTable(events) {
  if (events.length === 0) return messageBlock("No audit events were recorded.");
  return table(
    ["Time", "Event", "Status", "Details"],
    events.map((event) =>
      el(
        "tr",
        {},
        el("td", { text: fmtTime(event.timestamp) }),
        el("td", { class: "mono", text: event.event_type }),
        el("td", {}, badge(event.status)),
        el("td", { class: "mono", text: summarize(event.safe_metadata) }),
      ),
    ),
  );
}

async function renderReport(investigationId) {
  if (!investigationId) return messageBlock("Open an investigation from History or Workspace to see its report.");
  const encoded = encodeURIComponent(investigationId);
  const [record, payload] = await Promise.all([
    api(`/api/v1/investigations/${encoded}`),
    api(`/api/v1/investigations/${encoded}/report`),
  ]);

  const header = el(
    "div",
    { class: "report-head" },
    el("h1", { text: record.question }),
    el(
      "p",
      { class: "muted" },
      `Target: ${record.target_system || "?"} / ${record.target_environment || "?"} · Run `,
      el("code", { text: record.id }),
      " · Status ",
      badge(record.status),
    ),
  );

  const report = payload.report;
  if (!report) {
    return el("section", {}, header, messageBlock(`No report is stored for this investigation (status: ${record.status}).`));
  }

  const checks = report.applicability_checks || [];
  const facts = report.observed_facts || [];
  const refs = report.document_references || [];
  const hypotheses = report.hypotheses || [];

  const factList = facts.length === 0
    ? messageBlock("No live observations were recorded.")
    : el(
        "ul",
        { class: "items" },
        facts.map((fact) =>
          el(
            "li",
            {},
            el("div", { class: "row" }, badge(fact.trust_status), fact.simulated ? simulatedBadge() : null, el("strong", { text: fact.source })),
            el("div", { class: "excerpt", text: fact.excerpt }),
          ),
        ),
      );

  const refList = refs.length === 0
    ? messageBlock("No document passages were retrieved.")
    : el(
        "ul",
        { class: "items" },
        refs.map((ref) =>
          el(
            "li",
            {},
            el("div", { class: "row" }, badge(ref.applicability_status), el("strong", { text: ref.source_name || ref.chunk_id })),
            referenceMeta(ref) ? el("div", { class: "muted", text: referenceMeta(ref) }) : null,
            el("div", { class: "excerpt", text: ref.excerpt }),
          ),
        ),
      );

  const checkTable = checks.length === 0
    ? messageBlock("No applicability checks were run.")
    : table(
        ["Prerequisite", "Status", "Details"],
        checks.map((check) =>
          el("tr", {}, el("td", { text: check.prerequisite }), el("td", {}, badge(check.status)), el("td", { text: check.details })),
        ),
      );

  const hypothesisList = hypotheses.length === 0
    ? messageBlock("No hypotheses were generated. Hypothesis generation needs a configured model.")
    : el("ul", { class: "items" }, hypotheses.map((h) => el("li", {}, badge(h.status), " ", h.statement)));

  const planList = (report.investigation_plan || []).length === 0
    ? messageBlock("No plan was recorded.")
    : el("ol", { class: "items" }, report.investigation_plan.map((step) => el("li", { text: step })));

  return el(
    "section",
    {},
    header,
    el("p", { class: "muted", text: `Generated ${fmtTime(report.generated_at)}` }),
    card("Executive summary", el("p", { text: report.executive_summary }), countsLine(countBy(checks, "status"))),
    card("Observed facts", factList),
    card("Documents and procedures", refList),
    card("Applicability checks", checkTable),
    card("Hypotheses", hypothesisList),
    card("Recommended next steps", listOf(report.recommended_next_steps)),
    card("Risks and required approvals", listOf(report.risks_and_required_approvals)),
    card("Missing evidence", listOf(report.missing_evidence)),
    card("Uncertainty", listOf(report.uncertainty)),
    card("Limitations", listOf(report.limitations)),
    card("Investigation plan", planList),
    auditCard(investigationId),
    el("p", { class: "disclaimer", text: report.disclaimer }),
  );
}

/* ---------- Routing ---------- */

const VIEWS = {
  library: renderLibrary,
  workspace: renderWorkspace,
  history: renderHistory,
  report: renderReport,
};

const NAV_FOR = { library: "library", workspace: "workspace", history: "history", report: "history" };

let routeToken = 0;

function safeDecode(value) {
  try {
    return decodeURIComponent(value);
  } catch (_error) {
    return value;
  }
}

function highlightNav(name) {
  for (const link of document.querySelectorAll("nav a[data-view]")) {
    if (link.dataset.view === name) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  }
}

function route() {
  const raw = location.hash.replace(/^#\/?/, "");
  const slash = raw.indexOf("/");
  const name = slash === -1 ? raw : raw.slice(0, slash);
  const argument = slash === -1 ? undefined : safeDecode(raw.slice(slash + 1));

  const viewName = VIEWS[name] ? name : "workspace";
  highlightNav(NAV_FOR[viewName]);

  const token = ++routeToken;
  const container = document.getElementById("view");
  container.replaceChildren(messageBlock("Loading…"));

  VIEWS[viewName](viewName === name ? argument : undefined).then(
    (node) => {
      if (token === routeToken) container.replaceChildren(node);
    },
    (error) => {
      if (token === routeToken) container.replaceChildren(messageBlock(`Could not load this view: ${error.message}`, true));
    },
  );
}

window.addEventListener("hashchange", route);
if (location.hash) route();
else location.hash = "#workspace"; // fires hashchange, which renders the default view
