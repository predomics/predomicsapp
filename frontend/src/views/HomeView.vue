<template>
  <div class="home">
    <!-- ═══════════════════════════════════════════
         HERO — Full-width gradient with logo + CTA
         ═══════════════════════════════════════════ -->
    <section class="hero">
      <div class="hero-bg"></div>
      <div class="hero-content">
        <img src="/logo-dark.png" alt="PredomicsApp" class="hero-logo" />
        <h1 class="hero-title">PredomicsApp</h1>
        <p class="hero-subtitle">{{ $t('home.subtitle') }}</p>
        <p class="hero-desc">{{ $t('home.description') }}</p>
        <div class="hero-actions">
          <router-link to="/projects" class="btn btn-primary">{{ $t('home.getStarted') }}</router-link>
          <a href="#workflow" class="btn btn-ghost" @click.prevent="scrollTo('workflow')">{{ $t('home.learnMore') }}</a>
        </div>
      </div>
    </section>

    <!-- ═══════════════════════════════════════════
         PIPELINE — Animated step-by-step workflow
         ═══════════════════════════════════════════ -->
    <section id="workflow" class="section workflow reveal">
      <h2 class="section-title">{{ $t('home.howItWorks') }}</h2>
      <p class="section-subtitle">{{ $t('home.howItWorksDesc') }}</p>
      <div class="workflow-track">
        <template v-for="(step, i) in workflowSteps" :key="i">
          <div class="wf-step" :style="{ '--delay': (i * 0.2 + 0.2) + 's' }">
            <div class="wf-icon-ring">
              <span class="wf-icon">{{ step.icon }}</span>
              <span class="wf-badge">{{ i + 1 }}</span>
            </div>
            <h3 class="wf-label">{{ step.label }}</h3>
            <p class="wf-desc">{{ step.desc }}</p>
          </div>
          <div v-if="i < workflowSteps.length - 1" class="wf-connector" :style="{ '--delay': (i * 0.2 + 0.35) + 's' }">
            <div class="wf-line"></div>
            <div class="wf-dot"></div>
            <div class="wf-dot wf-dot-2"></div>
          </div>
        </template>
      </div>
    </section>

    <!-- ═══════════════════════════════════════════
         FEATURES — Three core feature cards
         ═══════════════════════════════════════════ -->
    <section class="section features-section reveal">
      <div class="features">
        <div class="feature-card" v-for="feat in featureCards" :key="feat.title">
          <div class="feature-icon-wrap">{{ feat.icon }}</div>
          <h3>{{ feat.title }}</h3>
          <p>{{ feat.desc }}</p>
        </div>
      </div>
    </section>

    <!-- ═══════════════════════════════════════════
         CAPABILITIES — Platform features grid
         ═══════════════════════════════════════════ -->
    <section class="section capabilities reveal">
      <h2 class="section-title">{{ $t('home.capabilities') }}</h2>
      <div class="cap-grid">
        <div class="cap-item" v-for="cap in capabilities" :key="cap.title">
          <div class="cap-icon">{{ cap.icon }}</div>
          <div class="cap-text">
            <h3>{{ cap.title }}</h3>
            <p>{{ cap.desc }}</p>
          </div>
        </div>
      </div>
    </section>

    <!-- ═══════════════════════════════════════════
         CTA BANNER — Mid-page call to action
         ═══════════════════════════════════════════ -->
    <section class="cta-banner reveal">
      <div class="cta-inner">
        <h2>{{ $t('home.startAnalyzing') }}</h2>
        <p>{{ $t('home.openSourceDesc') }}</p>
        <router-link to="/projects" class="btn btn-primary btn-lg">{{ $t('home.startNow') }}</router-link>
      </div>
    </section>

    <!-- ═══════════════════════════════════════════
         USE CASES — Real-world examples with stats
         ═══════════════════════════════════════════ -->
    <section class="section use-cases reveal">
      <h2 class="section-title">{{ $t('home.useCases') }}</h2>
      <div class="case-grid">
        <div class="case-card" v-for="uc in useCases" :key="uc.id">
          <div class="case-header">
            <span class="case-icon">{{ uc.icon }}</span>
            <h3>{{ $t(`home.uc.${uc.id}.title`) }}</h3>
          </div>
          <p class="case-desc">{{ $t(`home.uc.${uc.id}.desc`) }}</p>
          <div class="case-stats">
            <span v-for="(val, label) in uc.stats" :key="label" class="case-stat">
              <strong>{{ val }}</strong>
              <span>{{ $t(`home.ucStat.${label}`) }}</span>
            </span>
          </div>
          <div class="case-ref" v-if="uc.reference">
            <a v-if="uc.doi" :href="uc.doi" target="_blank" rel="noopener">{{ uc.reference }}</a>
            <span v-else>{{ uc.reference }}</span>
            <span v-if="uc.demo" class="demo-badge">{{ $t('home.demoBadge') }}</span>
          </div>
        </div>
      </div>
    </section>

    <!-- ═══════════════════════════════════════════
         TECH STATS — Key performance numbers
         ═══════════════════════════════════════════ -->
    <section class="section tech reveal">
      <h2 class="section-title">{{ $t('home.builtForPerformance') }}</h2>
      <div class="tech-grid">
        <div class="tech-item" v-for="stat in techStats" :key="stat.label">
          <div class="tech-val">{{ stat.value }}</div>
          <div class="tech-label">{{ stat.label }}</div>
        </div>
      </div>
    </section>

    <!-- ═══════════════════════════════════════════
         TECHNOLOGY STACK — Framework tags
         ═══════════════════════════════════════════ -->
    <section class="section stack reveal">
      <h2 class="section-title">{{ $t('home.techStack') }}</h2>
      <div class="stack-grid">
        <div class="stack-group" v-for="group in stackGroups" :key="group.label">
          <h4>{{ group.label }}</h4>
          <div class="stack-tags">
            <span
              v-for="tag in group.tags"
              :key="tag.name"
              class="stack-tag"
              :class="{ accent: tag.accent }"
            >{{ tag.name }}</span>
          </div>
        </div>
      </div>
    </section>

    <!-- ═══════════════════════════════════════════
         FOOTER STATUS — API health
         ═══════════════════════════════════════════ -->
    <footer class="site-footer">
      <div class="footer-inner" v-if="health">
        <span class="footer-pill">
          <span class="footer-dot" :class="health.status === 'ok' ? 'ok' : 'err'"></span>
          {{ $t('home.api') }}: {{ health.status }}
        </span>
        <span class="footer-pill">
          <span class="footer-dot" :class="health.gpredomicspy_available ? 'ok' : 'warn'"></span>
          {{ $t('home.engine') }}: {{ health.gpredomicspy_available ? $t('home.ready') : $t('home.mockMode') }}
        </span>
        <span class="footer-version">v{{ health.version }}</span>
      </div>
      <div class="footer-copy">{{ $t('home.openSource') }} &middot; GPL-3.0</div>
    </footer>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api'

