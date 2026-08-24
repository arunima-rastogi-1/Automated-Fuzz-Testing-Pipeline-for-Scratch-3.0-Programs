"use strict";

const fs = require("fs");
const path = require("path");
const JSZip = require("jszip");

function classifyVariable(name, value) {
  const n = name
    .toLowerCase()
    .replace(/[^a-z0-9]/g, " ")
    .trim();

  if (/cam(era)?\s*(x|y)|scroll\s*(x|y)/.test(n)) return "camera_axis";
  if (/zoom|scale|magnif/.test(n)) return "camera_zoom";
  if (/player\s*(x|y)|pos\s*(x|y)|\bpx\b|\bpy\b/.test(n)) return "position";
  if (/dir(ection)?|angle|heading|facing|rot/.test(n)) return "direction";
  if (/fps|delta|tick(?!s)|elapsed|ms\b/.test(n)) return "timing";

  if (/\bstate\b|phase|screen|menu|mode/.test(n) && typeof value === "string")
    return "game_state";
  if (/stat(us)?\b/.test(n) && typeof value === "string") return "game_state";

  if (/count(?!er)|countdown|timer/.test(n) && !isNaN(parseFloat(value)))
    return "countdown";

  if (
    /score|points?|coins?|stars?|kills?|found|rescued|walked|meters|streak|rescues|playtime/.test(
      n,
    )
  )
    return "score";
  if (/lives?|health|hp|hearts?|shield|energy/.test(n)) return "lives";

  if (
    /\?$/.test(name) ||
    value === true ||
    value === false ||
    value === "true" ||
    value === "false"
  )
    return "flag";

  if (typeof value === "string" && value.length > 80) return "encoded_data";
  if (!isNaN(parseFloat(value)) && value !== "") return "numeric";

  return "unknown";
}

// BLOCK WALKERS

function allOpcodes(blocks) {
  return Object.values(blocks)
    .filter((b) => typeof b === "object" && b !== null)
    .map((b) => b.opcode)
    .filter(Boolean);
}

// Find all hat (top-level) blocks
function hats(blocks) {
  return Object.values(blocks).filter(
    (b) => typeof b === "object" && b !== null && b.topLevel === true,
  );
}

// Collect broadcast names sent by a sprite
function broadcastsSent(blocks) {
  const names = new Set();
  for (const b of Object.values(blocks)) {
    if (typeof b !== "object" || !b) continue;
    if (
      b.opcode === "event_broadcast" ||
      b.opcode === "event_broadcastandwait"
    ) {
      const inp = b.inputs?.BROADCAST_INPUT;
      if (Array.isArray(inp) && Array.isArray(inp[1])) {
        names.add(inp[1][1]);
      }
    }
  }
  return [...names];
}

// Collect broadcast names listened to by a sprite
function broadcastsListened(blocks) {
  const names = new Set();
  for (const b of hats(blocks)) {
    if (b.opcode === "event_whenbroadcastreceived") {
      const opt = b.fields?.BROADCAST_OPTION;
      if (Array.isArray(opt)) names.add(opt[0]);
    }
  }
  return [...names];
}

// Collect keys listened to by a sprite
function keysListened(blocks) {
  const keys = new Set();
  for (const b of hats(blocks)) {
    if (b.opcode === "event_whenkeypressed") {
      const k = b.fields?.KEY_OPTION;
      if (Array.isArray(k)) keys.add(k[0]);
    }
  }
  // "key [x] pressed?" boolean reporter — the key choice lives in a child
  // sensing_keyoptions shadow block, not a hat, so it needs a full block scan.
  for (const b of Object.values(blocks)) {
    if (typeof b !== "object" || !b) continue;
    if (b.opcode === "sensing_keyoptions") {
      const k = b.fields?.KEY_OPTION;
      if (Array.isArray(k)) keys.add(k[0]);
    }
  }
  return [...keys];
}

// Check if a sprite has collision-sensing logic
function hasCollisionLogic(blocks) {
  return allOpcodes(blocks).some(
    (op) =>
      op === "sensing_touchingobject" ||
      op === "sensing_touchingcolor" ||
      op === "sensing_coloristouchingcolor",
  );
}

