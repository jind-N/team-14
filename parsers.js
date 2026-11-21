// Parsers turn raw export files into ONE common shape:
//   { platform, category, item, time, sensitivity }
// Everything runs locally. No network calls.

const SENSITIVE_WORDS = ['symptom', 'pain', 'anxiety', 'loan', 'credit', 'salary', 'rent', 'therapy', 'doctor'];

function localParts(isoString, tzOffsetMin) {
  const d = new Date(new Date(isoString).getTime() + tzOffsetMin * 60000);
  return { hour: d.getUTCHours(), dow: d.getUTCDay(), date: d.toISOString().slice(0, 10) };
}

// Group points into ~200 m grid cells and return the busiest one.
function busiestCell(points) {
  const CELL = 0.002;
  const cells = new Map();
  for (const p of points) {
    const key = Math.round(p.lat / CELL) + ',' + Math.round(p.lng / CELL);
    const c = cells.get(key) || { n: 0, lat: 0, lng: 0 };
    c.n++; c.lat += p.lat; c.lng += p.lng;
    cells.set(key, c);
  }
  let best = null;
  for (const c of cells.values()) if (!best || c.n > best.n) best = c;
  if (!best) return null;
  return { lat: best.lat / best.n, lng: best.lng / best.n, count: best.n, share: best.n / points.length };
}

async function parseGoogle(entries, opts = {}) {
  const tz = opts.tzOffsetMin ?? -new Date().getTimezoneOffset();
  const result = { items: [], points: [], home: null, work: null, notes: [], stats: {}, topSearches: [] };

  const records = entries.find(e => /Records\.json$/i.test(e.name));
  const phone = entries.find(e => /(Timeline|location-history)\.json$/i.test(e.name));
  const semantic = entries.filter(e => /Semantic Location History/i.test(e.name));

  if (records) {
    const data = await records.json();
    const locs = data.locations || [];
    for (const l of locs) {
      const t = l.timestamp || (l.timestampMs ? new Date(+l.timestampMs).toISOString() : null);
      if (!t || l.latitudeE7 == null) continue;
      const { hour, dow } = localParts(t, tz);
      result.points.push({ lat: l.latitudeE7 / 1e7, lng: l.longitudeE7 / 1e7, hour, dow, t });
    }
    result.notes.push('Format found: Records.json (raw GPS points)');
  } else if (phone) {
    result.notes.push('Format found: phone Timeline export. Not supported yet in this version.');
  } else if (semantic.length) {
    result.notes.push('Format found: Semantic Location History only. Not supported yet in this version.');
  }

  const pts = result.points;
  if (pts.length) {
    const night = pts.filter(p => p.hour >= 22 || p.hour < 6);
    const day = pts.filter(p => p.dow >= 1 && p.dow <= 5 && p.hour >= 10 && p.hour < 16);
    result.home = busiestCell(night);
    result.work = busiestCell(day);
    const times = pts.map(p => p.t).sort();
    result.stats = { points: pts.length, from: times[0].slice(0, 10), to: times[times.length - 1].slice(0, 10) };

    if (result.home) result.items.push({ platform: 'Google', category: 'location',
      item: 'Likely home area', time: result.stats.to, sensitivity: 'high' });
    if (result.work) result.items.push({ platform: 'Google', category: 'location',
      item: 'Likely workplace', time: result.stats.to, sensitivity: 'high' });
    result.items.push({ platform: 'Google', category: 'location',
      item: pts.length + ' precise location points', time: result.stats.to, sensitivity: 'high' });
  }

  const search = entries.find(e => /MyActivity\.json$/i.test(e.name));
  if (search) {
    const acts = await search.json();
    const counts = new Map();
    for (const a of acts) {
      const q = String(a.title || '').replace(/^Searched for\s+/i, '');
      if (!q) continue;
      counts.set(q, (counts.get(q) || 0) + 1);
      const sens = SENSITIVE_WORDS.some(w => q.toLowerCase().includes(w)) ? 'high' : 'medium';
      result.items.push({ platform: 'Google', category: 'search', item: q, time: a.time, sensitivity: sens });
    }
    result.topSearches = [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 6);
  }
  return result;
}

if (typeof module !== 'undefined') module.exports = { parseGoogle };