const { t } = useI18n()
const health = ref(null)

// ── Scroll reveal via IntersectionObserver ──
let observer = null
onMounted(() => {
  observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add('visible')
          observer.unobserve(entry.target)
        }
      })
    },
    { threshold: 0.12, rootMargin: '0px 0px -40px 0px' }
  )
  document.querySelectorAll('.reveal').forEach((el) => observer.observe(el))
})
onUnmounted(() => {
  if (observer) observer.disconnect()
})

function scrollTo(id) {
  document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' })
}

// ── Data ──
const workflowSteps = computed(() => [
  { icon: '\u21EA', label: t('home.workflow.upload'), desc: t('home.workflow.uploadDesc') },
  { icon: '\u2699', label: t('home.workflow.configure'), desc: t('home.workflow.configureDesc') },
  { icon: '\u26A1', label: t('home.workflow.analyze'), desc: t('home.workflow.analyzeDesc') },
  { icon: '\u2316', label: t('home.workflow.explore'), desc: t('home.workflow.exploreDesc') },
])

const featureCards = computed(() => [
  { icon: '\u{21EA}', title: t('home.uploadData'), desc: t('home.uploadDataDesc') },
  { icon: '\u{2699}', title: t('home.configureRun'), desc: t('home.configureRunDesc') },
  { icon: '\u{2316}', title: t('home.exploreResults'), desc: t('home.exploreResultsDesc') },
])

