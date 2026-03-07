import { test, expect } from '@playwright/test'

test.describe('Smoke Tests', () => {
  test('should load the top page with HTTP 200', async ({ page }) => {
    const response = await page.goto('/')
    expect(response).not.toBeNull()
    expect(response!.status()).toBe(200)
  })

  test('should have correct page title', async ({ page }) => {
    await page.goto('/')
    await expect(page).toHaveTitle(/Engineer Cafe Navigator/)
  })

  test('should render the html element with lang="ja"', async ({ page }) => {
    await page.goto('/')
    const lang = await page.locator('html').getAttribute('lang')
    expect(lang).toBe('ja')
  })

  test('should load without console errors', async ({ page }) => {
    const consoleErrors: string[] = []
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        consoleErrors.push(msg.text())
      }
    })

    await page.goto('/')
    await page.waitForLoadState('domcontentloaded')

    // Filter out known acceptable errors (e.g., missing env vars in dev)
    const criticalErrors = consoleErrors.filter(
      (err) =>
        !err.includes('favicon') &&
        !err.includes('Failed to load resource') &&
        !err.includes('ERR_CONNECTION_REFUSED')
    )
    expect(criticalErrors).toHaveLength(0)
  })

  test('should have a visible body element', async ({ page }) => {
    await page.goto('/')
    await expect(page.locator('body')).toBeVisible()
  })
})
