"""
generate_bug_replay.py
Usage: python generate_bug_replay.py <bug_report.json> [analysis.json]

Generic, data-driven bug replay — works for ANY project's bug_report.json
(has.sb3, desert.sb3, Maze.sb3, or anything from scan_projects/), unlike
generate_demo_video.py / generate_replay_report.py which hand-illustrate
has.sb3's specific aliasing-bug story and should not be reused for other
projects (they were built for that one narrative and are left untouched).

This script never invents data: if a project has no aliasing bug, no LLM
oracles, or zero bugs at all, it says so instead of fabricating content.
Every "scene" is built directly from the actual bugs[] entries in the
program's own bug_report.json, stepped through chronologically by tick.

Press Win+G to open Xbox Game Bar and hit Record before opening this page.
"""

import sys, json, re, webbrowser
from pathlib import Path

if len(sys.argv) < 2:
    print("Usage: python generate_bug_replay.py <bug_report.json> [analysis.json]")
    sys.exit(1)

REPORT_PATH = Path(sys.argv[1]).resolve()
ANALYSIS_PATH = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else None

report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
analysis = (
    json.loads(ANALYSIS_PATH.read_text(encoding="utf-8"))
    if ANALYSIS_PATH and ANALYSIS_PATH.exists()
    else {}
)

PROGRAM = report.get("program", REPORT_PATH.stem)
STEM = re.sub(r"\.(sb3|json)$", "", PROGRAM, flags=re.IGNORECASE)

_out_dir = REPORT_PATH.parent
try:
    (_out_dir / ".write_test").touch()
    (_out_dir / ".write_test").unlink()
except OSError:
    _out_dir = Path.cwd()

OUT = _out_dir / f"{STEM}_bug_replay.html"

# ── DATA ─────────────────────────────────────────────────────────────────────
bugs = report.get("bugs", [])
total_ticks = report.get("totalTicks", 0)
total_seqs = report.get("totalSequences", 0)
oracle_count = report.get("oracleCount", 0)
camera_system = report.get("cameraSystem", False)
states_visited = report.get("coverage", {}).get("statesVisited", [])
events_triggered = report.get("coverage", {}).get("eventsTriggered", [])
timestamp = report.get("timestamp", "")

sprites = analysis.get("sprites", [])
stage_vars = analysis.get("stage", {}).get("variables", [])
all_keys = analysis.get("allKeys", [])
all_broadcasts = analysis.get("allBroadcasts", [])
inferred_states = analysis.get("fsm", {}).get("inferredStates", [])

# Dedupe bugs by oracle name (an oracle can fire in many sequences — the
# report already dedupes per-sequence, this is the same dedup the existing
# scripts use for consistency), then sort chronologically by tick.
unique_bugs = {}
for b in bugs:
    if b["oracle"] not in unique_bugs:
        unique_bugs[b["oracle"]] = b
beats = sorted(unique_bugs.values(), key=lambda b: b.get("tick", 0))

tier2_count = sum(1 for b in beats if b.get("tier") == 2)
tier3_count = sum(1 for b in beats if b.get("tier") == 3)
silent_count = max(oracle_count - len(beats), 0)


def parse_detail(detail):
    """Best-effort structured read of a bug's detail string, for a small
    visual on top of the raw text — never required, always falls back to
    plain text if the pattern isn't recognised."""
    m = re.match(r"^(.+?) decreased: ([\d.\-]+) → ([\d.\-]+)$", detail)
    if m:
        return {
            "kind": "drop",
            "var": m.group(1),
            "before": float(m.group(2)),
            "after": float(m.group(3)),
        }
    m = re.match(r'^(.+?) = "(.*?)" — not in allowed set: (.+)$', detail)
    if m:
        return {
            "kind": "invalid_enum",
            "var": m.group(1),
            "value": m.group(2),
            "allowed": m.group(3),
        }
    if "shared variable IDs" in detail or "Examples:" in detail:
        return {"kind": "aliasing", "text": detail}
    return {"kind": "text", "text": detail}