// Find variables only ever incremented (never decremented) ->score candidates
function findMonotonicVars(blocks) {
  const incremented = new Set();
  const decremented = new Set();
  for (const b of Object.values(blocks)) {
    if (typeof b !== "object" || !b) continue;
    if (b.opcode === "data_changevariableby") {
      const varName = b.fields?.VARIABLE?.[0];
      if (!varName) continue;
      // Try to get the literal change value
      const inp = b.inputs?.VALUE;
      let delta = null;
      if (Array.isArray(inp) && Array.isArray(inp[1]))
        delta = parseFloat(inp[1][1]);
      if (delta !== null) {
        if (delta > 0) incremented.add(varName);
        else if (delta < 0) decremented.add(varName);
      } else {
        decremented.add(varName);
      }
    }
  }
  // Monotonic = incremented and never decremented
  return [...incremented].filter((v) => !decremented.has(v));
}

// Detect variables whose value is set to a string literal (state machine candidates)
function findStateVariables(blocks) {
  const varValues = {}; // varName -> Set of string values assigned
  for (const b of Object.values(blocks)) {
    if (typeof b !== "object" || !b) continue;
    if (b.opcode === "data_setvariableto") {
      const varName = b.fields?.VARIABLE?.[0];
      if (!varName) continue;
      const inp = b.inputs?.VALUE;
      if (Array.isArray(inp) && Array.isArray(inp[1])) {
        const val = inp[1][1];
        if (
          typeof val === "string" &&
          isNaN(parseFloat(val)) &&
          val.length < 40
        ) {
          if (!varValues[varName]) varValues[varName] = new Set();
          varValues[varName].add(val);
        }
      }
    }
  }
  // Return vars assigned 2+ distinct string literals (classic state variable)
  return Object.entries(varValues)
    .filter(([, vals]) => vals.size >= 2)
    .map(([name, vals]) => ({ name, values: [...vals] }));
}

// DUPLICATE VARIABLE ID DETECTOR
// Variables sharing the same ID across sprites point to the same runtime slot.
// When Bot1 writes "speed up", it overwrites Player's "speed up" simultaneously.

//detetced in has.sb3

function detectDuplicateVariableIds(targets) {
  const idMap = {}; // id → [{ sprite, name, value }]
  for (const t of targets) {
    for (const [id, v] of Object.entries(t.variables || {})) {
      if (!idMap[id]) idMap[id] = [];
      idMap[id].push({ sprite: t.name, name: v[0], value: v[1] });
    }
  }
  const shared = Object.entries(idMap)
    .filter(([, entries]) => entries.length > 1)
    .map(([id, entries]) => ({ id, entries }));
  return shared;
}

// CAMERA SYSTEM DETECTOR
// If a project has CAM X / CAM Y / ZOOM stage variables, sprites are deliberately
// moved off-stage as the camera pans. SpatialBounds violations are expected
// this is critical context for the oracle generator to suppress false positives.

function detectCameraSystem(stageVars) {
  const names = stageVars.map((v) => v.name.toLowerCase());
  const hasX = names.some((n) => /cam.?x|scroll.?x/.test(n));
  const hasY = names.some((n) => /cam.?y|scroll.?y/.test(n));
  const hasZoom = names.some((n) => /zoom|scale/.test(n));
  return { present: hasX && hasY, hasZoom };
}

//  FSM BUILDER
// Infers the game's state machine from broadcast names and state variables.

function inferFSM(allBroadcasts, stateVars) {
  // Categorise broadcasts by likely role
  const setup = allBroadcasts.filter((b) =>
    /prepare|init|load|setup|reset/i.test(b),
  );
  const start = allBroadcasts.filter((b) => /start|play|begin|launch/i.test(b));
  const end = allBroadcasts.filter((b) =>
    /end|stop|finish|over|win|lose/i.test(b),
  );
  const menu = allBroadcasts.filter((b) => /menu|title|home|lobby/i.test(b));
  const tick = allBroadcasts.filter((b) => /tick|update|step|loop/i.test(b));
  const other = allBroadcasts.filter(
    (b) => ![...setup, ...start, ...end, ...menu, ...tick].includes(b),
  );

  return {
    stateVariables: stateVars.map((v) => v.name),
    broadcasts: { setup, start, end, menu, tick, other },
    inferredStates: buildStateList(setup, start, end, menu),
  };
}

