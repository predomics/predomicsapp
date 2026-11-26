/**
 * Expert mode through the interface: launch from the Parameters tab, follow the
 * job to its results, open every results section, and check who may see what
 * (another user, a guest with or without a public link).
 *
 * Needs the real engine.
 */
import { test, expect } from '@playwright/test'
import {
  BASE, SAMPLE_NAME, newUser, openAs, trackPageErrors, loadSample, listJobs, waitForJob,
} from './helpers.mjs'

/** Error boxes of the results sections (visible ones only). */
const ERRORS = ['.async-error', '.error-msg', '.error-message', '.error-text']
  .map(c => `.results-tab ${c}:visible`).join(', ')

test.describe.serial('Expert flow', () => {
  let owner
  let projectId = ''
  let jobId = ''

  test.beforeAll(async ({ request }) => {
    owner = await newUser(request, 'expert')
    ;({ projectId } = await loadSample(request, owner))
  })

  test('launch from the Parameters tab and land on the results', async ({ page, request }) => {
    test.setTimeout(300000)
    const errors = trackPageErrors(page)
    await openAs(page, owner, { mode: 'expert' })
    await page.goto(`${BASE}/project/${projectId}/parameters`)

    const quick = page.locator('.preset-btn', { hasText: 'Quick' })
    await quick.click()
    await expect(quick).toHaveAttribute('aria-pressed', 'true')
    const launch = page.locator('.btn-launch')
    await expect(launch).toBeEnabled()
    await launch.click()

    // The console opens for the new job.
    await expect(page.locator('.console-bottom')).toBeVisible({ timeout: 30000 })
    const [job] = await listJobs(request, owner, projectId)
    expect(job, 'a job was created').toBeTruthy()
    jobId = job.job_id
    const done = await waitForJob(request, owner, projectId, jobId)
    expect(done.status, `job ended as ${done.status}: ${done.error_message || ''}`).toBe('completed')

    // The completion toast leads to the results of that job.
    await page.getByRole('button', { name: /view results/i }).first().click({ timeout: 60000 })
    await expect(page).toHaveURL(new RegExp(`/project/${projectId}/results/${jobId}$`))
    await expect(page.locator('.sub-tabs')).toBeVisible({ timeout: 60000 })
    expect(errors).toEqual([])
  })

  test('every results section opens without a script error', async ({ page }) => {
    test.setTimeout(240000)
    expect(jobId, 'a job ran in the previous test').toBeTruthy()
    const errors = trackPageErrors(page)
    await openAs(page, owner, { mode: 'expert' })
    await page.goto(`${BASE}/project/${projectId}/results/${jobId}`)
    const tabs = page.locator('.sub-tabs [role=tab]')
    await expect(tabs.first()).toBeVisible({ timeout: 60000 })

    const names = await tabs.allInnerTexts()
    expect(names.length).toBeGreaterThanOrEqual(8)
    for (let i = 0; i < names.length; i++) {
      const tab = tabs.nth(i)
      await tab.click()
      await expect(tab).toHaveAttribute('aria-selected', 'true')
      // Sections load their data and draw charts asynchronously; a section
      // that is too slow ends on a timeout message, which counts as a failure.
      await expect(page.locator('.async-loading:visible, .loading-msg:visible')).toHaveCount(0, { timeout: 60000 })
      await expect(page.locator(ERRORS), `section "${names[i]}" shows an error`).toHaveCount(0)
    }
    expect(errors, `script errors while opening: ${names.join(', ')}`).toEqual([])
  })

  test('another user cannot open a private project', async ({ page, request }) => {
    const other = await newUser(request, 'intruder')
    for (const url of [
      `${BASE}/api/projects/${projectId}`,
      `${BASE}/api/analysis/${projectId}/jobs`,
      `${BASE}/api/analysis/${projectId}/jobs/${jobId}/results`,
    ]) {
      const r = await request.get(url, { headers: other.headers })
      expect([403, 404], `${url} → ${r.status()}`).toContain(r.status())
    }

    await openAs(page, other, { mode: 'expert' })
    await page.goto(`${BASE}/project/${projectId}/data`)
    await expect(page.locator('.async-error')).toBeVisible({ timeout: 30000 })
    await expect(page.getByText(SAMPLE_NAME)).toHaveCount(0)
  })

  test('a public link shows the results to a guest, a wrong one does not', async ({ browser, request }) => {
    const created = await request.post(`${BASE}/api/projects/${projectId}/public`, { headers: owner.headers, data: {} })
    expect(created.ok(), `create public link: ${created.status()}`).toBeTruthy()
    const { token } = await created.json()

    const guest = await browser.newContext()
    const page = await guest.newPage()
    const errors = trackPageErrors(page)
    await page.goto(`${BASE}/public/${token}`)
    await expect(page.locator('.project-info')).toContainText(SAMPLE_NAME, { timeout: 30000 })
    await page.locator('.job-card').first().click()
    await expect(page.locator('.metric-card').first()).toBeVisible({ timeout: 30000 })
    expect(errors).toEqual([])

    await page.goto(`${BASE}/public/not-a-real-token`)
    await expect(page.locator('.error-box')).toBeVisible({ timeout: 30000 })
    await expect(page.locator('.project-info')).toHaveCount(0)
    await guest.close()
  })
})
