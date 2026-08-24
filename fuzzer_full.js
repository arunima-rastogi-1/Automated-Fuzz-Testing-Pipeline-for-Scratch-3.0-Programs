"use strict";

// fuzzer_full.js
// Usage: node fuzzer_full.js <program.sb3|program.json> <oracles.js> [analysis.json]
//
// Step 3 of the pipeline.
// Combines FSM-aware fuzzing with the oracle module from Step 2.
// Produces a JSON bug report: <program>_bug_report.json
//
// Accepts either a real .sb3 (zip) file or a raw project.json (as saved by
// download_projects.js for projects the Scratch CDN serves without an asset
// zip). Uses <program>_analysis.json (analyser.js, Step 1) to derive the
// project's own keys, start/menu broadcasts and state variables, so the
// fuzzing harness generalises across projects instead of being tuned to one.

const fs = require("fs");
const path = require("path");
const ScratchVM = require("scratch-vm");

// ── CRASH RESILIENCE ──────────────────────────────────────────────────────────
// scratch-vm's async block execution (e.g. extension blocks) runs off its own
// setInterval, outside the synchronous per-tick loop below — so errors from it
// (most commonly: browser-only extensions like Text-to-Speech/Translate
// referencing `window` in this headless Node build) land as uncaught
// exceptions / unhandled rejections that the per-sequence try/catch can't see
// and would otherwise kill the whole batch run. Log once per distinct error
// and keep going instead.
const seenCrashes = new Set();
function reportEscapedError(kind, err) {
  const msg = err?.message || String(err);
  if (seenCrashes.has(msg)) return;
  seenCrashes.add(msg);
  console.error(
    `⚠  ${kind} escaped the VM step loop (likely an unsupported extension in headless mode): ${msg}`,
  );
}
process.on("uncaughtException", (err) => reportEscapedError("Uncaught error", err));
process.on("unhandledRejection", (err) => reportEscapedError("Unhandled rejection", err));

// ── ARGS ──────────────────────────────────────────────────────────────────────
const sb3Path = process.argv[2];
const oraclePath = process.argv[3];
const analysisPathArg = process.argv[4];

if (!sb3Path || !oraclePath) {
  console.error(
    "Usage: node fuzzer_full.js <program.sb3|program.json> <oracles.js> [analysis.json]",
  );
  process.exit(1);
}

const ORACLE_ABS = path.resolve(oraclePath);

// Load CAMERA_SYSTEM flag once (it's static)
const { CAMERA_SYSTEM } = require(ORACLE_ABS);

// ── ANALYSIS (Step 1 output) ─────────────────────────────────────────────────
// Optional but recommended: without it we fall back to generic defaults
// (no broadcast-based start injection, no state-variable coverage, arrow
// keys + space as the input alphabet).
const ANALYSIS_PATH = analysisPathArg
  ? path.resolve(analysisPathArg)
  : path.join(
      path.dirname(sb3Path),
      path.basename(sb3Path).replace(/\.(sb3|json)$/i, "") + "_analysis.json",
    );

let ANALYSIS = null;
if (fs.existsSync(ANALYSIS_PATH)) {
  ANALYSIS = JSON.parse(fs.readFileSync(ANALYSIS_PATH, "utf8"));
} else {
  console.warn(
    `⚠  No analysis file at ${ANALYSIS_PATH} — using generic fallback keys/injection. Run analyser.js first for project-specific fuzzing.`,
  );
}

// ── SETTINGS ──────────────────────────────────────────────────────────────────
const TICKS_PER_EVENT = 30; // ticks held per key event
const ORACLE_CHECK_EVERY = 3; // check oracles every N ticks (performance)
const BOOT_TICKS = 120; // ticks to let game boot before injecting

// Scratch's own key-option names aren't what scratch-vm's keyboard IO expects
// (it wants DOM KeyboardEvent-style strings) — translate the ones that differ.
const SCRATCH_TO_DOM_KEY = {
  space: " ",
  "left arrow": "Left",
  "right arrow": "Right",
  "up arrow": "Up",
  "down arrow": "Down",
  enter: "Enter",
};

function resolveGameKeys(analysis) {
  const raw = (analysis?.allKeys || []).filter(
    (k) => k && k.toLowerCase() !== "any",
  );
  const mapped = raw.map((k) => SCRATCH_TO_DOM_KEY[k.toLowerCase()] ?? k);
  const deduped = [...new Set(mapped)];
  return deduped.length ? deduped : ["Left", "Right", "Up", "Down", " "];
}

// Keys this project actually listens for (from analyser.js Step 1), mapped
// to scratch-vm's expected key-string format.
const GAME_KEYS = resolveGameKeys(ANALYSIS);

