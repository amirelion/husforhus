// fetchGz must give the same bytes with DecompressionStream and with the fflate fallback (Safari < 16.4),
// for files served without Content-Encoding. Review Focus #4.
import { test, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { gzipSync } from 'node:zlib';
import { fetchGz, gunzip, decoder } from '../gz.js';

const realFetch = globalThis.fetch;
const realDS = globalThis.DecompressionStream;
afterEach(() => { globalThis.fetch = realFetch; globalThis.DecompressionStream = realDS; });

// Serve bytes the way python's http.server and Cloudflare do: as a plain file, no Content-Encoding.
const serve = files => {
  globalThis.fetch = async url => files[url]
    ? new Response(files[url], { status: 200, headers: { 'content-type': 'application/gzip' } })
    : new Response('missing', { status: 404 });
};
const withoutDS = async fn => {
  delete globalThis.DecompressionStream;
  try { return await fn(); } finally { globalThis.DecompressionStream = realDS; }
};
const bytes = b => Buffer.from(new Uint8Array(b));

const tileGz = readFileSync(new URL('./fixtures/tile_v1.bin.gz', import.meta.url));
const tileRaw = readFileSync(new URL('./fixtures/tile_v1.bin', import.meta.url));
// A larger, compressible input so the inflaters go through dynamic Huffman blocks, like a real pack.
const big = Buffer.alloc(3_000_000);
for (let i = 0; i < big.length; i++) big[i] = (i * 2654435761 >>> 24) & (i % 7 === 0 ? 0xff : 0x0f);
const bigGz = gzipSync(big, { level: 9 });

test('the native path is used when DecompressionStream exists', () => {
  assert.equal(decoder(), 'native');
});

test('fixture: DecompressionStream and fflate give identical bytes', async () => {
  serve({ 'data/v1/tile_v1.bin.gz': tileGz });
  const native = await fetchGz('data/v1/tile_v1.bin.gz');
  const fallback = await withoutDS(async () => {
    assert.equal(decoder(), 'fflate');
    return fetchGz('data/v1/tile_v1.bin.gz');
  });
  assert.ok(bytes(native).equals(tileRaw));
  assert.ok(bytes(fallback).equals(tileRaw));
});

test('3 MB buffer: both paths match the original', async () => {
  serve({ 'pack0.bin.gz': bigGz });
  const native = await fetchGz('pack0.bin.gz');
  const fallback = await withoutDS(() => fetchGz('pack0.bin.gz'));
  assert.equal(native.byteLength, big.length);
  assert.ok(bytes(native).equals(big));
  assert.ok(bytes(fallback).equals(big));
});

test('a body the server already unpacked passes through unchanged', async () => {
  const out = await gunzip(tileRaw.buffer.slice(tileRaw.byteOffset, tileRaw.byteOffset + tileRaw.byteLength));
  assert.ok(bytes(out).equals(tileRaw));
});

test('a dropped connection is retried once', async () => {
  let calls = 0;
  globalThis.fetch = async () => {
    if (++calls === 1) throw new TypeError('Failed to fetch');
    return new Response(tileGz, { status: 200 });
  };
  const out = await fetchGz('data/v1/tile_v1.bin.gz');
  assert.equal(calls, 2);
  assert.ok(bytes(out).equals(tileRaw));
});

test('HTTP errors reject with the URL', async () => {
  serve({});
  await assert.rejects(fetchGz('data/v1/nope.bin.gz'), /nope\.bin\.gz: HTTP 404/);
});

test('a download stopped by its signal is not retried; the signal reaches fetch', async () => {
  const ctl = new AbortController();
  const seen = [];
  globalThis.fetch = async (url, opts) => {
    seen.push(opts?.signal);
    ctl.abort();
    throw new DOMException('The operation was aborted.', 'AbortError');
  };
  await assert.rejects(fetchGz('data/v1/tile_v1.bin.gz', 2, ctl.signal), /aborted/);
  assert.deepEqual(seen, [ctl.signal]);
});
