/**
 * PredomicsApp End-to-End Integration Tests
 *
 * Prerequisites:
 *   - App running at BASE_URL (default http://localhost:8001), built with the
 *     real engine (the job test fails on mock results) and with registration
 *     open (PREDOMICS_REGISTRATION_ENABLED=true, the default)
 *   - npm ci                             (repository root)
 *   - npx playwright install chromium
 *
 * Usage (from the repository root):
 *   npm run test:e2e
 *   BASE_URL=http://localhost:8001 npx playwright test
 */
import { test, expect } from '@playwright/test'
import path from 'path'
import fs from 'fs'

const BASE = process.env.BASE_URL || 'http://localhost:8001'
const TEST_EMAIL = `e2e_${Date.now()}@test.com`
const TEST_PASSWORD = 'TestPass123!'
// Bundled demo dataset (tracked in the repository)
const DATA_DIR = path.resolve('samples/qin2014_cirrhosis')

// Shared state across serial tests
let authToken = ''
let projectId = ''

// Helper: login via API and set token in localStorage
async function loginViaAPI(page) {
  await page.goto(BASE)
  await page.evaluate(async (creds) => {
    const resp = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(creds),
    })
    const data = await resp.json()
    if (data.access_token) {
      localStorage.setItem('token', data.access_token)
    }
  }, { email: TEST_EMAIL, password: TEST_PASSWORD })
}

// Helper: dismiss onboarding tour overlay (uses correct localStorage key)
async function dismissOverlays(page) {
  await page.evaluate(() => {
    // Correct key used by OnboardingTour.vue
    localStorage.setItem('predomics_onboarding_dismissed', 'true')
    // Remove any tour overlays from the DOM
    document.querySelectorAll('.tour-overlay, .tour-backdrop').forEach(el => el.remove())
  })
  // Also try clicking dismiss/close buttons if they exist
  const closeBtn = page.locator('.tour-close, button.tour-btn:has-text("Get Started")').first()
  if (await closeBtn.isVisible({ timeout: 500 }).catch(() => false)) {
    await closeBtn.click({ force: true }).catch(() => {})
  }
  await page.waitForTimeout(300)
}