const capabilities = computed(() => [
  { icon: '\u{2713}', title: t('home.externalValidation'), desc: t('home.externalValidationDesc') },
  { icon: '\u{2301}', title: t('home.predictionApi'), desc: t('home.predictionApiDesc') },
  { icon: '\u{2261}', title: t('home.pdfReports'), desc: t('home.pdfReportsDesc') },
  { icon: '\u{25A3}', title: t('home.dashboardOverview'), desc: t('home.dashboardOverviewDesc') },
  { icon: '\u{2235}', title: t('home.projectNotes'), desc: t('home.projectNotesDesc') },
  { icon: '\u{21C4}', title: t('home.publicSharing'), desc: t('home.publicSharingDesc') },
  { icon: '\u{25CE}', title: t('home.ecosystemNetwork'), desc: t('home.ecosystemNetworkDesc') },
])

const useCases = [
  {
    icon: '\u{2695}',
    id: 'cirrhosis',
    stats: { auc: '0.94', features: 'k=8', samples: '210' },
    reference: 'Qin N, Yang F, Li A, Prifti E, et al. Nature 2014;513:59-64',
    doi: 'https://doi.org/10.1038/nature13568',
    demo: true,
  },
  {
    icon: '\u{2684}',
    id: 'cancer',
    stats: { auc: '0.92', features: 'k=12', samples: '156' },
    reference: 'Zeller G, et al. Mol. Syst. Biol. 2014;10(11):766',
    doi: 'https://doi.org/10.15252/msb.20145645',
  },
  {
    icon: '\u{2318}',
    id: 'ici',
    stats: { auc: '0.87', features: 'k=71', samples: '417' },
    reference: 'Derosa L, Iebba V, et al. Cell 2024;187(13):3373-3389',
    doi: 'https://doi.org/10.1016/j.cell.2024.05.029',
    demo: true,
  },
  {
    icon: '\u{2623}',
    id: 'metabolic',
    stats: { auc: '0.89', features: 'k=10', samples: '345' },
    reference: 'Karlsson FH, et al. Nature 2013;498:99-103',
    doi: 'https://doi.org/10.1038/nature12198',
  },
]

const techStats = computed(() => [
  { value: 'Rust', label: t('home.coreEngine') },
  { value: '3', label: t('home.algorithms') },
  { value: '3', label: t('home.modelLanguages') },
  { value: 'GPU', label: t('home.acceleration') },
  { value: '50+', label: t('home.apiEndpoints') },
  { value: '274', label: t('home.tests') },
])

const stackGroups = computed(() => [
  {
    label: t('home.frontend'),
    tags: [
      { name: 'Vue 3' }, { name: 'Pinia' }, { name: 'Vue Router' },
      { name: 'Plotly.js' }, { name: 'vue-i18n' }, { name: 'Vite' },
    ],
  },
  {
    label: t('home.backend'),
    tags: [
      { name: 'FastAPI' }, { name: 'SQLAlchemy' }, { name: 'Pydantic' },
      { name: 'WebSocket' }, { name: 'reportlab' },
    ],
  },
  {
    label: t('home.mlEngine'),
    tags: [
      { name: 'Rust', accent: true }, { name: 'gpredomicspy', accent: true },
      { name: 'GPU (CUDA)' }, { name: 'NumPy' }, { name: 'pandas' },
    ],
  },
  {
    label: t('home.infrastructure'),
    tags: [
      { name: 'Docker' }, { name: 'PostgreSQL' }, { name: 'NGINX' },
      { name: 'JWT + API Keys' }, { name: 'pytest + Vitest' },
    ],
  },
])

onMounted(async () => {
  try {
    const { data } = await api.system.health()
    health.value = data
  } catch (e) {
    console.error('Health check failed:', e)
  }
})
</script>

<style scoped>
/* ================================================================
   RESET & LAYOUT
   ================================================================ */
.home {
  text-align: center;
  overflow-x: hidden;
}

.section {
  max-width: 1100px;
  margin: 0 auto;
  padding: 4rem 1.5rem;
}

.section-title {
  font-size: 1.75rem;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 0.5rem;
  letter-spacing: -0.02em;
}

.section-subtitle {
  font-size: 1rem;
  color: var(--text-muted);
  margin-bottom: 2.5rem;
  max-width: 520px;
  margin-left: auto;
  margin-right: auto;
  line-height: 1.6;
}

/* ================================================================
   SCROLL REVEAL ANIMATIONS
   ================================================================ */
