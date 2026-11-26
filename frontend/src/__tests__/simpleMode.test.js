/**
 * Simple mode: the Simple / Expert switch and the helpers of the guided page.
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useUiModeStore } from '../stores/uiMode'
import {
  buildSimplePayload, aucGrade, splitSignature, latestCompletedJob, liveJob,
} from '../utils/simpleRun'
import { paramDefault } from '../data/parameterDefs'

describe('useUiModeStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })

  it('starts in expert mode so existing users keep the full interface', () => {
    expect(useUiModeStore().mode).toBe('expert')
  })

  it('toggles and remembers the choice', () => {
    const ui = useUiModeStore()
    ui.toggle()
    expect(ui.isSimple).toBe(true)
    expect(localStorage.getItem('ui_mode')).toBe('simple')
    setActivePinia(createPinia())
    expect(useUiModeStore().isSimple).toBe(true)
  })

  it('ignores unknown stored or requested modes', () => {
    localStorage.setItem('ui_mode', 'wizard')
    const ui = useUiModeStore()
    expect(ui.mode).toBe('expert')
    ui.setMode('nonsense')
    expect(ui.mode).toBe('expert')
  })
})

describe('buildSimplePayload', () => {
  it('starts from the defaults and applies the preset', () => {
    const p = buildSimplePayload('quick')
    expect(p.general.algo).toBe(paramDefault('general', 'algo'))
    expect(p.general.fit).toBe(paramDefault('general', 'fit'))
    expect(p.ga.population_size).toBe(200)
    expect(p.data.holdout_ratio).toBeGreaterThan(0)
  })

  it('falls back to the standard preset for an unknown id', () => {
    expect(buildSimplePayload('nope')).toEqual(buildSimplePayload('standard'))
  })

  it('returns independent objects', () => {
    const a = buildSimplePayload('thorough')
    a.ga.population_size = 1
    expect(buildSimplePayload('thorough').ga.population_size).toBe(5000)
  })
})

describe('aucGrade', () => {
  it.each([
    [0.95, 'excellent'], [0.85, 'good'], [0.72, 'fair'], [0.65, 'weak'], [0.5, 'chance'], [null, null],
  ])('%s → %s', (auc, grade) => {
    expect(aucGrade(auc)).toBe(grade)
  })
})

describe('splitSignature', () => {
  it('splits features by coefficient sign and names them', () => {
    const { up, down } = splitSignature({ 2: 1, 0: -1, 1: 1 }, ['a', 'b', 'c'])
    expect(up).toEqual(['b', 'c'])
    expect(down).toEqual(['a'])
  })

  it('keeps an index when the name is missing', () => {
    expect(splitSignature({ 5: -1 }, []).down).toEqual(['#5'])
  })
})

describe('job pickers', () => {
  const jobs = [
    { job_id: 'a', status: 'completed', created_at: '2026-01-01T00:00:00' },
    { job_id: 'b', status: 'completed', created_at: '2026-02-01T00:00:00' },
    { job_id: 'c', status: 'failed', created_at: '2026-03-01T00:00:00' },
    'bare-id',
  ]

  it('latestCompletedJob picks the newest completed job', () => {
    expect(latestCompletedJob(jobs).job_id).toBe('b')
    expect(latestCompletedJob([])).toBeNull()
  })

  it('liveJob prefers a running job over a pending one', () => {
    expect(liveJob(jobs)).toBeNull()
    expect(liveJob([{ job_id: 'p', status: 'pending' }, { job_id: 'r', status: 'running' }]).job_id).toBe('r')
  })
})
