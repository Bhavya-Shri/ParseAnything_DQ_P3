const state = { doc: null, selected: null, view: "exports", markdown: "", json: "" };

const $ = (id) => document.getElementById(id);

function textOf(block) {
  const content = block.content;
  if (typeof content === "string") return content;
  if (!content || typeof content !== "object") return "";
  if (content.text) return String(content.text);
  if (content.latex) return String(content.latex);
  if (content.caption) return String(content.caption);
  return "";
}

function ordered(doc) {
  return [...(doc.blocks || [])].sort((a, b) => (a.page_start - b.page_start) || (a.reading_order - b.reading_order));
}

function titleOf(doc) {
  const heading = ordered(doc).find((block) => block.type === "heading" && textOf(block));
  return heading ? textOf(heading) : (doc.filename || "Untitled");
}

function cellText(cell) {
  if (cell && typeof cell === "object") return cell.text || "";
  return cell == null ? "" : String(cell);
}

function tableGrid(content) {
  const headerRows = content.header_rows || [];
  const headers = Array.isArray(content.headers) && content.headers.length
    ? content.headers
    : (headerRows.length ? headerRows[headerRows.length - 1] : []);
  const rows = (content.rows || []).map((row) => {
    if (Array.isArray(row)) return row.map(cellText);
    if (row && Array.isArray(row.cells)) return row.cells.map(cellText);
    return [];
  });
  return { headers: headers.map(cellText), rows };
}

function pageLabel(page) {
  return page ? "Page " + page : "In the file";
}

function boxText(block) {
  const box = block.bbox || [];
  return box.some((value) => value) ? box.map((value) => Math.round(value)).join(", ") : "no page box";
}

function renderBlock(block) {
  const article = document.createElement("article");
  article.className = "block";
  const content = block.content || {};
  if (block.type === "heading") {
    const heading = document.createElement("h2");
    heading.textContent = textOf(block);
    article.appendChild(heading);
  } else if (block.type === "table" && content && typeof content === "object") {
    const table = document.createElement("table");
    const grid = tableGrid(content);
    if (grid.headers.length) {
      const head = document.createElement("tr");
      grid.headers.forEach((header) => {
        const cell = document.createElement("th");
        cell.textContent = header;
        head.appendChild(cell);
      });
      table.appendChild(head);
    }
    grid.rows.slice(0, 24).forEach((row) => {
      const line = document.createElement("tr");
      row.forEach((value) => {
        const cell = document.createElement("td");
        cell.textContent = value;
        line.appendChild(cell);
      });
      table.appendChild(line);
    });
    article.appendChild(table);
  } else if (block.type === "equation") {
    const line = document.createElement("p");
    line.className = "equation";
    line.textContent = textOf(block) || "Equation";
    article.appendChild(line);
  } else if (block.type === "chart" && content.series) {
    const line = document.createElement("p");
    const points = ((content.series[0] || {}).points || []).map((point) => point.label + " " + point.value).filter(Boolean);
    line.textContent = points.length ? points.join(", ") : "Chart";
    article.appendChild(line);
  } else {
    const line = document.createElement("p");
    line.textContent = textOf(block) || block.type;
    article.appendChild(line);
  }
  const meta = document.createElement("p");
  meta.className = "meta";
  const risk = document.createElement("span");
  risk.textContent = block.risk;
  if (block.risk === "CRITICAL" || block.risk === "HIGH") risk.className = "critical";
  meta.append(
    document.createTextNode(pageLabel(block.page_start) + "  ·  " + block.type + "  ·  "),
    risk,
    document.createTextNode("  ·  " + Number(block.confidence.final).toFixed(2) + "  ·  " + (block.extractor || "unread"))
  );
  article.appendChild(meta);
  return article;
}

