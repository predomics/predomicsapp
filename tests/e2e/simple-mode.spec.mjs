/**
 * Simple mode, end to end: the Simple / Expert switch and the guided project
 * page (add the two files → pick a preset → run → read the result).
 *
 * Needs the real engine (results are compared with the API, and the run must
 * produce a model).
 */
import { test, expect } from '@playwright/test'
import path from 'path'
import {
  BASE, SAMPLE_DIR, newUser, openAs, trackPageErrors, newProject, listJobs, waitForJob,
} from './helpers.mjs'

test.describe.serial('Simple mode', () => {
  let user
  let projectId = ''
  let jobId = ''

  test.beforeAll(async ({ request }) => {
    user = await newUser(request, 'simple')
    projectId = await newProject(request, user, 'Simple mode e2e')
  })

  test('the switch starts on Expert, is remembered, and trims the navbar', async ({ page }) => {
    const errors = trackPageErrors(page)
    await openAs(page, user, { mode: null })
    await page.goto(`${BASE}/projects`)

    const sw = page.getByRole('switch')
    await expect(sw).toHaveAttribute('aria-checked', 'false')
    await expect(page.locator('#nav-links a[href="/datasets"]')).toHaveCount(1)
    await expect(page.locator('#nav-links a[href="/meta-analysis"]')).toHaveCount(1)

    await sw.click()
    await expect(sw).toHaveAttribute('aria-checked', 'true')
    await expect(page.locator('#nav-links a[href="/datasets"]')).toHaveCount(0)
    await expect(page.locator('#nav-links a[href="/meta-analysis"]')).toHaveCount(0)
    await expect(page.locator('#nav-links a[href="/projects"]')).toHaveCount(1)

    await page.reload()
    await expect(page.getByRole('switch')).toHaveAttribute('aria-checked', 'true')
    expect(errors).toEqual([])
  })

  test('guided page: add the files, run Quick, read the result', async ({ page, request }) => {
    test.setTimeout(300000)
    const errors = trackPageErrors(page)
    await openAs(page, user, { mode: 'simple' })
    // An expert draft with another algorithm must not leak into a simple run.
    await page.evaluate((pid) => {
      localStorage.setItem(`predomics_params_${pid}`, JSON.stringify({ v: 1, form: { general: { algo: 'beam' } } }))
    }, projectId)

    await page.goto(`${BASE}/project/${projectId}`)
    const simple = page.locator('.simple-project')
    await expect(simple).toBeVisible()
    await expect(page.locator('.tab-nav')).toHaveCount(0)
    await expect(simple.locator('.step h3')).toHaveCount(3)
    await expect(page.locator('.btn-run')).toBeDisabled()

    // Step 1: the two files
    const inputs = simple.locator('input[type=file]')
    await inputs.nth(0).setInputFiles(path.join(SAMPLE_DIR, 'Xtrain.tsv'))
    await expect(simple.locator('.file-ok')).toHaveCount(1, { timeout: 60000 })
    await inputs.nth(1).setInputFiles(path.join(SAMPLE_DIR, 'Ytrain.tsv'))
    await expect(simple.locator('.file-ok')).toHaveCount(2, { timeout: 60000 })
    await expect(simple.locator('.msg-error')).toHaveCount(0)

    // Step 2: Quick, run
    await simple.locator('.preset', { hasText: 'Quick' }).click()
    await expect(page.locator('.btn-run')).toBeEnabled()
    await page.locator('.btn-run').click()

    // Step 3: the result
    const verdict = simple.locator('.verdict')
    await expect(verdict).toBeVisible({ timeout: 240000 })

    const jobs = await listJobs(request, user, projectId)
    expect(jobs).toHaveLength(1)
    jobId = jobs[0].job_id
    expect(jobs[0].status).toBe('completed')

    // The run used the defaults plus the Quick preset, not the expert draft.
    const { config: cfg } = await (await request.get(`${BASE}/api/analysis/${projectId}/jobs/${jobId}/config`, { headers: user.headers })).json()
    expect(cfg.general.algo).toBe('ga')
    expect(cfg.ga.population_size).toBe(200)
    expect(cfg.general.cv).toBe(false)

    // What the page shows matches the API.
    const detail = await (await request.get(`${BASE}/api/analysis/${projectId}/jobs/${jobId}/detail`, { headers: user.headers })).json()
    expect(detail.best_auc_test, 'holdout test AUC is recorded').toBeGreaterThan(0.5)
    await expect(verdict.locator('.score-label')).toHaveText('AUC on the test samples')
    await expect(verdict.locator('.score-value')).toHaveText(detail.best_auc_test.toFixed(3))
    await expect(simple.locator('.metrics dd').first()).toHaveText(String(detail.best_k))

    const expected = Object.keys(detail.best_individual.features).map(i => detail.feature_names[Number(i)]).sort()
    const shown = (await simple.locator('.sig-col li').allInnerTexts()).map(s => s.trim()).sort()
    expect(shown).toEqual(expected)

    expect(errors).toEqual([])
  })

  test('the expert link opens the same job in the full results', async ({ page }) => {
    expect(jobId, 'a job ran in the previous test').toBeTruthy()
    await openAs(page, user, { mode: 'simple' })
    await page.goto(`${BASE}/project/${projectId}`)
    await expect(page.locator('.verdict')).toBeVisible({ timeout: 30000 })

    await page.getByRole('button', { name: 'See every detail in Expert mode' }).click()
    await expect(page).toHaveURL(new RegExp(`/project/${projectId}/results/${jobId}$`))
    await expect(page.getByRole('switch')).toHaveAttribute('aria-checked', 'false')
    await expect(page.locator('.tab-nav')).toBeVisible()
    await expect(page.locator('.sub-tabs')).toBeVisible({ timeout: 60000 })
  })

  test('a running analysis shows progress and can be stopped', async ({ page, request }) => {
    test.setTimeout(180000)
    const errors = trackPageErrors(page)
    await openAs(page, user, { mode: 'simple' })
    await page.goto(`${BASE}/project/${projectId}`)
    const simple = page.locator('.simple-project')
    await expect(simple.locator('.file-ok')).toHaveCount(2)

    // Thorough is long enough to watch it run.
    await simple.locator('.preset', { hasText: 'Thorough' }).click()
    await page.locator('.btn-run').click()
    await expect(simple.locator('.running')).toBeVisible({ timeout: 30000 })
    await expect(page.locator('.btn-run')).toBeDisabled()
    await expect(simple.locator('.progress-text')).toHaveText(/^\d+ % done$/, { timeout: 90000 })

    await simple.getByRole('button', { name: 'Stop the analysis' }).click()
    await expect(simple.locator('.running')).toHaveCount(0, { timeout: 60000 })
    await expect(page.locator('.btn-run')).toBeEnabled()

    const [latest] = await listJobs(request, user, projectId)
    expect(latest.job_id).not.toBe(jobId)
    const stopped = await waitForJob(request, user, projectId, latest.job_id, 60000)
    expect(stopped.status).toBe('failed')
    expect(stopped.error_message).toMatch(/cancel/i)

    // A stopped run is not an error: the previous result is shown again.
    await expect(simple.locator('.verdict')).toBeVisible({ timeout: 30000 })
    await expect(simple.locator('.msg-error')).toHaveCount(0)
    expect(errors).toEqual([])
  })
})