.reveal {
  opacity: 0;
  transform: translateY(30px);
  transition: opacity 0.7s ease, transform 0.7s ease;
}
.reveal.visible {
  opacity: 1;
  transform: translateY(0);
}

/* ================================================================
   HERO
   ================================================================ */
.hero {
  position: relative;
  padding: 5rem 1.5rem 4rem;
  overflow: hidden;
}

.hero-bg {
  position: absolute;
  inset: 0;
  background:
    radial-gradient(ellipse 80% 60% at 50% -10%, rgba(79, 195, 247, 0.15), transparent),
    radial-gradient(ellipse 60% 50% at 80% 80%, rgba(79, 195, 247, 0.08), transparent),
    linear-gradient(180deg, var(--bg-page) 0%, var(--bg-card) 100%);
  z-index: 0;
}

/* Decorative dots */
.hero-bg::before {
  content: '';
  position: absolute;
  inset: 0;
  background-image:
    radial-gradient(circle 1.5px, rgba(79, 195, 247, 0.18) 1px, transparent 1px);
  background-size: 40px 40px;
  background-position: 0 0;
  mask-image: radial-gradient(ellipse 70% 60% at 50% 40%, black 20%, transparent 70%);
  -webkit-mask-image: radial-gradient(ellipse 70% 60% at 50% 40%, black 20%, transparent 70%);
}

.hero-content {
  position: relative;
  z-index: 1;
  max-width: 680px;
  margin: 0 auto;
}

.hero-logo {
  width: 80px;
  height: 80px;
  object-fit: contain;
  border-radius: 16px;
  margin-bottom: 1.25rem;
  box-shadow: 0 4px 24px rgba(79, 195, 247, 0.2);
}

.hero-title {
  font-size: 3rem;
  font-weight: 800;
  color: var(--text-primary);
  letter-spacing: -0.03em;
  margin-bottom: 0.75rem;
  line-height: 1.1;
}

.hero-subtitle {
  font-size: 1.25rem;
  color: var(--text-secondary);
  margin-bottom: 1rem;
  line-height: 1.5;
  animation: fadeUp 0.8s ease 0.2s both;
}

.hero-desc {
  font-size: 0.95rem;
  color: var(--text-muted);
  max-width: 540px;
  margin: 0 auto 2rem;
  line-height: 1.65;
  animation: fadeUp 0.8s ease 0.4s both;
}

@keyframes fadeUp {
  from { opacity: 0; transform: translateY(16px); }
  to { opacity: 1; transform: translateY(0); }
}

.hero-actions {
  display: flex;
  justify-content: center;
  gap: 1rem;
  animation: fadeUp 0.8s ease 0.6s both;
}

/* ── Buttons ── */
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0.75rem 2rem;
  border-radius: 10px;
  text-decoration: none;
  font-weight: 600;
  font-size: 0.95rem;
  cursor: pointer;
  transition: all 0.2s ease;
  border: none;
}

.btn-primary {
  background: var(--accent);
  color: var(--accent-text);
  box-shadow: 0 2px 12px rgba(26, 26, 46, 0.15);
}
.btn-primary:hover {
  background: var(--accent-hover);
  box-shadow: 0 4px 20px rgba(26, 26, 46, 0.25);
  transform: translateY(-1px);
}

.btn-ghost {
  background: transparent;
  color: var(--text-secondary);
  border: 1.5px solid var(--border);
}
.btn-ghost:hover {
  border-color: var(--accent);
  color: var(--accent);
}

.btn-lg {
  padding: 0.9rem 2.5rem;
  font-size: 1.05rem;
}

/* ================================================================
   ANIMATED WORKFLOW
   ================================================================ */
.workflow {
  background: var(--bg-card);
  border-top: 1px solid var(--border-lighter);
  border-bottom: 1px solid var(--border-lighter);
  max-width: 100%;
  padding: 4rem 1.5rem;
}

/* Steps animate individually, so override section-level reveal */
.workflow.reveal {
  opacity: 1;
  transform: none;
  transition: none;
}

.workflow .section-title,
.workflow .section-subtitle {
  opacity: 0;
  transform: translateY(20px);
  transition: opacity 0.6s ease, transform 0.6s ease;
}
.workflow.visible .section-title { opacity: 1; transform: translateY(0); }
.workflow.visible .section-subtitle { opacity: 1; transform: translateY(0); transition-delay: 0.1s; }

