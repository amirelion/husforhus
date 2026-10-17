#!/usr/bin/env node
// Public export: select allow-listed tracked files, copy them, and scan for leaks.
// Usage: node scripts/public/export.mjs --check | --out <dir>
// Never pushes or creates repositories.
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
export const REPO = path.resolve(HERE, '..', '..');

export function globToRegExp(glob) {
  let re = '';
  for (let i = 0; i < glob.length; i++) {
    const c = glob[i];
    if (c === '*' && glob[i + 1] === '*') {
      i++;
      if (glob[i + 1] === '/') { i++; re += '(?:.*/)?'; } else re += '.*';
    } else if (c === '*') re += '[^/]*';
    else if (c === '?') re += '[^/]';
    else re += c.replace(/[.+^${}()|[\]\\]/g, '\\$&');
  }
  return new RegExp(`^${re}$`);
}

export function parseAllowlist(text) {
  const include = [], exclude = [];
  for (const raw of text.split('\n')) {
    const line = raw.trim();
    if (!line || line.startsWith('#')) continue;
    if (line.startsWith('!')) exclude.push(globToRegExp(line.slice(1)));
    else include.push(globToRegExp(line));
  }
  return (file) => include.some((r) => r.test(file)) && !exclude.some((r) => r.test(file));
}

export function parseLeaks(text) {
  return text.split('\n').filter((l) => l.trim() && !l.startsWith('#')).map((l) => {
    const tab = l.indexOf('\t');
    if (tab < 0) throw new Error(`bad leak rule (needs name<TAB>regex): ${l}`);
    return { name: l.slice(0, tab), re: new RegExp(l.slice(tab + 1), 'i') };
  });
}

// The owner's name is allowed only on LICENSE's copyright lines, in the test that checks them, and as the maker
// (Plan 4b's decision 2, answered 2026-10-17: About names the maker as the GDPR controller) on pipeline/city.py's
// MAKER line alone; the project's own address only on its CONTACT line. Nothing else on those lines.
function allowed(rule, file, line) {
  if (file === 'pipeline/city.py') {
    if (rule.name === 'owner-name' && /^MAKER = "[^"]+"$/.test(line)) return true;
    if (rule.name === 'email' && /^CONTACT = "[a-z]+@husforhus\.se"$/.test(line)) return true;
  }
  if (rule.name !== 'owner-name') return false;
  if (file === 'LICENSE') return /^\s*copyright\b/i.test(line);
  return file === 'tests/test_repo.py' && /"Copyright \(c\) \d{4} /.test(line);
}

export function scan(root, files, rules) {
  const hits = [];
  for (const file of files) {
    const buf = fs.readFileSync(path.join(root, file));
    if (buf.includes(0)) continue; // binary
    buf.toString('utf8').split('\n').forEach((line, i) => {
      for (const rule of rules) {
        if (rule.re.test(line) && !allowed(rule, file, line)) hits.push({ file, line: i + 1, rule: rule.name });
      }
    });
  }
  return hits;
}

// docs-public/X.md becomes X.md at the public repo's root, its "../" links rewritten to match.
export function publicPath(file) {
  return file.startsWith('docs-public/') ? file.slice('docs-public/'.length) : file;
}
export function publicText(file, buf) {
  return file.startsWith('docs-public/') ? Buffer.from(buf.toString('utf8').replaceAll('](../', '](')) : buf;
}

export function selectFiles(repo, allowText) {
  const match = parseAllowlist(allowText);
  const tracked = execFileSync('git', ['ls-files', '-z'], { cwd: repo, encoding: 'utf8' }).split('\0').filter(Boolean);
  return tracked.filter((f) => match(f) && fs.existsSync(path.join(repo, f)));
}

export function isInside(parent, child) {
  const rel = path.relative(fs.realpathSync(parent), realish(child));
  return rel === '' || (!rel.startsWith('..') && !path.isAbsolute(rel));
}
function realish(p) {
  // Resolve symlinks of the nearest existing ancestor (dir may not exist yet).
  let cur = path.resolve(p), rest = [];
  while (!fs.existsSync(cur)) { rest.unshift(path.basename(cur)); cur = path.dirname(cur); }
  return path.join(fs.realpathSync(cur), ...rest);
}

function report(hits, nFiles) {
  for (const h of hits) console.log(`${h.file}:${h.line}: ${h.rule}`);
  const byRule = {}, files = new Set();
  for (const h of hits) { byRule[h.rule] = (byRule[h.rule] || 0) + 1; files.add(h.file); }
  console.log(`\nScanned ${nFiles} files: ${hits.length} hits in ${files.size} files.`);
  for (const [r, n] of Object.entries(byRule).sort()) console.log(`  ${r}: ${n}`);
  return hits.length ? 1 : 0;
}

export function main(argv, repo = REPO) {
  const allowText = fs.readFileSync(path.join(repo, 'scripts/public/allowlist.txt'), 'utf8');
  const rules = parseLeaks(fs.readFileSync(path.join(repo, 'scripts/public/leaks.txt'), 'utf8'));
  const files = selectFiles(repo, allowText);
  if (argv[0] === '--check') return report(scan(repo, files, rules), files.length);
  if (argv[0] === '--out' && argv[1]) {
    const out = path.resolve(argv[1]);
    if (isInside(repo, out)) { console.error(`refusing --out inside the repo: ${out}`); return 2; }
    const dests = files.map(publicPath);
    const twice = dests.filter((d, i) => dests.indexOf(d) !== i);
    if (twice.length) { console.error(`two files map to: ${twice.join(', ')}`); return 2; }
    files.forEach((f, i) => {
      fs.mkdirSync(path.dirname(path.join(out, dests[i])), { recursive: true });
      fs.writeFileSync(path.join(out, dests[i]), publicText(f, fs.readFileSync(path.join(repo, f))));
    });
    console.log(`Copied ${files.length} files to ${out}`);
    return report(scan(out, dests, rules), files.length);
  }
  console.error('usage: export.mjs --check | --out <dir>');
  return 2;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  process.exitCode = main(process.argv.slice(2));
}