for b in beats:
    b["_parsed"] = parse_detail(b.get("detail", ""))

beats_js = json.dumps(
    [
        {
            "oracle": b["oracle"],
            "tier": b.get("tier"),
            "description": b.get("description", ""),
            "sequence": b.get("sequence", ""),
            "tick": b.get("tick", 0),
            "detail": b.get("detail", ""),
            "parsed": b["_parsed"],
        }
        for b in beats
    ]
)

sprite_chips = [
    {"name": s.get("name", "?"), "blocks": s.get("blockCount", 0)} for s in sprites
]
sprite_chips_js = json.dumps(sprite_chips)

# ── HTML ─────────────────────────────────────────────────────────────────────
html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Bug Replay — {STEM}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
:root{{
  --bg:#07090f; --surface:#0d1219; --border:#1a2535;
  --blue:#4a90d9; --green:#22c55e; --red:#ef4444;
  --amber:#f59e0b; --purple:#a855f7; --text:#e2e8f0; --muted:#64748b;
}}
body{{font-family:'Segoe UI',system-ui,sans-serif;background:var(--bg);color:var(--text);
      padding:2rem;line-height:1.6;max-width:1100px;margin:0 auto}}
h1{{font-size:1.7rem;font-weight:700;color:#fff;margin-bottom:.25rem}}
.sub{{color:var(--muted);font-size:.9rem;margin-bottom:2rem;font-family:monospace}}
.metrics{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:1rem;margin-bottom:2rem}}
.metric{{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:1rem;text-align:center}}
.metric .val{{font-size:2rem;font-weight:800;display:block;line-height:1.2}}
.metric .lbl{{font-size:.72rem;color:var(--muted);text-transform:uppercase;letter-spacing:.05em;margin-top:.25rem}}
h2{{font-size:.95rem;font-weight:700;color:var(--blue);text-transform:uppercase;letter-spacing:.08em;
    margin:2rem 0 .75rem;padding-bottom:.4rem;border-bottom:1px solid var(--border)}}
.chips{{display:flex;flex-wrap:wrap;gap:.4rem;margin-bottom:1rem}}
.chip{{background:#111827;border:1px solid var(--border);border-radius:20px;padding:.25rem .75rem;
       font-size:.78rem;font-family:monospace;color:#cbd5e1}}
.chip.key{{color:var(--amber)}}
.chip.bc{{color:var(--purple)}}
.chip.state{{color:var(--green)}}
.empty-note{{color:var(--muted);font-size:.85rem;font-style:italic}}

/* ── REPLAY ── */
#replay{{background:var(--surface);border:1px solid var(--border);border-radius:12px;
         padding:1.5rem;margin-top:1rem}}
#replay-empty{{text-align:center;padding:3rem 1rem;color:var(--muted)}}
#replay-empty .big{{font-size:2.5rem;margin-bottom:.5rem}}
#scene-head{{display:flex;justify-content:space-between;align-items:center;margin-bottom:1rem;
             flex-wrap:wrap;gap:.5rem}}
.tier-badge{{padding:2px 10px;border-radius:20px;font-size:.7rem;font-weight:700;text-transform:uppercase}}
.tier-badge.t2{{background:#1e3a2e;color:var(--green)}}
.tier-badge.t3{{background:#3a2e1e;color:var(--amber)}}
#seq-tick{{font-family:monospace;font-size:.78rem;color:var(--muted)}}
#scene-desc{{font-size:1rem;color:#fff;margin-bottom:1rem}}
#scene-visual{{background:#0a0e18;border-radius:8px;padding:1.25rem;margin-bottom:1rem;min-height:110px;
               display:flex;align-items:center;justify-content:center}}
#scene-detail{{font-family:monospace;font-size:.85rem;color:#fca5a5;background:#1a0e0e;
               border-left:3px solid var(--red);padding:.6rem .9rem;border-radius:4px}}

.drop-gauge{{width:100%;max-width:420px}}
.drop-gauge .label{{display:flex;justify-content:space-between;font-family:monospace;font-size:.8rem;
                     color:var(--muted);margin-bottom:.35rem}}