// ── COLOURS ───────────────────────────────────────────────────────────────────
const C = {
  reset: "\x1b[0m",
  bold: "\x1b[1m",
  cyan: "\x1b[36m",
  green: "\x1b[32m",
  yellow: "\x1b[33m",
  red: "\x1b[31m",
  gray: "\x1b[90m",
};
const log = {
  info: (m) => console.log(`${C.cyan}ℹ${C.reset}  ${m}`),
  ok: (m) => console.log(`${C.green}✔${C.reset}  ${m}`),
  fail: (m) => console.log(`${C.red}✘${C.reset}  ${m}`),
  warn: (m) => console.log(`${C.yellow}⚠${C.reset}  ${m}`),
  dim: (m) => console.log(`${C.gray}   ${m}${C.reset}`),
  title: (m) => console.log(`\n${C.bold}${C.cyan}${m}${C.reset}\n`),
  rule: () => console.log(`${C.gray}${"─".repeat(55)}${C.reset}`),
  bug: (m) => console.log(`${C.red}${C.bold}BUG${C.reset}  ${m}`),
};

// ── ORACLE LOADER ─────────────────────────────────────────────────────────────
// Re-require the oracle module fresh for each sequence so that stateful closures
// (e.g. monotonic _prev trackers) reset between runs on a fresh VM.
function freshOracles() {
  delete require.cache[ORACLE_ABS];
  return require(ORACLE_ABS).ORACLES;
}

// ── VM HELPERS ────────────────────────────────────────────────────────────────
function stageVar(vm, name) {
  const stage = vm.runtime.getTargetForStage();
  if (!stage) return null;
  const v = stage.lookupVariableByNameAndType(name, "");
  return v ? v.value : null;
}

// State-space coverage, generalised: track the live values of whatever
// variables analyser.js classified as game_state type (name matches
// state/phase/menu/mode/status patterns) — a project-agnostic heuristic.
// Falls back to the cruder fsm.stateVariables list (assigned 2+ distinct
// string literals) only if analysis didn't type-classify anything, since
// that list can include long encoded-data variables (e.g. a serialised
// level layout) that happen to take multiple short string values.
const STATE_VARS = (() => {
  const typed = (ANALYSIS?.stage?.variables || [])
    .filter((v) => v.type === "game_state")
    .map((v) => v.name);
  if (typed.length) return typed;
  return ANALYSIS?.fsm?.stateVariables || [];
})();

// Hard backstop: never let one oversized variable value blow up a state
// signature or a bug report, regardless of how it was classified.
function truncateValue(v, max = 60) {
  const s = String(v);
  return s.length > max ? `${s.slice(0, max)}…(${s.length} chars)` : s;
}

function detectState(vm) {
  if (!STATE_VARS.length) return "Unclassified";
  return STATE_VARS.map((name) => `${name}=${truncateValue(stageVar(vm, name))}`).join("|");
}

// Kicks the project from Boot/Menu into gameplay the way a player would:
// fire the broadcasts analyser.js classified as "start" (falling back to
// "menu", then to every broadcast as a last resort). This uses the
// project's own mechanism instead of guessing at variable semantics.
const START_BROADCASTS = (() => {
  const b = ANALYSIS?.fsm?.broadcasts;
  if (b?.start?.length) return b.start;
  if (b?.menu?.length) return b.menu;
  return ANALYSIS?.allBroadcasts || [];
})();

function triggerStart(vm) {
  for (const name of START_BROADCASTS) {
    vm.runtime.startHats("event_whenbroadcastreceived", {
      BROADCAST_OPTION: name,
    });
  }
}

function pressKey(vm, key, down) {
  vm.postIOData("keyboard", { key, isDown: down });
}

// ── PROJECT LOADER ────────────────────────────────────────────────────────────
async function loadVM() {
  const vm = new ScratchVM();
  if (typeof vm.setTurboMode === "function") vm.setTurboMode(true);
  else if (typeof vm.runtime.setTurboMode === "function")
    vm.runtime.setTurboMode(true);

  const data = fs.readFileSync(sb3Path);
  const isZip = data[0] === 0x50 && data[1] === 0x4b; // "PK" — .sb3 zip

  if (isZip) {
    const arrayBuffer = data.buffer.slice(
      data.byteOffset,
      data.byteOffset + data.byteLength,
    );
    await vm.loadProject(arrayBuffer);
  } else {
    // Raw project.json (e.g. from scan_projects/, saved without an asset
    // zip) — scratch-vm accepts a parsed project object directly.
    await vm.loadProject(JSON.parse(data.toString("utf8")));
  }

  vm.start();
  vm.greenFlag(); // run the project's own "when green flag clicked" init scripts
  return vm;
}

