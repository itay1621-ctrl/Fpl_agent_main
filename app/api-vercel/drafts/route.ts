import { NextResponse } from 'next/server';

export async function GET() {
  try {
    const rawBackendUrl = process.env.BACKEND_URL || process.env.NEXT_PUBLIC_BACKEND_URL || 'https://fpl-elite-scout-api.onrender.com';
    const backendUrl = rawBackendUrl.replace(/\/+$/, '');
    const res = await fetch(`${backendUrl}/api/drafts`, {
      next: { revalidate: 3600 }
    });

    if (!res.ok) {
      return NextResponse.json(
        { error: `Upstream backend responded with status ${res.status}` },
        { status: res.status }
      );
    }

    const data = await res.json();

    if (!data || !Array.isArray(data.drafts) || data.drafts.length === 0) {
      return NextResponse.json(
        { error: 'Invalid drafts payload from upstream backend' },
        { status: 502 }
      );
    }

    return NextResponse.json(data);
  } catch (err: any) {
    return NextResponse.json(
      { error: err.message || 'Failed to fetch drafts from backend' },
      { status: 500 }
    );
  }
}