function buildStateList(setup, start, end, menu) {
  const states = ["Boot"];
  if (setup.length) states.push("Initialising");
  if (menu.length) states.push("Menu");
  states.push("Playing");
  if (end.length) states.push("GameOver");
  return states;
}

//  NATURAL LANGUAGE SUMMARY (for LLM prompt)
// Produces the text that gets sent to the LLM in Step 2.

function buildLLMSummary(analysis) {
  const lines = [];
  lines.push(`This is a Scratch program called "${analysis.project}".`);
  lines.push(
    `It has ${analysis.sprites.length} sprites: ${analysis.sprites.map((s) => s.name).join(", ")}.`,
  );

  if (analysis.cameraSystem.present) {
    lines.push(
      `It uses a virtual camera system (variables: ${analysis.stage.variables
        .filter((v) => v.type === "camera_axis" || v.type === "camera_zoom")
        .map((v) => v.name)
        .join(
          ", ",
        )}). Sprites are intentionally moved off the 480×360 stage as the camera pans — spatial bounds violations are expected and are NOT bugs.`,
    );
  }

  const stateVars = analysis.stage.variables.filter(
    (v) => v.type === "game_state",
  );
  if (stateVars.length) {
    lines.push(
      `The game tracks state using: ${stateVars.map((v) => `"${v.name}" (current value: "${v.currentValue}")`).join(", ")}.`,
    );
  }

  const scoreVars = [
    ...analysis.stage.variables.filter((v) => v.type === "score"),
    ...analysis.sprites.flatMap((s) =>
      s.variables.filter((v) => v.type === "score"),
    ),
  ];
  if (scoreVars.length) {
    lines.push(
      `Score/stat variables (should only increase): ${scoreVars.map((v) => v.name).join(", ")}.`,
    );
  }

  const livesVars = [
    ...analysis.stage.variables.filter((v) => v.type === "lives"),
    ...analysis.sprites.flatMap((s) =>
      s.variables.filter((v) => v.type === "lives"),
    ),
  ];
  if (livesVars.length) {
    lines.push(
      `Lives/health variables: ${livesVars.map((v) => `"${v.name}" (starts at ${v.currentValue})`).join(", ")}.`,
    );
  }

  if (analysis.duplicateVariables.length) {
    lines.push(
      `WARNING: ${analysis.duplicateVariables.length} variable IDs are shared across multiple sprites. This means writes to those variables in one sprite immediately affect another sprite — a likely aliasing bug.`,
    );
  }

  const fsm = analysis.fsm;
  lines.push(`Inferred game states: ${fsm.inferredStates.join(" → ")}.`);
  if (fsm.broadcasts.tick.length) {
    lines.push(
      `Tick broadcasts (fire every frame): ${fsm.broadcasts.tick.join(", ")}.`,
    );
  }
  if (fsm.broadcasts.end.length) {
    lines.push(`End-of-round broadcasts: ${fsm.broadcasts.end.join(", ")}.`);
  }

  const colliders = analysis.sprites.filter((s) => s.hasCollisionLogic);
  if (colliders.length) {
    lines.push(
      `Sprites with collision detection logic: ${colliders.map((s) => s.name).join(", ")}.`,
    );
  }

  lines.push(
    `\nBased on the above, list 5 to 8 properties that should ALWAYS be true while this program runs. For each property, write it as a single sentence starting with "The". Focus on game logic correctness, not graphical rendering.`,
  );

  return lines.join("\n");
}

// MAIN ANALYSIS

