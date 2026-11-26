/**
 * Content-Security-Policy check.
 *
 * The production proxy sends the policy written in
 * nginx/snippets/security-headers.conf. This test runs the application behind
 * that proxy configuration and fails if the browser reports a single violation
 * while the Data and Results pages draw their charts.
 *
 * BASE_URL must therefore point at the proxy (`make test-e2e` and CI start one
 * from the repository's NGINX templates). Against an instance that sends no
 * policy the test is skipped, unless E2E_REQUIRE_CSP=1 makes that a failure.
 *
 * Needs the real engine (it runs a small job) and open registration.
 */
import { test, expect } from '@playwright/test'
import fs from 'fs'
import path from 'path'

const BASE = process.env.BASE_URL || 'http://localhost:8001'
const EMAIL = `csp_${Date.now()}@test.com`
const PASSWORD = 'TestPass123!'

function policyFromNginx() {
  const conf = fs.readFileSync(path.resolve('nginx/snippets/security-headers.conf'), 'utf8')
  const m = conf.match(/^add_header\s+Content-Security-Policy\s+"([^"]+)"/m)
  if (!m) throw new Error('No enforced Content-Security-Policy in nginx/snippets/security-headers.conf')
  return m[1]
}

test.describe.serial('Content-Security-Policy', () => {
  let token = ''
  let projectId = ''
  let jobId = ''

  test('prepare a project with a finished job', async ({ request }) => {
    test.setTimeout(300000)
    const reg = await request.post(`${BASE}/api/auth/register`, {
      data: { email: EMAIL, password: PASSWORD, full_name: 'CSP Test' },
    })
    expect(reg.ok(), `register: ${reg.status()} ${await reg.text()}`).toBeTruthy()
    const login = await request.post(`${BASE}/api/auth/login`, { data: { email: EMAIL, password: PASSWORD } })
    expect(login.ok(), `login: ${login.status()}`).toBeTruthy()
    token = (await login.json()).access_token
    const headers = { Authorization: `Bearer ${token}` }

    const loaded = await request.post(`${BASE}/api/samples/qin2014_cirrhosis/load`, { headers })
    expect(loaded.ok(), `sample load: ${loaded.status()}`).toBeTruthy()
    const project = await loaded.json()
    projectId = project.project_id
    const files = (project.datasets || []).flatMap(d => d.files || [])
    const fileId = role => files.find(f => f.role === role)?.id
    const query = new URLSearchParams({
      x_file_id: fileId('xtrain'),
      y_file_id: fileId('ytrain'),
      xtest_file_id: fileId('xtest'),
      ytest_file_id: fileId('ytest'),
      job_name: 'csp check',
    })
    const run = await request.post(`${BASE}/api/analysis/${projectId}/run?${query}`, {
      headers,
      data: {
        general: { algo: 'ga', language: 'bin,ter', data_type: 'raw,prev', thread_number: 2, seed: 42 },
        ga: { population_size: 200, max_epochs: 15, min_epochs: 5 },
      },
    })
    expect(run.ok(), `job launch: ${run.status()} ${await run.text()}`).toBeTruthy()
    jobId = (await run.json()).job_id

    let status = 'pending'
    for (let i = 0; i < 120 && !['completed', 'failed'].includes(status); i++) {
      await new Promise(r => setTimeout(r, 2000))
      status = (await (await request.get(`${BASE}/api/analysis/${projectId}/jobs/${jobId}`, { headers })).json()).status
    }
    expect(status).toBe('completed')
  })

  test('Data and Results pages draw charts without any CSP violation', async ({ page }) => {
    test.setTimeout(240000)
    const policy = policyFromNginx()
    const violations = []

    // The page must really be served with the repository's policy.
    const served = (await (await page.request.get(`${BASE}/`)).headers())['content-security-policy']
    if (!served) {
      if (process.env.E2E_REQUIRE_CSP) throw new Error(`${BASE} sends no Content-Security-Policy header: run the suite through the NGINX proxy`)
      test.skip(true, `${BASE} sends no Content-Security-Policy header (not behind the proxy)`)
    }
    expect(served, 'the proxy serves the policy of nginx/snippets/security-headers.conf').toBe(policy)

    await page.addInitScript(() => {
      window.__cspViolations = []
      document.addEventListener('securitypolicyviolation', e => {
        window.__cspViolations.push(`${e.violatedDirective} blocked ${e.blockedURI || 'inline'} (${e.sourceFile || ''}:${e.lineNumber || ''})`)
      })
    })
    page.on('console', msg => {
      const text = msg.text()
      if (/Content Security Policy|Refused to (load|execute|apply|connect|create)/i.test(text)) violations.push(text)
    })
    const collect = async () => {
      const fromPage = await page.evaluate(() => window.__cspViolations || []).catch(() => [])
      violations.push(...fromPage)
    }

    // Signed in, tour dismissed
    await page.goto(BASE)
    await page.evaluate(([t]) => {
      localStorage.setItem('token', t)
      localStorage.setItem('predomics_onboarding_dismissed', 'true')
    }, [token])

    // A page that stays blank is usually the policy blocking the application
    // itself: report what the browser refused before anything else.
    const waitForChart = async where => {
      try {
        await page.locator('.js-plotly-plot').first().waitFor({ state: 'visible', timeout: 60000 })
      } catch {
        await collect()
        throw new Error(`No chart was drawn on ${where}. CSP violations so far: ${JSON.stringify([...new Set(violations)], null, 2)}`)
      }
    }

    // --- Data tab: every chart sub-tab -------------------------------------
    await page.goto(`${BASE}/project/${projectId}/data`)
    await waitForChart('the Data tab')
    const dataTabs = await page.locator('[role="tab"]').count()
    for (let i = 0; i < dataTabs; i++) {
      const tab = page.locator('[role="tab"]').nth(i)
      if (await tab.isVisible().catch(() => false)) {
        await tab.click({ timeout: 5000 }).catch(() => {})
        await page.waitForTimeout(1500)
      }
    }
    await collect()

    // --- Results: every sub-tab of the finished job --------------------------
    await page.goto(`${BASE}/project/${projectId}/results/${jobId}`)
    await expect(page.locator('[role="tab"]').first()).toBeVisible({ timeout: 60000 })
    let drawn = 0
    const resultTabs = await page.locator('[role="tab"]').count()
    for (let i = 0; i < resultTabs; i++) {
      const tab = page.locator('[role="tab"]').nth(i)
      if (!(await tab.isVisible().catch(() => false))) continue
      await tab.click({ timeout: 5000 }).catch(() => {})
      await page.waitForTimeout(2500)
      drawn = Math.max(drawn, await page.locator('.js-plotly-plot').count())
    }
    expect(drawn, 'charts are drawn on the Results tabs').toBeGreaterThan(0)
    await collect()

    expect([...new Set(violations)], 'Content-Security-Policy violations').toEqual([])
  })
})
