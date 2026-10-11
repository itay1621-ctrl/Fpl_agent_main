import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';

const routePath = path.resolve('app/api-vercel/drafts/route.ts');

function createHandler(envOverrides = {}) {
  const code = fs.readFileSync(routePath, 'utf8');
  const jsCode = code
    .replace(/import\s+{[^}]+}\s+from\s+['"][^'"]+['"];?/g, '')
    .replace(/export\s+async\s+function/g, 'async function')
    .replace(/:\s*any/g, '');

  let calledUrl = null;
  let fetchOptions = null;
  const mockFetch = async (url, opts) => {
    calledUrl = url;
    fetchOptions = opts;
    return {
      ok: true,
      status: 200,
      json: async () => ({
        drafts: [
          { id: 1, name_en: 'Premium Build', data: { squad: [], cost: 995 } }
        ]
      })
    };
  };

  const mockNextResponse = {
    json: (body, init) => ({ body, status: init?.status || 200 })
  };

  const sandbox = {
    fetch: mockFetch,
    NextResponse: mockNextResponse,
    process: { env: { ...envOverrides } },
    console
  };

  const script = new vm.Script(jsCode + '\n;globalThis.__getHandler = GET;');
  vm.createContext(sandbox);
  script.runInContext(sandbox);

  return {
    handler: sandbox.__getHandler,
    getCalledUrl: () => calledUrl,
    getFetchOptions: () => fetchOptions,
    sandbox
  };
}

test('Vercel Adapter: static file audit', () => {
  assert.ok(fs.existsSync(routePath), 'route.ts must exist');
  const code = fs.readFileSync(routePath, 'utf8');
  assert.ok(!code.includes('calculatePlayerProjection'), 'Must not contain calculatePlayerProjection');
  assert.ok(!code.includes('buildSquad'), 'Must not contain buildSquad');
  assert.ok(!code.includes('saves_per_90'), 'Must not contain saves_per_90 linear calculation');
  assert.ok(!code.includes('defcon_per_90'), 'Must not contain defcon calculation');
  assert.ok(code.includes('/api/drafts'), 'Must call /api/drafts');
});

test('Vercel Adapter: runtime behavior with mock fetch', async () => {
  const { handler, getCalledUrl, getFetchOptions, sandbox } = createHandler({
    BACKEND_URL: 'https://test-backend.internal'
  });

  assert.equal(typeof handler, 'function', 'GET handler must be exported');

  // 1. Test successful upstream response forwarding
  const res = await handler();
  assert.equal(getCalledUrl(), 'https://test-backend.internal/api/drafts');
  assert.equal(getFetchOptions()?.next?.revalidate, 3600);
  assert.equal(res.status, 200);
  assert.equal(res.body.drafts[0].id, 1);

  // 2. Test non-2xx upstream error handling
  sandbox.fetch = async () => ({ ok: false, status: 503, json: async () => ({}) });
  const errRes = await handler();
  assert.equal(errRes.status, 503);
  assert.ok(errRes.body.error.includes('503'));

  // 3. Test malformed payload handling
  sandbox.fetch = async () => ({ ok: true, status: 200, json: async () => ({ drafts: [] }) });
  const malformedRes = await handler();
  assert.equal(malformedRes.status, 502);
  assert.ok(malformedRes.body.error.includes('Invalid drafts payload'));

  // 4. Test network failure handling
  sandbox.fetch = async () => { throw new Error('Network Connection Refused'); };
  const failRes = await handler();
  assert.equal(failRes.status, 500);
  assert.ok(failRes.body.error.includes('Network Connection Refused'));
});

test('Vercel Adapter: base URL normalization (trailing slashes & precedence)', async () => {
  // 1. Base URL with no trailing slash
  {
    const { handler, getCalledUrl } = createHandler({
      BACKEND_URL: 'https://custom-host.com'
    });
    const res = await handler();
    assert.equal(res.status, 200);
    assert.equal(getCalledUrl(), 'https://custom-host.com/api/drafts');
  }

  // 2. Base URL with one trailing slash
  {
    const { handler, getCalledUrl } = createHandler({
      BACKEND_URL: 'https://custom-host.com/'
    });
    const res = await handler();
    assert.equal(res.status, 200);
    assert.equal(getCalledUrl(), 'https://custom-host.com/api/drafts');
  }

  // 3. Base URL with multiple trailing slashes
  {
    const { handler, getCalledUrl } = createHandler({
      BACKEND_URL: 'https://custom-host.com///'
    });
    const res = await handler();
    assert.equal(res.status, 200);
    assert.equal(getCalledUrl(), 'https://custom-host.com/api/drafts');
  }

  // 4. NEXT_PUBLIC_BACKEND_URL with trailing slashes when BACKEND_URL is unset
  {
    const { handler, getCalledUrl } = createHandler({
      NEXT_PUBLIC_BACKEND_URL: 'https://public-host.com//'
    });
    const res = await handler();
    assert.equal(res.status, 200);
    assert.equal(getCalledUrl(), 'https://public-host.com/api/drafts');
  }

  // 5. Precedence: BACKEND_URL overrides NEXT_PUBLIC_BACKEND_URL
  {
    const { handler, getCalledUrl } = createHandler({
      BACKEND_URL: 'https://priority-host.com/',
      NEXT_PUBLIC_BACKEND_URL: 'https://secondary-host.com/'
    });
    const res = await handler();
    assert.equal(res.status, 200);
    assert.equal(getCalledUrl(), 'https://priority-host.com/api/drafts');
  }

  // 6. Fallback URL when both env vars are unset
  {
    const { handler, getCalledUrl } = createHandler({});
    const res = await handler();
    assert.equal(res.status, 200);
    assert.equal(getCalledUrl(), 'https://fpl-elite-scout-api.onrender.com/api/drafts');
  }
});