function markdownOf(doc) {
  const lines = ["# " + (doc.filename || "Document"), ""];
  if (doc.status === "failed") {
    lines.push("**Status:** Failed");
    (doc.errors || []).forEach((error) => {
      lines.push("> Error (" + (error.error_code || "") + "): " + (error.message || ""));
    });
    lines.push("");
  }
  ordered(doc).forEach((block) => {
    const marker = (block.status === "needs_review" || block.status === "failed") ? " [needs review]" : "";
    const content = block.content && typeof block.content === "object" ? block.content : {};
    if (block.type === "heading") {
      const level = Math.min(Number(content.level) || 1, 6);
      lines.push("#".repeat(level) + " " + textOf(block) + marker);
    } else if (block.type === "table") {
      const grid = tableGrid(content);
      const width = Math.max(grid.headers.length, ...grid.rows.map((row) => row.length), 0);
      if (!width) {
        lines.push("<!-- Table Data -->");
      } else {
        const header = grid.headers.concat(Array(Math.max(0, width - grid.headers.length)).fill(""));
        lines.push("| " + header.join(" | ") + " |");
        lines.push("| " + header.map(() => "---").join(" | ") + " |");
        grid.rows.forEach((row) => {
          const padded = row.concat(Array(Math.max(0, width - row.length)).fill(""));
          lines.push("| " + padded.join(" | ") + " |");
        });
        if (marker) lines.push(marker.trim());
      }
    } else if (block.type === "equation") {
      lines.push("$$\n" + (content.latex || textOf(block)) + "\n$$");
    } else if (block.type === "chart") {
      const points = [];
      (content.series || []).forEach((series) => {
        (series.points || []).forEach((point) => points.push(point.label + " " + point.value));
      });
      const title = content.title || content.chart_type || "chart";
      lines.push("**Chart:** " + title + (points.length ? ". " + points.join(", ") : "") + marker);
    } else if (block.type === "figure") {
      lines.push("**Figure:** " + (textOf(block) || "figure") + marker);
    } else if (block.status === "failed") {
      return;
    } else {
      lines.push((textOf(block) || block.type) + marker);
    }
    lines.push("");
  });
  return lines.join("\n");
}

function regionRows(doc) {
  return ordered(doc).map((block, index) => ({
    order: index + 1,
    page: block.page_start,
    type: block.type,
    region: block.region || "",
    box: boxText(block),
    extractor: block.extractor || "",
    confidence: Number(block.confidence.final).toFixed(2),
    risk: block.risk,
    text: (textOf(block) || "").replace(/\s+/g, " ").slice(0, 80)
  }));
}

function regionsText(doc) {
  const rows = regionRows(doc);
  const header = "order\tpage\ttype\tregion\tbox\textractor\tconfidence\trisk\ttext";
  const body = rows.map((row) => [row.order, row.page, row.type, row.region, row.box, row.extractor, row.confidence, row.risk, row.text].join("\t"));
  return [header].concat(body).join("\n");
}

function orderText(doc) {
  return ordered(doc).map((block, index) => {
    const line = (textOf(block) || block.type).replace(/\s+/g, " ");
    return (index + 1) + ". " + block.type + " — " + line + " (" + (block.extractor || "unread") + ", " + pageLabel(block.page_start) + ")";
  }).join("\n");
}

function readingText(doc) {
  return ordered(doc).map((block) => textOf(block) || block.type).join("\n\n");
}

function renderRegions(doc) {
  const host = $("regions");
  host.innerHTML = "";
  const rows = regionRows(doc);
  if (!rows.length) {
    host.textContent = "The file opened and returned no regions.";
    return;
  }
  const table = document.createElement("table");
  const head = document.createElement("tr");
  ["Order", "Page", "Type", "Region", "Box", "Extractor", "Score", "Risk"].forEach((name) => {
    const cell = document.createElement("th");
    cell.textContent = name;
    head.appendChild(cell);
  });
  table.appendChild(head);
  rows.slice(0, 200).forEach((row) => {
    const line = document.createElement("tr");
    [row.order, pageLabel(row.page), row.type, row.region || "—", row.box, row.extractor || "—", row.confidence, row.risk].forEach((value) => {
      const cell = document.createElement("td");
      cell.textContent = value;
      line.appendChild(cell);
    });
    table.appendChild(line);
  });
  host.appendChild(table);
  if (rows.length > 200) {
    const note = document.createElement("p");
    note.className = "colophon";
    note.textContent = "Showing 200 of " + rows.length + " regions. Copy regions includes every row.";
    host.appendChild(note);
  }
}

