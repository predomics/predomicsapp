import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import CollapsibleSection from '../components/CollapsibleSection.vue'
import { isSectionOpen, setAllSections, mountedSections, resetSections } from '../composables/useSections'

function make(props = {}) {
  return mount(CollapsibleSection, {
    props: { sid: 'test.section', ...props },
    slots: { title: 'Population table', default: '<p class="content">rows</p>' },
    attachTo: document.body,
  })
}

describe('CollapsibleSection', () => {
  beforeEach(() => { localStorage.clear(); resetSections() })

  it('is open by default and folds on click, remembering the choice', async () => {
    const w = make()
    const btn = w.get('button')
    expect(btn.attributes('aria-expanded')).toBe('true')
    expect(w.get('.content').isVisible()).toBe(true)
    await btn.trigger('click')
    expect(btn.attributes('aria-expanded')).toBe('false')
    expect(w.get('.content').isVisible()).toBe(false) // still mounted, just hidden
    expect(JSON.parse(localStorage.getItem('predomics.sections'))).toEqual({ 'test.section': false })
    w.unmount()
    const again = make()
    expect(again.get('button').attributes('aria-expanded')).toBe('false')
    again.unmount()
  })

  it('honours default-open=false until the user chooses', async () => {
    const w = make({ sid: 'test.table', defaultOpen: false })
    expect(w.get('button').attributes('aria-expanded')).toBe('false')
    await w.get('button').trigger('click')
    expect(isSectionOpen('test.table', false)).toBe(true)
    w.unmount()
  })

  it('names its button after the title and controls its body', () => {
    const w = make()
    const btn = w.get('button')
    const title = w.get(`#${btn.attributes('aria-labelledby')}`)
    expect(title.text()).toBe('Population table')
    expect(w.find(`#${btn.attributes('aria-controls')}`).exists()).toBe(true)
    w.unmount()
  })

  it('fold all / unfold all act on the sections on screen', async () => {
    const a = make({ sid: 'p.a' })
    const b = make({ sid: 'p.b', defaultOpen: false })
    expect(mountedSections().map(s => s.sid).sort()).toEqual(['p.a', 'p.b'])
    setAllSections(false)
    await nextTick()
    expect(a.get('button').attributes('aria-expanded')).toBe('false')
    setAllSections(true)
    await nextTick()
    expect(b.get('button').attributes('aria-expanded')).toBe('true')
    a.unmount(); b.unmount()
    expect(mountedSections()).toEqual([])
  })
})
