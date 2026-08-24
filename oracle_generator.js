"use strict";

//structural oracles

const fs = require("fs");
const path = require("path");

// ── COLOURS ───────────────────────────────────────────────────────────────────
const C = {
  reset: "\x1b[0m",
  bold: "\x1b[1m",
  cyan: "\x1b[36m",
  green: "\x1b[32m",
  yellow: "\x1b[33m",
  red: "\x1b[31m",
  gray: "\x1b[90m",
  magenta: "\x1b[35m",
};
const log = {
  info: (m) => console.log(`${C.cyan}ℹ${C.reset}  ${m}`),
  ok: (m) => console.log(`${C.green}✔${C.reset}  ${m}`),
  fail: (m) => console.log(`${C.red}✘${C.reset}  ${m}`),
  warn: (m) => console.log(`${C.yellow}⚠${C.reset}  ${m}`),
  dim: (m) => console.log(`${C.gray}   ${m}${C.reset}`),
  title: (m) => console.log(`\n${C.bold}${C.cyan}${m}${C.reset}\n`),
  rule: () => console.log(`${C.gray}${"─".repeat(55)}${C.reset}`),
};

// Variables we skip for monotonic oracles (internal counters, not game logic)
const MONOTONIC_SKIP = new Set([
  "#",
  "TOUCHING SOMETHING OTHER?",
  "TOUCHING SPOT ICON?",
  "spot#",
  "tile#",
  "letter#",
  "item#",
  "TICK",
  "brush dir",
  "brush cost#",
  "save code letter#",
  "save code item",
  "distance",
  "hidden for seeker?",
  "hidden for player?",
  "last click release",
]);

// Stage variables worth tracking for state enum violations
const STATE_ENUM_INCLUDE = new Set([
  "CURRENT PLAYER STAT",
  "MENU",
  "AUDIO",
  "SEEKER",
  "EDITOR?",
  "LOADED PATHS?",
  "MAP",
  "SEEKER IS COUNTING?",
]);

function buildTier2Oracles(analysis) {
  const oracles = [];
  const seen = new Set();

  for (const hint of analysis.oracleHints) {
    const key = `${hint.type}:${hint.variable ?? ""}`;
    if (seen.has(key)) continue;
    seen.add(key);

    switch (hint.type) {
      case "monotonic_increase":
        if (MONOTONIC_SKIP.has(hint.variable)) break;
        oracles.push({
          tier: 2,
          type: "monotonic",
          name: `Monotonic_${slug(hint.variable)}`,
          description: hint.description,
          varName: hint.variable,
        });
        break;

      case "countdown_non_negative":
        if (hint.variable !== "COUNT") break;
        oracles.push({
          tier: 2,
          type: "countdown",
          name: "Countdown_NonNegative",
          description: hint.description,
          varName: hint.variable,
        });
        break;

      case "state_enum":
        if (!STATE_ENUM_INCLUDE.has(hint.variable)) break;
        oracles.push({
          tier: 2,
          type: "state_enum",
          name: `StateEnum_${slug(hint.variable)}`,
          description: hint.description,
          varName: hint.variable,
          knownValues: hint.knownValues,
        });
        break;

      case "aliasing_bug":
        oracles.push({
          tier: 2,
          type: "static_report",
          name: "StaticBug_AliasingVariables",
          description: hint.description,
          examples: hint.examples,
        });
        break;

      case "camera_system":
        // Not a runtime oracle — just suppress spatial bounds in the runner.
        // We record it as metadata.
        oracles.push({
          tier: 2,
          type: "suppression",
          name: "Suppression_SpatialBounds",
          description: hint.description,
        });
        break;
    }
  }

  return oracles;
}

// ── TIER 3: LLM ORACLE GENERATION ─────────────────────────────────────────────
// Two-step LLM pipeline:
//   Step A — ask Claude to list 5-8 natural language properties.
//   Step B — for each property, ask Claude to write a JS predicate function.

const SCRATCH_VM_API_REFERENCE = `

`.trim();