function drawPrecedence(doc) {
  const sheet = $("sheet");
  sheet.innerHTML = "";
  const blocks = ordered(doc);
  if (!blocks.length) {
    sheet.textContent = "There is no order to show.";
    return;
  }
  const shown = blocks.slice(0, 80);
  shown.forEach((block, index) => {
    const step = document.createElement("div");
    step.className = "step";
    const number = document.createElement("p");
    number.className = "step-n";
    number.textContent = String(index + 1);
    const body = document.createElement("div");
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.id = block.id;
    button.textContent = (textOf(block) || block.type).replace(/\s+/g, " ");
    button.addEventListener("click", () => selectBlock(block.id));
    const evidence = document.createElement("p");
    evidence.className = "chain-evidence";
    evidence.textContent = block.type + "  ·  " + (block.extractor || "unread") + "  ·  " + Number(block.confidence.final).toFixed(2) + "  ·  " + boxText(block);
    body.append(button, evidence);
    step.append(number, body);
    if (index < shown.length - 1) {
      const link = document.createElement("p");
      link.className = "precedes";
      link.textContent = "precedes";
      step.appendChild(link);
    }
    sheet.appendChild(step);
  });
  if (blocks.length > shown.length) {
    const note = document.createElement("p");
    note.className = "colophon";
    note.textContent = "Showing the first " + shown.length + " of " + blocks.length + ". Copy order includes every block.";
    sheet.appendChild(note);
  }
}

function selectBlock(id) {
  state.selected = id;
  document.querySelectorAll(".step button").forEach((node) => {
    node.classList.toggle("is-on", node.dataset.id === id);
  });
  const block = (state.doc.blocks || []).find((item) => item.id === id);
  const detail = $("detail");
  if (!block) return;
  const confidence = block.confidence || {};
  const source = block.source || {};
  detail.innerHTML = "";
  const heading = document.createElement("h2");
  heading.textContent = block.type;
  detail.appendChild(heading);
  const rows = [
    ["Risk", block.risk],
    ["Status", block.status],
    ["Final", Number(confidence.final).toFixed(2)],
    ["Extraction", Number(confidence.extraction).toFixed(2)],
    ["Structure", Number(confidence.structure).toFixed(2)],
    ["Source", Number(confidence.source_quality).toFixed(2)],
    ["Extractor", block.extractor || "—"],
    ["Page", pageLabel(block.page_start)],
    ["Box", boxText(block)],
    ["File", String(source.file || state.doc.filename || "—").split(/[/\\]/).pop()]
  ];
  if (source.sheet) rows.push(["Sheet", source.sheet]);
  if (source.cell_range) rows.push(["Cells", source.cell_range]);
  if (block.flags && block.flags.length) rows.push(["Flags", block.flags.join(", ")]);
  const list = document.createElement("dl");
  rows.forEach(([name, value]) => {
    const term = document.createElement("dt");
    term.textContent = name;
    const data = document.createElement("dd");
    data.textContent = value;
    list.append(term, data);
  });
  detail.appendChild(list);
}

function showDocument(doc) {
  state.doc = doc;
  state.selected = null;
  $("landing").hidden = true;
  $("work").hidden = false;
  $("tabs").hidden = false;
  $("title").textContent = titleOf(doc);
  const report = doc.trust_report || {};
  const counts = report.risk_counts || {};
  const risks = Object.entries(counts).filter(([, count]) => count).map(([level, count]) => count + " " + level.toLowerCase());
  $("kicker").textContent = (doc.format || "file").toUpperCase() + "  ·  " + (doc.status || "");
  const pages = doc.page_count ? doc.page_count + (doc.page_count === 1 ? " page" : " pages") : "office file";
  $("colophon").textContent = [
    doc.filename,
    pages,
    (doc.blocks || []).length + " blocks",
    report.mean_final != null ? "confidence " + Number(report.mean_final).toFixed(2) : "",
    risks.join(", ")
  ].filter(Boolean).join("   ·   ");
  const errors = $("errors");
  errors.innerHTML = "";
  if (doc.errors && doc.errors.length) {
    errors.hidden = false;
    doc.errors.slice(0, 6).forEach((error) => {
      const line = document.createElement("p");
      line.textContent = (error.error_code || "Error") + ". " + (error.message || "");
      errors.appendChild(line);
    });
  } else {
    errors.hidden = true;
  }
  const host = $("blocks");
  host.innerHTML = "";
  if (!(doc.blocks || []).length) {
    const empty = document.createElement("p");
    empty.className = "lede";
    empty.textContent = "The file opened and returned no blocks.";
    host.appendChild(empty);
  } else {
    ordered(doc).forEach((block) => host.appendChild(renderBlock(block)));
  }
  renderRegions(doc);
  const markdown = state.markdown || markdownOf(doc);
  const jsonText = state.json || JSON.stringify(doc, null, 2);
  $("markdown").textContent = markdown || "The writer returned no Markdown.";
  $("json").textContent = jsonText || "The writer returned no JSON.";
  $("md-count").textContent = "Markdown  ·  " + markdown.length + " characters";
  $("json-count").textContent = "JSON  ·  " + jsonText.length + " characters";
  drawPrecedence(doc);
  $("detail").innerHTML = "<p class=\"detail-empty\">Select a block to see its source.</p>";
  setView("exports");
}

