import { createRequire } from 'node:module';
import assert from 'node:assert/strict';

const require = createRequire(import.meta.url);
process.env.LEAD_DRY_RUN = '1';
process.env.LEAD_RATE_MAX = '2';
const { handleLeadRequest, resetRateLimitForTests } = require('../server/lead-core');
const vercelHandler = require('../api/leads');
const netlifyHandler = require('../netlify/functions/leads').handler;

function request(overrides = {}){
  return handleLeadRequest({
    method:'POST',
    headers:{ origin:'https://airank.net.cn', 'x-forwarded-for':'203.0.113.10' },
    body:{ website:'example.com', company:'测试企业', intent:'release-check' },
    ...overrides
  });
}

resetRateLimitForTests();
const valid = await request();
assert.equal(valid.status, 200);
assert.equal(JSON.parse(valid.body).ok, true);

resetRateLimitForTests();
const invalid = await request({ body:{} });
assert.equal(invalid.status, 400);

resetRateLimitForTests();
const foreign = await request({ headers:{ origin:'https://example.invalid', 'x-forwarded-for':'203.0.113.11' } });
assert.equal(foreign.status, 403);

const wrongMethod = await request({ method:'GET' });
assert.equal(wrongMethod.status, 405);

const tooLarge = await request({ body:{ website:'example.com', note:'x'.repeat(20 * 1024) } });
assert.equal(tooLarge.status, 413);

resetRateLimitForTests();
await request({ headers:{ origin:'https://airank.net.cn', 'x-forwarded-for':'203.0.113.12' } });
await request({ headers:{ origin:'https://airank.net.cn', 'x-forwarded-for':'203.0.113.12' } });
const limited = await request({ headers:{ origin:'https://airank.net.cn', 'x-forwarded-for':'203.0.113.12' } });
assert.equal(limited.status, 429);

resetRateLimitForTests();
const vercelResult = await new Promise(resolve => {
  const responseHeaders = {};
  const response = {
    statusCode:0,
    setHeader(key, value){ responseHeaders[key] = value; },
    end(body){ resolve({ status:this.statusCode, headers:responseHeaders, body }); }
  };
  vercelHandler({
    method:'POST',
    headers:{ origin:'https://airank.net.cn', 'x-forwarded-for':'203.0.113.20' },
    body:{ website:'example.com', intent:'vercel-adapter-check' }
  }, response);
});
assert.equal(vercelResult.status, 200);

resetRateLimitForTests();
const netlifyResult = await netlifyHandler({
  httpMethod:'POST',
  headers:{ origin:'https://airank.net.cn', 'x-forwarded-for':'203.0.113.21' },
  body:JSON.stringify({ website:'example.com', intent:'netlify-adapter-check' })
});
assert.equal(netlifyResult.statusCode, 200);

console.log('OK: lead API validation, abuse controls, Vercel and Netlify adapters passed.');
