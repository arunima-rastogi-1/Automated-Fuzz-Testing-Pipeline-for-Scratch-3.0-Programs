/**
 * download_projects.js
 * Downloads Scratch .sb3 files for aliasing-bug scanning.
 *
 * Modes:
 *   node download_projects.js                  -- download IDs from ids.txt
 *   node download_projects.js --trending [N]   -- fetch N trending project IDs (default 40),
 *                                                 save to ids.txt, then download
 *   node download_projects.js --debug          -- extra diagnostic output
 *
 * Output: scan_projects/{id}.sb3
 */

const https = require('https');
const http  = require('http');
const fs    = require('fs');
const path  = require('path');

const IDS_FILE = 'ids.txt';
const OUT_DIR  = 'scan_projects';
const DELAY_MS = 600;
const TIMEOUT  = 15000;

const DEBUG    = process.argv.includes('--debug');
const TRENDING = process.argv.includes('--trending');
const COUNT    = (() => {
  const idx = process.argv.indexOf('--trending');
  if (idx !== -1 && process.argv[idx+1] && /^\d+$/.test(process.argv[idx+1]))
    return parseInt(process.argv[idx+1], 10);
  return 40;
})();

// ── HTTP helper ────────────────────────────────────────────────────────────────
function fetchBuf(url) {
  return new Promise((resolve, reject) => {
    const lib = url.startsWith('https') ? https : http;
    const req = lib.get(url, {
      headers: { 'User-Agent': 'Mozilla/5.0 ScratchResearch/1.0' }
    }, res => {
      if ([301,302,303,307,308].includes(res.statusCode) && res.headers.location)
        return resolve(fetchBuf(res.headers.location));
      if (res.statusCode !== 200) {
        res.resume();
        return reject(new Error(`HTTP ${res.statusCode} from ${url}`));
      }
      const chunks = [];
      res.on('data', c => chunks.push(c));
      res.on('end',  () => resolve(Buffer.concat(chunks)));
      res.on('error', reject);
    });
    req.setTimeout(TIMEOUT, () => { req.destroy(); reject(new Error('Timeout')); });
    req.on('error', reject);
  });
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

// ── Detect format ──────────────────────────────────────────────────────────────
function isZip(buf) { return buf.length > 4 && buf[0] === 0x50 && buf[1] === 0x4b; }

// Returns 'sb3zip' | 'sb3json' | 'sb2' | 'unknown'
function classifyBuf(buf) {
  if (isZip(buf)) return 'sb3zip';
  const text = buf.toString('utf8', 0, Math.min(buf.length, 300));
  if (text.includes('"targets"')) return 'sb3json';   // Scratch 3.0 project.json
  if (text.includes('"objName"')) return 'sb2';       // Scratch 2.0
  return 'unknown';
}

// ── Fetch project IDs — accumulates from all reachable sources ────────────────
async function fetchTrendingIds(count) {
  const seen = new Set();
  const ids  = [];

  function add(list) {
    for (const id of list) {
      const s = String(id || '');
      if (/^\d{6,}$/.test(s) && !seen.has(s)) { seen.add(s); ids.push(s); }
    }
  }

  // Source 1: direct Scratch API explore
  console.log('  [1] Scratch API explore…');
  try {
    const url  = `https://api.scratch.mit.edu/explore/projects?limit=40&offset=0&language=en&mode=trending`;
    const list = JSON.parse((await fetchBuf(url)).toString());
    if (Array.isArray(list)) add(list.map(p => p.id));
  } catch (e) { console.log(`      failed: ${e.message}`); }
  console.log(`      total IDs so far: ${ids.length}`);

  // Source 2: Scratch featured endpoint — all sections
  if (ids.length < count) {
    console.log('  [2] Scratch featured (all sections)…');
    try {
      const data = JSON.parse((await fetchBuf('https://api.scratch.mit.edu/proxy/featured')).toString());
      for (const key of ['community_featured_projects','community_newest_projects',
                         'community_most_loved_projects','community_most_remixed_projects',
                         'scratch_design_studio','curator_top_projects']) {
        add((data[key] || []).map(p => p.id || p.project_id));
      }
    } catch (e) { console.log(`      failed: ${e.message}`); }
    console.log(`      total IDs so far: ${ids.length}`);
  }

  // Source 3: TurboWarp studio proxy — paginate several active studios
  if (ids.length < count) {
    console.log('  [3] TurboWarp studio proxy (paginated)…');
    const studioIds = ['27205812','32774952','29799849','1299102','25798780','28230688'];
    for (const sid of studioIds) {
      if (ids.length >= count) break;
      for (let off = 0; ids.length < count; off += 40) {
        try {
          const url  = `https://trampoline.turbowarp.org/proxy/studios/${sid}/projects?limit=40&offset=${off}`;
          const list = JSON.parse((await fetchBuf(url)).toString());
          if (!Array.isArray(list) || list.length === 0) break;
          add(list.map(p => p.id));
          await sleep(300);
          if (list.length < 40) break;
        } catch (_) { break; }
      }
    }
    console.log(`      total IDs so far: ${ids.length}`);
  }

  // Source 4: scrape the Scratch explore page
  if (ids.length < count) {
    console.log('  [4] Scratch explore webpage…');
    try {
      const html = (await fetchBuf('https://scratch.mit.edu/explore/projects/all/')).toString();
      add([...html.matchAll(/\/projects\/(\d{7,})\//g)].map(m => m[1]));
    } catch (e) { console.log(`      failed: ${e.message}`); }
    console.log(`      total IDs so far: ${ids.length}`);
  }

  return ids.slice(0, count);
}

// ── Step 1: get project_token from trampoline metadata ─────────────────────────
async function getToken(id) {
  const url  = `https://trampoline.turbowarp.org/proxy/projects/${id}`;
  const buf  = await fetchBuf(url);
  const meta = JSON.parse(buf.toString());
  if (DEBUG) {
    console.log(`\n    [debug] keys: ${Object.keys(meta).join(', ')}`);
    console.log(`    [debug] project_token: ${meta.project_token ? meta.project_token.slice(0,30)+'...' : 'NOT PRESENT'}`);
  }
  if (!meta.project_token) throw new Error('No project_token in trampoline response');
  return { token: meta.project_token, title: meta.title || `project-${id}` };
}

// ── Step 2: download and classify ─────────────────────────────────────────────
async function downloadOne(id) {
  let token, title;
  try {
    ({ token, title } = await getToken(id));
  } catch (e) {
    if (DEBUG) console.log(`\n    [debug] token error: ${e.message}`);
    return { err: e.message };
  }

  const url = `https://projects.scratch.mit.edu/${id}?token=${token}`;
  try {
    const buf  = await fetchBuf(url);
    const kind = classifyBuf(buf);
    if (DEBUG) console.log(`\n    [debug] CDN ${buf.length} bytes, kind=${kind}`);
    if (kind === 'sb3zip')  return { buf, title, ext: '.sb3' };
    if (kind === 'sb3json') return { buf, title, ext: '.json' };   // project.json directly
    if (kind === 'sb2')     return { sb2: true, title };
    return { err: `unexpected format (first 8 bytes: ${buf.slice(0,8).toString('hex')})` };
  } catch (e) {
    if (DEBUG) console.log(`\n    [debug] CDN error: ${e.message}`);
    return { err: e.message };
  }
}

// ── Main ───────────────────────────────────────────────────────────────────────
async function main() {
  const SEP = '='.repeat(52);
  const BAR = '-'.repeat(52);
  console.log(SEP);
  console.log(' SCRATCH PROJECT DOWNLOADER');
  console.log(SEP);

  let ids = [];

  if (TRENDING) {
    console.log(`\n  Fetching ${COUNT} trending Scratch 3.0 project IDs…\n`);
    ids = await fetchTrendingIds(COUNT);
    if (ids.length === 0) {
      console.error('  ERROR: could not fetch any IDs from the explore API.'); process.exit(1);
    }
    fs.writeFileSync(IDS_FILE, ids.join('\n') + '\n');
    console.log(`  Saved ${ids.length} IDs to ${IDS_FILE}\n`);
  } else {
    if (!fs.existsSync(IDS_FILE)) {
      console.error(`\n  ${IDS_FILE} not found. Run with --trending to fetch IDs automatically.\n`);
      process.exit(1);
    }
    ids = fs.readFileSync(IDS_FILE, 'utf8')
      .split('\n')
      .map(l => { const m = l.trim().match(/(\d{5,})/); return m ? m[1] : null; })
      .filter(Boolean);
    if (ids.length === 0) {
      console.error('\n  No valid IDs found in ids.txt\n'); process.exit(1);
    }
  }

  console.log(`  Processing ${ids.length} project IDs`);
  if (!fs.existsSync(OUT_DIR)) fs.mkdirSync(OUT_DIR);
  console.log(`  Saving .sb3 files to ./${OUT_DIR}/\n`);
  console.log(BAR);

  let ok = 0, sb2 = 0, fail = 0;

  for (let i = 0; i < ids.length; i++) {
    const id   = ids[i];
    const dest = path.join(OUT_DIR, `${id}.sb3`);
    process.stdout.write(`[${String(i+1).padStart(2)}/${ids.length}] ${id}  `);

    // Check for both .sb3 and .json versions already saved
    const destJson = path.join(OUT_DIR, `${id}.json`);
    if (fs.existsSync(dest) || fs.existsSync(destJson)) {
      console.log('(already exists, skipping)');
      ok++; continue;
    }

    const result = await downloadOne(id);

    if (result.buf) {
      const savePath = path.join(OUT_DIR, `${id}${result.ext}`);
      fs.writeFileSync(savePath, result.buf);
      const kb = (result.buf.length/1024).toFixed(0);
      const label = result.ext === '.json' ? 'JSON(sb3)' : 'ZIP(sb3)';
      console.log(`OK  ${kb} KB  [${label}]  "${result.title}"`);
      ok++;
    } else if (result.sb2) {
      console.log(`SKIP  Scratch 2.0 format  "${result.title}"`);
      sb2++;
    } else {
      console.log(`FAIL  ${result.err}`);
      fail++;
    }

    await sleep(DELAY_MS);
  }

  console.log(BAR);
  console.log(`\n  Saved: ${ok}   Scratch 2.0 (skipped): ${sb2}   Errors: ${fail}`);

  if (ok > 0) {
    console.log(`\n  Next step:`);
    console.log(`  node scratch_aliasing_scan.js --scan-folder ${OUT_DIR}\n`);
  } else if (sb2 === ids.length) {
    console.log(`\n  All projects were Scratch 2.0 — try: node download_projects.js --trending\n`);
  }
}

main().catch(e => { console.error('\nFatal:', e); process.exit(1); });