async function loadProjectJson(inputPath) {
  const buf = fs.readFileSync(inputPath);
  const isZip = buf[0] === 0x50 && buf[1] === 0x4b; // "PK" — .sb3 zip
  if (isZip) {
    const zip = await JSZip.loadAsync(buf);
    return JSON.parse(await zip.file("project.json").async("string"));
  }
  // Raw project.json (e.g. saved by download_projects.js when the Scratch
  // CDN serves the project directly instead of an asset zip).
  return JSON.parse(buf.toString("utf8"));
}

async function analyse(sb3Path) {
  const proj = await loadProjectJson(sb3Path);

  const stage = proj.targets.find((t) => t.isStage);
  const sprites = proj.targets.filter((t) => !t.isStage);

  //  Stage variables
  const stageVars = Object.values(stage.variables || {}).map(
    ([name, value]) => ({
      name,
      currentValue: value,
      type: classifyVariable(name, value),
    }),
  );

  // All broadcasts across the whole project
  const allBroadcastNames = new Set();
  for (const t of proj.targets) {
    broadcastsSent(t.blocks).forEach((b) => allBroadcastNames.add(b));
    broadcastsListened(t.blocks).forEach((b) => allBroadcastNames.add(b));
  }

  // State variables inferred from block analysis
  const allBlocks = {};
  for (const t of proj.targets) Object.assign(allBlocks, t.blocks);
  const stateVariables = findStateVariables(allBlocks);

  // Per-sprite analysis
  const spriteAnalyses = sprites.map((t) => {
    const vars = Object.values(t.variables || {}).map(([name, value]) => ({
      name,
      currentValue: value,
      type: classifyVariable(name, value),
    }));

    return {
      name: t.name,
      variables: vars,
      lists: Object.values(t.lists || {}).map(([name]) => name),
      costumes: (t.costumes || []).map((c) => c.name),
      keysListened: keysListened(t.blocks),
      broadcastsListened: broadcastsListened(t.blocks),
      broadcastsSent: broadcastsSent(t.blocks),
      hasCollisionLogic: hasCollisionLogic(t.blocks),
      monotonicVars: findMonotonicVars(t.blocks),
      blockCount: Object.keys(t.blocks || {}).length,
    };
  });

  // Oracle hints
  const oracleHints = [];

  // Monotonic variables across all sprites + stage
  const stageMonotonic = findMonotonicVars(stage.blocks || {});
  [
    ...stageMonotonic,
    ...spriteAnalyses.flatMap((s) => s.monotonicVars),
  ].forEach((v) => {
    oracleHints.push({
      type: "monotonic_increase",
      variable: v,
      description: `"${v}" should never decrease`,
    });
  });

  // Lives variables
  stageVars
    .filter((v) => v.type === "lives")
    .forEach((v) => {
      oracleHints.push({
        type: "lives_bounds",
        variable: v.name,
        initialValue: v.currentValue,
        description: `"${v.name}" should stay between 0 and ${v.currentValue}`,
      });
    });

  // Countdown
  stageVars
    .filter((v) => v.type === "countdown")
    .forEach((v) => {
      oracleHints.push({
        type: "countdown_non_negative",
        variable: v.name,
        description: `"${v.name}" should not go below 0 during normal play`,
      });
    });

  // State variable values
  stateVariables.forEach((sv) => {
    oracleHints.push({
      type: "state_enum",
      variable: sv.name,
      knownValues: sv.values,
      description: `"${sv.name}" should only take values: ${sv.values.join(", ")}`,
    });
  });

  // Duplicate variable IDs
  const dupes = detectDuplicateVariableIds(proj.targets);
  if (dupes.length) {
    oracleHints.push({
      type: "aliasing_bug",
      count: dupes.length,
      examples: dupes
        .slice(0, 3)
        .map((d) => d.entries.map((e) => `${e.sprite}.${e.name}`).join(" = ")),
      description: `${dupes.length} variable IDs shared across sprites — writes in one sprite corrupt another`,
    });
  }

  // Camera system
  const cam = detectCameraSystem(stageVars);
  if (cam.present) {
    oracleHints.push({
      type: "camera_system",
      description:
        "Virtual camera present — SpatialBounds violations are false positives. Suppress generic spatial oracle.",
    });
  }

  // ── All keys across project ────────────────────────────────────────────────
  const allKeys = new Set(spriteAnalyses.flatMap((s) => s.keysListened));

  // ── Build FSM ──────────────────────────────────────────────────────────────
  const fsm = inferFSM([...allBroadcastNames], stateVariables);

  // ── Assemble output ────────────────────────────────────────────────────────
  const analysis = {
    project: path.basename(sb3Path),
    sprites: spriteAnalyses,
    stage: {
      variables: stageVars,
      lists: Object.values(stage.lists || {}).map(([n]) => n),
    },
    allBroadcasts: [...allBroadcastNames].sort(),
    allKeys: [...allKeys].sort(),
    fsm,
    cameraSystem: cam,
    duplicateVariables: dupes,
    oracleHints,
    llmPrompt: "", // filled below
  };

  analysis.llmPrompt = buildLLMSummary(analysis);
  return analysis;
}