async function callLLM(client, prompt, maxTokens) {
  const resp = await client.chat.completions.create({
    model: "qwen/qwen3.6-27b",
    max_tokens: maxTokens,
    messages: [{ role: "user", content: prompt }],
  });
  return resp.choices[0].message.content;
}

async function buildTier3Oracles(analysis, client) {
  log.info(
    "Calling Groq (Llama 3.3 70B) — Step A: generating natural language properties...",
  );

  // Step A — get natural language properties
  const rawProperties = await callLLM(client, analysis.llmPrompt, 4096);

  log.ok("Step A complete.");
  log.dim("LLM properties received:");
  rawProperties
    .split("\n")
    .filter((l) => l.trim())
    .forEach((l) => log.dim(`  ${l}`));

  // Parse lines (numbered or starting with "The")
  let cleaned;
  if (rawProperties.includes("</think>")) {
    cleaned = rawProperties.split("</think>").pop().trim();
  } else if (rawProperties.includes("<think>")) {
    cleaned = ""; // thinking never closed — no usable properties
  } else {
    cleaned = rawProperties.trim();
  }
  const propertyLines = cleaned
    .split("\n")
    .map((l) =>
      l
        .replace(/^\d+[\.\)]\s*/, "")
        .replace(/^[-*•]\s*/, "")
        .trim(),
    )
    .filter((l) => l.length > 15 && /^[A-Z]/.test(l) && !l.startsWith("**"))
    .slice(0, 8);
  log.rule();

  // Step B — convert each property to a JS function
  const oracles = [];
  for (let i = 0; i < propertyLines.length; i++) {
    const prop = propertyLines[i];
    log.info(
      `Step B [${i + 1}/${propertyLines.length}]: converting to code...`,
    );
    log.dim(`  "${prop}"`);

    const codePrompt = `You are writing a JavaScript oracle function for fuzz testing a Scratch game.

The function receives (vm) where vm is a scratch-vm runtime instance.

${SCRATCH_VM_API_REFERENCE}

Property to implement:
"${prop}"

Context about this specific program:
- It is a hide and seek game with sprites: Player, Bot1, Bot2, Bot3, Bot4
- Stage variables include: CURRENT PLAYER STAT, MENU, SEEKER, COUNT, LOADED PATHS?, CAM X, CAM Y, ZOOM, Meters walked:, Total Players found:, Your total rescues:, Rescue streak:
- CURRENT PLAYER STAT takes values: hided, discovered, saved, found
- MENU takes values: Main, In-Game, Game-End, Editor, Load Paths, Play Settings
- The game has a virtual camera (CAM X, CAM Y, ZOOM) — sprites going off stage is NORMAL

Return ONLY a valid JavaScript arrow function with signature (vm) => { ... }.
No markdown, no explanation, no module.exports. Just the function.
If the property cannot be checked programmatically, return: (vm) => ({ violated: false })`;

    try {
      let raw = (await callLLM(client, codePrompt, 4096)).trim();

      // Handle thinking models: take only what comes after </think>
      let code;
      if (raw.includes("</think>")) {
        code = raw.split("</think>").pop().trim();
      } else if (raw.includes("<think>")) {
        // Thinking block never closed (truncated) — no usable code
        code = "(vm) => ({ violated: false }) // generation failed";
      } else {
        code = raw;
      }

      // Strip markdown fences
      code = code
        .replace(/^```(?:javascript|js)?\n?/i, "")
        .replace(/\n?```$/i, "")
        .trim();

      // Final safety check
      if (!code || code.includes("<think>")) {
        code = "(vm) => ({ violated: false }) // generation failed";
      }

      // Syntax validation: the model occasionally truncates a function body
      // mid-generation (missing closing braces/return). Embedding invalid
      // code directly into ORACLES would break the whole module's parse,
      // taking every other oracle down with it — so check it compiles as a
      // standalone function expression before accepting it.
      try {
        // eslint-disable-next-line no-new-func
        new Function(`return (${code})`);
      } catch (syntaxErr) {
        log.warn(`  Generated code failed to parse (${syntaxErr.message}) — using no-op fallback.`);
        code = "(vm) => ({ violated: false }) // generation failed (invalid syntax)";
      }

      oracles.push({
        tier: 3,
        type: "llm",
        name: `LLM_${slug(prop.slice(0, 50))}`,
        description: prop,
        code,
      });
      log.ok(`  Generated.`);
    } catch (err) {
      log.warn(`  Failed to generate code: ${err.message}`);
      oracles.push({
        tier: 3,
        type: "llm",
        name: `LLM_${slug(prop.slice(0, 50))}`,
        description: prop,
        code: "(vm) => ({ violated: false }) // generation failed",
      });
    }
  }

  return oracles;
}

