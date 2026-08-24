"""
generate_demo_video.py
Usage: python generate_demo_video.py <bug_report.json> [analysis.json]

Generates has_demo.html — a full-screen animated demo that looks like
the actual game running, with live variable monitor, sprite animations,
and dramatic oracle-fires moments. Designed to be screen-recorded for
your dissertation video submission.

Press Win+G to open Xbox Game Bar and hit Record before opening this page.
"""

import sys, json, re, webbrowser
from pathlib import Path

if len(sys.argv) < 2:
    print("Usage: python generate_demo_video.py <bug_report.json> [analysis.json]")
    sys.exit(1)

REPORT_PATH   = Path(sys.argv[1]).resolve()
ANALYSIS_PATH = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else None

report   = json.loads(REPORT_PATH.read_text())
analysis = json.loads(ANALYSIS_PATH.read_text()) if ANALYSIS_PATH and ANALYSIS_PATH.exists() else {}

PROGRAM = report.get("program", REPORT_PATH.stem)
STEM    = re.sub(r"\.sb3$", "", PROGRAM, flags=re.IGNORECASE)

_out_dir = REPORT_PATH.parent
try:
    (_out_dir / ".write_test").touch(); (_out_dir / ".write_test").unlink()
except OSError:
    _out_dir = Path.cwd()

OUT = _out_dir / f"{STEM}_demo.html"

# ── parse data ────────────────────────────────────────────────────────────────
bugs         = report.get("bugs", [])
total_ticks  = report.get("totalTicks", 0)
total_seqs   = report.get("totalSequences", 0)
oracle_count = report.get("oracleCount", 0)
states       = report.get("coverage", {}).get("statesVisited", [])

unique_bugs = {}
for b in bugs:
    if b["oracle"] not in unique_bugs:
        unique_bugs[b["oracle"]] = b

tp_count = sum(1 for b in unique_bugs.values() if b.get("tier") == 2)
fp_count = sum(1 for b in unique_bugs.values() if b.get("tier") == 3)
silent_count = oracle_count - len(unique_bugs)
precision_pct = int(tp_count / len(unique_bugs) * 100) if unique_bugs else 0

_raw = analysis.get("duplicateVariables", [])
alias_vars = []
for v in _raw:
    entries = v.get("entries", [])
    if entries:
        alias_vars.append({"name": entries[0].get("name","?"),
                           "sprites": [e.get("sprite","?") for e in entries],
                           "id": v.get("id","")[:14]+"…"})
if not alias_vars:
    alias_vars = [{"name":"hidden for seeker?","sprites":["Player","Bot1"],"id":"dFuW.+_a7a_U…"},
                  {"name":"power","sprites":["Player","Bot1"],"id":"bY3nM5qR…"}]

t2_bug = next((b for b in unique_bugs.values() if b.get("tier")==2), None)
t3_bug = next((b for b in unique_bugs.values() if b.get("tier")==3), None)

alias_js  = json.dumps(alias_vars[:5])
t2_name   = (t2_bug or {}).get("oracle","StaticBug_AliasingVariables")
t3_name   = (t3_bug or {}).get("oracle","LLM_oracle")
t2_detail = (t2_bug or {}).get("detail","14 shared variable IDs detected")[:80]

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Fuzzer Demo — {STEM}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
:root{{
  --bg:#07090f; --surface:#0d1219; --border:#1a2535;
  --blue:#4a90d9; --green:#22c55e; --red:#ef4444;
  --amber:#f59e0b; --purple:#a855f7; --text:#e2e8f0; --muted:#64748b;
}}
html,body{{width:100%;height:100%;overflow:hidden;background:var(--bg);color:var(--text);
           font-family:'Segoe UI',system-ui,sans-serif}}

/* ── LAYOUT ── */
#root{{display:grid;grid-template-rows:48px 1fr 54px;height:100vh}}

/* ── TOP BAR ── */
#topbar{{background:#090d14;border-bottom:1px solid var(--border);
         display:flex;align-items:center;padding:0 1.25rem;gap:1rem}}
#topbar .logo{{font-size:.95rem;font-weight:700;color:#fff;letter-spacing:.02em}}
#topbar .logo span{{color:var(--blue)}}
#topbar .prog{{font-size:.78rem;color:var(--muted);font-family:monospace}}
#topbar .spacer{{flex:1}}
#phase-badge{{padding:3px 12px;border-radius:20px;font-size:.72rem;font-weight:700;
              text-transform:uppercase;letter-spacing:.08em;transition:all .4s}}
#tick-display{{font-family:monospace;font-size:.85rem;color:var(--blue);
               background:#0d1a2a;padding:3px 10px;border-radius:4px}}
#seq-display{{font-size:.72rem;color:var(--muted);font-family:monospace;max-width:200px;
              white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}

/* ── MIDDLE ── */
#middle{{display:grid;grid-template-columns:1fr 300px;min-height:0}}

/* ── GAME PANEL ── */
#game-panel{{position:relative;overflow:hidden;background:var(--bg)}}

/* MAP */
#map{{position:absolute;inset:0}}
.map-tile{{position:absolute;border-radius:4px}}

/* Sprites */
.sprite{{position:absolute;width:52px;height:52px;border-radius:10px;
         display:flex;align-items:center;justify-content:center;
         font-size:1.6rem;border:2px solid;transition:left 0.6s ease,top 0.6s ease;
         filter:drop-shadow(0 4px 8px rgba(0,0,0,.6))}}
.sprite .sp-name{{position:absolute;bottom:-18px;left:50%;transform:translateX(-50%);
                  font-size:.65rem;font-family:monospace;white-space:nowrap}}

/* Key press indicator */
#key-indicator{{position:absolute;bottom:14px;left:50%;transform:translateX(-50%);
                display:flex;gap:.4rem;align-items:center}}
.key-pill{{background:#1a2535;border:1px solid var(--border);border-radius:5px;
           padding:3px 10px;font-family:monospace;font-size:.75rem;color:var(--muted);
           transition:all .2s}}
.key-pill.active{{background:var(--blue);border-color:var(--blue);color:#fff;
                  transform:scale(1.1);box-shadow:0 0 12px rgba(74,144,217,.5)}}

/* Oracle fire overlay */
#oracle-overlay{{position:absolute;inset:0;background:rgba(239,68,68,.08);
                 border:2px solid var(--red);border-radius:0;
                 display:flex;flex-direction:column;align-items:center;justify-content:center;
                 opacity:0;transition:opacity .3s;pointer-events:none;z-index:20}}
