/**
 * scratch_aliasing_scan.js
 * ─────────────────────────────────────────────────────────────────────────────
 * Fetches public Scratch projects from the Scratch REST API, downloads each
 * .sb3 file, and checks for UUID-sharing aliasing bugs (sprites that share
 * the same variable UUID after being duplicated in the editor).
 *
 * Usage:
 *   node scratch_aliasing_scan.js [--count 40] [--mode trending|popular|recent]
 *   node scratch_aliasing_scan.js --from-file trending_projects.json
 *
 * If the Scratch API is blocked by your network/proxy, open this URL in your
 * browser, save the page as trending_projects.json, then use --from-file.
 *   https://api.scratch.mit.edu/explore/projects?limit=40&offset=0&language=en&mode=trending
 *
 * Output:
 *   aliasing_scan_results.json   — full per-project data
 *   aliasing_scan_summary.txt    — human-readable table for dissertation
 * ─────────────────────────────────────────────────────────────────────────────
 */

const https  = require('https');
const http   = require('http');
const fs     = require('fs');
const path   = require('path');

// ── config ────────────────────────────────────────────────────────────────────
function getArg(name, fallback = null) {
  const idx = process.argv.indexOf(name);
  if (idx === -1 || idx + 1 >= process.argv.length) return fallback;
  const val = process.argv[idx + 1];
  return (val && !val.startsWith('--')) ? val : fallback;
}
const COUNT       = parseInt(getArg('--count', '40'), 10);
const MODE        = getArg('--mode', 'trending');
const FROM_FILE   = getArg('--from-file');
const IDS_FILE    = getArg('--ids-file');
const SCAN_FOLDER = getArg('--scan-folder');
const DELAY   = 600;   // ms between requests — be polite to Scratch servers
const TIMEOUT = 12000; // ms per download before giving up

// ── JSZip (bundled with scratch-vm, so likely already present) ────────────────
let JSZip;
try {
  JSZip = require('jszip');
} catch (_) {
  try {
    // Try resolving from scratch-vm's own node_modules
    JSZip = require(require.resolve('jszip', { paths: [
      path.join(__dirname, 'node_modules'),
      path.join(__dirname, '..', 'node_modules'),
    ]}));
  } catch (_2) {
    console.error('\n  JSZip not found. Run:  npm install jszip\n');
    process.exit(1);
  }
}

// ── helpers ───────────────────────────────────────────────────────────────────
function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

function fetch(url, timeoutMs = TIMEOUT) {
  return new Promise((resolve, reject) => {
    const lib = url.startsWith('https') ? https : http;
    const req = lib.get(url, {
      headers: {
        'User-Agent': 'ScratchAliasingResearch/1.0 (MSc dissertation; not commercial)',
        'Accept': 'application/json, application/octet-stream, */*',
      }
    }, res => {
      // Follow redirects (up to 5)
      if ([301, 302, 303, 307, 308].includes(res.statusCode) && res.headers.location) {
        return resolve(fetch(res.headers.location, timeoutMs));
      }
      if (res.statusCode !== 200) {
        res.resume();
        return reject(new Error(`HTTP ${res.statusCode} for ${url}`));
      }
      const chunks = [];
      res.on('data', c => chunks.push(c));
      res.on('end',  () => resolve(Buffer.concat(chunks)));
      res.on('error', reject);
    });
    req.setTimeout(timeoutMs, () => { req.destroy(); reject(new Error('Timeout')); });
    req.on('error', reject);
  });
}