// ── CODE EMITTER ──────────────────────────────────────────────────────────────
// Converts oracle descriptors into JavaScript source code strings.

function emitOracleCode(oracle) {
  switch (oracle.type) {
    case "monotonic": {
      const vn = JSON.stringify(oracle.varName);
      return `(() => {
  let _prev = null;
  return (vm) => {
    const stage = vm.runtime.getTargetForStage();
    if (!stage) return { violated: false };
    const v = stage.lookupVariableByNameAndType(${vn}, "");
    if (!v) return { violated: false };
    const current = parseFloat(v.value);
    if (_prev !== null && !isNaN(current) && !isNaN(_prev) && current < _prev - 0.001) {
      const d = \`${oracle.varName} decreased: \${_prev} → \${current}\`;
      _prev = current;
      return { violated: true, detail: d };
    }
    if (!isNaN(current)) _prev = current;
    return { violated: false };
  };
})()`;
    }

    case "countdown": {
      const vn = JSON.stringify(oracle.varName);
      return `(vm) => {
  const stage = vm.runtime.getTargetForStage();
  if (!stage) return { violated: false };
  const v = stage.lookupVariableByNameAndType(${vn}, "");
  if (!v) return { violated: false };
  const vc = stage.lookupVariableByNameAndType("SEEKER IS COUNTING?", "");
  const counting = vc && (vc.value === "true" || vc.value === true);
  const count = parseFloat(v.value);
  if (counting && count < -5) {
    return { violated: true, detail: \`COUNT underflowed to \${count} during countdown\` };
  }
  return { violated: false };
}`;
    }

    case "state_enum": {
      const vn = JSON.stringify(oracle.varName);
      const vals = JSON.stringify(oracle.knownValues);
      return `(vm) => {
  const stage = vm.runtime.getTargetForStage();
  if (!stage) return { violated: false };
  const v = stage.lookupVariableByNameAndType(${vn}, "");
  if (!v) return { violated: false };
  const allowed = ${vals};
  const cur = String(v.value);
  if (!allowed.includes(cur)) {
    return { violated: true, detail: \`${oracle.varName} = "\${cur}" — not in allowed set: \${allowed.join(", ")}\` };
  }
  return { violated: false };
}`;
    }

    case "static_report": {
      const desc = JSON.stringify(oracle.description);
      const exs = JSON.stringify((oracle.examples || []).join("; "));
      return `(() => {
  let _reported = false;
  return (vm) => {
    if (_reported) return { violated: false };
    _reported = true;
    return { violated: true, detail: ${desc} + " Examples: " + ${exs} };
  };
})()`;
    }

    case "suppression":
      // No runtime check — metadata only
      return `(vm) => ({ violated: false }) // suppression marker`;

    case "llm":
      return oracle.code;

    default:
      return `(vm) => ({ violated: false })`;
  }
}

// ── OUTPUT FILE WRITER ────────────────────────────────────────────────────────