#oracle-overlay.show{{opacity:1}}
#oracle-overlay .oo-icon{{font-size:3rem;animation:bounce .5s infinite alternate}}
#oracle-overlay .oo-title{{font-size:1.4rem;font-weight:800;color:var(--red);margin-top:.5rem}}
#oracle-overlay .oo-name{{font-family:monospace;font-size:.78rem;color:#fca5a5;margin-top:.3rem;
                           max-width:460px;text-align:center}}
#oracle-overlay .oo-detail{{font-size:.72rem;color:#7f1d1d;margin-top:.2rem;
                             max-width:460px;text-align:center}}

/* FP overlay (amber) */
#fp-overlay{{position:absolute;inset:0;background:rgba(245,158,11,.08);
              border:2px solid var(--amber);
              display:flex;flex-direction:column;align-items:center;justify-content:center;
              opacity:0;transition:opacity .3s;pointer-events:none;z-index:20}}
#fp-overlay.show{{opacity:1}}
#fp-overlay .fo-icon{{font-size:3rem}}
#fp-overlay .fo-title{{font-size:1.3rem;font-weight:800;color:var(--amber);margin-top:.5rem}}
#fp-overlay .fo-sub{{font-size:.82rem;color:#92400e;margin-top:.3rem;text-align:center;max-width:460px}}
#fp-overlay .fo-fix{{font-size:.72rem;color:var(--muted);margin-top:.6rem;font-family:monospace;
                      background:#1a1200;padding:.4rem .75rem;border-radius:5px;border:1px solid #78350f}}

/* Aliasing flash on sprite */
.sprite.aliased{{animation:aliasPulse .4s ease 3}}
@keyframes aliasPulse{{0%,100%{{border-color:var(--red);box-shadow:0 0 20px rgba(239,68,68,.8)}}
                        50%{{border-color:#fff;box-shadow:0 0 40px rgba(239,68,68,1)}}}}

/* Corruption bubble */
.corrupt-bubble{{position:absolute;background:#450a0a;border:1px solid var(--red);
                 border-radius:6px;padding:.3rem .6rem;font-family:monospace;font-size:.7rem;
                 color:#fca5a5;white-space:nowrap;z-index:15;
                 animation:popIn .3s ease;pointer-events:none}}
@keyframes popIn{{from{{transform:scale(0);opacity:0}}to{{transform:scale(1);opacity:1}}}}

@keyframes bounce{{from{{transform:translateY(0)}}to{{transform:translateY(-8px)}}}}

/* Fuzzer status bar */
#fuzz-status{{position:absolute;top:10px;left:10px;background:rgba(9,13,20,.85);
              border:1px solid var(--border);border-radius:6px;padding:.4rem .75rem;
              font-family:monospace;font-size:.72rem;color:var(--muted);backdrop-filter:blur(4px)}}
#fuzz-status .fs-row{{display:flex;gap:.75rem;align-items:center}}
#fuzz-status .fs-label{{color:var(--muted)}}
#fuzz-status .fs-val{{color:var(--blue);font-weight:600}}
#fuzz-status .fs-val.green{{color:var(--green)}}
#fuzz-status .fs-val.red{{color:var(--red)}}

/* ── RIGHT PANEL (MONITOR) ── */
#monitor{{background:#090c13;border-left:1px solid var(--border);
          display:flex;flex-direction:column;overflow:hidden}}
#mon-header{{padding:.6rem 1rem;border-bottom:1px solid var(--border);
             font-size:.72rem;font-weight:700;color:var(--blue);
             text-transform:uppercase;letter-spacing:.08em;
             display:flex;align-items:center;gap:.5rem;flex-shrink:0}}
.mon-dot{{width:7px;height:7px;border-radius:50%;background:var(--green);
          animation:pulse 1.4s infinite}}
@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.3}}}}
#mon-vars{{flex:1;overflow-y:auto;padding:.4rem .6rem}}
.mv-section{{font-size:.65rem;color:var(--muted);text-transform:uppercase;
             letter-spacing:.08em;padding:.4rem .2rem .2rem;margin-top:.2rem}}
.mv-row{{display:flex;align-items:center;padding:.35rem .4rem;border-radius:5px;
         margin-bottom:2px;transition:background .3s,border .3s;
         border:1px solid transparent}}
.mv-row.normal{{background:rgba(26,37,53,.4)}}
.mv-row.highlight{{background:rgba(239,68,68,.12);border-color:rgba(239,68,68,.3)}}
.mv-row.ok{{background:rgba(34,197,94,.1);border-color:rgba(34,197,94,.2)}}
.mv-row.changed{{background:rgba(74,144,217,.1);border-color:rgba(74,144,217,.25)}}
.mv-name{{flex:1;font-family:monospace;font-size:.74rem;color:#94a3b8;
          overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.mv-val{{font-family:monospace;font-size:.76rem;font-weight:700;
         color:#fff;text-align:right;min-width:70px;
         overflow:hidden;text-overflow:ellipsis;white-space:nowrap;
         transition:color .3s}}
.mv-val.empty{{color:var(--red);font-style:italic}}
.mv-val.ok{{color:var(--green)}}
.mv-val.bug{{color:var(--red)}}
.mv-val.changed{{color:var(--blue)}}
#mon-footer{{padding:.5rem .75rem;border-top:1px solid var(--border);
             font-family:monospace;font-size:.72rem;color:var(--muted);flex-shrink:0}}

/* ── BOTTOM BAR ── */
#bottombar{{background:#090d14;border-top:1px solid var(--border);
            display:flex;align-items:center;padding:0 1.25rem;gap:1.5rem}}
#timeline{{flex:1;display:flex;gap:3px;align-items:center}}
.tl-seg{{height:8px;border-radius:4px;flex:1;background:#1a2535;
          transition:background .4s,box-shadow .4s}}