// ── PRETTY PRINT ──────────────────────────────────────────────────────────────

function printSummary(a) {
  const hr = () => console.log("─".repeat(55));
  console.log(`\n${"═".repeat(55)}`);
  console.log(` ANALYSER — ${a.project}`);
  console.log(`${"═".repeat(55)}\n`);

  console.log(`Sprites (${a.sprites.length}):`);
  for (const s of a.sprites) {
    console.log(`  ${s.name}  [${s.blockCount} blocks]`);
    console.log(`    keys:       ${s.keysListened.join(", ") || "none"}`);
    console.log(
      `    listens to: ${s.broadcastsListened.slice(0, 4).join(", ")}${s.broadcastsListened.length > 4 ? "…" : ""}`,
    );
    console.log(`    collision:  ${s.hasCollisionLogic ? "yes" : "no"}`);
  }

  hr();
  console.log(`Stage variables (${a.stage.variables.length}):`);
  for (const v of a.stage.variables) {
    console.log(
      `  [${v.type.padEnd(14)}]  ${v.name} = ${String(v.currentValue).slice(0, 40)}`,
    );
  }

  hr();
  console.log(`FSM — inferred states: ${a.fsm.inferredStates.join(" → ")}`);
  console.log(`Broadcasts total: ${a.allBroadcasts.length}`);
  console.log(`  tick:  ${a.fsm.broadcasts.tick.join(", ") || "none"}`);
  console.log(`  start: ${a.fsm.broadcasts.start.join(", ") || "none"}`);
  console.log(`  end:   ${a.fsm.broadcasts.end.join(", ") || "none"}`);
  console.log(`  menu:  ${a.fsm.broadcasts.menu.join(", ") || "none"}`);

  hr();
  console.log(`Oracle hints (${a.oracleHints.length}):`);
  for (const h of a.oracleHints) {
    console.log(`  [${h.type}]  ${h.description}`);
  }

  if (a.duplicateVariables.length) {
    hr();
    console.log(
      `⚠  ALIASING BUG: ${a.duplicateVariables.length} shared variable IDs across sprites`,
    );
    a.duplicateVariables
      .slice(0, 3)
      .forEach((d) =>
        console.log(
          `   ${d.entries.map((e) => `${e.sprite}.${e.name}`).join(" ↔ ")}`,
        ),
      );
  }

  hr();
  console.log(`\nLLM PROMPT PREVIEW:\n`);
  console.log(a.llmPrompt);
  console.log();
}

// ── ENTRY POINT ───────────────────────────────────────────────────────────────

(async () => {
  const sb3Path = process.argv[2];
  if (!sb3Path) {
    console.error("Usage: node analyser.js <file.sb3|file.json>");
    process.exit(1);
  }

  const analysis = await analyse(sb3Path);
  printSummary(analysis);

  const outFile = path.join(
    path.dirname(sb3Path),
    path.basename(sb3Path).replace(/\.(sb3|json)$/i, "") + "_analysis.json",
  );
  fs.writeFileSync(outFile, JSON.stringify(analysis, null, 2));
  console.log(`Analysis saved to: ${outFile}`);
})();
