"use strict";

// batch_fuzz.js
// Usage: node batch_fuzz.js [folder]      (default folder: scan_projects)
//
// Runs the full 3-step pipeline (analyser.js -> oracle_generator.js ->
// fuzzer_full.js) over every .sb3/.json project in <folder>, so the same
// pipeline validated on has.sb3 / Maze.sb3 / desert.sb3 scales to an
// arbitrary batch of downloaded projects (see download_projects.js + ids.txt).
//
// One project crashing (bad file, VM error, LLM timeout) does not stop the
// batch — it's logged and skipped. Set GROQ_API_KEY in your shell before
// running this if you want Tier 3 LLM oracles generated for every project;
// oracle_generator.js reads it from the environment automatically, and the
// child processes spawned here inherit this process's environment.

const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

const folder = process.argv[2] || "scan_projects";
const HERE = __dirname;

function run(script, args) {
  return spawnSync(process.execPath, [path.join(HERE, script), ...args], {
    cwd: HERE,
    encoding: "utf8",
    env: process.env,
  });
}

function main() {
  if (!fs.existsSync(folder)) {
    console.error(`Folder not found: ${folder}`);
    process.exit(1);
  }

  const files = fs
    .readdirSync(folder)
    .filter((f) => f.endsWith(".sb3") || f.endsWith(".json"))
    .filter(
      (f) => !f.endsWith("_analysis.json") && !f.endsWith("_bug_report.json"),
    )
    .sort();

  console.log(`Found ${files.length} project(s) in ${folder}/\n`);

  const summary = [];

  for (const file of files) {
    const projectPath = path.join(folder, file);
    const base = file.replace(/\.(sb3|json)$/i, "");
    console.log(`${"=".repeat(60)}\n${base}\n${"=".repeat(60)}`);

    const row = {
      project: file,
      ok: false,
      bugsFound: null,
      statesVisited: null,
      error: null,
    };

    const a = run("analyser.js", [projectPath]);
    console.log(a.stdout || "");
    if (a.status !== 0) {
      row.error = `analyser.js failed: ${(a.stderr || a.stdout || "").slice(0, 300)}`;
      console.error(row.error);
      summary.push(row);
      continue;
    }

    const analysisPath = path.join(folder, `${base}_analysis.json`);
    const o = run("oracle_generator.js", [analysisPath]);
    console.log(o.stdout || "");
    if (o.status !== 0) {
      row.error = `oracle_generator.js failed: ${(o.stderr || o.stdout || "").slice(0, 300)}`;
      console.error(row.error);
      summary.push(row);
      continue;
    }

    const oraclesPath = path.join(folder, `${base}_oracles.js`);
    const f = run("fuzzer_full.js", [projectPath, oraclesPath, analysisPath]);
    console.log(f.stdout || "");
    if (f.status !== 0) {
      row.error = `fuzzer_full.js failed: ${(f.stderr || f.stdout || "").slice(0, 300)}`;
      console.error(row.error);
      summary.push(row);
      continue;
    }

    const reportPath = path.join(folder, `${base}_bug_report.json`);
    try {
      const report = JSON.parse(fs.readFileSync(reportPath, "utf8"));
      row.ok = true;
      row.bugsFound = report.bugsFound;
      row.statesVisited = report.coverage.statesVisited.length;
    } catch (err) {
      row.error = `Could not read bug report: ${err.message}`;
    }

    summary.push(row);
  }

  console.log(`\n${"=".repeat(60)}\nBATCH SUMMARY\n${"=".repeat(60)}`);
  const lines = [
    `SCAN_PROJECTS BATCH FUZZ RUN — ${new Date().toISOString()}`,
    `Folder: ${folder}`,
    "",
    "Project".padEnd(24) + "Bugs".padEnd(8) + "States".padEnd(8) + "Status",
    "-".repeat(60),
  ];
  for (const r of summary) {
    lines.push(
      `${r.project.padEnd(24)}${String(r.bugsFound ?? "-").padEnd(8)}${String(r.statesVisited ?? "-").padEnd(8)}${r.ok ? "ok" : "FAILED: " + r.error}`,
    );
  }
  const text = lines.join("\n");
  console.log(text);

  fs.writeFileSync(
    path.join(HERE, "scan_projects_bug_summary.json"),
    JSON.stringify(summary, null, 2),
  );
  fs.writeFileSync(path.join(HERE, "scan_projects_bug_summary.txt"), text);
  console.log(
    `\nSaved: scan_projects_bug_summary.json, scan_projects_bug_summary.txt`,
  );
}

main();