.workflow-track {
  display: flex;
  align-items: flex-start;
  justify-content: center;
  max-width: 960px;
  margin: 0 auto;
}

/* ── Step card ── */
.wf-step {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  padding: 1.25rem 0.75rem;
  flex: 1;
  min-width: 0;
  opacity: 0;
  transform: translateY(24px);
  cursor: default;
}
.workflow.visible .wf-step {
  animation: wfStepReveal 0.6s ease forwards;
  animation-delay: var(--delay, 0s);
}

.wf-icon-ring {
  width: 68px;
  height: 68px;
  border-radius: 50%;
  background: linear-gradient(135deg, rgba(79, 195, 247, 0.12), rgba(79, 195, 247, 0.03));
  border: 2px solid rgba(79, 195, 247, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  transition: all 0.35s ease;
}
.wf-step:hover .wf-icon-ring {
  border-color: var(--brand);
  background: linear-gradient(135deg, rgba(79, 195, 247, 0.22), rgba(79, 195, 247, 0.08));
  box-shadow: 0 0 24px rgba(79, 195, 247, 0.25), 0 0 48px rgba(79, 195, 247, 0.08);
  transform: scale(1.1);
}

.wf-icon {
  font-size: 1.7rem;
  line-height: 1;
}

.wf-badge {
  position: absolute;
  top: -3px;
  right: -3px;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: var(--brand);
  color: #fff;
  font-size: 0.75rem;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 2px 8px rgba(79, 195, 247, 0.4);
}

.wf-label {
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--text-primary);
  margin-top: 0.75rem;
  margin-bottom: 0.25rem;
}

.wf-desc {
  font-size: 0.78rem;
  color: var(--text-muted);
  line-height: 1.5;
  max-width: 170px;
  margin: 0 auto;
}

/* ── Connector with flowing dots ── */
.wf-connector {
  display: flex;
  align-items: center;
  width: 48px;
  flex-shrink: 0;
  padding-top: 2.1rem;
  position: relative;
  opacity: 0;
  transform: translateY(24px);
}
.workflow.visible .wf-connector {
  animation: wfStepReveal 0.5s ease forwards;
  animation-delay: var(--delay, 0s);
}

.wf-line {
  width: 100%;
  height: 2px;
  background: linear-gradient(90deg, rgba(79, 195, 247, 0.5), rgba(79, 195, 247, 0.2));
  border-radius: 1px;
}
.wf-line::after {
  content: '';
  position: absolute;
  right: -1px;
  top: calc(2.1rem - 3px);
  width: 0;
  height: 0;
  border-top: 4px solid transparent;
  border-bottom: 4px solid transparent;
  border-left: 6px solid rgba(79, 195, 247, 0.45);
}

.wf-dot {
  position: absolute;
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--brand);
  box-shadow: 0 0 6px rgba(79, 195, 247, 0.7);
  top: calc(2.1rem - 1.5px);
}
.workflow.visible .wf-dot {
  animation: wfFlowDot 2.2s ease-in-out infinite;
}
.workflow.visible .wf-dot-2 {
  animation: wfFlowDot 2.2s ease-in-out 1.1s infinite;
}

/* ── Keyframes ── */
@keyframes wfFlowDot {
  0%   { left: -5px; opacity: 0; }
  12%  { opacity: 1; }
  88%  { opacity: 1; }
  100% { left: calc(48px - 5px); opacity: 0; }
}

@keyframes wfStepReveal {
  from { opacity: 0; transform: translateY(24px); }
  to   { opacity: 1; transform: translateY(0); }
}

/* ================================================================
   FEATURE CARDS
   ================================================================ */
.features {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 1.5rem;
}

.feature-card {
  background: var(--bg-card);
  padding: 2rem 1.75rem;
  border-radius: var(--card-radius);
  box-shadow: var(--card-shadow);
  text-align: left;
  border-left: 3px solid var(--brand);
  transition: box-shadow 0.25s, transform 0.25s;
}
.feature-card:hover {
  box-shadow: var(--card-shadow-hover);
  transform: translateY(-3px);
}

.feature-icon-wrap {
  font-size: 1.8rem;
  width: 48px;
  height: 48px;
  border-radius: 12px;
  background: var(--info-bg);
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 1rem;
}