// ── Scratch API ───────────────────────────────────────────────────────────────
async function getProjectList(count, mode) {
  // Manual IDs mode: plain text file, one project ID per line
  // e.g. ids.txt contains:  123456789
  //                          987654321
  if (IDS_FILE) {
    if (!fs.existsSync(IDS_FILE)) {
      console.error(`\n  File not found: ${IDS_FILE}\n`);
      process.exit(1);
    }
    const lines = fs.readFileSync(IDS_FILE, 'utf8')
      .split('\n')
      .map(l => {
        l = l.trim();
        // Accept bare IDs ("123456") or full URLs ("https://scratch.mit.edu/projects/123456/")
        const m = l.match(/(\d{5,})/);
        return m ? m[1] : null;
      })
      .filter(Boolean);
    if (lines.length === 0) {
      console.error('\n  ids.txt contains no valid project IDs.');
      console.error('  Put one Scratch project ID (or full URL) per line.\n');
      process.exit(1);
    }
    const ids = lines.slice(0, count).map(id => ({ id: Number(id), title: `project-${id}`, author: '?' }));
    console.log(`  (manual mode — loaded ${ids.length} IDs from ${IDS_FILE})`);
    return ids;
  }

  // Offline mode: read from a saved JSON file
  if (FROM_FILE) {
    if (!fs.existsSync(FROM_FILE)) {
      console.error(`\n  File not found: ${FROM_FILE}\n`);
      process.exit(1);
    }
    const raw  = fs.readFileSync(FROM_FILE, 'utf8');
    const list = JSON.parse(raw);
    if (!Array.isArray(list)) {
      console.error('\n  JSON file must be an array of Scratch project objects.\n');
      process.exit(1);
    }
    const ids = list.slice(0, count).map(p => ({ id: p.id, title: p.title, author: p.author?.username || '?' }));
    console.log(`  (offline mode — loaded ${ids.length} IDs from ${FROM_FILE})`);
    return ids;
  }

  // Online mode: fetch in pages of 40 (API max)
  const ids = [];
  const PAGE = 40;
  for (let offset = 0; offset < count; offset += PAGE) {
    const limit = Math.min(PAGE, count - offset);
    const url = `https://api.scratch.mit.edu/explore/projects?limit=${limit}&offset=${offset}&language=en&mode=${mode}`;
    try {
      const buf  = await fetch(url);
      const list = JSON.parse(buf.toString());
      if (!Array.isArray(list) || list.length === 0) break;
      for (const p of list) ids.push({ id: p.id, title: p.title, author: p.author?.username || '?' });
      await sleep(DELAY);
    } catch (e) {
      console.warn(`  ⚠  API page failed (offset=${offset}): ${e.message}`);
      console.warn(`\n  TIP: If your network blocks Node.js outbound requests, open this URL`);
      console.warn(`  in your browser, save the page as trending_projects.json, then run:`);
      console.warn(`  node scratch_aliasing_scan.js --from-file trending_projects.json\n`);
      console.warn(`  URL: https://api.scratch.mit.edu/explore/projects?limit=40&offset=0&language=en&mode=trending\n`);
      break;
    }
  }
  return ids;
}

async function getProjectToken(id) {
  const url = `https://api.scratch.mit.edu/projects/${id}`;
  const buf  = await fetch(url);
  const meta = JSON.parse(buf.toString());
  return meta.project_token || null;
}

async function downloadSb3(id) {
  // Try tokenless first (works for many projects, avoids API call)
  try {
    return await fetch(`https://projects.scratch.mit.edu/${id}`);
  } catch (_) {}

  // Fall back to token-authenticated download
  let token;
  try {
    token = await getProjectToken(id);
  } catch (e) {
    throw new Error(`Token fetch failed: ${e.message}`);
  }
  return await fetch(`https://projects.scratch.mit.edu/${id}?token=${token}`);
}

// ── aliasing detection ────────────────────────────────────────────────────────
function detectAliasing(projectJson) {
  const targets = projectJson.targets || [];
  const sprites = targets.filter(t => !t.isStage);

  // Map: variableUUID → { name, sprites[] }
  const uuidMap = {};
  for (const sprite of sprites) {
    const vars = sprite.variables || {};
    for (const [uuid, val] of Object.entries(vars)) {
      const varName = Array.isArray(val) ? val[0] : String(val);
      if (!uuidMap[uuid]) uuidMap[uuid] = { name: varName, sprites: [] };
      if (!uuidMap[uuid].sprites.includes(sprite.name)) {
        uuidMap[uuid].sprites.push(sprite.name);
      }
    }
    // Also check lists (same duplication problem)
    const lists = sprite.lists || {};
    for (const [uuid, val] of Object.entries(lists)) {
      const listName = Array.isArray(val) ? val[0] : String(val);
      const key = `list:${uuid}`;
      if (!uuidMap[key]) uuidMap[key] = { name: listName, sprites: [], isList: true };
      if (!uuidMap[key].sprites.includes(sprite.name)) {
        uuidMap[key].sprites.push(sprite.name);
      }
    }
  }

  const aliased = Object.entries(uuidMap)
    .filter(([, v]) => v.sprites.length > 1)
    .map(([uuid, v]) => ({
      uuid:    uuid.replace('list:', '').slice(0, 14) + '…',
      name:    v.name,
      sprites: v.sprites,
      isList:  v.isList || false,
    }));

  return { aliased, spriteCount: sprites.length };
}

