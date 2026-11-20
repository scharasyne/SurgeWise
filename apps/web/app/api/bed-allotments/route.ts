import { NextResponse } from 'next/server';

export const runtime = 'nodejs';
const MAX_BYTES = 1_000_000;

/**
 * Forwards an uploaded CSV/.xlsx of per-hospital bed allotments to the engine,
 * which parses it and matches rows to the approved QC hospitals. The browser's
 * file is never trusted as verified capacity; it is a scenario assumption.
 */
export async function POST(request: Request) {
  const base = process.env.ENGINE_BASE_URL;
  if (!base) return NextResponse.json({ error: 'Set server-only ENGINE_BASE_URL to connect the audited research engine.' }, { status: 503 });
  const declared = Number(request.headers.get('content-length') ?? 0);
  if (declared > MAX_BYTES) return NextResponse.json({ error: 'The file is larger than 1 MB.' }, { status: 413 });
  const reader = request.body?.getReader();
  if (!reader) return NextResponse.json({ error: 'Choose a CSV or Excel file.' }, { status: 422 });
  const chunks: Uint8Array[] = [];
  let size = 0;
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    size += value.byteLength;
    if (size > MAX_BYTES) {
      await reader.cancel();
      return NextResponse.json({ error: 'The file is larger than 1 MB.' }, { status: 413 });
    }
    chunks.push(value);
  }
  try {
    const response = await fetch(`${base.replace(/\/$/, '')}/v1/qc-simulation/bed-allotments`, {
      method: 'POST', headers: { 'content-type': 'application/octet-stream' }, body: Buffer.concat(chunks),
      signal: AbortSignal.any([request.signal, AbortSignal.timeout(20000)]), cache: 'no-store',
    });
    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch {
    return NextResponse.json({ error: 'Research engine unavailable or timed out.' }, { status: 503 });
  }
}