function setView(name) {
  state.view = name;
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.classList.toggle("is-on", tab.dataset.view === name);
  });
  ["exports", "reading", "regions", "precedence"].forEach((view) => {
    const pane = $("view-" + view);
    const on = view === name;
    pane.hidden = !on;
    pane.classList.toggle("is-on", on);
  });
}

function payloadFor(kind) {
  const doc = state.doc;
  if (!doc) return "";
  if (kind === "reading") return readingText(doc);
  if (kind === "regions") return regionsText(doc);
  if (kind === "markdown") return state.markdown || $("markdown").textContent;
  if (kind === "json") return state.json || $("json").textContent;
  return orderText(doc);
}

async function copyKind(kind, button) {
  const text = payloadFor(kind);
  try {
    await navigator.clipboard.writeText(text);
  } catch (error) {
    const area = document.createElement("textarea");
    area.value = text;
    document.body.appendChild(area);
    area.select();
    document.execCommand("copy");
    area.remove();
  }
  const previous = button.textContent;
  button.textContent = "Copied";
  button.classList.add("is-on");
  window.setTimeout(() => {
    button.textContent = previous;
    button.classList.remove("is-on");
  }, 1200);
}

function busy(message, failed) {
  const status = $("status");
  status.hidden = !message;
  status.textContent = message || "";
  status.classList.toggle("is-error", Boolean(failed));
  $("drop-title").textContent = message && !failed ? message : "Drop a document here, or choose a file";
}

async function receive(response) {
  const data = await response.json();
  if (!response.ok || data.error) throw new Error(data.error || "The read failed.");
  const document = data.document || data;
  if (!document.blocks && document.status !== "failed" && document.status !== "complete" && document.status !== "partial") {
    throw new Error(data.error || "The read did not return a document.");
  }
  state.markdown = data.markdown || "";
  state.json = data.json || "";
  showDocument(document);
}

async function parseSample() {
  busy("Reading the sample report.");
  try {
    const response = await fetch("/api/parse", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sample: "sample.docx" })
    });
    await receive(response);
  } catch (error) {
    busy(error.message, true);
    return;
  }
  busy("");
}

async function parseUpload(file) {
  busy("Reading " + file.name + ".");
  const body = new FormData();
  body.append("file", file);
  try {
    const response = await fetch("/api/parse", { method: "POST", body });
    await receive(response);
  } catch (error) {
    busy(error.message, true);
    return;
  }
  busy("");
}

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => setView(tab.dataset.view));
});

document.querySelectorAll(".copy").forEach((button) => {
  button.addEventListener("click", () => copyKind(button.dataset.copy, button));
});

$("file").addEventListener("change", () => {
  const file = $("file").files && $("file").files[0];
  if (file) parseUpload(file);
});

$("sample").addEventListener("click", parseSample);

const drop = $("drop");
["dragenter", "dragover"].forEach((name) => {
  drop.addEventListener(name, (event) => {
    event.preventDefault();
    drop.classList.add("is-over");
  });
});
["dragleave", "drop"].forEach((name) => {
  drop.addEventListener(name, (event) => {
    event.preventDefault();
    drop.classList.remove("is-over");
  });
});
drop.addEventListener("drop", (event) => {
  const file = event.dataTransfer && event.dataTransfer.files && event.dataTransfer.files[0];
  if (file) parseUpload(file);
});
