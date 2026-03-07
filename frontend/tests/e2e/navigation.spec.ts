import { test, expect } from '@playwright/test'

test.describe('Navigation Tests', () => {
  test('should access admin page', async ({ page }) => {
    const response = await page.goto('/admin/knowledge')

    // Admin page should either:
    // - Return 200 (if no auth guard, page renders)
    // - Return 401/403 (if auth guard blocks)
    // - Redirect to login (302/307)
    expect(response).not.toBeNull()
    const status = response!.status()
    expect([200, 401, 403, 302, 307]).toContain(status)
  })

  test('should return 404 for non-existent pages', async ({ page }) => {
    const response = await page.goto('/this-page-does-not-exist-12345')
    expect(response).not.toBeNull()
    expect(response!.status()).toBe(404)
  })

  test('should navigate from top page without errors', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('domcontentloaded')

    // Verify the page is interactive (no crash/blank screen)
    const bodyContent = await page.locator('body').textContent()
    expect(bodyContent).not.toBeNull()
    expect(bodyContent!.length).toBeGreaterThan(0)
  })

  test('should have proper meta viewport for mobile', async ({ page }) => {
    await page.goto('/')
    const viewport = page.locator('meta[name="viewport"]')
    await expect(viewport).toHaveAttribute('content', /width=device-width/)
  })
})
