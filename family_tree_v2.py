#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Demiralay Sülalesi - İnteraktif Aile Ağacı Görselleştirici v2
Kullanım: python family_tree_v2.py
Çıktı  : sulale_agaci_v2.html  (tarayıcıda açın)
"""

import json
import os
import pandas as pd

EXCEL_PATH  = "Demiralay_Sulalesi.xlsx"
OUTPUT_HTML = "sulale_agaci_v2.html"


# ─── helpers ────────────────────────────────────────────────────────────────

def safe(val):
    if val is None:
        return ""
    s = str(val).strip()
    return "" if s.lower() in ("nan", "none") else s


def find_parent(code):
    if not code or code == "0":
        return None
    if len(code) == 1:
        return "0"
    if "-" in code:                        # e.g. "2FE-1" → "2FE"
        base = code.split("-")[0]
        return base[:-1] if len(base) > 1 else "0"
    return code[:-1]


def walk(node):
    yield node
    for child in node.get("children", []):
        yield from walk(child)


# ─── data ────────────────────────────────────────────────────────────────────

def load_data():
    df       = pd.read_excel(EXCEL_PATH, sheet_name="Sülale Listesi")
    df_cross = pd.read_excel(EXCEL_PATH, sheet_name="Çapraz Akrabalıklar")

    df.columns       = df.columns.str.strip()
    df_cross.columns = df_cross.columns.str.strip()

    df["Kod"] = df["Kod"].astype(str).str.strip().apply(lambda x: x.split(".")[0])
    df = df[df["Kod"] != "nan"].copy()

    # Build flat node dict
    nodes = {}
    for _, row in df.iterrows():
        code = safe(row["Kod"])
        if not code:
            continue
        nodes[code] = {
            "id"           : code,
            "name"         : safe(row.get("Ad"))                  or "Bilinmiyor",
            "spouse"       : safe(row.get("Eş Adı")),
            "spouseSurname": safe(row.get("Eşin Kızlık Soyadı")),
            "birth"        : safe(row.get("Doğum Tarihi")),
            "death"        : safe(row.get("Ölüm Tarihi")),
            "generation"   : safe(row.get("Nesil")),
            "notes"        : safe(row.get("Notlar / Çapraz Ref")),
        }

    # Parent → children mapping
    children_map = {c: [] for c in nodes}
    for code in list(nodes.keys()):
        p = find_parent(code)
        if p and p in nodes:
            children_map[p].append(code)

    # Recursive tree builder
    def build(code):
        n    = dict(nodes[code])
        kids = sorted(children_map.get(code, []))
        if kids:
            n["children"] = [build(c) for c in kids]
        return n

    tree = build("0")

    # Cross-family marriages
    cross = []
    for _, row in df_cross.iterrows():
        p1 = safe(str(row.get("Kişi 1 Kodu", "")))
        p2 = safe(str(row.get("Kişi 2 Kodu", "")))
        if p1 and p2 and p1 in nodes and p2 in nodes:
            cross.append({
                "source" : p1,
                "target" : p2,
                "person1": safe(row.get("Kişi 1 Adı")),
                "person2": safe(row.get("Kişi 2 Adı")),
                "desc"   : safe(row.get("Açıklama")),
            })

    total = sum(1 for _ in walk(tree))
    return tree, cross, total


# ─── HTML template ───────────────────────────────────────────────────────────
# Placeholders replaced at the end: __TREE_JSON__, __CROSS_JSON__, __TOTAL__

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Demiralay Sülalesi Ağacı</title>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body {
  font-family:'Segoe UI',system-ui,sans-serif;
  background:#0d1b2a;
  color:#dde;
  height:100vh;
  display:flex;
  flex-direction:column;
  overflow:hidden;
}

/* ── Header ─────────────────────────────── */
#header {
  background:#122340;
  padding:9px 16px;
  display:flex;
  align-items:center;
  gap:10px;
  border-bottom:1px solid #1c3a5c;
  flex-shrink:0;
  flex-wrap:wrap;
}
#title {
  font-size:16px;
  font-weight:700;
  color:#d4a843;
  white-space:nowrap;
}
#search {
  padding:5px 14px;
  border-radius:20px;
  border:1px solid #1c3a5c;
  background:#0d1b2a;
  color:#dde;
  font-size:13px;
  outline:none;
  width:210px;
  transition:border-color .2s;
}
#search:focus { border-color:#d4a843; }
#search::placeholder { color:#445; }
.btn {
  padding:5px 12px;
  border-radius:6px;
  border:1px solid #1c3a5c;
  background:#172f4a;
  color:#bbc;
  cursor:pointer;
  font-size:12px;
  white-space:nowrap;
  transition:background .15s,color .15s;
}
.btn:hover { background:#1c3a5c; color:#fff; }
.btn.on    { background:#d4a843; color:#0d1b2a; border-color:#d4a843; }
#stat { color:#445; font-size:12px; margin-left:auto; white-space:nowrap; }

/* ── Main ───────────────────────────────── */
#main { flex:1; display:flex; overflow:hidden; }

/* ── Canvas ─────────────────────────────── */
#canvas { flex:1; position:relative; overflow:hidden; }
svg { width:100%; height:100%; cursor:grab; display:block; }
svg:active { cursor:grabbing; }

/* ── D3 ─────────────────────────────────── */
.link {
  fill:none;
  stroke:rgba(255,255,255,.08);
  stroke-width:1.5;
}
.cross-link {
  fill:none;
  stroke:#d4a843;
  stroke-width:1.5;
  stroke-dasharray:7,4;
  opacity:.6;
}
.node rect.bg {
  cursor:pointer;
  rx:7; ry:7;
  transition:filter .15s;
}
.node:hover rect.bg {
  filter:brightness(1.3) drop-shadow(0 3px 10px rgba(0,0,0,.7));
}
.node.sel rect.bg { stroke:#d4a843; stroke-width:2.5; }
.node.hit rect.bg { filter:drop-shadow(0 0 9px #ffe066) brightness(1.35); }
.node text { pointer-events:none; }

/* ── Overlay controls ───────────────────── */
#controls {
  position:absolute;
  bottom:16px;
  left:16px;
  display:flex;
  flex-direction:column;
  gap:5px;
}
.ctl {
  width:30px; height:30px;
  border-radius:6px;
  border:1px solid #1c3a5c;
  background:#122340cc;
  color:#bbc;
  cursor:pointer;
  font-size:15px;
  display:flex;
  align-items:center;
  justify-content:center;
  backdrop-filter:blur(4px);
}
.ctl:hover { background:#1c3a5c; color:#fff; }

/* ── Legend ─────────────────────────────── */
#legend {
  position:absolute;
  top:12px;
  left:12px;
  background:#122340dd;
  border:1px solid #1c3a5c;
  border-radius:8px;
  padding:10px 13px;
  backdrop-filter:blur(4px);
  font-size:12px;
}
.leg-title { color:#445; text-transform:uppercase; letter-spacing:.5px; font-size:10px; margin-bottom:7px; }
.leg-row { display:flex; align-items:center; gap:7px; margin-bottom:4px; }
.leg-dot { width:11px; height:11px; border-radius:3px; flex-shrink:0; }

/* ── Detail panel ───────────────────────── */
#panel {
  width:0;
  background:#122340;
  border-left:1px solid #1c3a5c;
  display:flex;
  flex-direction:column;
  overflow:hidden;
  transition:width .25s ease;
  flex-shrink:0;
}
#panel.open { width:288px; }
#ph {
  padding:13px 15px;
  border-bottom:1px solid #1c3a5c;
  display:flex;
  justify-content:space-between;
  align-items:flex-start;
  flex-shrink:0;
}
#pname { font-size:15px; font-weight:700; color:#d4a843; line-height:1.3; }
#pcode { font-size:11px; color:#445; font-family:monospace; margin-top:2px; }
#pbody { flex:1; overflow-y:auto; padding:13px 15px; }
#pbody::-webkit-scrollbar { width:5px; }
#pbody::-webkit-scrollbar-thumb { background:#1c3a5c; border-radius:3px; }
.pr { margin-bottom:11px; }
.pl { font-size:10px; color:#445; text-transform:uppercase; letter-spacing:.5px; margin-bottom:3px; }
.pv { font-size:13px; color:#ccd; line-height:1.45; }
.gen-chip {
  display:inline-block;
  padding:2px 9px;
  border-radius:10px;
  font-size:11px;
  font-weight:600;
  color:#fff;
}
#pcross { padding:11px 15px; border-top:1px solid #1c3a5c; flex-shrink:0; }
.cx-title { font-size:10px; color:#d4a843; text-transform:uppercase; letter-spacing:.5px; margin-bottom:6px; }
.cx-row { font-size:12px; color:#99a; margin-bottom:5px; line-height:1.4; }
</style>
</head>
<body>

<div id="header">
  <div id="title">🌿 Demiralay Sülalesi</div>
  <input id="search" type="text" placeholder="İsim ara…" autocomplete="off" spellcheck="false">
  <button class="btn" id="btn-expand">Tümünü Aç</button>
  <button class="btn" id="btn-collapse">Tümünü Kapat</button>
  <button class="btn" id="btn-fit">Ekrana Sığdır</button>
  <button class="btn on" id="btn-cross">Çapraz Bağlar</button>
  <div id="stat">__TOTAL__ kişi · 4 çapraz akrabalık</div>
</div>

<div id="main">
  <div id="canvas">
    <svg id="svg"></svg>

    <div id="legend">
      <div class="leg-title">Nesil</div>
      <div class="leg-row"><div class="leg-dot" style="background:#8d6e63"></div>Kök</div>
      <div class="leg-row"><div class="leg-dot" style="background:#1976d2"></div>Nesil 1</div>
      <div class="leg-row"><div class="leg-dot" style="background:#2e7d32"></div>Nesil 2</div>
      <div class="leg-row"><div class="leg-dot" style="background:#e65100"></div>Nesil 3</div>
      <div class="leg-row"><div class="leg-dot" style="background:#6a1b9a"></div>Nesil 4</div>
      <div class="leg-row"><div class="leg-dot" style="background:#b71c1c"></div>Nesil 5</div>
      <div class="leg-row"><div class="leg-dot" style="background:#00695c"></div>Nesil 6</div>
      <div class="leg-row" style="margin-top:7px;border-top:1px solid #1c3a5c;padding-top:7px">
        <svg width="22" height="8" style="flex-shrink:0">
          <line x1="1" y1="4" x2="21" y2="4" stroke="#d4a843" stroke-width="1.5" stroke-dasharray="5,3"/>
        </svg>
        Çapraz Evlilik
      </div>
    </div>

    <div id="controls">
      <button class="ctl" id="z-in"  title="Yakınlaştır">+</button>
      <button class="ctl" id="z-fit" title="Ekrana Sığdır">⊙</button>
      <button class="ctl" id="z-out" title="Uzaklaştır">−</button>
    </div>
  </div>

  <div id="panel">
    <div id="ph">
      <div>
        <div id="pname">—</div>
        <div id="pcode"></div>
      </div>
      <button class="ctl" id="pclose" style="flex-shrink:0">✕</button>
    </div>
    <div id="pbody"></div>
    <div id="pcross" style="display:none">
      <div class="cx-title">⚡ Çapraz Akrabalıklar</div>
      <div id="pcross-list"></div>
    </div>
  </div>
</div>

<script src="https://d3js.org/d3.v7.min.js"></script>
<script>
/* ── Data injected by Python ───────────────────── */
const TREE_DATA   = __TREE_JSON__;
const CROSS_LINKS = __CROSS_JSON__;

/* ── Generation colours ────────────────────────── */
const GEN_COLOR = {
  "Kök":    "#8d6e63",
  "Nesil 1":"#1976d2",
  "Nesil 2":"#2e7d32",
  "Nesil 3":"#e65100",
  "Nesil 4":"#6a1b9a",
  "Nesil 5":"#b71c1c",
  "Nesil 6":"#00695c",
};
const DEF_COLOR = "#37474f";

/* ── Layout constants ──────────────────────────── */
const NW = 176, NH = 44;   // node width / height
const DX = NH + 12;        // vertical spacing between siblings
const DY = 210;            // horizontal spacing between generations

/* ── SVG + zoom ────────────────────────────────── */
const svg    = d3.select("#svg");
const rootG  = svg.append("g");

const zoomBeh = d3.zoom()
  .scaleExtent([0.04, 4])
  .on("zoom", e => rootG.attr("transform", e.transform));
svg.call(zoomBeh);

/* layer order matters: links behind cross-links behind nodes */
const gLinks = rootG.append("g");
const gCross = rootG.append("g");
const gNodes = rootG.append("g");

/* ── Tree layout ───────────────────────────────── */
const treeLayout = d3.tree().nodeSize([DX, DY]);

let root = d3.hierarchy(TREE_DATA);
let uid  = 0;

/* Collapse everything at depth >= 2 initially */
root.descendants().forEach(d => {
  d._uid = ++uid;
  if (d.depth >= 2 && d.children) {
    d._children = d.children;
    d.children  = null;
  }
});

/* ── State ─────────────────────────────────────── */
let selId      = null;
let searchTerm = "";
let showCross  = true;
const posMap   = new Map();   // node id → {sx, sy} screen coords

/* ── Utilities ─────────────────────────────────── */
const trunc = (s, n) => s && s.length > n ? s.slice(0, n - 1) + "…" : (s || "");

function countDesc(nodeArr) {
  let n = 0;
  const q = [...(nodeArr || [])];
  while (q.length) {
    const d = q.shift();
    n++;
    if (d._children) q.push(...d._children);
    if (d.children)  q.push(...d.children);
  }
  return n;
}

/* ── Main update ───────────────────────────────── */
function update(src) {
  treeLayout(root);
  const nodes = root.descendants();
  const links = root.links();

  /* refresh position map (screen x = d.y, screen y = d.x in horizontal tree) */
  posMap.clear();
  nodes.forEach(d => posMap.set(d.data.id, { sx: d.y, sy: d.x }));

  /* ── Links ── */
  const path = gLinks.selectAll("path.link").data(links, d => d.target._uid);

  const pathEnter = path.enter().append("path").attr("class", "link")
    .attr("d", () => {
      const o = { x: src._sx0 ?? src.y, y: src._sy0 ?? src.x };
      return d3.linkHorizontal()({ source: o, target: o });
    });

  path.merge(pathEnter).transition().duration(350)
    .attr("d", d => d3.linkHorizontal()({
      source: { x: d.source.y, y: d.source.x },
      target: { x: d.target.y, y: d.target.x },
    }));

  path.exit().transition().duration(350)
    .attr("d", () => {
      const o = { x: src.y, y: src.x };
      return d3.linkHorizontal()({ source: o, target: o });
    }).remove();

  /* ── Nodes ── */
  const node = gNodes.selectAll("g.node").data(nodes, d => d._uid);

  const enter = node.enter().append("g").attr("class", "node")
    .attr("transform", () => `translate(${src._sx0 ?? src.y},${src._sy0 ?? src.x})`)
    .on("click", (evt, d) => {
      evt.stopPropagation();
      toggleNode(d);
      selId = d.data.id;
      update(d);
      showPanel(d);
    });

  /* background rect */
  enter.append("rect").attr("class", "bg")
    .attr("x", -NW / 2).attr("y", -NH / 2)
    .attr("width", NW).attr("height", NH)
    .attr("rx", 7).attr("ry", 7)
    .attr("stroke", "rgba(255,255,255,.1)").attr("stroke-width", 1);

  /* primary name */
  enter.append("text").attr("class", "t-name")
    .attr("text-anchor", "middle")
    .attr("fill", "#fff")
    .attr("font-size", 12).attr("font-weight", "bold");

  /* spouse name */
  enter.append("text").attr("class", "t-spouse")
    .attr("text-anchor", "middle")
    .attr("fill", "rgba(255,255,255,.65)")
    .attr("font-size", 10).attr("font-style", "italic");

  /* expand/collapse state badge background */
  enter.append("rect").attr("class", "bdg-bg")
    .attr("x", NW / 2 - 36).attr("y", -11)
    .attr("width", 36).attr("height", 22)
    .attr("rx", 5);

  /* expand/collapse state badge text */
  enter.append("text").attr("class", "t-bdg")
    .attr("x", NW / 2 - 18).attr("y", 0)
    .attr("text-anchor", "middle").attr("dominant-baseline", "middle")
    .attr("fill", "rgba(255,255,255,.9)").attr("font-size", 10);

  /* ── Merge + update ── */
  const merged = node.merge(enter);

  merged.transition().duration(350)
    .attr("transform", d => `translate(${d.y},${d.x})`);

  merged.select("rect.bg")
    .attr("fill", d => GEN_COLOR[d.data.generation] ?? DEF_COLOR);

  merged.select("text.t-name")
    .attr("y", d => d.data.spouse ? -11 : 1)
    .text(d => trunc(d.data.name, 22));

  merged.select("text.t-spouse")
    .attr("y", d => d.data.spouse ? 9 : 0)
    .text(d => trunc(d.data.spouse, 23));

  merged.select("rect.bdg-bg")
    .attr("display", d => (d._children || (d.children && d.children.length)) ? null : "none")
    .attr("fill", d => d._children ? "rgba(0,0,0,.55)" : "rgba(255,255,255,.12)");

  merged.select("text.t-bdg")
    .text(d => {
      if (d._children) return `▶ +${countDesc(d._children)}`;
      if (d.children && d.children.length) return "▼";
      return "";
    });

  merged
    .classed("sel", d => d.data.id === selId)
    .classed("hit", d => searchTerm !== "" && d.data.name.toLowerCase().includes(searchTerm));

  /* ── Exit ── */
  node.exit().transition().duration(350)
    .attr("transform", `translate(${src.y},${src.x})`).remove();

  /* store positions for next animated transition */
  nodes.forEach(d => { d._sx0 = d.y; d._sy0 = d.x; });

  drawCrossLinks();
}

function toggleNode(d) {
  if (d.children) {
    d._children = d.children;
    d.children  = null;
  } else if (d._children) {
    d.children  = d._children;
    d._children = null;
  }
}

/* ── Cross-link arcs ───────────────────────────── */
function drawCrossLinks() {
  if (!showCross) { gCross.selectAll("*").remove(); return; }

  const valid = CROSS_LINKS.filter(c => posMap.has(c.source) && posMap.has(c.target));

  const arcs = gCross.selectAll("path.cross-link").data(valid, d => d.source + d.target);

  arcs.enter().append("path").attr("class", "cross-link")
    .merge(arcs)
    .attr("d", d => {
      const s  = posMap.get(d.source);
      const t  = posMap.get(d.target);
      const cx = (s.sx + t.sx) / 2 - 60;
      return `M${s.sx},${s.sy} C${cx},${s.sy} ${cx},${t.sy} ${t.sx},${t.sy}`;
    });

  arcs.select("title").remove();
  gCross.selectAll("path.cross-link").append("title")
    .text(d => `${d.person1} × ${d.person2}\n${d.desc}`);

  arcs.exit().remove();
}

/* ── Detail panel ──────────────────────────────── */
function showPanel(d) {
  const p   = d.data;
  const col = GEN_COLOR[p.generation] ?? DEF_COLOR;

  document.getElementById("pname").textContent = p.name;
  document.getElementById("pcode").textContent = "Kod: " + p.id;

  let html = "";
  if (p.generation)
    html += `<div class="pr"><div class="pl">Nesil</div>
      <span class="gen-chip" style="background:${col}">${p.generation}</span></div>`;
  if (p.spouse)
    html += row("Eş", p.spouse + (p.spouseSurname ? ` (${p.spouseSurname})` : ""));
  if (p.birth) html += row("Doğum", p.birth);
  if (p.death) html += row("Ölüm",  p.death);
  if (p.notes) html += row("Notlar", p.notes);

  const visible  = d.children  ? d.children.length  : 0;
  const hidden   = d._children ? d._children.length : 0;
  const kidCount = visible + hidden;
  if (kidCount > 0)
    html += row("Çocuklar", kidCount + (hidden ? ` (${hidden} gizli)` : ""));

  document.getElementById("pbody").innerHTML =
    html || "<div style='color:#445;font-size:13px;margin-top:8px'>Detay yok</div>";

  /* cross-link entries for this person */
  const cx  = CROSS_LINKS.filter(c => c.source === p.id || c.target === p.id);
  const cxEl = document.getElementById("pcross");
  if (cx.length) {
    cxEl.style.display = "";
    document.getElementById("pcross-list").innerHTML = cx.map(c =>
      `<div class="cx-row">↔ <b>${c.person1}</b> × <b>${c.person2}</b><br>
       <span style="color:#556">${c.desc}</span></div>`
    ).join("");
  } else {
    cxEl.style.display = "none";
  }

  document.getElementById("panel").classList.add("open");
}

function row(label, value) {
  return `<div class="pr"><div class="pl">${label}</div><div class="pv">${value}</div></div>`;
}

document.getElementById("pclose").onclick = () => {
  document.getElementById("panel").classList.remove("open");
  selId = null;
  update(root);
};

/* ── Search ────────────────────────────────────── */
document.getElementById("search").addEventListener("input", e => {
  searchTerm = e.target.value.trim().toLowerCase();
  if (searchTerm) expandForSearch(root, searchTerm);
  update(root);
});

function hasMatch(d, term) {
  if (d.data.name.toLowerCase().includes(term)) return true;
  const kids = [...(d.children || []), ...(d._children || [])];
  return kids.some(k => hasMatch(k, term));
}

function expandForSearch(d, term) {
  /* expand this node if any hidden descendant matches */
  if (d._children) {
    if (d._children.some(k => hasMatch(k, term))) {
      d.children  = [...(d.children || []), ...d._children];
      d._children = null;
    }
  }
  (d.children || []).forEach(k => expandForSearch(k, term));
}

/* ── Toolbar ───────────────────────────────────── */
document.getElementById("btn-expand").onclick = () => {
  root.descendants().forEach(d => {
    if (d._children) { d.children = d._children; d._children = null; }
  });
  update(root);
};

document.getElementById("btn-collapse").onclick = () => {
  root.descendants().forEach(d => {
    if (d.depth >= 2 && d.children) { d._children = d.children; d.children = null; }
  });
  update(root);
};

document.getElementById("btn-fit").onclick = fitView;

document.getElementById("btn-cross").addEventListener("click", function () {
  showCross = !showCross;
  this.classList.toggle("on", showCross);
  drawCrossLinks();
});

/* ── Zoom buttons ──────────────────────────────── */
document.getElementById("z-in" ).onclick = () => svg.transition().call(zoomBeh.scaleBy, 1.4);
document.getElementById("z-out").onclick = () => svg.transition().call(zoomBeh.scaleBy, 0.72);
document.getElementById("z-fit").onclick = fitView;

function fitView() {
  const bb = rootG.node().getBBox();
  if (!bb.width) return;
  const svgEl = document.getElementById("svg");
  const W = svgEl.clientWidth  || 900;
  const H = svgEl.clientHeight || 600;
  const pad   = 60;
  const scale = Math.min((W - pad) / bb.width, (H - pad) / bb.height, 1.6);
  const tx    = (W - bb.width  * scale) / 2 - bb.x * scale;
  const ty    = (H - bb.height * scale) / 2 - bb.y * scale;
  svg.transition().duration(600)
     .call(zoomBeh.transform, d3.zoomIdentity.translate(tx, ty).scale(scale));
}

/* ── Boot ──────────────────────────────────────── */
update(root);
setTimeout(fitView, 120);
</script>
</body>
</html>
"""


# ─── main ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    if not os.path.exists(EXCEL_PATH):
        print(f"Hata: '{EXCEL_PATH}' bulunamadi.")
        raise SystemExit(1)

    print("Excel okunuyor...")
    tree, cross, total = load_data()

    print(f"  -> {total} kisi, {len(cross)} capraz akrabalik")
    print("HTML olusturuluyor...")

    tree_json  = json.dumps(tree,  ensure_ascii=False)
    cross_json = json.dumps(cross, ensure_ascii=False)

    html = (HTML_TEMPLATE
            .replace("__TREE_JSON__",  tree_json)
            .replace("__CROSS_JSON__", cross_json)
            .replace("__TOTAL__",      str(total)))

    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\n[OK] '{OUTPUT_HTML}' olusturuldu.")
    print("  Tarayicide acmak icin dosyaya cift tiklayin.")
    print("  (Not: Internete baglantiyi gerektirir - D3.js CDN'den yuklenir.)")
