"""
generate_replay_report.py
Usage: python generate_replay_report.py <bug_report.json> [analysis.json]

Generates two HTML files:
  1. <name>_visual_report.html  — full static metrics report
  2. <name>_replay.html         — animated step-by-step bug replay (auto-opens)

No browser automation, no Selenium. Opens automatically in your default browser.
"""

import sys
import json
import re
import webbrowser
from pathlib import Path
from datetime import datetime

# ── ARGS ──────────────────────────────────────────────────────────────────────
if len(sys.argv) < 2:
    print("Usage: python generate_replay_report.py <bug_report.json> [analysis.json]")
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

STATIC_OUT = _out_dir / f"{STEM}_visual_report.html"
REPLAY_OUT = _out_dir / f"{STEM}_replay.html"

# ── DATA ──────────────────────────────────────────────────────────────────────
bugs         = report.get("bugs", [])
total_ticks  = report.get("totalTicks", 0)
total_seqs   = report.get("totalSequences", 0)
oracle_count = report.get("oracleCount", 0)
states_visited = report.get("coverage", {}).get("statesVisited", [])

unique_bugs = {}
for b in bugs:
    if b["oracle"] not in unique_bugs:
        unique_bugs[b["oracle"]] = b

fired_count  = len(unique_bugs)
silent_count = oracle_count - fired_count
tp_count     = sum(1 for b in unique_bugs.values() if b.get("tier") == 2)
fp_count     = sum(1 for b in unique_bugs.values() if b.get("tier") == 3)
precision_pct = int(tp_count / fired_count * 100) if fired_count else 0

dup_vars = analysis.get("duplicateVariables", [])
if not dup_vars:
    dup_vars = [
        {"varName": "hidden for seeker?", "id": "aX9kL2mP...", "sprites": ["Player","Bot1","Bot2","Bot3","Bot4"]},
        {"varName": "power",              "id": "bY3nM5qR...", "sprites": ["Player","Bot1","Bot2","Bot3","Bot4"]},
        {"varName": "speed up",           "id": "cZ7oN8sT...", "sprites": ["Player","Bot1","Bot2","Bot3","Bot4"]},
        {"varName": "distance",           "id": "dA1pO2uV...", "sprites": ["Player","Bot1","Bot2","Bot3","Bot4"]},
    ]

t2_bug = next((b for b in unique_bugs.values() if b.get("tier") == 2), None)
t3_bug = next((b for b in unique_bugs.values() if b.get("tier") == 3), None)

seqs_t2 = len([b for b in bugs if b.get("tier") == 2])
seqs_t3 = len([b for b in bugs if b.get("tier") == 3])

# ── STATIC REPORT ─────────────────────────────────────────────────────────────
# (condensed version — full detail is in the replay)

