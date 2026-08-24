<<<<<<< HEAD
# Scratch Fuzzer

An automated fuzz-testing pipeline for [Scratch 3.0](https://scratch.mit.edu) programs. It reads a `.sb3` project, statically analyses its blocks and variables, generates test oracles (deterministic structural rules plus LLM-inferred semantic properties), then runs the actual program inside a headless copy of the Scratch virtual machine and checks those oracles continuously while it plays.

No hand-written test cases, no formal specification. It found a previously undocumented **variable-aliasing defect** in the Scratch 3.0 runtime, where duplicating a sprite in the editor can make two sprites silently share the same variable storage — confirmed independently by both a static structural check and an LLM reasoning from a plain-English project summary, and validated across a scan of 40 public Scratch projects.

## What it does

1. **Static analysis** (`analyser.js`) — unzips a `.sb3` file, reads its block structure without executing anything, and extracts every sprite's variables, keys, broadcasts, and collision logic. Flags duplicate variable identifiers shared across sprites (the aliasing defect) and infers a rough state machine from broadcast names.
2. **Oracle generation** (`oracle_generator.js`) — turns that analysis into runnable JavaScript checks in two tiers:
   - **Tier 2** — deterministic rules (monotonic variables, state enums, countdown bounds, aliasing).
   - **Tier 3** — an LLM (via the Groq API) reads a plain-English summary of the project and proposes properties that should always hold, which get compiled into check functions.
3. **Fuzzing** (`fuzzer_full.js`) — loads the project into headless [`scratch-vm`](https://github.com/scratchfoundation/scratch-vm), presses the green flag, and runs it through 14 scripted input sequences (idle, key holds, random input, rapid key-switching, double-start idempotency checks) derived from that project's own detected key vocabulary. Every few ticks, every oracle is checked against the live VM state. Produces a JSON bug report.
4. **Reporting** — `generate_bug_replay.py` renders any bug report into a self-contained, step-through HTML page, built generically from whatever the report actually contains (no per-project hardcoding).

A separate, lighter path scans many projects at once for just the aliasing defect, without full fuzzing:

- `download_projects.js` — downloads public Scratch projects by ID.
- `scratch_aliasing_scan.js` — runs the static aliasing check across a whole folder and produces a summary table.
- `batch_fuzz.js` — runs the *full* pipeline (analysis → oracles → fuzzing) across a folder of projects, for when the lighter scan isn't enough.

## Findings

Evaluated against three real, structurally different Scratch programs:

| Program | Genre | Sprites | Result |
|---|---|---|---|
| `has.sb3` | Hide-and-seek rescue game | 16 | **14 variable IDs shared across 5 sprites** — a structural aliasing defect, found by static analysis alone |
| `Maze.sb3` | Navigation / puzzle game | 5 | 1 monotonic-variable oracle violation under fuzzing |
| `desert.sb3` | Survival game | 11 | 1 monotonic-variable oracle violation under fuzzing |

A follow-up scan of 40 public Scratch projects found the same aliasing defect in 1 further project (2.5%), suggesting it's a real, if uncommon, risk tied to the ordinary "duplicate sprite" editor workflow rather than a one-off.

Full methodology, honest limitations (the monotonic oracle is a syntactic heuristic — see the write-up for why that matters), and references are in the accompanying dissertation.

## Running it

Requires Node.js and, optionally, a [Groq](https://console.groq.com) API key for Tier 3 oracles (set as `GROQ_API_KEY` in your environment — never hardcode it in a file).

```bash
npm install
```

Run the pipeline against a project, one stage at a time:

```bash
node analyser.js has/has.sb3
```
```bash
node oracle_generator.js has/has_analysis.json
```
```bash
node fuzzer_full.js has/has.sb3 has/has_oracles.js
```
```bash
python generate_bug_replay.py has/has_bug_report.json has/has_analysis.json
```

Or run the whole thing across a folder of projects at once:

```bash
node batch_fuzz.js scan_projects
```

Each stage's output feeds the next: `_analysis.json` → `_oracles.js` → `_bug_report.json` → `_bug_replay.html`. Accepts either a real `.sb3` file or a raw `project.json` (as served by the Scratch CDN for some projects).

## Tech stack

Node.js, [`scratch-vm`](https://github.com/scratchfoundation/scratch-vm) (headless), [Groq](https://groq.com) LLM inference API, Python (for HTML report rendering).
=======
# Automated-Fuzz-Testing-Pipeline-for-Scratch-3.0-Programs
Automated fuzz-testing pipeline for Scratch 3.0 — static analysis + LLM-generated oracles + headless VM execution. Found a previously undocumented variable-aliasing defect in the Scratch runtime.
>>>>>>> 8078c3c6ca76bd892a5157207f7ca89e00dc2318