// ── TICK + ORACLE CHECK ───────────────────────────────────────────────────────
function stepAndCheck(
  vm,
  oracles,
  seqName,
  tick,
  bugs,
  reported,
  statesVisited,
) {
  vm.runtime._step();
  statesVisited.add(detectState(vm));

  if (tick % ORACLE_CHECK_EVERY === 0) {
    for (const oracle of oracles) {
      try {
        const result = oracle.check(vm);
        if (result && result.violated) {
          // Deduplicate: same oracle fires at most once per sequence
          const key = `${seqName}::${oracle.name}`;
          if (!reported.has(key)) {
            reported.add(key);
            const bug = {
              oracle: oracle.name,
              tier: oracle.tier,
              description: oracle.description,
              sequence: seqName,
              tick,
              detail: result.detail ?? "(no detail)",
            };
            bugs.push(bug);
            log.bug(`[T${oracle.tier}] ${oracle.name}`);
            log.dim(`    Sequence : ${seqName}`);
            log.dim(`    Tick     : ${tick}`);
            log.dim(`    Detail   : ${bug.detail}`);
          }
        }
      } catch (_) {
        // Oracle threw — internal error, skip
      }
    }
  }
}

// ── SEQUENCE RUNNER ───────────────────────────────────────────────────────────
async function runSequence(seq, bugs, coverage) {
  const oracles = freshOracles(); // fresh closures each run
  const vm = await loadVM();
  const reported = new Set();
  let tick = 0;

  log.info(`Sequence: ${seq.name}`);

  for (const s of seq.steps) {
    if (s.type === "idle") {
      for (let i = 0; i < s.n; i++, tick++) {
        stepAndCheck(
          vm,
          oracles,
          seq.name,
          tick,
          bugs,
          reported,
          coverage.states,
        );
      }
    } else if (s.type === "inject") {
      triggerStart(vm);
      coverage.events.add("inject:start");
    } else if (s.type === "key") {
      pressKey(vm, s.key, true);
      coverage.events.add(`key:${s.key}`);
      for (let i = 0; i < s.n; i++, tick++) {
        stepAndCheck(
          vm,
          oracles,
          seq.name,
          tick,
          bugs,
          reported,
          coverage.states,
        );
      }
      pressKey(vm, s.key, false);
    } else if (s.type === "random") {
      for (let i = 0; i < s.n; i++, tick++) {
        if (i % 10 === 0) {
          GAME_KEYS.forEach((k) => pressKey(vm, k, false));
          const k = GAME_KEYS[Math.floor(Math.random() * GAME_KEYS.length)];
          pressKey(vm, k, true);
          coverage.events.add(`key:${k}`);
        }
        stepAndCheck(
          vm,
          oracles,
          seq.name,
          tick,
          bugs,
          reported,
          coverage.states,
        );
      }
      GAME_KEYS.forEach((k) => pressKey(vm, k, false));
    } else if (s.type === "allkeys") {
      for (const k of GAME_KEYS) {
        pressKey(vm, k, true);
        coverage.events.add(`key:${k}`);
        for (let i = 0; i < s.each; i++, tick++) {
          stepAndCheck(
            vm,
            oracles,
            seq.name,
            tick,
            bugs,
            reported,
            coverage.states,
          );
        }
        pressKey(vm, k, false);
        for (let i = 0; i < 5; i++, tick++) {
          stepAndCheck(
            vm,
            oracles,
            seq.name,
            tick,
            bugs,
            reported,
            coverage.states,
          );
        }
      }
    }
  }

  try {
    vm.stopAll();
    // vm.start() sets up a real setInterval-driven step loop independent of
    // our manual _step() calls above; without quit() it keeps firing (and
    // re-running any broken async blocks, e.g. unsupported extensions) after
    // this sequence is "done", leaking across every remaining sequence.
    vm.quit();
  } catch (_) {}
  log.dim(`  Ticks: ${tick}  Bugs found: ${reported.size}`);
  return tick;
}

// ── SEQUENCE DEFINITIONS ──────────────────────────────────────────────────────
const idle = (n) => ({ type: "idle", n });
const inject = () => ({ type: "inject" });
const key = (k, n) => ({ type: "key", key: k, n: n ?? TICKS_PER_EVENT });
const random = (n) => ({ type: "random", n });
const allkeys = (each) => ({ type: "allkeys", each: each ?? 20 });

const BOOT = idle(BOOT_TICKS);

function slugKey(k) {
  return k === " " ? "Space" : k.replace(/[^a-zA-Z0-9]/g, "");
}