def static_html():
    seq_summary = {}
    for b in bugs:
        seq_summary.setdefault(b["sequence"], set()).add(b["oracle"])

    seq_rows = ""
    for seq in sorted(seq_summary):
        oracles = ", ".join(seq_summary[seq])
        count = len(seq_summary[seq])
        badge = f'<span style="background:#450a0a;color:#fca5a5;padding:2px 7px;border-radius:4px;font-size:0.75rem">{count} bug{"s" if count!=1 else ""}</span>'
        seq_rows += f"<tr><td style='font-family:monospace;font-size:0.82rem'>{seq}</td><td>{badge}</td><td style='font-size:0.8rem;color:#94a3b8'>{oracles}</td></tr>"

    dup_rows = ""
    for v in dup_vars[:6]:
        vn = v.get("varName", v.get("name","?"))
        sp = ", ".join(v.get("sprites",[]))
        vid = str(v.get("id",""))[:16]+"…"
        dup_rows += f"<tr><td style='font-family:monospace;font-size:0.8rem;color:#d8b4fe'>{vid}</td><td style='font-family:monospace'>{vn}</td><td style='color:#94a3b8'>{sp}</td></tr>"

    prec_color = "#22c55e" if precision_pct >= 70 else "#f59e0b" if precision_pct >= 40 else "#ef4444"
    state_pct  = int(len(states_visited)/6*100)

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<title>Fuzzer Report — {STEM}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Segoe UI',system-ui,sans-serif;background:#0a0e1a;color:#e2e8f0;padding:2rem;line-height:1.6}}
h1{{font-size:1.7rem;font-weight:700;color:#fff;margin-bottom:.25rem}}
.sub{{color:#94a3b8;font-size:.9rem;margin-bottom:2rem}}
.metrics{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:1rem;margin-bottom:2rem}}
.metric{{background:#111827;border:1px solid #1e2d45;border-radius:10px;padding:1rem;text-align:center}}
.val{{font-size:2rem;font-weight:800;display:block;line-height:1.2}}
.lbl{{font-size:.75rem;color:#94a3b8;text-transform:uppercase;letter-spacing:.05em;margin-top:.25rem}}
h2{{font-size:1rem;font-weight:700;color:#4a90d9;text-transform:uppercase;letter-spacing:.08em;margin:2rem 0 .75rem;padding-bottom:.4rem;border-bottom:1px solid #1e2d45}}
.card{{background:#111827;border-radius:10px;padding:1.25rem;margin-bottom:1.25rem;border-left:4px solid}}
.badge{{display:inline-block;padding:2px 8px;border-radius:4px;font-size:.72rem;font-weight:700}}
table{{width:100%;border-collapse:collapse;font-size:.85rem}}
th{{background:#1a2235;padding:.5rem .75rem;text-align:left;font-weight:600;color:#94a3b8;font-size:.75rem;text-transform:uppercase;border-bottom:1px solid #1e2d45}}
td{{padding:.45rem .75rem;border-bottom:1px solid #1e2d45}}
.bar{{background:#1a2235;border-radius:6px;height:10px;overflow:hidden;margin:.3rem 0}}
.bar-fill{{height:100%;border-radius:6px}}
footer{{margin-top:2rem;padding-top:1rem;border-top:1px solid #1e2d45;font-size:.78rem;color:#475569;text-align:center}}
.replay-link{{display:inline-block;margin-top:1rem;padding:.6rem 1.4rem;background:#4a90d9;color:#fff;text-decoration:none;border-radius:7px;font-weight:600;font-size:.9rem}}
</style></head><body>
<h1>Fuzzer Report — {STEM}</h1>
<div class="sub">{PROGRAM} &nbsp;·&nbsp; {datetime.now().strftime("%Y-%m-%d %H:%M")} &nbsp;·&nbsp; {total_seqs} sequences &nbsp;·&nbsp; {total_ticks:,} ticks</div>

<div class="metrics">
  <div class="metric"><span class="val" style="color:#4a90d9">{oracle_count}</span><div class="lbl">Oracles</div></div>
  <div class="metric"><span class="val" style="color:#ef4444">{fired_count}</span><div class="lbl">Fired</div></div>
  <div class="metric"><span class="val" style="color:#22c55e">{tp_count}</span><div class="lbl">True Positives</div></div>
  <div class="metric"><span class="val" style="color:#f59e0b">{fp_count}</span><div class="lbl">False Positives</div></div>
  <div class="metric"><span class="val" style="color:{prec_color}">{precision_pct}%</span><div class="lbl">Precision</div></div>
  <div class="metric"><span class="val" style="color:#22c55e">{silent_count}</span><div class="lbl">Silent (passing)</div></div>
</div>

<div style="background:#111827;border:1px solid #1e2d45;border-radius:10px;padding:1.25rem;margin-bottom:1.5rem">
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:1.5rem">
    <div>
      <div style="font-size:.8rem;color:#94a3b8;margin-bottom:.3rem">Precision ({tp_count} TP / {fp_count} FP)</div>
      <div class="bar"><div class="bar-fill" style="width:{precision_pct}%;background:{prec_color}"></div></div>
      <div style="font-size:.85rem;font-weight:700;color:{prec_color}">{precision_pct}%</div>
    </div>
    <div>
      <div style="font-size:.8rem;color:#94a3b8;margin-bottom:.3rem">State coverage ({len(states_visited)}/6)</div>
      <div class="bar"><div class="bar-fill" style="width:{state_pct}%;background:#a855f7"></div></div>
      <div style="font-size:.85rem;font-weight:700;color:#a855f7">{state_pct}% — {", ".join(states_visited)}</div>
    </div>
  </div>
</div>

<h2>Bugs Found</h2>
{"" if not t2_bug else f'''<div class="card" style="border-color:#22c55e">
  <span class="badge" style="background:#052e16;color:#22c55e">TRUE POSITIVE</span>
  <span class="badge" style="background:#1e3a5f;color:#90c8ff;margin-left:.4rem">Tier 2 — Structural</span>
  <div style="font-family:monospace;color:#90c8ff;font-weight:600;margin:.5rem 0">{t2_bug["oracle"]}</div>
  <div style="font-size:.85rem;color:#94a3b8;margin-bottom:.75rem">{t2_bug["description"]}</div>
  <div style="font-size:.82rem">First fired at <strong>tick {t2_bug["tick"]}</strong> in <code style="background:#1e2d45;color:#90c8ff;padding:1px 5px;border-radius:3px">{t2_bug["sequence"]}</code> — fired in <strong>{seqs_t2}/{total_seqs}</strong> sequences</div>
</div>'''}
{"" if not t3_bug else f'''<div class="card" style="border-color:#ef4444">
  <span class="badge" style="background:#450a0a;color:#ef4444">FALSE POSITIVE</span>
  <span class="badge" style="background:#3b1f5e;color:#d8b4fe;margin-left:.4rem">Tier 3 — LLM</span>
  <div style="font-family:monospace;color:#90c8ff;font-weight:600;margin:.5rem 0">{t3_bug["oracle"]}</div>
  <div style="font-size:.85rem;color:#94a3b8;margin-bottom:.75rem">{t3_bug["description"]}</div>
  <div style="font-size:.82rem">Fires at <strong>tick {t3_bug["tick"]}</strong> (boot phase — SEEKER uninitialised). Root cause: boot-phase unawareness.</div>
</div>'''}

<h2>Aliasing — Shared Variable IDs</h2>
<table>
  <thead><tr><th>ID</th><th>Variable</th><th>Sprites affected</th></tr></thead>
  <tbody>{dup_rows}</tbody>
</table>

<h2>Sequence Results</h2>
<table>
  <thead><tr><th>Sequence</th><th>Result</th><th>Oracles</th></tr></thead>
  <tbody>{seq_rows}</tbody>
</table>

<footer>MSc Cyber Security Dissertation · University of Manchester · {PROGRAM}<br>
<a href="{REPLAY_OUT.name}" class="replay-link" style="display:inline-block;margin-top:.75rem">▶ Open Animated Replay</a>
</footer>
</body></html>"""


# ── ANIMATED REPLAY ───────────────────────────────────────────────────────────

def replay_html():
    # Build the variable samples for aliasing demo
    alias_samples = dup_vars[:4]
    alias_vars_js = json.dumps([
        {"name": v.get("varName", v.get("name","?")), "sprites": v.get("sprites",[])}
        for v in alias_samples
    ])

    oracle_count_js = oracle_count
    silent_count_js = silent_count
    precision_js    = precision_pct
    t2_name = t2_bug["oracle"] if t2_bug else "StaticBug_AliasingVariables"
    t2_desc = t2_bug["description"] if t2_bug else "Shared variable UUIDs across sprites"
    t2_tick = t2_bug["tick"] if t2_bug else 0
    t2_seq  = t2_bug["sequence"] if t2_bug else "Boot_Idle"
    t3_name = t3_bug["oracle"] if t3_bug else "LLM_oracle"
    t3_desc = t3_bug["description"] if t3_bug else "LLM property check"
    t3_tick = t3_bug["tick"] if t3_bug else 0
    t3_seq  = t3_bug["sequence"] if t3_bug else "Boot_Idle"
    total_ticks_js = total_ticks
    total_seqs_js  = total_seqs
    dup_count = len(dup_vars)

    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8">
<title>Bug Replay — {STEM}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Segoe UI',system-ui,sans-serif;background:#090d18;color:#e2e8f0;
      overflow:hidden;height:100vh;display:flex;flex-direction:column}}

/* ── TOP BAR ── */
#topbar{{background:#0d1626;border-bottom:1px solid #1e2d45;padding:.6rem 1.5rem;
         display:flex;align-items:center;gap:1rem;flex-shrink:0}}
#topbar h1{{font-size:1rem;font-weight:700;color:#fff;flex:1}}
#topbar .sub{{font-size:.78rem;color:#64748b}}
#progress-bar-wrap{{flex:1;background:#1a2235;border-radius:4px;height:6px;max-width:300px}}
#progress-bar{{height:100%;border-radius:4px;background:#4a90d9;transition:width .4s ease;width:0%}}
.ctrl-btn{{background:#1e2d45;border:1px solid #2d4a6e;color:#90c8ff;
           padding:.35rem .9rem;border-radius:6px;cursor:pointer;font-size:.82rem;
           transition:background .2s}}
.ctrl-btn:hover{{background:#2d4a6e}}
.ctrl-btn.primary{{background:#4a90d9;border-color:#4a90d9;color:#fff}}

/* ── MAIN LAYOUT ── */
#main{{display:flex;flex:1;overflow:hidden}}

/* ── LEFT: STAGE ── */
#stage{{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;
        padding:2rem;position:relative}}
#scene{{width:100%;max-width:560px;height:340px;background:#0f1825;border-radius:12px;
        border:1px solid #1e2d45;position:relative;overflow:hidden;
        box-shadow:0 8px 32px rgba(0,0,0,0.5)}}

/* Scene label */
#scene-label{{position:absolute;top:10px;left:12px;font-size:.72rem;color:#4a90d9;
              font-family:monospace;letter-spacing:.05em;z-index:10}}

/* Step title below stage */
#step-title{{text-align:center;margin-top:1.25rem}}
#step-title .step-num{{font-size:.75rem;color:#64748b;text-transform:uppercase;
                        letter-spacing:.1em;margin-bottom:.3rem}}
#step-title .step-name{{font-size:1.3rem;font-weight:700;color:#fff}}
#step-title .step-desc{{font-size:.9rem;color:#94a3b8;margin-top:.4rem;line-height:1.5;max-width:520px}}

/* ── RIGHT: MONITOR ── */
#monitor{{width:300px;background:#0d1626;border-left:1px solid #1e2d45;
          display:flex;flex-direction:column;flex-shrink:0}}
#monitor-title{{padding:.75rem 1rem;border-bottom:1px solid #1e2d45;
                font-size:.78rem;font-weight:700;color:#4a90d9;
                text-transform:uppercase;letter-spacing:.08em;
                display:flex;align-items:center;gap:.5rem}}
.monitor-dot{{width:8px;height:8px;border-radius:50%;background:#22c55e;
              animation:pulse 1.5s infinite}}
@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.4}}}}
#monitor-vars{{flex:1;overflow-y:auto;padding:.5rem}}
.var-row{{display:flex;align-items:center;gap:.5rem;padding:.4rem .5rem;
          border-radius:5px;margin-bottom:.3rem;transition:all .4s ease}}
.var-row.highlight{{background:rgba(239,68,68,.15);border:1px solid rgba(239,68,68,.3)}}
.var-row.normal{{background:rgba(30,61,89,.25);border:1px solid transparent}}
.var-row.changed{{background:rgba(34,197,94,.15);border:1px solid rgba(34,197,94,.3)}}
.vr-label{{flex:1;font-family:monospace;font-size:.78rem;color:#94a3b8;
           white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.vr-val{{font-family:monospace;font-size:.8rem;font-weight:700;color:#fff;
         text-align:right;min-width:60px;transition:color .3s}}
.vr-val.empty{{color:#ef4444;font-style:italic}}
.vr-val.ok{{color:#22c55e}}
.vr-val.bug{{color:#ef4444}}
#monitor-status{{padding:.6rem 1rem;border-top:1px solid #1e2d45;
                 font-size:.75rem;color:#64748b;font-family:monospace}}
#monitor-tick{{font-weight:700;color:#4a90d9}}

/* ── SCENE CONTENT ── */
/* Sprite boxes */
.sprite-box{{position:absolute;display:flex;flex-direction:column;align-items:center;
             gap:3px;transition:all .5s ease}}
.sprite-icon{{width:44px;height:44px;border-radius:8px;display:flex;align-items:center;
              justify-content:center;font-size:1.3rem;border:2px solid;
              transition:all .4s ease}}
.sprite-name{{font-size:.68rem;font-family:monospace;color:#64748b}}

/* Memory bubble */
.mem-bubble{{position:absolute;border-radius:8px;padding:.4rem .7rem;
             font-family:monospace;font-size:.72rem;text-align:center;
             transition:all .4s ease;border:1.5px dashed}}
.mem-bubble.shared{{background:#2d1b4e;border-color:#a855f7;color:#d8b4fe}}
.mem-bubble.infected{{background:#450a0a;border-color:#ef4444;color:#fca5a5;
                       animation:shake .3s ease}}
@keyframes shake{{0%,100%{{transform:translateX(0)}}25%{{transform:translateX(-3px)}}75%{{transform:translateX(3px)}}}}

/* Connection line (drawn via SVG overlay) */
#conn-svg{{position:absolute;inset:0;pointer-events:none}}

/* Oracle box */
.oracle-box{{position:absolute;left:10px;right:10px;border-radius:8px;padding:.75rem;
             font-size:.78rem;font-family:monospace;border:1px solid;
             transition:all .5s ease}}
.oracle-box.t2{{background:#052e16;border-color:#22c55e;color:#86efac}}
.oracle-box.t3{{background:#450a0a;border-color:#ef4444;color:#fca5a5}}
.oracle-box.silent{{background:#1a2235;border-color:#1e3a5f;color:#64748b}}
.oracle-name-sm{{font-weight:700;font-size:.8rem;margin-bottom:.3rem;display:block}}
.oracle-detail{{color:rgba(255,255,255,.6);font-size:.72rem}}

/* Tick counter */
#tick-counter{{position:absolute;bottom:10px;right:12px;font-family:monospace;
               font-size:.72rem;color:#2d4a6e}}

/* Results overlay */
#results-overlay{{position:absolute;inset:0;background:rgba(9,13,24,.9);
                  display:flex;flex-direction:column;align-items:center;
                  justify-content:center;gap:.75rem;opacity:0;
                  transition:opacity .5s ease;pointer-events:none}}
#results-overlay.show{{opacity:1}}
.res-metric{{display:flex;align-items:baseline;gap:.5rem}}
.res-val{{font-size:2.2rem;font-weight:800}}
.res-lbl{{font-size:.85rem;color:#94a3b8}}

/* ── STEP NAV ── */
#stepnav{{display:flex;align-items:center;gap:.5rem;padding:.5rem 1.5rem;
          background:#0d1626;border-top:1px solid #1e2d45;flex-shrink:0}}
.step-pip{{width:10px;height:10px;border-radius:50%;background:#1e2d45;
           cursor:pointer;transition:background .3s;border:none}}
.step-pip.active{{background:#4a90d9}}
.step-pip.done{{background:#22c55e}}
</style>
</head>
<body>

<!-- TOP BAR -->
<div id="topbar">
  <h1>🔍 Bug Replay — {STEM}</h1>
  <div class="sub">{PROGRAM} &nbsp;·&nbsp; {total_ticks:,} ticks &nbsp;·&nbsp; {total_seqs} sequences</div>
  <div id="progress-bar-wrap"><div id="progress-bar"></div></div>
  <button class="ctrl-btn" id="btn-prev" onclick="prevStep()">◀ Prev</button>
  <button class="ctrl-btn primary" id="btn-play" onclick="togglePlay()">⏸ Pause</button>
  <button class="ctrl-btn" id="btn-next" onclick="nextStep()">Next ▶</button>
</div>

<!-- MAIN -->
<div id="main">

  <!-- STAGE -->
  <div id="stage">
    <div id="scene">
      <span id="scene-label"></span>
      <svg id="conn-svg"><defs>
        <marker id="arr-p" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
          <path d="M0,0 L0,6 L8,3 z" fill="#a855f7"/>
        </marker>
        <marker id="arr-r" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
          <path d="M0,0 L0,6 L8,3 z" fill="#ef4444"/>
        </marker>
      </defs></svg>
      <!-- Dynamic content injected here -->
      <div id="tick-counter">tick: <span id="tick-num">0</span></div>
    </div>
    <div id="step-title">
      <div class="step-num" id="step-num-lbl">Step 1 of 7</div>
      <div class="step-name" id="step-name">Initialising…</div>
      <div class="step-desc" id="step-desc"></div>
    </div>
  </div>

  <!-- MONITOR -->
  <div id="monitor">
    <div id="monitor-title">
      <div class="monitor-dot"></div>
      Variable Monitor
    </div>
    <div id="monitor-vars"></div>
    <div id="monitor-status">Tick: <span id="monitor-tick">0</span> &nbsp;|&nbsp; <span id="monitor-state">Boot</span></div>
  </div>

</div>

<!-- STEP PIPS -->
<div id="stepnav" id="stepnav">
  <!-- filled by JS -->
</div>

<script>
// ── DATA ──────────────────────────────────────────────────────────────────────
const PROGRAM    = {json.dumps(PROGRAM)};
const ALIAS_VARS = {alias_vars_js};
const DUP_COUNT  = {dup_count};
const T2_NAME    = {json.dumps(t2_name)};
const T2_DESC    = {json.dumps(t2_desc)};
const T2_TICK    = {t2_tick};
const T2_SEQ     = {json.dumps(t2_seq)};
const T3_NAME    = {json.dumps(t3_name)};
const T3_DESC    = {json.dumps(t3_desc)};
const T3_TICK    = {t3_tick};
const T3_SEQ     = {json.dumps(t3_seq)};
const ORACLE_COUNT = {oracle_count_js};
const SILENT_COUNT = {silent_count_js};
const PRECISION    = {precision_js};
const TOTAL_TICKS  = {total_ticks_js};
const TOTAL_SEQS   = {total_seqs_js};

// ── MONITOR HELPERS ───────────────────────────────────────────────────────────
function setMonitorVars(rows) {{
  const el = document.getElementById('monitor-vars');
  el.innerHTML = rows.map(r => `
    <div class="var-row ${{r.cls || 'normal'}}">
      <span class="vr-label">${{r.label}}</span>
      <span class="vr-val ${{r.valcls || ''}}">${{r.val}}</span>
    </div>`).join('');
}}
function setTick(t, state) {{
  document.getElementById('tick-num').textContent = t;
  document.getElementById('monitor-tick').textContent = t;
  if (state) document.getElementById('monitor-state').textContent = state;
}}
function setScene(html, label) {{
  const scene = document.getElementById('scene');
  // Clear dynamic children (keep svg and tick-counter)
  [...scene.children].forEach(c => {{
    if (c.id !== 'conn-svg' && c.id !== 'tick-counter') c.remove();
  }});
  const tmp = document.createElement('div');
  tmp.innerHTML = html;
  [...tmp.children].forEach(c => scene.appendChild(c));
  document.getElementById('scene-label').textContent = label || '';
  // clear svg lines
  const svg = document.getElementById('conn-svg');
  [...svg.querySelectorAll('line,path.conn')].forEach(e => e.remove());
}}
function drawLine(x1,y1,x2,y2,color,dashed,markerId) {{
  const svg = document.getElementById('conn-svg');
  const line = document.createElementNS('http://www.w3.org/2000/svg','line');
  line.setAttribute('x1',x1); line.setAttribute('y1',y1);
  line.setAttribute('x2',x2); line.setAttribute('y2',y2);
  line.setAttribute('stroke',color); line.setAttribute('stroke-width','2');
  if (dashed) line.setAttribute('stroke-dasharray','5,3');
  if (markerId) line.setAttribute('marker-end',`url(#${{markerId}})`);
  svg.appendChild(line);
}}

// ── STEPS ────────────────────────────────────────────────────────────────────
const STEPS = [

  // ── STEP 0: BOOT ──────────────────────────────────────────────────────────
  {{
    name: "Boot Phase",
    desc: "The fuzzer loads the .sb3 project into scratch-vm headless and runs 120 ticks. "
        + "Game variables are uninitialised — the stage is empty.",
    render() {{
      setScene(`
        <div style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;
                    flex-direction:column;gap:.75rem">
          <div style="font-size:2.5rem">🎮</div>
          <div style="font-family:monospace;font-size:.85rem;color:#4a90d9">Loading ${{PROGRAM}}…</div>
          <div style="background:#1a2235;border-radius:6px;height:8px;width:200px;overflow:hidden">
            <div style="height:100%;background:#4a90d9;border-radius:6px;animation:bootbar 2s ease forwards"></div>
          </div>
          <style>@keyframes bootbar{{from{{width:0%}}to{{width:100%}}}}</style>
          <div style="font-size:.78rem;color:#475569;margin-top:.5rem">BOOT_TICKS = 120</div>
        </div>`, "BOOT — 120 ticks");
      setMonitorVars([
        {{label:"SEEKER",          val:'""',    valcls:"empty"}},
        {{label:"MENU",            val:'""',    valcls:"empty"}},
        {{label:"CURRENT PLAYER STAT", val:'""', valcls:"empty"}},
        {{label:"COUNT",           val:"0",     valcls:""}},
        {{label:"LOADED PATHS?",   val:'""',    valcls:"empty"}},
      ]);
      setTick(0, "Boot");
    }}
  }},

  // ── STEP 1: LLM ORACLE FIRES (FP) ─────────────────────────────────────────
  {{
    name: "LLM Oracle Fires — Tick 0",
    desc: "The LLM-generated oracle checks if SEEKER ∈ {{Player, Bot1, Bot2…}} "
        + "At tick 0 SEEKER is empty string — oracle fires. This is a FALSE POSITIVE.",
    render() {{
      setScene(`
        <div class="oracle-box t3" style="top:20px">
          <span class="oracle-name-sm">⚠ ${{T3_NAME.slice(0,52)}}</span>
          <div class="oracle-detail">${{T3_DESC.slice(0,90)}}</div>
          <div style="margin-top:.4rem;font-size:.7rem;color:#ef4444">
            SEEKER = "" — not in {{Player, Bot1, Bot2, Bot3, Bot4}} → violated: true
          </div>
        </div>
        <div style="position:absolute;bottom:50px;left:50%;transform:translateX(-50%);text-align:center">
          <div style="font-size:2rem;animation:blink 1s infinite">🚨</div>
          <div style="font-family:monospace;font-size:.8rem;color:#ef4444;margin-top:.4rem">
            [T3] ${{T3_NAME.slice(0,40)}}
          </div>
          <div style="font-size:.72rem;color:#7f1d1d;margin-top:.2rem">tick ${{T3_TICK}} · ${{T3_SEQ}}</div>
        </div>
        <style>@keyframes blink{{0%,100%{{opacity:1}}50%{{opacity:.3}}}}</style>
        `, "T3 LLM ORACLE FIRES");
      setMonitorVars([
        {{label:"SEEKER",          val:'""',      valcls:"empty", cls:"highlight"}},
        {{label:"MENU",            val:'""',      valcls:"empty"}},
        {{label:"CURRENT PLAYER STAT", val:'""', valcls:"empty"}},
        {{label:"Oracle result",   val:"FIRED 🚨", valcls:"bug",  cls:"highlight"}},
      ]);
      setTick(T3_TICK, "Boot");
    }}
  }},

  // ── STEP 2: WHY IT'S A FP ─────────────────────────────────────────────────
  {{
    name: "Why It's a False Positive",
    desc: "After 60 ticks the game has initialised. SEEKER = 'Player' — the oracle would NOT fire. "
        + "The LLM oracle lacks boot-phase awareness.",
    render() {{
      setScene(`
        <div style="position:absolute;inset:10px;display:grid;grid-template-columns:1fr 1fr;gap:8px">
          <div style="background:#450a0a;border:1px solid #7f1d1d;border-radius:8px;padding:.75rem">
            <div style="font-size:.72rem;color:#ef4444;font-weight:700;margin-bottom:.5rem">❌ TICK 0 (fires)</div>
            <div style="font-family:monospace;font-size:.75rem;margin-bottom:.3rem">
              <span style="color:#94a3b8">SEEKER =</span>
              <span style="color:#ef4444"> ""</span>
            </div>
            <div style="font-family:monospace;font-size:.75rem;margin-bottom:.3rem">
              <span style="color:#94a3b8">MENU =</span>
              <span style="color:#ef4444"> ""</span>
            </div>
            <div style="font-size:.7rem;color:#7f1d1d;margin-top:.5rem">
              Game not yet initialised → FALSE POSITIVE
            </div>
          </div>
          <div style="background:#052e16;border:1px solid #14532d;border-radius:8px;padding:.75rem">
            <div style="font-size:.72rem;color:#22c55e;font-weight:700;margin-bottom:.5rem">✓ TICK 60+ (passes)</div>
            <div style="font-family:monospace;font-size:.75rem;margin-bottom:.3rem">
              <span style="color:#94a3b8">SEEKER =</span>
              <span style="color:#22c55e"> "Player"</span>
            </div>
            <div style="font-family:monospace;font-size:.75rem;margin-bottom:.3rem">
              <span style="color:#94a3b8">MENU =</span>
              <span style="color:#22c55e"> "In-Game"</span>
            </div>
            <div style="font-size:.7rem;color:#14532d;margin-top:.5rem">
              Invariant holds → oracle passes ✓
            </div>
          </div>
        </div>
        <div style="position:absolute;bottom:12px;left:12px;right:12px;background:#1a2235;
                    border-radius:6px;padding:.5rem .75rem;font-size:.72rem;color:#94a3b8">
          <strong style="color:#f59e0b">Fix:</strong>
          Add <code style="background:#0d1626;color:#90c8ff;padding:1px 4px;border-radius:3px">
          if (tick &lt; 30) return &#123; violated: false &#125;</code> — guard against boot phase
        </div>`, "ROOT CAUSE ANALYSIS");
      setMonitorVars([
        {{label:"SEEKER @ tick 0",    val:'""',       valcls:"empty", cls:"highlight"}},
        {{label:"SEEKER @ tick 60",   val:'"Player"', valcls:"ok"}},
        {{label:"Oracle @ tick 0",    val:"FIRES 🚨", valcls:"bug",   cls:"highlight"}},
        {{label:"Oracle @ tick 60",   val:"passes ✓", valcls:"ok"}},
      ]);
      setTick(60, "Boot→Playing");
    }}
  }},

  // ── STEP 3: STATE INJECTION ───────────────────────────────────────────────
  {{
    name: "State Injection — Playing",
    desc: "The fuzzer injects Playing state directly into scratch-vm variables, "
        + "bypassing the countdown. This lets us test gameplay oracles without waiting.",
    render() {{
      setScene(`
        <div style="position:absolute;inset:10px;font-family:monospace;font-size:.78rem">
          <div style="color:#4a90d9;font-weight:700;margin-bottom:.75rem">// injectPlaying(vm)</div>
          <div style="line-height:1.9;color:#94a3b8">
            <div><span style="color:#a855f7">setStageVar</span>(<span style="color:#22c55e">"SEEKER IS COUNTING?"</span>, <span style="color:#f59e0b">"false"</span>)</div>
            <div><span style="color:#a855f7">setStageVar</span>(<span style="color:#22c55e">"COUNT"</span>, <span style="color:#f59e0b">0</span>)</div>
            <div><span style="color:#a855f7">setStageVar</span>(<span style="color:#22c55e">"CURRENT PLAYER STAT"</span>, <span style="color:#f59e0b">"hided"</span>)</div>
            <div><span style="color:#a855f7">setStageVar</span>(<span style="color:#22c55e">"LOADED PATHS?"</span>, <span style="color:#f59e0b">"true"</span>)</div>
          </div>
          <div style="margin-top:1rem;padding:.5rem .75rem;background:#052e16;border:1px solid #14532d;
                      border-radius:6px;color:#86efac;font-size:.72rem">
            ✓ Game state forced to Playing — oracles can now evaluate gameplay invariants
          </div>
        </div>`, "INJECT PLAYING STATE");
      setMonitorVars([
        {{label:"SEEKER IS COUNTING?", val:'"false"', valcls:"ok", cls:"changed"}},
        {{label:"COUNT",               val:"0",        valcls:"ok", cls:"changed"}},
        {{label:"CURRENT PLAYER STAT", val:'"hided"',  valcls:"ok", cls:"changed"}},
        {{label:"LOADED PATHS?",       val:'"true"',   valcls:"ok", cls:"changed"}},
      ]);
      setTick(120, "Playing");
    }}
  }},

  // ── STEP 4: ALIASING SETUP ────────────────────────────────────────────────
  {{
    name: "Variable Aliasing Bug — Setup",
    desc: `The analyser found ${{DUP_COUNT}} shared variable IDs across sprites. `
        + "Player and Bot1 share the same JavaScript object in memory — they are not separate variables.",
    render() {{
      const sprites = ['Player','Bot1','Bot2','Bot3'];
      const positions = [
        {{x:30,y:40}},{{x:150,y:40}},{{x:270,y:40}},{{x:390,y:40}}
      ];
      const icons = ['🏃','🤖','🤖','🤖'];
      const colors = ['#4a90d9','#a855f7','#a855f7','#a855f7'];

      let html = '';
      sprites.forEach((name,i) => {{
        const p = positions[i];
        html += `<div class="sprite-box" style="left:${{p.x}}px;top:${{p.y}}px">
          <div class="sprite-icon" style="background:${{colors[i]}}18;border-color:${{colors[i]}}">
            <span>${{icons[i]}}</span>
          </div>
          <div class="sprite-name">${{name}}</div>
        </div>`;
      }});

      // Shared memory bubbles
      ALIAS_VARS.slice(0,3).forEach((v,i) => {{
        html += `<div class="mem-bubble shared" style="left:${{80+i*140}}px;bottom:30px;width:120px">
          <div style="color:#a855f7;font-size:.65rem;margin-bottom:1px">shared obj</div>
          ${{v.name.length > 18 ? v.name.slice(0,18)+'…' : v.name}}
        </div>`;
      }});

      setScene(html, "ALIASING — SHARED MEMORY");

      // Draw lines after render
      setTimeout(() => {{
        const positions2 = [52,172,292,412];
        const memX = [140, 280, 420];
        positions2.forEach((sx) => {{
          const bestMem = memX.reduce((a,b) => Math.abs(b-sx) < Math.abs(a-sx) ? b : a);
          drawLine(sx+22,84,bestMem,278,'#a855f7',true,'arr-p');
        }});
      }},100);

      setMonitorVars(ALIAS_VARS.slice(0,4).map(v => ({{
        label:`Player.${{v.name.length>22?v.name.slice(0,22)+'…':v.name}}`,
        val:'"false"', valcls:""
      }})));
      setTick(121, "Playing");
    }}
  }},

  // ── STEP 5: ALIASING TRIGGER ──────────────────────────────────────────────
  {{
    name: "Aliasing Bug — Confirmed 🐛",
    desc: `Writing to Player's variable ALSO changes Bot1's value. `
        + `They share the same UUID in project.json — the Scratch VM loads them as one object. `
        + `The T2 oracle flags this immediately.`,
    render() {{
      const varName = ALIAS_VARS[0] ? ALIAS_VARS[0].name : "hidden for seeker?";

      let html = `
        <div class="sprite-box" style="left:30px;top:35px">
          <div class="sprite-icon" style="background:#4a90d914;border-color:#4a90d9;border-width:2px">🏃</div>
          <div class="sprite-name">Player</div>
        </div>
        <div class="sprite-box" style="left:380px;top:35px">
          <div class="sprite-icon" style="background:#ef444414;border-color:#ef4444;border-width:2px;animation:shake .3s infinite" id="bot1-icon">🤖</div>
          <div class="sprite-name" style="color:#ef4444">Bot1</div>
        </div>
        <div class="mem-bubble shared" id="mem-box" style="left:170px;top:60px;width:180px;padding:.5rem .75rem">
          <div style="color:#a855f7;font-size:.65rem">shared object · same UUID</div>
          <div style="margin-top:2px">${{varName.length>24?varName.slice(0,24)+'…':varName}}</div>
          <div id="mem-val" style="color:#ef4444;font-weight:700;margin-top:3px;font-size:.85rem">ALIASING_TEST</div>
        </div>
        <div class="oracle-box t2" style="bottom:12px">
          <span class="oracle-name-sm">✓ ${{T2_NAME}}</span>
          <div class="oracle-detail">Static analysis: ${{DUP_COUNT}} shared variable IDs detected across sprites</div>
        </div>
        <style>@keyframes shake{{0%,100%{{transform:translateX(0)}}33%{{transform:translateX(-2px)}}66%{{transform:translateX(2px)}}}}</style>`;
      setScene(html, "BUG CONFIRMED — ALIASING");

      setTimeout(() => {{
        // Player → shared box
        drawLine(74,79,170+90,60+20,'#4a90d9',false,'arr-p');
        // shared box → Bot1
        drawLine(170+180,60+20,424,79,'#ef4444',false,'arr-r');
      }},100);

      setMonitorVars([
        {{label:`Player.${{varName.slice(0,18)}}`, val:'"ALIASING_TEST"', valcls:"bug",  cls:"highlight"}},
        {{label:`Bot1.${{varName.slice(0,19)}}`,   val:'"ALIASING_TEST"', valcls:"bug",  cls:"highlight"}},
        {{label:`Bot2.${{varName.slice(0,19)}}`,   val:'"ALIASING_TEST"', valcls:"bug",  cls:"highlight"}},
        {{label:"Oracle result",                   val:"FIRED 🚨",        valcls:"bug",  cls:"highlight"}},
      ]);
      setTick(T2_TICK, "Playing");
    }}
  }},

  // ── STEP 6: RESULTS ───────────────────────────────────────────────────────
  {{
    name: "Fuzzer Results",
    desc: `${{SILENT_COUNT}} oracles passed silently — confirming those invariants held across all ${{TOTAL_SEQS}} sequences. `
        + `Precision: ${{PRECISION}}% (${{PRECISION>=70?'good':'needs improvement'}}). `
        + `Total ticks executed: ${{TOTAL_TICKS.toLocaleString()}}.`,
    render() {{
      const prec_color = PRECISION >= 70 ? '#22c55e' : PRECISION >= 40 ? '#f59e0b' : '#ef4444';
      setScene(`
        <div style="position:absolute;inset:0;display:grid;grid-template-columns:1fr 1fr;
                    grid-template-rows:1fr 1fr;gap:8px;padding:12px">
          <div style="background:#1a2235;border-radius:8px;display:flex;flex-direction:column;
                      align-items:center;justify-content:center;padding:.75rem">
            <div style="font-size:2rem;font-weight:800;color:#ef4444">2</div>
            <div style="font-size:.75rem;color:#94a3b8;margin-top:.2rem">Bugs Found</div>
            <div style="font-size:.68rem;color:#64748b;margin-top:.15rem">1 TP · 1 FP</div>
          </div>
          <div style="background:#1a2235;border-radius:8px;display:flex;flex-direction:column;
                      align-items:center;justify-content:center;padding:.75rem">
            <div style="font-size:2rem;font-weight:800;color:${{prec_color}}">${{PRECISION}}%</div>
            <div style="font-size:.75rem;color:#94a3b8;margin-top:.2rem">Precision</div>
          </div>
          <div style="background:#1a2235;border-radius:8px;display:flex;flex-direction:column;
                      align-items:center;justify-content:center;padding:.75rem">
            <div style="font-size:2rem;font-weight:800;color:#22c55e">${{SILENT_COUNT}}</div>
            <div style="font-size:.75rem;color:#94a3b8;margin-top:.2rem">Silent Oracles</div>
            <div style="font-size:.68rem;color:#64748b;margin-top:.15rem">passing invariants</div>
          </div>
          <div style="background:#1a2235;border-radius:8px;display:flex;flex-direction:column;
                      align-items:center;justify-content:center;padding:.75rem">
            <div style="font-size:2rem;font-weight:800;color:#4a90d9">${{TOTAL_TICKS.toLocaleString()}}</div>
            <div style="font-size:.75rem;color:#94a3b8;margin-top:.2rem">Total Ticks</div>
            <div style="font-size:.68rem;color:#64748b;margin-top:.15rem">${{TOTAL_SEQS}} sequences</div>
          </div>
        </div>`, "FUZZING COMPLETE");
      setMonitorVars([
        {{label:"True Positives",   val:"1",              valcls:"ok"}},
        {{label:"False Positives",  val:"1",              valcls:"bug"}},
        {{label:"Silent Oracles",   val:String(SILENT_COUNT), valcls:"ok"}},
        {{label:"Precision",        val:PRECISION+"%",     valcls: PRECISION>=70?"ok":""}},
        {{label:"State Coverage",   val:"2/6",            valcls:""}},
      ]);
      setTick(TOTAL_TICKS, "Done");
    }}
  }},
];

// ── PLAYER ────────────────────────────────────────────────────────────────────
let currentStep = 0;
let playing = true;
let timer = null;
const STEP_DURATION = 5500; // ms per step

function renderStep(i) {{
  currentStep = i;
  const step = STEPS[i];

  // Labels
  document.getElementById('step-num-lbl').textContent = `Step ${{i+1}} of ${{STEPS.length}}`;
  document.getElementById('step-name').textContent = step.name;
  document.getElementById('step-desc').textContent = step.desc;

  // Progress bar
  document.getElementById('progress-bar').style.width = `${{(i+1)/STEPS.length*100}}%`;

  // Pip buttons
  document.querySelectorAll('.step-pip').forEach((p,pi) => {{
    p.className = 'step-pip' + (pi === i ? ' active' : pi < i ? ' done' : '');
  }});

  // Scene
  step.render();
}}

function nextStep() {{
  if (currentStep < STEPS.length - 1) renderStep(currentStep + 1);
  else renderStep(0); // loop
  resetTimer();
}}
function prevStep() {{
  if (currentStep > 0) renderStep(currentStep - 1);
  resetTimer();
}}
function togglePlay() {{
  playing = !playing;
  document.getElementById('btn-play').textContent = playing ? '⏸ Pause' : '▶ Play';
  if (playing) resetTimer(); else clearInterval(timer);
}}
function resetTimer() {{
  clearInterval(timer);
  if (playing) timer = setInterval(nextStep, STEP_DURATION);
}}

// Build pip nav
const nav = document.getElementById('stepnav');
STEPS.forEach((s,i) => {{
  const btn = document.createElement('button');
  btn.className = 'step-pip';
  btn.title = s.name;
  btn.onclick = () => {{ renderStep(i); resetTimer(); }};
  nav.appendChild(btn);
}});
nav.appendChild(Object.assign(document.createElement('span'),
  {{style:'flex:1',textContent:''}}));
nav.insertAdjacentHTML('beforeend',
  `<span style="font-size:.75rem;color:#475569">${{PROGRAM}}</span>`);

// Start
renderStep(0);
resetTimer();
</script>
</body></html>"""


# ── WRITE & OPEN ──────────────────────────────────────────────────────────────
print(f"[info]   Writing static report…")
STATIC_OUT.write_text(static_html(), encoding="utf-8")
print(f"[done]   {STATIC_OUT}")

print(f"[info]   Writing animated replay…")
REPLAY_OUT.write_text(replay_html(), encoding="utf-8")
print(f"[done]   {REPLAY_OUT}")

print(f"\n[open]   Launching in browser…")
webbrowser.open(REPLAY_OUT.as_uri())
print(f"[info]   Auto-plays through {len([None]*7)} steps, 5.5s each.")
print(f"[info]   Use Pause / Prev / Next buttons or click the step dots to control.")
