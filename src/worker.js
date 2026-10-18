// The Worker in front of the static site (wrangler.jsonc): it runs first only for /api/* (assets.run_worker_first);
// every other path is the assets exactly as before. POST /api/report files a report from the map's form;
// /api/admin/* is the owner's triage behind Cloudflare Access; a daily cron forgets old emails.
import { handleReport, publicPhoto, json } from './report.js';
import { handleAdmin, forgetEmails } from './admin.js';

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === '/api/report') return handleReport(request, env);
    if (url.pathname.startsWith('/api/admin/')) return handleAdmin(request, env, url);
    const photo = url.pathname.match(/^\/api\/photos\/(\d+)$/);
    if (photo && request.method === 'GET') return publicPhoto(env, Number(photo[1]));
    if (url.pathname.startsWith('/api/')) return json({ error: 'not found' }, 404);
    return env.ASSETS.fetch(request);
  },
  async scheduled(event, env) {
    await forgetEmails(env, event.scheduledTime);
  },
};