// ── scan-folder mode (offline, no network needed) ─────────────────────────────
async function scanFolder(folder) {
  const BAR = '═'.repeat(55);
  console.log(BAR);
  console.log(' SCRATCH ALIASING BUG SCAN — LOCAL FOLDER');
  console.log(` Folder: ${folder}`);
  console.log(BAR + '\n');

  if (!fs.existsSync(folder)) {
    console.error(`  Folder not found: ${folder}`);
    process.exit(1);
  }

  // Accept .sb3 (ZIP) and .json (raw project.json from CDN)
  const files = fs.readdirSync(folder).filter(f => f.endsWith('.sb3') || f.endsWith('.json'));
  if (files.length === 0) {
    console.error(`  No .sb3 or .json files found in ${folder}`);
    process.exit(1);
  }
  console.log(`Found ${files.length} project file(s)\n`);

  const results = [];
  let withBug = 0, failed = 0;

  for (const file of files) {
    const label = file.slice(0, 42).padEnd(42);
    process.stdout.write(`  ${label} `);
    const fullPath = path.join(folder, file);
    let aliased = [], spriteCount = 0;
    try {
      const buf = fs.readFileSync(fullPath);
      let projectJson;
      if (file.endsWith('.json')) {
        // Raw project.json from CDN — parse directly
        projectJson = JSON.parse(buf.toString('utf8'));
        if (!projectJson.targets) throw new Error('Not a Scratch 3.0 project.json (no targets)');
      } else {
        // .sb3 ZIP — extract project.json
        const zip   = await JSZip.loadAsync(buf);
        const entry = zip.file('project.json');
        if (!entry) throw new Error('No project.json in ZIP');
        projectJson = JSON.parse(await entry.async('string'));
      }
      ({ aliased, spriteCount } = detectAliasing(projectJson));
    } catch (e) {
      console.log(`⚠  ${e.message.slice(0, 50)}`);
      failed++;
      results.push({ file, status: 'failed', aliased_count: 0, aliased_vars: [], has_bug: false });
      continue;
    }

    if (aliased.length > 0) {
      const names = aliased.map(a => `"${a.name}"`).join(', ');
      console.log(`✘  ${aliased.length} aliased  →  ${names.slice(0, 50)}`);
      withBug++;
    } else {
      console.log(`✔  clean  (${spriteCount} sprites)`);
    }
    results.push({ file, status: aliased.length > 0 ? 'aliased' : 'clean',
      sprite_count: spriteCount, aliased_count: aliased.length,
      aliased_vars: aliased, has_bug: aliased.length > 0 });
  }

  const parsed = files.length - failed;
  const pct = parsed > 0 ? Math.round(withBug / parsed * 100) : 0;
  console.log('\n' + BAR);
  console.log(` RESULTS: ${withBug}/${parsed} have aliasing bug (${pct}%)`);
  console.log(BAR);

  const lines = [
    'SCRATCH ALIASING BUG SCAN — LOCAL FOLDER',
    `Folder: ${folder}   Date: ${new Date().toDateString()}`,
    '',
    `Projects with aliasing bug : ${withBug} / ${parsed} (${pct}%)`,
    `Clean projects             : ${parsed - withBug} / ${parsed} (${100-pct}%)`,
    '',
    'File                                        Sprites  Aliased  Bug',
    '─'.repeat(68),
    ...results.filter(r => r.status !== 'failed').map(r =>
      `${r.file.slice(0,42).padEnd(44)}${String(r.sprite_count).padEnd(9)}${String(r.aliased_count).padEnd(9)}${r.has_bug ? 'YES' : 'no'}`
    ),
  ];
  fs.writeFileSync('aliasing_scan_results.json', JSON.stringify(results, null, 2));
  fs.writeFileSync('aliasing_scan_summary.txt', lines.join('\n'));
  console.log('\nSaved: aliasing_scan_results.json');
  console.log('Saved: aliasing_scan_summary.txt\n');
}