test.describe.serial('PredomicsApp E2E', () => {
  // ── 1. Landing page ──
  test('landing page loads and shows brand', async ({ page }) => {
    await page.goto(BASE)
    await page.waitForTimeout(2000)
    const brand = page.locator('.brand')
    await expect(brand).toBeVisible()
    await expect(brand).toContainText('PredomicsApp')
  })

  // ── 2. Registration ──
  test('register a new user', async ({ page }) => {
    await page.goto(`${BASE}/login`)
    await page.waitForTimeout(1000)

    // Click the Register tab (first matching, to avoid ambiguity with submit button)
    const registerTab = page.locator('button:has-text("Register")').first()
    if (await registerTab.isVisible()) {
      await registerTab.click()
      await page.waitForTimeout(500)
    }

    // Fill registration form
    await page.fill('input[type="email"]', TEST_EMAIL)
    // Password and its confirmation
    const passwordFields = page.locator('input[type="password"]')
    for (let i = 0; i < await passwordFields.count(); i++) {
      await passwordFields.nth(i).fill(TEST_PASSWORD)
    }

    // Fill name field if visible (register mode has it)
    const nameField = page.locator('input[type="text"][placeholder*="name" i]')
    if (await nameField.isVisible({ timeout: 500 }).catch(() => false)) {
      await nameField.fill('E2E Test User')
    }

    // Submit — target the .btn-primary submit button specifically
    await page.locator('button[type="submit"].btn-primary').click()
    await page.waitForTimeout(3000)

    // Should redirect to /projects after successful registration
    await expect(page).toHaveURL(/projects/)
  })

  // ── 3. Login ──
  test('login with credentials', async ({ page }) => {
    await page.goto(`${BASE}/login`)
    await page.waitForTimeout(1000)

    // Make sure we're on the Login tab (not Register)
    const loginTab = page.locator('button:has-text("Login")').first()
    if (await loginTab.isVisible({ timeout: 500 }).catch(() => false)) {
      await loginTab.click()
      await page.waitForTimeout(300)
    }

    await page.fill('input[type="email"]', TEST_EMAIL)
    await page.fill('input[type="password"]', TEST_PASSWORD)
    // Submit button text is "Login" in login mode
    await page.locator('button[type="submit"].btn-primary').click()
    await page.waitForTimeout(3000)

    await expect(page).toHaveURL(/projects/)
    authToken = await page.evaluate(() => localStorage.getItem('token'))
    expect(authToken).toBeTruthy()
  })

  // ── 4. Create project ──
  test('create a new project', async ({ page }) => {
    await loginViaAPI(page)

    await page.goto(`${BASE}/projects`)
    await page.waitForTimeout(2000)
    await dismissOverlays(page)

    // Click the "+" button (class btn-new, title "New project") to reveal the form
    const newBtn = page.locator('button.btn-new')
    await expect(newBtn).toBeVisible({ timeout: 10000 })
    await newBtn.click()
    await page.waitForTimeout(500)

    // Fill project name in the create form
    const nameInput = page.locator('.create-form input[placeholder*="name" i]')
    await expect(nameInput).toBeVisible({ timeout: 5000 })
    await nameInput.fill('E2E Test Project')

    // Click the "Create" button inside the form
    const createBtn = page.locator('.create-form button:has-text("Create")')
    await createBtn.click()
    await page.waitForTimeout(3000)

    // After creation, the page stays on /projects with the project selected
    // Extract project ID from the API
    const token = await page.evaluate(() => localStorage.getItem('token'))
    const projects = await page.evaluate(async (t) => {
      const r = await fetch('/api/projects/', { headers: { Authorization: `Bearer ${t}` } })
      return r.json()
    }, token)
    if (Array.isArray(projects) && projects.length > 0) {
      projectId = projects[0].project_id
    }
    expect(projectId).toBeTruthy()
  })

  // ── 5. Upload dataset ──
  test('upload dataset files', async ({ page }) => {
    expect(projectId, 'project was created by the previous test').toBeTruthy()
    const xFile = path.join(DATA_DIR, 'Xtrain.tsv')
    expect(fs.existsSync(xFile), `sample file ${xFile} exists`).toBeTruthy()

    await loginViaAPI(page)

    await page.goto(`${BASE}/project/${projectId}/data`)
    await page.waitForTimeout(3000)
    await dismissOverlays(page)

    // Upload the X train matrix through the first file input of the Data tab
    const fileInput = page.locator('input[type="file"]').first()
    await expect(fileInput).toBeAttached({ timeout: 10000 })
    await fileInput.setInputFiles(xFile)

    // The upload really happened: the project now has a dataset holding the
    // file, recognised as the training matrix.
    const token = await page.evaluate(() => localStorage.getItem('token'))
    await expect.poll(async () => {
      const project = await page.evaluate(async ({ t, id }) => {
        const r = await fetch(`/api/projects/${id}`, { headers: { Authorization: `Bearer ${t}` } })
        return r.ok ? r.json() : null
      }, { t: token, id: projectId })
      const files = (project?.datasets || []).flatMap(d => d.files || [])
      return files.filter(f => f.filename === 'Xtrain.tsv').map(f => f.role)
    }, { timeout: 30000, message: 'Xtrain.tsv attached to the project as xtrain' }).toEqual(['xtrain'])
  })

  // ── 6. Dashboard shows stats ──
  test('dashboard displays summary cards', async ({ page }) => {
    await loginViaAPI(page)

    await page.goto(`${BASE}/dashboard`)
    await page.waitForTimeout(3000)
    await dismissOverlays(page)

    // Dashboard should have stat-card elements (at least Projects, Datasets, Completed)
    const statCards = page.locator('.stat-card')
    await expect(statCards.first()).toBeVisible({ timeout: 10000 })
    const count = await statCards.count()
    expect(count).toBeGreaterThanOrEqual(3)
  })

  // ── 7. Meta-analysis page loads ──
  test('meta-analysis page is accessible', async ({ page }) => {
    await loginViaAPI(page)

    await page.goto(`${BASE}/meta-analysis`)
    await page.waitForTimeout(2000)

    // Heading is "Multi-Cohort Meta-Analysis" (i18n key meta.title)
    const heading = page.locator('h2')
    await expect(heading).toContainText('Meta-Analysis')
  })

  // ── 8. Public share page (unauthenticated) ──
  test('public share page loads for guest', async ({ browser }) => {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
    const page = await ctx.newPage()

    // An invalid token renders the public page with an error, never project data.
    await page.goto(`${BASE}/public/invalid-token-test`)
    await expect(page.locator('.public-header')).toBeVisible({ timeout: 15000 })
    await expect(page.locator('.error-box')).toBeVisible({ timeout: 15000 })
    await expect(page.locator('.project-info')).toHaveCount(0)
    await ctx.close()
  })

  // ── 9. API health check ──
  test('health endpoint returns ok', async ({ request }) => {
    const resp = await request.get(`${BASE}/health`)
    expect(resp.ok()).toBeTruthy()
    const body = await resp.json()
    expect(body.status).toBe('ok')
  })

  // ── 10. API docs accessible ──
  test('swagger docs are accessible', async ({ request }) => {
    // The interactive docs live under /api (a bare /docs is the SPA fallback).
    const docs = await request.get(`${BASE}/api/docs`)
    expect(docs.ok()).toBeTruthy()
    expect((await docs.text()).toLowerCase()).toContain('swagger')

    const spec = await request.get(`${BASE}/api/openapi.json`)
    expect(spec.ok()).toBeTruthy()
    const body = await spec.json()
    expect(Object.keys(body.paths || {}).length).toBeGreaterThan(50)
  })

  // ── 11. A real analysis job, end to end ──
  test('runs a real analysis job on the bundled sample dataset', async ({ request }) => {
    test.setTimeout(300000)

    // The image must contain the engine: mock results are not acceptable here.
    const health = await (await request.get(`${BASE}/health`)).json()
    expect(health.gpredomicspy_available, 'gpredomicspy engine is available').toBe(true)

    const login = await request.post(`${BASE}/api/auth/login`, {
      data: { email: TEST_EMAIL, password: TEST_PASSWORD },
    })
    expect(login.ok()).toBeTruthy()
    const headers = { Authorization: `Bearer ${(await login.json()).access_token}` }

    // Load the demo dataset into a new project
    const loaded = await request.post(`${BASE}/api/samples/qin2014_cirrhosis/load`, { headers })
    expect(loaded.ok(), `sample load: ${loaded.status()}`).toBeTruthy()
    const project = await loaded.json()
    const files = (project.datasets || []).flatMap(d => d.files || [])
    const fileId = role => files.find(f => f.role === role)?.id
    expect(fileId('xtrain'), 'xtrain file in the sample project').toBeTruthy()
    expect(fileId('ytrain'), 'ytrain file in the sample project').toBeTruthy()

    // Launch a deliberately small genetic-algorithm run
    const query = new URLSearchParams({
      x_file_id: fileId('xtrain'),
      y_file_id: fileId('ytrain'),
      job_name: 'e2e tiny run',
    })
    if (fileId('xtest') && fileId('ytest')) {
      query.set('xtest_file_id', fileId('xtest'))
      query.set('ytest_file_id', fileId('ytest'))
    }
    const run = await request.post(`${BASE}/api/analysis/${project.project_id}/run?${query}`, {
      headers,
      data: {
        general: { algo: 'ga', language: 'bin,ter', data_type: 'raw,prev', thread_number: 2, seed: 42 },
        // Small but not degenerate: with a population near 100 the engine's parent
        // selection can leave fewer than two parents and gpredomics panics (ga.rs cross_over).
        ga: { population_size: 200, max_epochs: 15, min_epochs: 5 },
      },
    })
    expect(run.ok(), `job launch: ${run.status()} ${await run.text()}`).toBeTruthy()
    const jobId = (await run.json()).job_id
    expect(jobId).toBeTruthy()

    // Wait for a terminal state
    const jobUrl = `${BASE}/api/analysis/${project.project_id}/jobs/${jobId}`
    let job = null
    await expect.poll(async () => {
      const r = await request.get(jobUrl, { headers })
      job = r.ok() ? await r.json() : null
      return job?.status ?? 'pending'
    }, { timeout: 240000, intervals: [2000], message: 'job reaches a terminal state' })
      .not.toMatch(/^(pending|queued|running)$/)

    const logs = await request.get(`${jobUrl}/logs`, { headers })
    const logText = logs.ok() ? await logs.text() : ''
    expect(job.status, `job failed; log tail: ${logText.slice(-1500)}`).toBe('completed')
    expect(logText, 'results come from the real engine').not.toContain('[mock]')
    expect(job.best_auc, 'a model was found').toBeGreaterThan(0.5)
    expect(job.best_k).toBeGreaterThanOrEqual(1)

    // Results are readable
    const results = await request.get(`${jobUrl}/results`, { headers })
    expect(results.ok(), `results: ${results.status()}`).toBeTruthy()
  })
})
