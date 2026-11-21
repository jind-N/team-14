// Minimal ZIP reader. No libraries, no network: works offline in modern browsers.
// Limits: no ZIP64 (files over 4 GB), no encryption. Fine for typical data exports under 4 GB;
// very large exports may need a streaming reader later.

async function inflateRaw(bytes) {
  const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream('deflate-raw'));
  return new Uint8Array(await new Response(stream).arrayBuffer());
}

async function readZip(arrayBuffer) {
  const view = new DataView(arrayBuffer);
  const bytes = new Uint8Array(arrayBuffer);

  let eocd = -1;
  for (let i = bytes.length - 22; i >= Math.max(0, bytes.length - 65557); i--) {
    if (view.getUint32(i, true) === 0x06054b50) { eocd = i; break; }
  }
  if (eocd < 0) throw new Error('This does not look like a ZIP file.');

  const count = view.getUint16(eocd + 10, true);
  let p = view.getUint32(eocd + 16, true);
  const decoder = new TextDecoder();
  const entries = [];

  for (let n = 0; n < count; n++) {
    if (view.getUint32(p, true) !== 0x02014b50) throw new Error('ZIP index is damaged.');
    const method = view.getUint16(p + 10, true);
    const compSize = view.getUint32(p + 20, true);
    const size = view.getUint32(p + 24, true);
    const nameLen = view.getUint16(p + 28, true);
    const extraLen = view.getUint16(p + 30, true);
    const commentLen = view.getUint16(p + 32, true);
    const localOffset = view.getUint32(p + 42, true);
    const name = decoder.decode(bytes.subarray(p + 46, p + 46 + nameLen));
    p += 46 + nameLen + extraLen + commentLen;

    if (name.endsWith('/')) continue;

    entries.push({
      name,
      size,
      async read() {
        const lh = localOffset;
        if (view.getUint32(lh, true) !== 0x04034b50) throw new Error('Bad entry: ' + name);
        const start = lh + 30 + view.getUint16(lh + 26, true) + view.getUint16(lh + 28, true);
        const data = bytes.subarray(start, start + compSize);
        if (method === 0) return data;
        if (method === 8) return inflateRaw(data);
        throw new Error('Unsupported compression in ' + name);
      },
      async text() { return decoder.decode(await this.read()); },
      async json() { return JSON.parse(await this.text()); },
    });
  }
  return entries;
}

if (typeof module !== 'undefined') module.exports = { readZip };