// ── main ──────────────────────────────────────────────────────────────────────
async function main() {
  // Local folder mode — no network needed
  if (SCAN_FOLDER) return scanFolder(SCAN_FOLDER);

  const BAR = '═'.repeat(55);
  console.log(BAR);
  console.log(' SCRATCH ALIASING BUG SCAN');
  console.log(` Mode: ${MODE}   Target: ${COUNT} projects`);
  console.log(BAR);

  const projects = await getProjectList(COUNT, MODE);
  console.log(`\nFetched ${projects.length} project IDs from Scratch API\n`);

  const results = [];
  let scanned = 0, withBug = 0, failed = 0;

  for (const { id, title, author } of projects) {
    const label = `${title}`.slice(0, 38).padEnd(38);
    process.stdout.write(`[${String(scanned + 1).padStart(2)}/${projects.length}] ${label} `);

    let projectJson, spriteCount = 0, aliased = [], status = 'ok';

    try {
      const buf = await downloadSb3(id);
      const zip = await JSZip.loadAsync(buf);
      const entry = zip.file('project.json');
      if (!entry) throw new Error('No project.json in archive');
      const text = await entry.async('string');
      projectJson = JSON.parse(text);
      ({ aliased, spriteCount } = detectAliasing(projectJson));
    } catch (e) {
      console.log(`⚠  ${e.message.slice(0, 50)}`);
      failed++;
      results.push({ id, title, author, status: 'failed', error: e.message, aliased_count: 0, aliased_vars: [], has_bug: false });
      scanned++;
      await sleep(DELAY);
      continue;
    }

    if (aliased.length > 0) {
      const varNames = aliased.map(a => `"${a.name}"`).join(', ');
      console.log(`✘  ${aliased.length} aliased  →  ${varNames.slice(0, 50)}`);
      withBug++;
      status = 'aliased';
    } else {
      console.log(`✔  clean  (${spriteCount} sprite${spriteCount !== 1 ? 's' : ''})`);
    }

    results.push({
      id,
      title,
      author,
      status,
      sprite_count:  spriteCount,
      aliased_count: aliased.length,
      aliased_vars:  aliased,
      has_bug:       aliased.length > 0,
      url:           `https://scratch.mit.edu/projects/${id}/`,
    });

    scanned++;
    await sleep(DELAY);
  }

  // ── summary ────────────────────────────────────────────────────────────────
  const successScanned = scanned - failed;
  const pct = successScanned > 0 ? Math.round(withBug / successScanned * 100) : 0;

  console.log('\n' + BAR);
  console.log(' SCAN COMPLETE');
  console.log(BAR);
  console.log(`Projects targeted : ${COUNT}`);
  console.log(`Successfully parsed: ${successScanned}`);
  console.log(`Download failures : ${failed}`);
  console.log(`WITH aliasing bug : ${withBug}  (${pct}% of parsed)`);
  console.log(`Clean             : ${successScanned - withBug}  (${100 - pct}% of parsed)`);

  // Breakdown: how many aliased vars per buggy project?
  if (withBug > 0) {
    const buggy = results.filter(r => r.has_bug);
    const avgAliased = (buggy.reduce((s, r) => s + r.aliased_count, 0) / buggy.length).toFixed(1);
    console.log(`Avg aliased vars  : ${avgAliased} per affected project`);
    console.log('\nAffected projects:');
    for (const r of buggy) {
      const vars = r.aliased_vars.map(v => v.name).join(', ');
      console.log(`  • [${r.id}] ${r.title.slice(0, 35)} — ${r.aliased_count} var(s): ${vars.slice(0, 60)}`);
    }
  }

  // ── save outputs ───────────────────────────────────────────────────────────
  fs.writeFileSync('aliasing_scan_results.json', JSON.stringify(results, null, 2));

  // Plain-text summary table for dissertation appendix
  const lines = [
    'SCRATCH ALIASING BUG SCAN — RESULTS',
    `Mode: ${MODE}   Scanned: ${successScanned}   Date: ${new Date().toDateString()}`,
    '',
    `Projects with aliasing bug : ${withBug} / ${successScanned} (${pct}%)`,
    `Clean projects             : ${successScanned - withBug} / ${successScanned} (${100 - pct}%)`,
    '',
    'ID          Title                                   Sprites  Aliased  Bug',
    '─'.repeat(72),
    ...results
      .filter(r => r.status !== 'failed')
      .map(r =>
        `${String(r.id).padEnd(12)}${r.title.slice(0, 38).padEnd(40)}${String(r.sprite_count).padEnd(9)}${String(r.aliased_count).padEnd(9)}${r.has_bug ? 'YES' : 'no'}`
      ),
    '',
    'Note: Aliasing = sprites sharing the same variable UUID (Scratch sprite',
    'duplication copies UUIDs verbatim; the VM treats them as one JS object).',
  ];
  fs.writeFileSync('aliasing_scan_summary.txt', lines.join('\n'));

  console.log('\nSaved: aliasing_scan_results.json');
  console.log('Saved: aliasing_scan_summary.txt');
  console.log(BAR);
}

main().catch(e => { console.error('\nFatal:', e); process.exit(1); });
