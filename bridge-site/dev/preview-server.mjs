// Local same-origin preview: static web/ + the real Function handler with fakes.
// Run: node dev/preview-server.mjs [port]   (from bridge-site/)
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { extname, join, normalize } from 'node:path';
import { fileURLToPath } from 'node:url';
import { application } from '../functions/routes.mjs';
import { BackendError, fakeDb, fakeFetch } from './fakes.mjs';

const root = join(fileURLToPath(new URL('.', import.meta.url)), '..');
const port = Number(process.argv[2] || 8010);
const envValues = {
  QODER_PAT: 'local-fake', TELEGRAM_BOT_TOKEN: 'local-fake', TELEGRAM_CHAT_ID: '42',
  TELEGRAM_WEBHOOK_SECRET: 'local-fake', FORWARD_SIGNING_SECRET: 'whsec_' + Buffer.from('local-fake-key-32-bytes-long!!').toString('base64'),
};
const handle = application({ db: fakeDb(), env: name => envValues[name], fetch: fakeFetch, BackendError });
const types = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.png': 'image/png', '.svg': 'image/svg+xml' };

createServer(async (req, res) => {
  const url = new URL(req.url, 'http://127.0.0.1');
  if (url.pathname.startsWith('/functions/v1/app')) {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    const request = new Request(url.href, {
      method: req.method,
      headers: req.headers,
      body: ['GET', 'HEAD'].includes(req.method) ? undefined : Buffer.concat(chunks),
    });
    try {
      const response = await handle({ request, requestId: 'local' });
      res.writeHead(response.status, Object.fromEntries(response.headers));
      res.end(Buffer.from(await response.arrayBuffer()));
    } catch (error) {
      const status = error instanceof BackendError ? error.status : 503;
      res.writeHead(status, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: error.code || 'internal' }));
    }
    return;
  }
  const path = normalize(url.pathname === '/' ? '/index.html' : url.pathname).replace(/^([/\\])+/, '');
  try {
    const data = await readFile(join(root, 'web', path));
    res.writeHead(200, { 'Content-Type': types[extname(path)] || 'application/octet-stream' });
    res.end(data);
  } catch {
    res.writeHead(404, { 'Content-Type': 'text/plain' });
    res.end('not found');
  }
}).listen(port, '127.0.0.1', () => console.log(`preview: http://127.0.0.1:${port}/`));