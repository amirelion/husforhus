// Fetching the pipeline's *.bin.gz files. They are served as plain files (no Content-Encoding), so the page
// unpacks them itself: with DecompressionStream where the browser has it, otherwise with the vendored fflate
// (Safari before 16.4). A file the server or browser already unpacked passes through unchanged.

export const decoder = () => (typeof DecompressionStream === 'function' ? 'native' : 'fflate');

export async function gunzip(buf) {
  const u8 = new Uint8Array(buf);
  if (u8.length < 2 || u8[0] !== 0x1f || u8[1] !== 0x8b) return buf;
  if (decoder() === 'native') {
    const stream = new Blob([u8]).stream().pipeThrough(new DecompressionStream('gzip'));
    return new Response(stream).arrayBuffer();
  }
  const { gunzipSync } = await import('./vendor/fflate.js');
  const out = gunzipSync(u8);
  return out.byteOffset === 0 && out.byteLength === out.buffer.byteLength ? out.buffer : out.slice().buffer;
}

// A dropped connection (fetch rejects) is retried once; an HTTP error is not, nor a download stopped by `signal` (an
// AbortSignal: it stops the request and the body's read alike). progress, when given, is called on the answer and on
// each chunk of the body as it arrives (web/terrain.js withTimeout's sign of life).
export async function fetchGz(url, tries = 2, signal = undefined, progress = undefined) {
  let r;
  try {
    r = await fetch(url, { signal });
  } catch (e) {
    if (tries <= 1 || signal?.aborted) throw e;
    await new Promise(done => setTimeout(done, 400));
    return fetchGz(url, tries - 1, signal, progress);
  }
  if (!r.ok) throw new Error(`${url}: HTTP ${r.status}`);
  if (!progress || !r.body?.getReader) return gunzip(await r.arrayBuffer());
  progress();
  const reader = r.body.getReader(), parts = [];
  let n = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    parts.push(value);
    n += value.byteLength;
    progress();
  }
  const all = new Uint8Array(n);
  let o = 0;
  for (const p of parts) { all.set(p, o); o += p.byteLength; }
  return gunzip(all.buffer);
}
