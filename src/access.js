// Cloudflare Access in front of /admin and /api/admin/*: the Worker checks the Cf-Access-Jwt-Assertion header itself
// too (signature by the team's keys, audience, issuer, expiry), so an admin call that bypasses Access is refused.
// The team domain and the application's AUD are Worker variables (ACCESS_TEAM_DOMAIN, ACCESS_AUD), never in the repo.

let cached = { team: '', at: 0, keys: [] };

const b64url = s => Uint8Array.from(atob(s.replace(/-/g, '+').replace(/_/g, '/').padEnd(Math.ceil(s.length / 4) * 4, '=')),
  c => c.charCodeAt(0));
const part = s => JSON.parse(new TextDecoder().decode(b64url(s)));

async function keys(team, now) {
  if (cached.team === team && now - cached.at < 3600_000) return cached.keys;
  const r = await fetch(`https://${team}/cdn-cgi/access/certs`);
  if (!r.ok) throw new Error('certs');
  cached = { team, at: now, keys: (await r.json()).keys || [] };
  return cached.keys;
}

// The signed-in identity's email, or null when the request does not carry a valid Access token.
export async function verifyAccess(request, env, now = Date.now()) {
  const team = env.ACCESS_TEAM_DOMAIN, aud = env.ACCESS_AUD;
  const token = request.headers.get('Cf-Access-Jwt-Assertion');
  if (!team || !aud || !token) return null;
  try {
    const [h, p, s] = token.split('.');
    const header = part(h), payload = part(p);
    if (header.alg !== 'RS256') return null;
    const jwk = (await keys(team, now)).find(k => k.kid === header.kid);
    if (!jwk) return null;
    const key = await crypto.subtle.importKey('jwk', jwk, { name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-256' }, false, ['verify']);
    const ok = await crypto.subtle.verify('RSASSA-PKCS1-v1_5', key, b64url(s), new TextEncoder().encode(`${h}.${p}`));
    if (!ok) return null;
    const auds = [].concat(payload.aud || []);
    if (!auds.includes(aud) || payload.iss !== `https://${team}`) return null;
    if (!(payload.exp * 1000 > now) || (payload.nbf && payload.nbf * 1000 > now + 60_000)) return null;
    return payload.email || 'access';
  } catch {
    return null;
  }
}
