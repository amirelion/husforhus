import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { parseAllowlist, parseLeaks, scan, main, publicPath, publicText } from './export.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const allowText = fs.readFileSync(path.join(HERE, 'allowlist.txt'), 'utf8');
const rules = parseLeaks(fs.readFileSync(path.join(HERE, 'leaks.txt'), 'utf8'));

// Built at runtime so this file doesn't trip the leak scan itself.
const NAME = 'Am' + 'ir';
const AT = '@';

function tmp() { return fs.mkdtempSync(path.join(os.tmpdir(), 'export-test-')); }
function write(root, file, text) {
  fs.mkdirSync(path.dirname(path.join(root, file)), { recursive: true });
  fs.writeFileSync(path.join(root, file), text);
}

test('allow-list selects and excludes', () => {
  const m = parseAllowlist(allowText);
  for (const f of ['pipeline/run.py', 'web/index.html', 'web/js/a/b.mjs', 'scripts/serve.py',
    'scripts/public/export.mjs', '.github/workflows/ci.yml', 'LICENSE', 'docs/accuracy.md', 'docs/data-sources.md',
    'docs-public/README.md', '.gitignore', '.nvmrc', 'wrangler.jsonc'])
    assert.ok(m(f), f);
  for (const f of ['web/data/x.json', 'web/data/a/b.pmtiles', 'scripts/public/leaks.txt', 'docs/deploy.md',
    'docs/research/x.md', '.claude/launch.json', 'README.mdx', 'xpipeline/a.py', 'README.md',
    'docs/decisions.md', 'docs/status.md', 'docs/out' + 'reach.md', 'docs-public/notes/x.md'])
    assert.ok(!m(f), f);
});

test('planted email and name are caught; LICENSE copyright allowed', () => {
  const root = tmp();
  write(root, 'a.md', 'ok\nmail me at someone' + AT + 'mailhost.se\n');
  write(root, 'b.py', '# by ' + NAME + '\n');
  write(root, 'LICENSE', `MIT\nCopyright (c) 2026 ${NAME} Elion\n${NAME} says hi\n`);
  const hits = scan(root, ['a.md', 'b.py', 'LICENSE'], rules);
  assert.deepEqual(hits, [
    { file: 'a.md', line: 2, rule: 'email' },
    { file: 'b.py', line: 1, rule: 'owner-name' },
    { file: 'LICENSE', line: 3, rule: 'owner-name' },
  ]);
  assert.deepEqual(scan(root, ['LICENSE'], rules).filter((h) => h.line === 2), []);
});

test('email rule ignores reserved example domains', () => {
  const root = tmp();
  write(root, 'c.py', ['a' + AT + 'example.com', 'b' + AT + 'example.org', 'c' + AT + 'sub.example.net',
    'd' + AT + 'example.org.evil.se', 'e' + AT + 'notexample.com'].join('\n'));
  assert.deepEqual(scan(root, ['c.py'], rules).map((h) => h.line), [4, 5]);
});

test('copyright check in tests/test_repo.py allowed; URL logins are not emails', () => {
  const root = tmp();
  write(root, 'tests/test_repo.py', `    assert "Copyright (c) 2026 ${NAME} Elion" in text\n# ask ${NAME}\n`);
  write(root, 'u.py', 'x = "https://user:pw' + AT + 'dl1.lantmateriet.se/a.tif"\ny = "me' + AT + 'mailhost.se"\n');
  assert.deepEqual(scan(root, ['tests/test_repo.py', 'u.py'], rules), [
    { file: 'tests/test_repo.py', line: 2, rule: 'owner-name' },
    { file: 'u.py', line: 2, rule: 'email' },
  ]);
});

// Plan 4b's decision 2 (answered 2026-10-17): About names the maker as the GDPR controller and gives the project's own
// address. Both come from one constant each in pipeline/city.py, the only lines allowed to hold them.
test('the maker and the contact are allowed on their own constants in pipeline/city.py, nowhere else', () => {
  const root = tmp();
  const maker = `MAKER = "${NAME} Elion"`, contact = 'CONTACT = "hej' + AT + 'husforhus.se"';
  write(root, 'pipeline/city.py', [maker, contact, `# ${NAME} decided`, 'OTHER = "hej' + AT + 'husforhus.se"',
    `MAKER = "${NAME} Elion"  # and more`, 'CONTACT = "x' + AT + 'mailhost.se"'].join('\n'));
  write(root, 'web/about.js', `const who = "${NAME} Elion";\n${contact}\n`);
  write(root, 'pipeline/other.py', `${maker}\n${contact}\n`);
  assert.deepEqual(scan(root, ['pipeline/city.py', 'web/about.js', 'pipeline/other.py'], rules), [
    { file: 'pipeline/city.py', line: 3, rule: 'owner-name' },
    { file: 'pipeline/city.py', line: 4, rule: 'email' },
    { file: 'pipeline/city.py', line: 5, rule: 'owner-name' },
    { file: 'pipeline/city.py', line: 6, rule: 'email' },
    { file: 'web/about.js', line: 1, rule: 'owner-name' },
    { file: 'web/about.js', line: 2, rule: 'email' },
    { file: 'pipeline/other.py', line: 1, rule: 'owner-name' },
    { file: 'pipeline/other.py', line: 2, rule: 'email' },
  ]);
});

test('--out refuses a path inside the repo, accepts outside', () => {
  const repo = tmp();
  write(repo, 'scripts/public/allowlist.txt', 'README.md\n');
  write(repo, 'scripts/public/leaks.txt', 'email\t[a-z0-9.]+@[a-z0-9.]+\\.[a-z]{2,}\n');
  write(repo, 'README.md', 'clean\n');
  execFileSync('git', ['init', '-q'], { cwd: repo });
  execFileSync('git', ['add', '.'], { cwd: repo });
  const err = console.error, log = console.log;
  console.error = console.log = () => {};
  try {
    assert.equal(main(['--out', path.join(repo, 'export')], repo), 2);
    assert.ok(!fs.existsSync(path.join(repo, 'export')));
    const out = path.join(tmp(), 'pub');
    assert.equal(main(['--out', out], repo), 0);
    assert.ok(fs.existsSync(path.join(out, 'README.md')));
    assert.ok(!fs.existsSync(path.join(out, 'scripts/public/leaks.txt')));
  } finally { console.error = err; console.log = log; }
});

test('docs-public files land at the root with their ../ links fixed', () => {
  assert.equal(publicPath('docs-public/README.md'), 'README.md');
  assert.equal(publicPath('pipeline/run.py'), 'pipeline/run.py');
  assert.equal(publicText('docs-public/README.md', Buffer.from('see [LICENSE](../LICENSE) and [x](HOW.md)')).toString(),
    'see [LICENSE](LICENSE) and [x](HOW.md)');
  assert.equal(publicText('web/a.md', Buffer.from('[a](../b)')).toString(), '[a](../b)');
});