.feature-card h3 {
  font-size: 1rem;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 0.5rem;
}

.feature-card p {
  color: var(--text-muted);
  font-size: 0.88rem;
  line-height: 1.6;
}

/* ================================================================
   CAPABILITIES
   ================================================================ */
.cap-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 1rem;
  text-align: left;
}

.cap-item {
  display: flex;
  gap: 1rem;
  align-items: flex-start;
  background: var(--bg-card);
  padding: 1.25rem 1.5rem;
  border-radius: var(--card-radius);
  border: 1px solid var(--border-lighter);
  transition: border-color 0.25s, box-shadow 0.25s, transform 0.25s;
}
.cap-item:hover {
  border-color: var(--brand);
  box-shadow: 0 0 0 1px var(--brand), var(--card-shadow-hover);
  transform: translateY(-2px);
}

.cap-icon {
  font-size: 1.5rem;
  flex-shrink: 0;
  width: 40px;
  height: 40px;
  border-radius: 10px;
  background: var(--info-bg);
  display: flex;
  align-items: center;
  justify-content: center;
}

.cap-text h3 {
  font-size: 0.92rem;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 0.25rem;
}
.cap-text p {
  font-size: 0.82rem;
  color: var(--text-muted);
  line-height: 1.55;
}

/* ================================================================
   CTA BANNER
   ================================================================ */
.cta-banner {
  padding: 0 1.5rem;
  margin: 0 auto;
  max-width: 1100px;
}

.cta-inner {
  background:
    radial-gradient(ellipse 80% 80% at 20% 100%, rgba(79, 195, 247, 0.12), transparent),
    var(--bg-card);
  border: 1px solid var(--border-lighter);
  border-radius: 16px;
  padding: 3rem 2rem;
  text-align: center;
}

.cta-inner h2 {
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 0.5rem;
}

.cta-inner p {
  color: var(--text-muted);
  font-size: 0.92rem;
  margin-bottom: 1.5rem;
}

/* ================================================================
   USE CASES
   ================================================================ */
.case-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 1.25rem;
  text-align: left;
}

.case-card {
  background: var(--bg-card);
  padding: 1.5rem;
  border-radius: var(--card-radius);
  border: 1px solid var(--border-lighter);
  border-top: 3px solid transparent;
  border-image: linear-gradient(90deg, var(--brand), var(--accent)) 1;
  border-image-slice: 1 0 0 0;
  transition: box-shadow 0.25s, transform 0.25s;
}
.case-card:hover {
  box-shadow: var(--card-shadow-hover);
  transform: translateY(-2px);
}

.case-header {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  margin-bottom: 0.75rem;
}

.case-icon {
  font-size: 1.6rem;
}

.case-card h3 {
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text-primary);
}

.case-desc {
  font-size: 0.84rem;
  color: var(--text-secondary);
  line-height: 1.55;
  margin-bottom: 0.75rem;
}

.case-stats {
  display: flex;
  gap: 0.6rem;
  flex-wrap: wrap;
  margin-bottom: 0.5rem;
}

.case-stat {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  background: var(--info-bg);
  padding: 0.2rem 0.6rem;
  border-radius: 20px;
  font-size: 0.75rem;
  color: var(--text-muted);
}
.case-stat strong {
  color: var(--brand);
  font-weight: 700;
}

.case-ref {
  font-size: 0.75rem;
  color: var(--text-faint);
  font-style: italic;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.case-ref a {
  color: var(--text-faint);
  text-decoration: none;
  transition: color 0.2s;
}
.case-ref a:hover {
  color: var(--accent);
  text-decoration: underline;
}
.demo-badge {
  font-style: normal;
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  background: var(--accent);
  color: #fff;
  padding: 0.1rem 0.4rem;
  border-radius: 3px;
  flex-shrink: 0;
}

/* ================================================================
   TECH STATS
   ================================================================ */
.tech {
  background: var(--bg-card);
  border-top: 1px solid var(--border-lighter);
  border-bottom: 1px solid var(--border-lighter);
  max-width: 100%;
  padding: 4rem 1.5rem;
}

.tech-grid {
  display: flex;
  justify-content: center;
  gap: 3.5rem;
  flex-wrap: wrap;
  max-width: 800px;
  margin: 0 auto;
}

.tech-item {
  text-align: center;
  min-width: 80px;
}

.tech-val {
  font-size: 2.2rem;
  font-weight: 800;
  color: var(--brand);
  letter-spacing: -0.02em;
  text-shadow: 0 0 30px rgba(79, 195, 247, 0.2);
}

.tech-label {
  font-size: 0.78rem;
  color: var(--text-muted);
  margin-top: 0.3rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  font-weight: 500;
}

/* ================================================================
   TECHNOLOGY STACK
   ================================================================ */
.stack-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
  gap: 1.25rem;
  text-align: left;
}