.drop-gauge .bar-track{{height:14px;background:#1a2535;border-radius:7px;overflow:hidden;position:relative}}
.drop-gauge .bar-before{{position:absolute;top:0;left:0;height:100%;background:#22c55e44}}
.drop-gauge .bar-after{{position:absolute;top:0;left:0;height:100%;background:var(--red);
                          transition:width 1.1s cubic-bezier(.4,0,.2,1)}}
.drop-gauge .vals{{display:flex;justify-content:space-between;font-family:monospace;font-size:.78rem;
                    margin-top:.35rem}}
.drop-gauge .vals .before{{color:var(--green)}}
.drop-gauge .vals .after{{color:var(--red)}}

.enum-visual{{font-family:monospace;font-size:.9rem;text-align:center}}
.enum-visual .got{{color:var(--red);font-weight:700}}
.enum-visual .allowed{{color:var(--muted);margin-top:.4rem;font-size:.78rem}}

#step-nav{{display:flex;align-items:center;gap:.75rem;margin-top:1.25rem}}
#step-nav button{{background:#1a2535;border:1px solid var(--border);color:var(--text);
                   padding:.4rem .9rem;border-radius:6px;cursor:pointer;font-size:.82rem}}
#step-nav button:hover{{background:#233047}}
#step-nav button:disabled{{opacity:.4;cursor:default}}
#step-dots{{display:flex;gap:.35rem;flex:1;justify-content:center}}
.dot{{width:8px;height:8px;border-radius:50%;background:#2a3548;cursor:pointer;transition:background .2s}}
.dot.active{{background:var(--blue)}}

footer{{margin-top:2rem;color:var(--muted);font-size:.78rem;text-align:center}}
</style>
</head>
<body>

<h1>Bug Replay — {STEM}</h1>
<div class="sub">{PROGRAM} · {timestamp}</div>

<div class="metrics">
  <div class="metric"><span class="val" style="color:var(--blue)">{total_seqs}</span><span class="lbl">Sequences</span></div>
  <div class="metric"><span class="val" style="color:var(--blue)">{total_ticks}</span><span class="lbl">Total Ticks</span></div>
  <div class="metric"><span class="val" style="color:var(--purple)">{oracle_count}</span><span class="lbl">Oracles</span></div>
  <div class="metric"><span class="val" style="color:{'var(--red)' if beats else 'var(--green)'}">{len(beats)}</span><span class="lbl">Bugs Found</span></div>
  <div class="metric"><span class="val" style="color:var(--green)">{silent_count}</span><span class="lbl">Silent Oracles</span></div>
  <div class="metric"><span class="val" style="color:var(--amber)">{len(states_visited)}</span><span class="lbl">States Visited</span></div>
</div>

<h2>Coverage</h2>
<div class="chips">
  {"".join(f'<span class="chip key">{k}</span>' for k in all_keys) or '<span class="empty-note">No keys detected for this project.</span>'}
</div>
<div class="chips">
  {"".join(f'<span class="chip bc">{e}</span>' for e in events_triggered) or '<span class="empty-note">No events triggered.</span>'}
</div>
<div class="chips">
  {"".join(f'<span class="chip state">{s}</span>' for s in states_visited) or '<span class="empty-note">No state signature captured for this project (no detected state variables).</span>'}
</div>
{'<div class="empty-note" style="margin-bottom:1rem">Virtual camera detected — SpatialBounds oracle suppressed for this project.</div>' if camera_system else ''}

<h2>Sprites ({len(sprites)})</h2>
<div class="chips">
  {"".join(f'<span class="chip">{s["name"]} · {s["blocks"]} blocks</span>' for s in sprite_chips) or '<span class="empty-note">No analysis.json supplied — sprite list unavailable.</span>'}
</div>

<h2>Bug Timeline</h2>
<div id="replay"></div>

<footer>
  Generated by generate_bug_replay.py — a project-agnostic view built only from
  {STEM}_bug_report.json {'and ' + STEM + '_analysis.json' if analysis else '(no analysis.json found)'}.
  Nothing on this page is fabricated: sections with no data say so.
</footer>

<script>
const BEATS = {beats_js};

function renderVisual(p) {{
  if (p.kind === 'drop') {{
    const pct = p.before > 0 ? Math.max(0, Math.min(100, (p.after / p.before) * 100)) : 0;
    return `<div class="drop-gauge">
      <div class="label"><span>${{p.var}}</span><span>should never decrease</span></div>
      <div class="bar-track">
        <div class="bar-before" style="width:100%"></div>
        <div class="bar-after" id="bar-after" style="width:100%"></div>
      </div>
      <div class="vals"><span class="before">${{p.before}}</span><span class="after">→ ${{p.after}}</span></div>
    </div>`;
  }}
  if (p.kind === 'invalid_enum') {{
    return `<div class="enum-visual">
      <div>${{p.var}} = <span class="got">"${{p.value}}"</span></div>
      <div class="allowed">allowed: ${{p.allowed}}</div>
    </div>`;
  }}
  if (p.kind === 'aliasing') {{
    return `<div class="enum-visual" style="color:var(--red)">Shared-variable aliasing detected</div>`;
  }}
  return `<div class="enum-visual" style="color:var(--muted)">See detail below</div>`;
}}

let idx = 0;
function draw() {{
  const root = document.getElementById('replay');
  if (BEATS.length === 0) {{
    root.innerHTML = `<div id="replay-empty"><div class="big">✔</div>
      <div>No oracle violations detected across ${{ {total_seqs} }} sequences / ${{ {total_ticks} }} ticks.</div></div>`;
    return;
  }}
  const b = BEATS[idx];
  const tierClass = b.tier === 2 ? 't2' : 't3';
  const tierLabel = b.tier === 2 ? 'Tier 2 · Structural' : 'Tier 3 · LLM';
  root.innerHTML = `
    <div id="scene-head">
      <div><strong>${{b.oracle}}</strong> <span class="tier-badge ${{tierClass}}">${{tierLabel}}</span></div>
      <div id="seq-tick">${{b.sequence}} · tick ${{b.tick}}</div>
    </div>
    <div id="scene-desc">${{b.description}}</div>
    <div id="scene-visual">${{renderVisual(b.parsed)}}</div>
    <div id="scene-detail">${{b.detail}}</div>
    <div id="step-nav">
      <button id="prev-btn">◀ Prev</button>
      <div id="step-dots"></div>
      <button id="next-btn">Next ▶</button>
    </div>
  `;
  const dots = document.getElementById('step-dots');
  BEATS.forEach((_, i) => {{
    const d = document.createElement('div');
    d.className = 'dot' + (i === idx ? ' active' : '');
    d.onclick = () => {{ idx = i; draw(); }};
    dots.appendChild(d);
  }});
  document.getElementById('prev-btn').disabled = idx === 0;
  document.getElementById('prev-btn').onclick = () => {{ idx = Math.max(0, idx - 1); draw(); }};
  document.getElementById('next-btn').disabled = idx === BEATS.length - 1;
  document.getElementById('next-btn').onclick = () => {{ idx = Math.min(BEATS.length - 1, idx + 1); draw(); }};

  if (b.parsed.kind === 'drop') {{
    const pct = b.parsed.before > 0 ? Math.max(0, Math.min(100, (b.parsed.after / b.parsed.before) * 100)) : 0;
    requestAnimationFrame(() => {{
      const el = document.getElementById('bar-after');
      if (el) el.style.width = pct + '%';
    }});
  }}
}}
draw();
</script>
</body>
</html>
"""

print("[info]   Writing bug replay…")
OUT.write_text(html, encoding="utf-8")
print(f"[done]   {OUT}")

print("\n[open]   Launching in browser…")
webbrowser.open(OUT.as_uri())
print(f"[info]   {len(beats)} bug(s) to step through — use Prev/Next or click the dots.")
