/**
 * Shared helpers for the end-to-end specs.
 *
 * Each spec creates its own users and projects through the API, so specs do
 * not depend on one another and can run in any order. The browser is then
 * pointed at the app with the token already in localStorage.
 */
import { expect } from '@playwright/test'
import path from 'path'

export const BASE = process.env.BASE_URL || 'http://localhost:8001'
export const PASSWORD = 'TestPass123!'
/** Bundled demo dataset (tracked in the repository). */
export const SAMPLE_DIR = path.resolve('samples/qin2014_cirrhosis')
export const SAMPLE_ID = 'qin2014_cirrhosis'
export const SAMPLE_NAME = 'Qin2014 Liver Cirrhosis'

/** A small genetic-algorithm run that still finds a real model in seconds. */
export const TINY_GA = {
  general: { algo: 'ga', language: 'bin,ter', data_type: 'raw,prev', thread_number: 2, seed: 42 },
  // Small but not degenerate: with a population near 100 the engine's parent
  // selection can leave fewer than two parents and gpredomics panics (ga.rs cross_over).
  ga: { population_size: 200, max_epochs: 15, min_epochs: 5 },
}

let seq = 0

/** Register and log in a fresh user. */
export async function newUser(request, tag = 'e2e') {
  const email = `${tag}_${Date.now()}_${seq++}@test.com`
  const reg = await request.post(`${BASE}/api/auth/register`, {
    data: { email, password: PASSWORD, full_name: `${tag} user` },
  })
  expect(reg.ok(), `register ${email}: ${reg.status()} ${await reg.text()}`).toBeTruthy()
  const login = await request.post(`${BASE}/api/auth/login`, { data: { email, password: PASSWORD } })
  expect(login.ok(), `login ${email}: ${login.status()}`).toBeTruthy()
  const token = (await login.json()).access_token
  return { email, token, headers: { Authorization: `Bearer ${token}` } }
}

/**
 * Open the app as `user`. `mode` sets the Simple / Expert switch (null leaves
 * it unset, i.e. the default). English is forced so text selectors are stable.
 */
export async function openAs(page, user, { mode = 'expert', locale = 'en' } = {}) {
  await page.goto(`${BASE}/credits`)
  await page.evaluate(({ token, mode, locale }) => {
    localStorage.setItem('token', token)
    localStorage.setItem('locale', locale)
    localStorage.setItem('predomics_onboarding_dismissed', 'true')
    if (mode) localStorage.setItem('ui_mode', mode)
    else localStorage.removeItem('ui_mode')
  }, { token: user.token, mode, locale })
}

/**
 * Collect uncaught script errors and console errors of a page. Failed network
 * requests are left out: the specs check HTTP outcomes themselves.
 */
export function trackPageErrors(page) {
  const errors = []
  page.on('pageerror', e => errors.push(`pageerror: ${e.message}`))
  page.on('console', m => {
    if (m.type() !== 'error') return
    const text = m.text()
    if (/Failed to load resource/i.test(text)) return
    errors.push(`console: ${text}`)
  })
  return errors
}

/** Create an empty project. */
export async function newProject(request, user, name = 'E2E project') {
  const r = await request.post(`${BASE}/api/projects/?${new URLSearchParams({ name })}`, { headers: user.headers })
  expect(r.ok(), `create project: ${r.status()}`).toBeTruthy()
  return (await r.json()).project_id
}

/** Load the bundled sample into a new project; returns its id and file ids by role. */
export async function loadSample(request, user) {
  const r = await request.post(`${BASE}/api/samples/${SAMPLE_ID}/load`, { headers: user.headers })
  expect(r.ok(), `sample load: ${r.status()}`).toBeTruthy()
  const project = await r.json()
  const files = {}
  for (const f of (project.datasets || []).flatMap(d => d.files || [])) files[f.role] = f.id
  expect(files.xtrain && files.ytrain, 'sample project has training files').toBeTruthy()
  return { projectId: project.project_id, files }
}

/** Launch a job through the API. */
export async function launchJob(request, user, projectId, files, config = TINY_GA, name = 'e2e run') {
  const query = new URLSearchParams({ x_file_id: files.xtrain, y_file_id: files.ytrain, job_name: name })
  if (files.xtest && files.ytest) {
    query.set('xtest_file_id', files.xtest)
    query.set('ytest_file_id', files.ytest)
  }
  const r = await request.post(`${BASE}/api/analysis/${projectId}/run?${query}`, { headers: user.headers, data: config })
  expect(r.ok(), `job launch: ${r.status()} ${await r.text()}`).toBeTruthy()
  return (await r.json()).job_id
}

/** Wait until a job leaves pending/running; returns its summary. */
export async function waitForJob(request, user, projectId, jobId, timeout = 240000) {
  const url = `${BASE}/api/analysis/${projectId}/jobs/${jobId}`
  let job = null
  await expect.poll(async () => {
    const r = await request.get(url, { headers: user.headers })
    job = r.ok() ? await r.json() : null
    return job?.status ?? 'pending'
  }, { timeout, intervals: [2000], message: `job ${jobId} reaches a terminal state` })
    .not.toMatch(/^(pending|queued|running)$/)
  return job
}

/** Jobs of a project, newest first. */
export async function listJobs(request, user, projectId) {
  const r = await request.get(`${BASE}/api/analysis/${projectId}/jobs`, { headers: user.headers })
  expect(r.ok(), `list jobs: ${r.status()}`).toBeTruthy()
  const jobs = await r.json()
  return jobs.sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || '')))
}