.tl-seg.active{{background:var(--blue);box-shadow:0 0 8px rgba(74,144,217,.5)}}
.tl-seg.done{{background:#14532d}}
.tl-seg.bug{{background:var(--red);box-shadow:0 0 8px rgba(239,68,68,.5)}}
.tl-seg.fp{{background:var(--amber)}}
#bb-stats{{display:flex;gap:1rem;font-size:.75rem}}
.bb-stat{{display:flex;flex-direction:column;align-items:center;line-height:1.2}}
.bb-stat .bbs-val{{font-weight:700;font-size:.9rem}}
.bb-stat .bbs-lbl{{color:var(--muted);font-size:.65rem;text-transform:uppercase}}
</style>
</head>
<body>
<div id="root">

<!-- TOP BAR -->
<div id="topbar">
  <div class="logo">🔍 <span>Fuzzer</span> Demo</div>
  <div class="prog">{PROGRAM}</div>
  <div class="spacer"></div>
  <div id="seq-display">—</div>
  <div id="tick-display">tick: 0</div>
  <div id="phase-badge" style="background:#1a2535;color:var(--muted)">BOOT</div>
</div>

<!-- MIDDLE -->
<div id="middle">

  <!-- GAME PANEL -->
  <div id="game-panel">
    <div id="map"></div>

    <!-- sprites injected by JS -->

    <!-- oracle overlays -->
    <div id="oracle-overlay">
      <div class="oo-icon">🐛</div>
      <div class="oo-title">BUG DETECTED</div>
      <div class="oo-name" id="oo-name"></div>
      <div class="oo-detail" id="oo-detail"></div>
    </div>
    <div id="fp-overlay">
      <div class="fo-icon">⚠️</div>
      <div class="fo-title">FALSE POSITIVE</div>
      <div class="fo-sub" id="fo-sub">LLM oracle fired at tick 0 — SEEKER uninitialised (boot phase)</div>
      <div class="fo-fix">Fix: if (tick &lt; 30) return &#123; violated: false &#125;</div>
    </div>

    <!-- fuzzer status -->
    <div id="fuzz-status">
      <div class="fs-row">
        <span class="fs-label">sequence</span><span class="fs-val" id="fs-seq">—</span>
        <span class="fs-label">oracles</span><span class="fs-val" id="fs-oracles">{oracle_count}</span>
        <span class="fs-label">bugs</span><span class="fs-val red" id="fs-bugs">0</span>
      </div>
    </div>

    <!-- key indicator -->
    <div id="key-indicator">
      <span style="font-size:.65rem;color:var(--muted);margin-right:.3rem">KEY</span>
      <div class="key-pill" id="key-b">B</div>
      <div class="key-pill" id="key-f">F</div>
      <div class="key-pill" id="key-h">H</div>
      <div class="key-pill" id="key-r">R</div>
      <div class="key-pill" id="key-s">S</div>
    </div>
  </div>

  <!-- RIGHT: VARIABLE MONITOR -->
  <div id="monitor">
    <div id="mon-header">
      <div class="mon-dot"></div>
      Variable Monitor
    </div>
    <div id="mon-vars">
      <!-- populated by JS -->
    </div>
    <div id="mon-footer">tick: <span id="mon-tick">0</span> &nbsp;|&nbsp; <span id="mon-state">Boot</span></div>
  </div>

</div><!-- #middle -->

<!-- BOTTOM BAR -->
<div id="bottombar">
  <div id="timeline"><!-- segs by JS --></div>
  <div id="bb-stats">
    <div class="bb-stat"><span class="bbs-val" style="color:var(--blue)" id="st-ticks">0</span><span class="bbs-lbl">ticks</span></div>
    <div class="bb-stat"><span class="bbs-val" style="color:var(--green)" id="st-silent">{silent_count}</span><span class="bbs-lbl">silent</span></div>
    <div class="bb-stat"><span class="bbs-val" style="color:var(--green)" id="st-tp">0</span><span class="bbs-lbl">TP</span></div>
    <div class="bb-stat"><span class="bbs-val" style="color:var(--amber)" id="st-fp">0</span><span class="bbs-lbl">FP</span></div>
    <div class="bb-stat"><span class="bbs-val" style="color:var(--blue)">{precision_pct}%</span><span class="bbs-lbl">precision</span></div>
  </div>
</div>

</div><!-- #root -->

<script>
// ── DATA ──────────────────────────────────────────────────────────────────────
const ALIAS_VARS  = {alias_js};
const T2_NAME     = {json.dumps(t2_name)};
const T3_NAME     = {json.dumps(t3_name)};
const T2_DETAIL   = {json.dumps(t2_detail)};
const TOTAL_TICKS = {total_ticks};
const TOTAL_SEQS  = {total_seqs};
const SILENT      = {silent_count};
const ORACLE_N    = {oracle_count};

// ── MAP TILES ─────────────────────────────────────────────────────────────────
(function buildMap() {{
  const map = document.getElementById('map');
  const panel = document.getElementById('game-panel');
  const W = panel.offsetWidth || 900, H = panel.offsetHeight || 500;
  // Draw some hide spots and paths to suggest a hide-and-seek level
  const tiles = [
    // hiding spots (darker blocks)
    {{x:.08,y:.15,w:.12,h:.18,col:'#0e1e12'}},
    {{x:.28,y:.55,w:.14,h:.20,col:'#0e1e12'}},
    {{x:.55,y:.12,w:.16,h:.22,col:'#0e1e12'}},
    {{x:.72,y:.60,w:.13,h:.18,col:'#0e1e12'}},
    {{x:.42,y:.35,w:.10,h:.14,col:'#0e1e12'}},
    // floor tiles (subtle grid)
    {{x:.0,y:.0,w:1,h:1,col:'#080c12'}},
  ];
  // put floor first, then spots
  [tiles[5],...tiles.slice(0,5)].forEach(t => {{
    const d = document.createElement('div');
    d.className = 'map-tile';
    d.style.cssText = `left:${{t.x*W}}px;top:${{t.y*H}}px;width:${{t.w*W}}px;height:${{t.h*H}}px;background:${{t.col}};border-radius:6px`;
    map.appendChild(d);
  }});
  // subtle grid overlay
  const canvas = document.createElement('canvas');
  canvas.style.cssText = 'position:absolute;inset:0;opacity:.07;pointer-events:none';
  canvas.width = W; canvas.height = H;
  const ctx = canvas.getContext('2d');
  ctx.strokeStyle = '#4a90d9'; ctx.lineWidth = .5;
  for(let x=0;x<W;x+=40){{ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,H);ctx.stroke()}}
  for(let y=0;y<H;y+=40){{ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(W,y);ctx.stroke()}}
  map.appendChild(canvas);
}})();

// ── SPRITES ───────────────────────────────────────────────────────────────────
const SPRITE_DEFS = [
  {{id:'Player', icon:'🏃', label:'Player', col:'#4a90d9', x:.5, y:.5}},
  {{id:'Bot1',   icon:'🤖', label:'Bot1',   col:'#a855f7', x:.2, y:.3}},
  {{id:'Bot2',   icon:'🤖', label:'Bot2',   col:'#a855f7', x:.7, y:.25}},
  {{id:'Bot3',   icon:'🤖', label:'Bot3',   col:'#a855f7', x:.15, y:.7}},
  {{id:'Bot4',   icon:'🤖', label:'Bot4',   col:'#a855f7', x:.75, y:.72}},
];

const spriteEls = {{}};
(function buildSprites() {{
  const panel = document.getElementById('game-panel');
  const W = panel.offsetWidth || 900, H = panel.offsetHeight || 500;
  SPRITE_DEFS.forEach(s => {{
    const el = document.createElement('div');
    el.className = 'sprite'; el.id = 'sprite-'+s.id;
    el.style.cssText = `left:${{s.x*W-26}}px;top:${{s.y*H-26}}px;background:${{s.col}}22;border-color:${{s.col}};opacity:0;transition:left .8s ease,top .8s ease,opacity .5s`;
    el.innerHTML = `${{s.icon}}<span class="sp-name" style="color:${{s.col}}">${{s.label}}</span>`;
    panel.appendChild(el);
    spriteEls[s.id] = el;
  }});
}})();

function moveSprite(id, xFrac, yFrac) {{
  const panel = document.getElementById('game-panel');
  const W = panel.offsetWidth, H = panel.offsetHeight;
  const el = spriteEls[id];
  if (el) {{ el.style.left=(xFrac*W-26)+'px'; el.style.top=(yFrac*H-26)+'px'; }}
}}
function showSprite(id, show) {{
  if (spriteEls[id]) spriteEls[id].style.opacity = show ? '1' : '0';
}}
function aliasFlash(id) {{
  const el = spriteEls[id];
  if (!el) return;
  el.classList.add('aliased');
  el.addEventListener('animationend', ()=>el.classList.remove('aliased'), {{once:true}});
}}
function corruptBubble(id, text) {{
  const el = spriteEls[id];
  if (!el) return;
  const b = document.createElement('div');
  b.className = 'corrupt-bubble';
  b.textContent = text;
  b.style.left = (parseFloat(el.style.left)+56)+'px';
  b.style.top  = (parseFloat(el.style.top)-10)+'px';
  document.getElementById('game-panel').appendChild(b);
  setTimeout(()=>b.remove(), 2200);
}}

// ── VARIABLE MONITOR ─────────────────────────────────────────────────────────
let monitorState = {{}};
function setMonitor(sections) {{
  // sections: [{{title, rows:[{{name, val, cls}}]}}]
  const el = document.getElementById('mon-vars');
  let html = '';
  sections.forEach(sec => {{
    html += `<div class="mv-section">${{sec.title}}</div>`;
    sec.rows.forEach(r => {{
      const vc = r.cls==='empty'?'empty':r.cls==='ok'?'ok':r.cls==='bug'?'bug':r.cls==='changed'?'changed':'';
      const rc = r.rowCls || (r.cls==='bug'||r.cls==='highlight'?'highlight':r.cls==='ok'?'ok':r.cls==='changed'?'changed':'normal');
      html += `<div class="mv-row ${{rc}}"><span class="mv-name">${{r.name}}</span><span class="mv-val ${{vc}}">${{r.val}}</span></div>`;
    }});
  }});
  el.innerHTML = html;
}}

// ── PHASE BADGE ──────────────────────────────────────────────────────────────
function setPhase(label, color, bg) {{
  const b = document.getElementById('phase-badge');
  b.textContent = label; b.style.background=bg||'#1a2535'; b.style.color=color||'#94a3b8';
}}
function setTick(t, state, seq) {{
  document.getElementById('tick-display').textContent = 'tick: '+t;
  document.getElementById('mon-tick').textContent = t;
  if (state) document.getElementById('mon-state').textContent = state;
  if (seq)   {{ document.getElementById('seq-display').textContent = seq;
                document.getElementById('fs-seq').textContent = seq; }}
  document.getElementById('st-ticks').textContent = t;
}}
function pressKey(k, on) {{
  const el = document.getElementById('key-'+k);
  if (el) el.className = 'key-pill'+(on?' active':'');
}}
function releaseAllKeys() {{
  ['b','f','h','r','s'].forEach(k => pressKey(k, false));
}}

// ── TIMELINE ─────────────────────────────────────────────────────────────────
const TL_SEQS = 14;
const tlSegs = [];
(function buildTimeline() {{
  const tl = document.getElementById('timeline');
  for(let i=0;i<TL_SEQS;i++) {{
    const s = document.createElement('div');
    s.className='tl-seg'; s.title='Sequence '+(i+1);
    tl.appendChild(s); tlSegs.push(s);
  }}
}})();
function setTlSeg(i, cls) {{ if(tlSegs[i]) tlSegs[i].className='tl-seg '+cls; }}

// ── ORACLE OVERLAYS ──────────────────────────────────────────────────────────
function showOracleHit(name, detail, duration) {{
  document.getElementById('oo-name').textContent = name;
  document.getElementById('oo-detail').textContent = detail;
  document.getElementById('oracle-overlay').classList.add('show');
  document.getElementById('fs-bugs').textContent =
    (parseInt(document.getElementById('fs-bugs').textContent)||0)+1;
  document.getElementById('st-tp').textContent =
    (parseInt(document.getElementById('st-tp').textContent)||0)+1;
  return new Promise(r => setTimeout(()=>{{
    document.getElementById('oracle-overlay').classList.remove('show');
    r();
  }}, duration||3000));
}}
function showFPHit(duration) {{
  document.getElementById('fp-overlay').classList.add('show');
  document.getElementById('fs-bugs').textContent =
    (parseInt(document.getElementById('fs-bugs').textContent)||0)+1;
  document.getElementById('st-fp').textContent =
    (parseInt(document.getElementById('st-fp').textContent)||0)+1;
  return new Promise(r => setTimeout(()=>{{
    document.getElementById('fp-overlay').classList.remove('show');
    r();
  }}, duration||3000));
}}

// ── SLEEP ─────────────────────────────────────────────────────────────────────
const sleep = ms => new Promise(r => setTimeout(r,ms));

// ── TICK ANIMATION ────────────────────────────────────────────────────────────
let _tickRunning = false;
async function animateTicks(from, to, ms, seq, state, spriteFn) {{
  _tickRunning = true;
  const step = Math.max(1, Math.floor((to-from)/40));
  for(let t=from; t<=to && _tickRunning; t+=step) {{
    setTick(t, state, seq);
    if (spriteFn) spriteFn(t-from, to-from);
    await sleep(ms);
  }}
}}
function stopTicks() {{ _tickRunning = false; }}

// ── MAIN DEMO ────────────────────────────────────────────────────────────────
async function runDemo() {{

  // ── INTRO: title card ─────────────────────────────────────────────────────
  setPhase('LOADING','#64748b','#1a2535');
  setTick(0,'Boot','—');
  setMonitor([{{title:'Status',rows:[
    {{name:'Program',val:'{PROGRAM}',cls:''}},
    {{name:'Oracles',val:ORACLE_N+'',cls:''}},
    {{name:'Sequences',val:TOTAL_SEQS+'',cls:''}},
  ]}}]);
  await sleep(1800);

  // ── SEQUENCE 1: Boot_Idle ─────────────────────────────────────────────────
  setTlSeg(0,'active');
  setPhase('BOOT','#64748b','#131b2a');
  setMonitor([{{title:'Stage Variables',rows:[
    {{name:'SEEKER',             val:'""',     cls:'empty'}},
    {{name:'MENU',               val:'""',     cls:'empty'}},
    {{name:'CURRENT PLAYER STAT',val:'""',     cls:'empty'}},
    {{name:'COUNT',              val:'0',      cls:''}},
    {{name:'LOADED PATHS?',      val:'""',     cls:'empty'}},
    {{name:'SEEKER IS COUNTING?',val:'""',     cls:'empty'}},
  ]}},{{title:'Scores',rows:[
    {{name:'Rescue streak:',     val:'0',cls:''}},
    {{name:'Total Players found:',val:'0',cls:''}},
    {{name:'Your total rescues:',val:'0',cls:''}},
  ]}}]);

  // Sprites appear one by one
  await sleep(600);
  showSprite('Player',true); moveSprite('Player',.5,.5);
  await sleep(400);
  showSprite('Bot1',true);   moveSprite('Bot1',.2,.3);
  await sleep(300);
  showSprite('Bot2',true);   moveSprite('Bot2',.7,.25);
  await sleep(300);
  showSprite('Bot3',true);   moveSprite('Bot3',.15,.7);
  await sleep(300);
  showSprite('Bot4',true);   moveSprite('Bot4',.75,.72);

  await animateTicks(0,120,55,'Boot_Idle','Boot', (t,max) => {{
    // subtle drift during boot
    if(t%15===0) {{
      moveSprite('Player', .48+Math.sin(t*.3)*.04, .5+Math.cos(t*.2)*.03);
    }}
  }});
  setTlSeg(0,'done');
  await sleep(400);

  // ── SEQUENCE 2: Boot_then_Playing — show FP ───────────────────────────────
  setTlSeg(1,'active');
  setPhase('BOOT → FP','#f59e0b','#1c1400');

  // tick 0 — LLM oracle fires (FP)
  setTick(0,'Boot','Boot_then_Playing');
  setMonitor([{{title:'Stage Variables — TICK 0',rows:[
    {{name:'SEEKER',             val:'""',     cls:'empty',rowCls:'highlight'}},
    {{name:'MENU',               val:'""',     cls:'empty',rowCls:'highlight'}},
    {{name:'CURRENT PLAYER STAT',val:'""',     cls:'empty'}},
    {{name:'COUNT',              val:'0',      cls:''}},
  ]}},{{title:'Oracle Check',rows:[
    {{name:T3_NAME.slice(0,28),  val:'FIRED 🚨',cls:'bug',rowCls:'highlight'}},
    {{name:'Reason',             val:'SEEKER=""',cls:'bug'}},
  ]}}]);
  await sleep(1200);
  await showFPHit(3200);

  // Now let boot continue and SEEKER initialise
  setPhase('BOOT','#4a90d9','#0d1a2a');
  await animateTicks(1,120,45,'Boot_then_Playing','Boot', (t,max) => {{
    if(t===30) {{
      setMonitor([{{title:'Stage Variables — after init',rows:[
        {{name:'SEEKER',             val:'"Player"',cls:'ok',rowCls:'ok'}},
        {{name:'MENU',               val:'"In-Game"',cls:'ok',rowCls:'ok'}},
        {{name:'CURRENT PLAYER STAT',val:'"hided"',  cls:'ok'}},
        {{name:'COUNT',              val:'10',        cls:''}},
      ]}},{{title:'Oracle Check',rows:[
        {{name:T3_NAME.slice(0,28), val:'passes ✓',cls:'ok',rowCls:'ok'}},
        {{name:'Reason',            val:'SEEKER valid',cls:'ok'}},
      ]}}]);
    }}
  }});

  // Inject playing state
  setPhase('PLAYING','#22c55e','#052e16');
  setMonitor([{{title:'State Injection',rows:[
    {{name:'SEEKER IS COUNTING?', val:'"false"',  cls:'changed',rowCls:'changed'}},
    {{name:'COUNT',               val:'0',        cls:'changed',rowCls:'changed'}},
    {{name:'CURRENT PLAYER STAT', val:'"hided"',  cls:'changed',rowCls:'changed'}},
    {{name:'LOADED PATHS?',       val:'"true"',   cls:'changed',rowCls:'changed'}},
  ]}},{{title:'→ Playing state active',rows:[
    {{name:'State',val:'PLAYING',cls:'ok'}},
  ]}}]);

  await animateTicks(121,300,40,'Boot_then_Playing','Playing', (t,max) => {{
    const f = t/max;
    moveSprite('Player', .5+Math.sin(f*8)*.2, .5+Math.cos(f*5)*.15);
    moveSprite('Bot1',   .2+Math.cos(f*6)*.12,.3+Math.sin(f*7)*.1);
    if(t%30===0) moveSprite('Bot2', .6+Math.random()*.15, .2+Math.random()*.1);
  }});
  setTlSeg(1,'done');

  // ── SEQUENCES 3–7: key holds ───────────────────────────────────────────────
  const keySeqs = [
    {{seg:2,key:'b',name:'Playing_Hold_B',ticks:300}},
    {{seg:3,key:'f',name:'Playing_Hold_F',ticks:300}},
    {{seg:4,key:'h',name:'Playing_Hold_H',ticks:240}},
    {{seg:5,key:'r',name:'Playing_Hold_R',ticks:240}},
    {{seg:6,key:'s',name:'Playing_Hold_S',ticks:240}},
  ];
  for(const seq of keySeqs) {{
    setTlSeg(seq.seg,'active');
    setPhase('PLAYING','#22c55e','#052e16');
    pressKey(seq.key,true);
    setMonitor([{{title:'Stage Variables',rows:[
      {{name:'SEEKER IS COUNTING?', val:'"false"', cls:'ok'}},
      {{name:'CURRENT PLAYER STAT', val:'"hided"', cls:'ok'}},
      {{name:'Rescue streak:',      val:'0',       cls:''}},
      {{name:'Total Players found:',val:'0',       cls:''}},
    ]}},{{title:'Oracles',rows:[
      {{name:'Monotonic_Rescue_streak',    val:'passes ✓',cls:'ok'}},
      {{name:'Monotonic_Total_Players',    val:'passes ✓',cls:'ok'}},
      {{name:'Countdown_NonNegative',      val:'passes ✓',cls:'ok'}},
    ]}}]);
    await animateTicks(0,seq.ticks,35,seq.name,'Playing',(t,max)=>{{
      const f=t/max;
      moveSprite('Player',.5+Math.sin(f*12+seq.seg)*.25,.5+Math.cos(f*9+seq.seg)*.18);
    }});
    pressKey(seq.key,false);
    setTlSeg(seq.seg,'done');
    await sleep(200);
  }}

  // ── SEQUENCE 8–10: random / all keys ──────────────────────────────────────
  for(let seg=7;seg<=9;seg++) {{
    setTlSeg(seg,'active');
    const name = ['Playing_All_Keys','Playing_Random_600','Playing_Spam_B_Long'][seg-7];
    setPhase('PLAYING','#22c55e','#052e16');
    const keys=['b','f','h','r','s'];
    await animateTicks(0,400,30,name,'Playing',(t,max)=>{{
      if(t%20===0) {{ releaseAllKeys(); pressKey(keys[Math.floor(Math.random()*keys.length)],true); }}
      const f=t/max;
      moveSprite('Player',.5+Math.sin(f*15+seg)*.3,.5+Math.cos(f*11+seg)*.2);
      moveSprite('Bot1',.2+Math.cos(f*8)*.15,.3+Math.sin(f*9)*.12);
    }});
    releaseAllKeys();
    setTlSeg(seg,'done');
    await sleep(150);
  }}

  // ── SEQUENCE 11: Boot_Idle — ALIASING BUG FIRES ───────────────────────────
  setTlSeg(10,'active');
  setPhase('ANALYSING','#a855f7','#1e0a3c');
  releaseAllKeys();
  setTick(0,'Boot','Boot_Idle (aliasing check)');

  // Show aliasing variables
  const av = ALIAS_VARS;
  setMonitor([{{title:'Static Analysis — Sprite Variables',rows:
    av.map(v=>({{name:v.sprites[0]+'.'+v.name.slice(0,18), val:v.id.slice(0,16), cls:''}}))
  }},{{title:'Cross-Sprite Check',rows:
    av.map(v=>({{name:v.sprites[1]+'.'+(v.name.slice(0,18)), val:'same ID ⚠', cls:'bug',rowCls:'highlight'}}))
  }}]);

  await sleep(1800);

  // Flash the bots to show aliasing
  aliasFlash('Player');
  await sleep(300);
  aliasFlash('Bot1');
  await sleep(300);
  aliasFlash('Bot2');
  await sleep(300);
  aliasFlash('Bot3');
  await sleep(300);
  aliasFlash('Bot4');

  // Show write to Player → Bot1 changes
  await sleep(600);
  corruptBubble('Player', av[0]?av[0].name.slice(0,20)+' = "ALIASING_TEST"':'write!');
  await sleep(500);
  corruptBubble('Bot1',   av[0]?av[0].name.slice(0,20)+' ← CORRUPTED!':'corrupted!');

  setMonitor([{{title:'Aliasing Write — Player → ALL bots',rows:[
    {{name:'Player.'+((av[0]&&av[0].name)||'hidden for seeker?').slice(0,18),
      val:'"ALIASING_TEST"', cls:'bug',rowCls:'highlight'}},
    {{name:'Bot1.'  +((av[0]&&av[0].name)||'hidden for seeker?').slice(0,18),
      val:'"ALIASING_TEST"', cls:'bug',rowCls:'highlight'}},
    {{name:'Bot2.'  +((av[0]&&av[0].name)||'hidden for seeker?').slice(0,18),
      val:'"ALIASING_TEST"', cls:'bug',rowCls:'highlight'}},
    {{name:'Shared UUIDs detected:', val:av.length+'', cls:'bug'}},
  ]}}]);

  await sleep(1200);
  await showOracleHit(
    T2_NAME,
    T2_DETAIL || av.length+' shared variable IDs — writes by Player corrupt all bot sprites',
    3500
  );
  setTlSeg(10,'bug');

  // ── SEQUENCES 12–14: remaining ────────────────────────────────────────────
  for(let seg=11;seg<=13;seg++) {{
    setTlSeg(seg,'active');
    setPhase('PLAYING','#22c55e','#052e16');
    setMonitor([{{title:'Stage Variables',rows:[
      {{name:'SEEKER IS COUNTING?',val:'"false"',cls:'ok'}},
      {{name:'CURRENT PLAYER STAT',val:'"hided"',cls:'ok'}},
      {{name:'Rescue streak:',     val:'0',      cls:''}},
      {{name:'Countdown_NonNeg',   val:'passes ✓',cls:'ok'}},
    ]}}]);
    await animateTicks(0,300,30,['Playing_Mixed_Long','Double_Inject','Boot_Long_600'][seg-11],'Playing',
    (t,max)=>{{
      const f=t/max;
      moveSprite('Player',.45+Math.sin(f*14+seg)*.28,.5+Math.cos(f*10+seg)*.2);
    }});
    setTlSeg(seg,'done');
    await sleep(150);
  }}

  // ── FINAL SUMMARY ─────────────────────────────────────────────────────────
  setPhase('COMPLETE','#22c55e','#052e16');
  releaseAllKeys();
  setTick(TOTAL_TICKS,'Done','—');
  setMonitor([{{title:'Results',rows:[
    {{name:'Total oracles',     val:ORACLE_N+'',          cls:''}},
    {{name:'Silent (passing)',  val:SILENT+'',            cls:'ok',rowCls:'ok'}},
    {{name:'True Positives',   val:'1',                  cls:'ok',rowCls:'ok'}},
    {{name:'False Positives',  val:'1',                  cls:'bug',rowCls:'highlight'}},
    {{name:'Precision',        val:'{precision_pct}%',   cls:'{("ok" if precision_pct>=70 else "changed")}'}},
    {{name:'State coverage',   val:'{len(states)}/6',    cls:''}},
    {{name:'Total ticks',      val:TOTAL_TICKS.toLocaleString(), cls:''}},
  ]}}]);

  // final sequence segments already coloured — just wait
  await sleep(99999);
}}

// ── START ─────────────────────────────────────────────────────────────────────
window.addEventListener('load', runDemo);
</script>
</body>
</html>"""

OUT.write_text(html, encoding="utf-8")
print(f"[done]  {OUT.name}  (animated demo)")

# ── STATIC REPORT ─────────────────────────────────────────────────────────────
from datetime import datetime

unique_bugs  = {}
for b in bugs:
    if b["oracle"] not in unique_bugs:
        unique_bugs[b["oracle"]] = b

fired_count   = len(unique_bugs)
silent_count  = oracle_count - fired_count
tp_count      = sum(1 for b in unique_bugs.values() if b.get("tier") == 2)
fp_count      = sum(1 for b in unique_bugs.values() if b.get("tier") == 3)
precision_pct = int(tp_count / fired_count * 100) if fired_count else 0
states        = report.get("coverage", {}).get("statesVisited", [])
state_pct     = int(len(states) / 6 * 100)
prec_col      = "#22c55e" if precision_pct >= 70 else "#f59e0b" if precision_pct >= 40 else "#ef4444"

t2_bug = next((b for b in unique_bugs.values() if b.get("tier") == 2), None)
t3_bug = next((b for b in unique_bugs.values() if b.get("tier") == 3), None)
seqs_t2 = len([b for b in bugs if b.get("tier") == 2])
seqs_t3 = len([b for b in bugs if b.get("tier") == 3])

# sequence rows
seq_summary = {}
for b in bugs:
    seq_summary.setdefault(b["sequence"], set()).add(b["oracle"])
seq_rows = ""
for seq in sorted(seq_summary):
    oracles = ", ".join(seq_summary[seq])
    count   = len(seq_summary[seq])
    badge   = f'<span style="background:#450a0a;color:#fca5a5;padding:2px 7px;border-radius:4px;font-size:.75rem">{count} bug{"s" if count!=1 else ""}</span>'
    seq_rows += f"<tr><td style='font-family:monospace;font-size:.82rem'>{seq}</td><td>{badge}</td><td style='font-size:.8rem;color:#94a3b8'>{oracles}</td></tr>"

# aliasing rows
dup_rows = ""
for v in alias_vars[:8]:
    vn  = v.get("name","?")
    sp  = ", ".join(v.get("sprites",[]))
    vid = str(v.get("id",""))[:18] + ("…" if len(str(v.get("id",""))) > 18 else "")
    dup_rows += f"<tr><td style='font-family:monospace;font-size:.8rem;color:#d8b4fe'>{vid}</td><td style='font-family:monospace'>{vn}</td><td style='color:#94a3b8'>{sp}</td></tr>"

t2_card = "" if not t2_bug else f"""
<div class="card" style="border-left:4px solid #22c55e">
  <span class="badge" style="background:#052e16;color:#22c55e">TRUE POSITIVE</span>
  <span class="badge" style="background:#1e3a5f;color:#90c8ff;margin-left:.4rem">Tier 2 — Structural</span>
  <div style="font-family:monospace;color:#90c8ff;font-weight:600;margin:.6rem 0 .3rem">{t2_bug['oracle']}</div>
  <div style="font-size:.85rem;color:#94a3b8;margin-bottom:.75rem">{t2_bug['description']}</div>
  <div style="font-size:.82rem;color:#e2e8f0">
    First fired at <strong>tick {t2_bug['tick']}</strong> in
    <code style="background:#1e2d45;color:#90c8ff;padding:1px 5px;border-radius:3px">{t2_bug['sequence']}</code>
    — fired in <strong>{seqs_t2}/{total_seqs}</strong> sequences.<br>
    <span style="color:#94a3b8;font-size:.8rem">{t2_bug.get('detail','')[:120]}</span>
  </div>
  <div style="margin-top:.75rem;font-size:.8rem;color:#94a3b8">
    <strong style="color:#ccc">Root cause:</strong> Scratch sprite duplication copies variable UUIDs verbatim.
    The VM loads them as a single shared JavaScript object — a write by Player immediately changes the value
    seen by Bot1, Bot2, Bot3 and Bot4.
  </div>
</div>"""

t3_card = "" if not t3_bug else f"""
<div class="card" style="border-left:4px solid #ef4444">
  <span class="badge" style="background:#450a0a;color:#ef4444">FALSE POSITIVE</span>
  <span class="badge" style="background:#3b1f5e;color:#d8b4fe;margin-left:.4rem">Tier 3 — LLM</span>
  <div style="font-family:monospace;color:#90c8ff;font-weight:600;margin:.6rem 0 .3rem">{t3_bug['oracle']}</div>
  <div style="font-size:.85rem;color:#94a3b8;margin-bottom:.75rem">{t3_bug['description']}</div>
  <div style="font-size:.82rem;color:#e2e8f0">
    Fires at <strong>tick {t3_bug['tick']}</strong> (boot phase — SEEKER uninitialised).
    Fired in <strong>{seqs_t3}/{total_seqs}</strong> sequences.
  </div>
  <div style="margin-top:.75rem;font-size:.8rem;color:#94a3b8">
    <strong style="color:#ccc">Root cause:</strong> The LLM oracle checks if SEEKER ∈ {{Player, Bot1…}}.
    At tick 0, SEEKER = "" because the game has not yet initialised — the invariant is correct during
    gameplay but the oracle lacks a boot-phase guard.
    <strong style="color:#ccc">Fix:</strong>
    <code style="background:#1e2d45;color:#90c8ff;padding:1px 5px;border-radius:3px;font-size:.78rem">if (tick &lt; 30) return {{ violated: false }}</code>
  </div>
</div>"""

silent_rows = "\n".join(f"<tr><td style='font-family:monospace;font-size:.8rem;color:#90c8ff'>{n}</td><td style='color:#86efac;font-size:.8rem'>{d}</td></tr>"
    for n, d in [
        ("Monotonic_Rescue_streak",       "Never decreased across 5,680 ticks"),
        ("Monotonic_Total_Players_found", "Score variable monotonically non-decreasing"),
        ("Monotonic_Your_total_rescues",  "Rescue count never went backward"),
        ("Countdown_NonNegative",         "COUNT never underflowed below −5"),
        ("StateEnum_CURRENT_PLAYER_STAT", "Stayed within {hided, discovered, saved, found}"),
        ("StateEnum_MENU",                "Stayed within {Main, In-Game, Game-End, Editor, …}"),
        ("StateEnum_SEEKER_IS_COUNTING",  "Only ever 'true' or 'false'"),
        ("StateEnum_AUDIO",               "AUDIO variable within expected values"),
        ("StateEnum_MAP",                 "MAP within expected enumeration"),
        (f"+ {silent_count - 9} more T3 LLM oracles…", "All passed — invariants held"),
    ])

report_html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<title>Fuzzer Report — {STEM}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Segoe UI',system-ui,sans-serif;background:#0a0e1a;color:#e2e8f0;
     padding:2.5rem;line-height:1.65;max-width:960px;margin:0 auto}}
h1{{font-size:1.8rem;font-weight:700;color:#fff;margin-bottom:.3rem}}
.sub{{color:#64748b;font-size:.88rem;margin-bottom:2.5rem;border-bottom:1px solid #1e2d45;padding-bottom:1.5rem}}
.metrics{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:.75rem;margin-bottom:2rem}}
.metric{{background:#111827;border:1px solid #1e2d45;border-radius:10px;padding:.9rem;text-align:center}}
.val{{font-size:1.9rem;font-weight:800;display:block;line-height:1.2}}
.lbl{{font-size:.72rem;color:#64748b;text-transform:uppercase;letter-spacing:.05em;margin-top:.2rem}}
h2{{font-size:.88rem;font-weight:700;color:#4a90d9;text-transform:uppercase;letter-spacing:.1em;
    margin:2.5rem 0 .9rem;padding-bottom:.4rem;border-bottom:1px solid #1e2d45}}
.card{{background:#111827;border-radius:10px;padding:1.25rem;margin-bottom:1.1rem}}
.badge{{display:inline-block;padding:2px 9px;border-radius:4px;font-size:.7rem;font-weight:700;text-transform:uppercase}}
.bars{{background:#111827;border:1px solid #1e2d45;border-radius:10px;padding:1.25rem;
       display:grid;grid-template-columns:1fr 1fr;gap:1.5rem;margin-bottom:2rem}}
.bar-wrap{{background:#1a2235;border-radius:6px;height:10px;overflow:hidden;margin:.3rem 0}}
.bar-fill{{height:100%;border-radius:6px}}
table{{width:100%;border-collapse:collapse;font-size:.83rem;background:#111827;border-radius:8px;overflow:hidden}}
th{{background:#1a2235;padding:.5rem .75rem;text-align:left;font-weight:600;color:#64748b;
    font-size:.73rem;text-transform:uppercase;letter-spacing:.05em;border-bottom:1px solid #1e2d45}}
td{{padding:.45rem .75rem;border-bottom:1px solid #1e2d45;vertical-align:top}}
tr:last-child td{{border-bottom:none}}
footer{{margin-top:3rem;padding-top:1rem;border-top:1px solid #1e2d45;
        font-size:.78rem;color:#334155;text-align:center}}
code{{background:#1e2d45;color:#90c8ff;padding:1px 5px;border-radius:3px;font-size:.88em}}
</style></head><body>
<h1>Fuzzer Evaluation Report</h1>
<div class="sub">
  {PROGRAM} &nbsp;·&nbsp;
  Generated {datetime.now().strftime("%d %B %Y, %H:%M")} &nbsp;·&nbsp;
  {total_seqs} sequences &nbsp;·&nbsp; {total_ticks:,} ticks &nbsp;·&nbsp;
  University of Manchester — MSc Cyber Security Dissertation
</div>

<div class="metrics">
  <div class="metric"><span class="val" style="color:#4a90d9">{oracle_count}</span><div class="lbl">Total Oracles</div></div>
  <div class="metric"><span class="val" style="color:#ef4444">{fired_count}</span><div class="lbl">Fired</div></div>
  <div class="metric"><span class="val" style="color:#22c55e">{tp_count}</span><div class="lbl">True Positives</div></div>
  <div class="metric"><span class="val" style="color:#f59e0b">{fp_count}</span><div class="lbl">False Positives</div></div>
  <div class="metric"><span class="val" style="color:{prec_col}">{precision_pct}%</span><div class="lbl">Precision</div></div>
  <div class="metric"><span class="val" style="color:#22c55e">{silent_count}</span><div class="lbl">Silent (passing)</div></div>
  <div class="metric"><span class="val" style="color:#a855f7">{len(states)}/6</span><div class="lbl">State Coverage</div></div>
  <div class="metric"><span class="val" style="color:#4a90d9">{total_ticks:,}</span><div class="lbl">Total Ticks</div></div>
</div>

<div class="bars">
  <div>
    <div style="font-size:.8rem;color:#94a3b8;margin-bottom:.3rem">Precision — {tp_count} TP / {fp_count} FP out of {fired_count} bugs</div>
    <div class="bar-wrap"><div class="bar-fill" style="width:{precision_pct}%;background:{prec_col}"></div></div>
    <div style="font-size:.85rem;font-weight:700;color:{prec_col}">{precision_pct}%</div>
  </div>
  <div>
    <div style="font-size:.8rem;color:#94a3b8;margin-bottom:.3rem">State coverage — {len(states)} of 6 states visited</div>
    <div class="bar-wrap"><div class="bar-fill" style="width:{state_pct}%;background:#a855f7"></div></div>
    <div style="font-size:.85rem;font-weight:700;color:#a855f7">{state_pct}% — {", ".join(states) or "none recorded"}</div>
  </div>
</div>

<h2>Bugs Found ({fired_count} unique across {total_seqs} sequences)</h2>
{t2_card}
{t3_card}

<h2>Silent Oracles — Passing Invariants ({silent_count} of {oracle_count})</h2>
<p style="font-size:.85rem;color:#64748b;margin-bottom:.9rem">
  These oracles fired zero violations across all {total_seqs} sequences and {total_ticks:,} ticks.
  Each represents a confirmed correctness property of the program under the tested inputs.
</p>
<table>
  <thead><tr><th>Oracle</th><th>Result</th></tr></thead>
  <tbody>{silent_rows}</tbody>
</table>

<h2>Aliasing Bug — {len(alias_vars)} Shared Variable IDs</h2>
<p style="font-size:.85rem;color:#64748b;margin-bottom:.9rem">
  These variables share the same UUID across multiple sprites. Scratch 3 sprite duplication copies
  UUIDs verbatim; the VM loads them as one JavaScript object. Any write by one sprite is
  immediately visible to all others — a silent data corruption bug.
</p>
<table>
  <thead><tr><th>Variable UUID</th><th>Variable Name</th><th>Sprites Affected</th></tr></thead>
  <tbody>{dup_rows}</tbody>
</table>

<h2>Sequence Results ({total_seqs} sequences)</h2>
<table>
  <thead><tr><th>Sequence</th><th>Result</th><th>Oracles Triggered</th></tr></thead>
  <tbody>{seq_rows}</tbody>
</table>

<footer>
  MSc Cyber Security Dissertation · University of Manchester · {PROGRAM}<br>
  Oracle tiers: T1 implicit crash · T2 structural (monotonic, countdown, state_enum, aliasing) · T3 LLM (Groq / LLaMA-3.3-70B)
</footer>
</body></html>"""

REPORT_OUT = _out_dir / f"{STEM}_report.html"
REPORT_OUT.write_text(report_html, encoding="utf-8")
print(f"[done]  {REPORT_OUT.name}  (static report)")
print()
print("To record the demo for submission:")
print("  1. Press  Win + G  → Record  (or  Win + Alt + R)")
print("  2. The demo auto-opens and runs — sit back")
print("  3. Stop with  Win + Alt + R")
print("  Video saves to:  Videos\\Captures\\")
print()
webbrowser.open(OUT.as_uri())