// Sequence shapes are fixed; the keys they exercise are derived from
// GAME_KEYS (analyser.js's Step 1 output), so the same ~14 sequences scale
// to however many distinct keys a project actually uses.
function buildSequences(gameKeys) {
  const holdKeys = gameKeys.slice(0, 5); // cap explicit hold-sequences
  const k0 = gameKeys[0] ?? " ";
  const k1 = gameKeys[1] ?? k0;
  const k2 = gameKeys[2] ?? k0;

  return [
    // 1. Cold boot — just watch
    { name: "Boot_Idle", steps: [idle(300)] },

    // 2. Boot → trigger start → idle
    { name: "Boot_then_Playing", steps: [BOOT, inject(), idle(180)] },

    // 3-7. Individual key holds after start
    ...holdKeys.map((k) => ({
      name: `Playing_Hold_${slugKey(k)}`,
      steps: [BOOT, inject(), key(k, 150)],
    })),

    // 8. Cycle all keys in sequence
    { name: "Playing_All_Keys", steps: [BOOT, inject(), allkeys(30)] },

    // 9. Random inputs, 600 ticks
    { name: "Playing_Random_600", steps: [BOOT, inject(), random(600)] },

    // 10. Long spam on the first key — stress monotonic score variables
    { name: "Playing_Spam_Long", steps: [BOOT, inject(), key(k0, 600)] },

    // 11. Mixed session
    {
      name: "Playing_Mixed_Long",
      steps: [
        BOOT,
        inject(),
        key(k0, 90),
        key(k1, 90),
        random(300),
        key(k2, 60),
        idle(60),
      ],
    },

    // 12. Double inject — idempotency test
    {
      name: "Double_Inject",
      steps: [BOOT, inject(), idle(30), inject(), idle(30), idle(120)],
    },

    // 13. Long cold boot — stress initialisation path
    { name: "Boot_Long_600", steps: [idle(600)] },

    // 14. Rapid key switching
    {
      name: "Playing_Rapid_Switch",
      steps: [
        BOOT,
        inject(),
        ...gameKeys.flatMap((k) => [key(k, 10), idle(5)]),
        idle(60),
      ],
    },
  ];
}

const SEQUENCES = buildSequences(GAME_KEYS);

// ── REPORT WRITER ─────────────────────────────────────────────────────────────
function writeReport(bugs, coverage, totalTicks) {
  const programName = path.basename(sb3Path);
  const report = {
    program: programName,
    oracles: path.basename(oraclePath),
    timestamp: new Date().toISOString(),
    totalSequences: SEQUENCES.length,
    totalTicks,
    oracleCount: freshOracles().length,
    cameraSystem: CAMERA_SYSTEM,
    coverage: {
      statesVisited: [...coverage.states],
      eventsTriggered: [...coverage.events],
    },
    bugsFound: bugs.length,
    bugs,
  };

  const outName = programName.replace(/\.sb3$/i, "") + "_bug_report.json";
  const outPath = path.join(path.dirname(sb3Path), outName);
  fs.writeFileSync(outPath, JSON.stringify(report, null, 2));
  return outPath;
}

// ── MAIN ──────────────────────────────────────────────────────────────────────
(async () => {
  log.title("Fuzzer Full — Step 3");
  log.info(`Program  : ${path.basename(sb3Path)}`);
  log.info(
    `Oracles  : ${path.basename(oraclePath)} (${freshOracles().length} oracles)`,
  );
  log.info(
    `Analysis : ${ANALYSIS ? path.basename(ANALYSIS_PATH) : "none (generic fallback)"}`,
  );
  log.info(`Keys     : ${GAME_KEYS.join(", ")}`);
  log.info(
    `Start    : ${START_BROADCASTS.length ? START_BROADCASTS.join(", ") : "none detected"}`,
  );
  log.info(
    `Camera   : ${CAMERA_SYSTEM ? "suppressed (virtual camera)" : "checked"}`,
  );
  log.info(`Sequences: ${SEQUENCES.length}`);
  log.rule();

  const bugs = [];
  const coverage = { states: new Set(), events: new Set() };
  let totalTicks = 0;

  for (const seq of SEQUENCES) {
    log.rule();
    try {
      totalTicks += await runSequence(seq, bugs, coverage);
    } catch (err) {
      log.fail(`Sequence "${seq.name}" crashed: ${err.message}`);
    }
  }

  log.rule();
  log.title("Summary");
  log.info(`Sequences     : ${SEQUENCES.length}`);
  log.info(`Total ticks   : ${totalTicks}`);
  log.info(`States visited: ${[...coverage.states].join(", ") || "none"}`);
  log.info(`Events used   : ${[...coverage.events].join(", ") || "none"}`);
  log.info(`Bugs found    : ${bugs.length}`);

  if (bugs.length > 0) {
    log.rule();
    bugs.forEach((b, i) => {
      log.fail(`Bug ${i + 1} [T${b.tier}] ${b.oracle}`);
      log.dim(`  Sequence : ${b.sequence}`);
      log.dim(`  Tick     : ${b.tick}`);
      log.dim(`  Detail   : ${b.detail}`);
    });
  } else {
    log.ok("No oracle violations detected.");
  }

  log.rule();
  const reportPath = writeReport(bugs, coverage, totalTicks);
  log.ok(`Report: ${reportPath}`);
})();
