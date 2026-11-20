import { NextResponse } from 'next/server';

export const runtime = 'nodejs';
const allowed = /^(predict|forecast-runs(?:\/[A-Za-z0-9_-]{1,120})?|research-evidence|qc-simulation|future-simulation|outbreak-demo|spatial-allocations\/[A-Za-z0-9_-]{1,120}|outbreak-context\/[A-Za-z0-9_-]{1,120}|(?:outbreak-scenarios|scenarios)(?:\/[a-f0-9]{64})?)$/;
const reportPath = /^outbreak-scenarios\/[a-f0-9]{64}\/report\.(json|pdf|csv)$/;
async function proxy(request: Request, context: { params: Promise<{ path: string[] }> }) {
  const path = (await context.params).path.join('/');
  const reportFormat = reportPath.exec(path)?.[1];
  if ((!allowed.test(path) && !reportFormat) || (request.method === 'POST' && !['predict', 'scenarios', 'outbreak-scenarios', 'qc-simulation', 'future-simulation'].includes(path)))
    return NextResponse.json({ error: 'Unsupported research endpoint' }, { status: 404 });
  if (path === 'predict' && request.method !== 'POST')
    return NextResponse.json({ error: 'Use POST to run a forecast.' }, { status: 405, headers: { Allow: 'POST' } });
  const base = process.env.ENGINE_BASE_URL;
  if (!base) return NextResponse.json({ error: 'Set server-only ENGINE_BASE_URL to connect the audited research engine.' }, { status: 503 });
  let body: string | undefined;
  if (request.method === 'POST') {
    const reader = request.body?.getReader();
    if (!reader) return NextResponse.json({ error: 'Missing JSON body' }, { status: 422 });
    const chunks: Uint8Array[] = [];
    const maximum = path === 'predict' ? 2 * 1024 * 1024 : 32768;
    let size = 0;
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > maximum) {
        await reader.cancel();
        return NextResponse.json({ error: `Request exceeds ${maximum / 1024} KB` }, { status: 413 });
      }
      chunks.push(value);
    }
    body = Buffer.concat(chunks).toString('utf8');
    try { JSON.parse(body); } catch { return NextResponse.json({ error: 'Invalid JSON' }, { status: 422 }); }
  }
  const query = new URL(request.url).searchParams;
  const area = query.get('area');
  if (area && (!['QUEZON_CITY', 'NCR'].includes(area) || (path === 'predict' && area !== 'QUEZON_CITY')))
    return NextResponse.json({ error: 'Unsupported area' }, { status: 422 });
  try {
    const response = await fetch(`${base.replace(/\/$/, '')}/v1/${path}${area ? `?area=${area}` : ''}`, {
      method: request.method, headers: { 'content-type': 'application/json' }, body,
      signal: AbortSignal.any([request.signal, AbortSignal.timeout(20000)]), cache: 'no-store',
    });
    if (response.ok && (reportFormat === 'pdf' || reportFormat === 'csv')) {
      const headers = new Headers({ 'content-type': reportFormat === 'pdf' ? 'application/pdf' : 'text/csv; charset=utf-8', 'cache-control': 'no-store' });
      const attachment = response.headers.get('content-disposition');
      if (attachment) headers.set('content-disposition', attachment);
      return new Response(response.body, { headers });
    }
    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch {
    return NextResponse.json({ error: 'Research engine unavailable or timed out.' }, { status: 503 });
  }
}
export const GET = proxy;
export const POST = proxy;