.stack-group {
  background: var(--bg-card);
  padding: 1.25rem 1.5rem;
  border-radius: var(--card-radius);
  border: 1px solid var(--border-lighter);
}

.stack-group h4 {
  font-size: 0.75rem;
  color: var(--text-faint);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font-weight: 600;
  margin-bottom: 0.75rem;
}

.stack-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
}

.stack-tag {
  display: inline-block;
  padding: 0.25rem 0.65rem;
  border-radius: 20px;
  font-size: 0.78rem;
  font-weight: 500;
  background: var(--bg-badge);
  color: var(--text-secondary);
  border: 1px solid var(--border-light);
  transition: all 0.15s;
}
.stack-tag:hover {
  border-color: var(--brand);
  color: var(--brand);
}

.stack-tag.accent {
  background: var(--info-bg);
  color: var(--info);
  border-color: transparent;
  font-weight: 600;
}
.stack-tag.accent:hover {
  background: var(--info);
  color: var(--accent-text);
}

/* ================================================================
   FOOTER
   ================================================================ */
.site-footer {
  padding: 2rem 1.5rem 1.5rem;
  text-align: center;
  border-top: 1px solid var(--border-lighter);
}

.footer-inner {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 1rem;
  margin-bottom: 0.75rem;
  flex-wrap: wrap;
}

.footer-pill {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.3rem 0.75rem;
  border-radius: 20px;
  background: var(--bg-badge);
  border: 1px solid var(--border-light);
  font-size: 0.75rem;
  color: var(--text-muted);
}

.footer-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  display: inline-block;
}
.footer-dot.ok { background: var(--success); box-shadow: 0 0 6px var(--success); }
.footer-dot.warn { background: var(--warning); box-shadow: 0 0 6px var(--warning); }
.footer-dot.err { background: var(--danger); box-shadow: 0 0 6px var(--danger); }

.footer-version {
  font-size: 0.75rem;
  color: var(--text-faint);
  font-weight: 500;
}

.footer-copy {
  font-size: 0.75rem;
  color: var(--text-faint);
}

/* ================================================================
   RESPONSIVE
   ================================================================ */
@media (max-width: 768px) {
  .hero { padding: 3rem 1rem 2.5rem; }
  .hero-title { font-size: 2.2rem; }
  .hero-subtitle { font-size: 1.05rem; }
  .hero-actions { flex-direction: column; align-items: center; gap: 0.75rem; }

  .workflow-track { flex-direction: column; align-items: center; gap: 0.5rem; }
  .wf-connector {
    width: 2px;
    height: 36px;
    padding-top: 0;
    flex-direction: column;
    justify-content: center;
  }
  .wf-line { width: 2px; height: 100%; background: linear-gradient(180deg, rgba(79, 195, 247, 0.5), rgba(79, 195, 247, 0.2)); }
  .wf-line::after {
    right: auto;
    top: auto;
    bottom: -6px;
    left: calc(50% - 4px);
    border-top: 6px solid rgba(79, 195, 247, 0.45);
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-bottom: none;
  }
  .wf-dot, .wf-dot-2 { display: none; }
  .wf-desc { max-width: 240px; }

  .section { padding: 3rem 1rem; }
  .section-title { font-size: 1.4rem; }

  .cap-grid { grid-template-columns: 1fr; }
  .tech-grid { gap: 2rem; }
  .stack-grid { grid-template-columns: 1fr; }
}

@media (max-width: 480px) {
  .hero-logo { width: 60px; height: 60px; }
  .hero-title { font-size: 1.8rem; }
  .tech-val { font-size: 1.6rem; }
  .case-grid { grid-template-columns: 1fr; }
  .features { grid-template-columns: 1fr; }
}
</style>
