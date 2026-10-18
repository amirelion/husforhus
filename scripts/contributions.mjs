// Readers' accepted reports into the data, and back: the owner's step between the triage page (web/admin/) and a
// data release. Uses wrangler's own login (npx wrangler login), not the admin API behind Cloudflare Access.
//   node scripts/contributions.mjs pull                 every accepted contribution -> pipeline/contributions.csv
//   node scripts/contributions.mjs applied v20261018-x  the CSV's not yet applied rows: applied in that data version,
//                                                       their reports "fixed", their GitHub issues closed (gh)
// pull reads D1 (never the email column), fetches each photo from R2 into a temporary folder and hands the rows to
// `uv run python -m pipeline.contributions resolve`, which finds each footprint's uuid, places the photo in
// web/data/photos/ and writes the CSV (all rows, applied or not, so the CSV is always the whole list). A refused row
// stops it with exit code 1 and names the reason. Add --local to use wrangler's local D1/R2 (wrangler dev).
import { execFileSync } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const DB = 'husforhus-reports', BUCKET = 'husforhus-report-photos';
const args = process.argv.slice(2);
const where = args.includes('--local') ? '--local' : '--remote';
const [cmd, version] = args.filter(a => a !== '--local');

function usage(message) {
  console.error(`contributions.mjs: ${message}`);
  process.exit(2);
}
const wrangler = (...a) => execFileSync('npx', ['wrangler', ...a], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'inherit'] });
const sql = command => JSON.parse(wrangler('d1', 'execute', DB, where, '--json', '--command', command))[0].results;

if (cmd === 'pull') {
  const rows = sql(`SELECT c.id, c.report_id, c.kind, c.value, c.public_note, c.replaces_register, c.gid, c.data_version,
    c.x, c.z, r.issue_url, r.photo_key FROM contributions c JOIN reports r ON r.id = c.report_id ORDER BY c.id`);
  const dir = mkdtempSync(join(tmpdir(), 'hfh-photos-'));
  try {
    for (const r of rows) {
      if (r.kind === 'photo' && r.photo_key) {
        r.photo_file = join(dir, `HFH-${r.report_id}`);
        wrangler('r2', 'object', 'get', `${BUCKET}/${r.photo_key}`, where, '--file', r.photo_file);
      }
      delete r.photo_key;
    }
    execFileSync('uv', ['run', 'python', '-m', 'pipeline.contributions', 'resolve'],
      { input: JSON.stringify(rows), stdio: ['pipe', 'inherit', 'inherit'] });
  } catch (e) {
    process.exitCode = e.status || 1;
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
} else if (cmd === 'applied') {
  if (!/^v\d{8}(-[a-z0-9]+)?$/.test(version || '')) usage('applied needs the data version, like v20261018-p4l');
  // Only what the release carried: the CSV's refs (a report accepted after the pull waits for the next release).
  const ids = [...readFileSync('pipeline/contributions.csv', 'utf8').matchAll(/^HFH-(\d+),/gm)].map(m => Number(m[1]));
  const now = new Date().toISOString();
  const these = `report_id IN (${ids.join(',') || 'NULL'}) AND applied_version IS NULL`;
  const issues = sql(`SELECT DISTINCT r.id, r.issue_url FROM contributions c JOIN reports r ON r.id = c.report_id WHERE c.${these}`);
  // Reports first, while applied_version still tells which contributions are new; closed_at kept if already closed
  sql(`UPDATE reports SET status = 'fixed', closed_at = COALESCE(closed_at, '${now}')
    WHERE id IN (SELECT report_id FROM contributions WHERE ${these})`);
  const done = sql(`UPDATE contributions SET applied_version = '${version}' WHERE ${these} RETURNING report_id`);
  console.log(`${done.length} contributions applied in ${version}: ${done.map(r => `HFH-${r.report_id}`).join(', ') || 'none'}`);
  for (const { id, issue_url: url } of issues) {
    if (!/^https:\/\/github\.com\/[^/]+\/[^/]+\/issues\/\d+$/.test(url || '')) continue;
    try {
      execFileSync('gh', ['issue', 'close', url, '--comment', `Applied in data ${version}.`], { stdio: ['ignore', 'ignore', 'inherit'] });
      console.log(`HFH-${id}: closed ${url}`);
    } catch { console.error(`HFH-${id}: could not close ${url} (gh auth?): close it by hand`); }
  }
} else {
  usage('pull | applied <version> [--local]');
}
