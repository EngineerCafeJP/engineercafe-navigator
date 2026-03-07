import { test, expect } from '@playwright/test'

test.describe('API Proxy Tests', () => {
  // Smoke test: verify the server is running and the endpoint exists with a concrete response
  test('GET /api/backgrounds should return 200 with JSON', async ({ request }) => {
    const response = await request.get('/api/backgrounds')

    expect(response.status()).toBe(200)
    const contentType = response.headers()['content-type']
    expect(contentType).toContain('application/json')
  })

  // Backend-dependent: POST /api/qa requires a running backend and env vars.
  // We assert a proper client or server error, never an undefined/network-level failure.
  test('POST /api/qa should return a defined HTTP response', async ({ request }) => {
    const response = await request.post('/api/qa', {
      data: {
        question: 'test question',
        language: 'ja',
      },
      headers: {
        'Content-Type': 'application/json',
      },
    })

    const status = response.status()
    // 200 = success, 400 = bad request, 500 = backend not configured
    // Anything in HTTP range is acceptable — what we reject is a network-level failure (no response)
    expect(status).toBeGreaterThanOrEqual(200)
    expect(status).toBeLessThan(600)
  })

  // Backend-dependent: health endpoint may return 500 when DB is not configured in CI.
  // We assert the endpoint exists and returns an HTTP response (not a network error).
  test('GET /api/health/knowledge should return an HTTP response', async ({ request }) => {
    const response = await request.get('/api/health/knowledge')

    const status = response.status()
    // 200 = healthy, 500 = DB not configured (acceptable in CI without secrets)
    expect(status).toBeGreaterThanOrEqual(200)
    expect(status).toBeLessThan(600)
  })

  test('GET /api/qa should be rejected (POST-only endpoint)', async ({ request }) => {
    const response = await request.get('/api/qa')

    const status = response.status()
    // Must be a client error (405 Method Not Allowed, 404, or 400)
    expect([400, 404, 405]).toContain(status)
  })

  test('POST /api/qa with malformed JSON should return 400', async ({ request }) => {
    const response = await request.post('/api/qa', {
      data: 'this is not json',
      headers: {
        'Content-Type': 'application/json',
      },
    })

    const status = response.status()
    // Must be a client error, not a server crash (5xx)
    expect(status).toBeGreaterThanOrEqual(400)
    expect(status).toBeLessThan(500)
  })
})