function writeOracleModule(allOracles, projectName, outPath) {
  const lines = [];
  lines.push(`"use strict";`);
  lines.push(`// Auto-generated oracle module for: ${projectName}`);
  lines.push(`// Generated by oracle_generator.js`);
  lines.push(`// DO NOT EDIT — regenerate by running oracle_generator.js`);
  lines.push(``);
  lines.push(
    `// cameraSystem: true — SpatialBounds oracle is suppressed for this project.`,
  );
  lines.push(
    `const CAMERA_SYSTEM = ${
      allOracles.some((o) => o.type === "suppression") ? "true" : "false"
    };`,
  );
  lines.push(``);
  lines.push(`const ORACLES = [`);

  for (const oracle of allOracles) {
    if (oracle.type === "suppression") continue; // handled via CAMERA_SYSTEM flag
    const code = emitOracleCode(oracle);
    lines.push(`  {`);
    lines.push(`    tier: ${oracle.tier},`);
    lines.push(`    name: ${JSON.stringify(oracle.name)},`);
    lines.push(`    description: ${JSON.stringify(oracle.description)},`);
    lines.push(`    check: ${code},`);
    lines.push(`  },`);
  }

  lines.push(`];`);
  lines.push(``);
  lines.push(`module.exports = { ORACLES, CAMERA_SYSTEM };`);

  fs.writeFileSync(outPath, lines.join("\n"));
}

// ── HELPERS ───────────────────────────────────────────────────────────────────
function slug(str) {
  return str
    .replace(/[^a-zA-Z0-9]+/g, "_")
    .replace(/^_|_$/g, "")
    .slice(0, 40);
}

// ── MAIN ──────────────────────────────────────────────────────────────────────
(async () => {
  const analysisPath = process.argv[2];
  if (!analysisPath) {
    console.error("Usage: node oracle_generator.js <analysis.json>");
    process.exit(1);
  }

  log.title("Oracle Generator — Step 2");
  log.info(`Reading: ${analysisPath}`);

  const analysis = JSON.parse(fs.readFileSync(analysisPath, "utf8"));
  const baseName = path.basename(analysisPath).replace(/_analysis\.json$/, "");

  // ── Tier 2: structural oracles ────────────────────────────────────────────
  log.rule();
  log.info("Generating Tier 2 structural oracles...");
  const tier2 = buildTier2Oracles(analysis);
  tier2.forEach((o) => log.ok(`  [T2] ${o.name}`));
  log.dim(`  ${tier2.length} structural oracles generated.`);

  // ── Tier 3: LLM oracles ──────────────────────────────────────────────────
  log.rule();
  let tier3 = [];
  const apiKey = process.env.GROQ_API_KEY;

  if (!apiKey) {
    log.warn("GROQ_API_KEY not set — skipping Tier 3 LLM oracle generation.");
    log.warn("Set it with: set GROQ_API_KEY=gsk_...  (Windows)");
    log.warn("             export GROQ_API_KEY=gsk_...  (Mac/Linux)");
  } else {
    let Groq;
    try {
      Groq = require("groq-sdk");
    } catch {
      log.warn("groq-sdk not installed. Run: npm install groq-sdk");
      log.warn("Skipping Tier 3 generation.");
    }

    if (Groq) {
      const client = new Groq.default({ apiKey });
      try {
        tier3 = await buildTier3Oracles(analysis, client);
        tier3.forEach((o) => log.ok(`  [T3] ${o.name}`));
        log.dim(`  ${tier3.length} LLM oracles generated.`);
      } catch (err) {
        log.fail(`LLM call failed: ${err.message}`);
      }
    }
  }

  // ── Combine and write output ───────────────────────────────────────────────
  log.rule();
  const allOracles = [...tier2, ...tier3];
  const outPath = path.join(
    path.dirname(analysisPath),
    `${baseName}_oracles.js`,
  );
  writeOracleModule(allOracles, analysis.project, outPath);

  log.ok(`Oracle module written to: ${outPath}`);
  log.rule();
  log.info(
    `Total oracles: ${allOracles.filter((o) => o.type !== "suppression").length}`,
  );
  log.info(
    `  Tier 2 (structural): ${tier2.filter((o) => o.type !== "suppression").length}`,
  );
  log.info(`  Tier 3 (LLM):        ${tier3.length}`);
  log.info(
    `  Camera suppression:  ${allOracles.some((o) => o.type === "suppression") ? "YES — SpatialBounds suppressed" : "no"}`,
  );

  if (tier3.length === 0 && apiKey) {
    log.warn(
      "No Tier 3 oracles were generated. Check your API key and network.",
    );
  }

  log.title(
    `Next step: node fuzzer_full.js <program.sb3|.json> ${path.basename(outPath)}`,
  );
})();
