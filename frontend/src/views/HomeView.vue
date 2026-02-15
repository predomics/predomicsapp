<template>
  <div class="home">
    <div class="hero">
      <h1>PredomicsApp</h1>
      <p class="subtitle">
        Discover sparse, interpretable predictive models from omics data.
      </p>
      <p class="description">
        Powered by <strong>gpredomics</strong> — a high-performance Rust engine
        for Binary, Ternary, and Ratio model languages using genetic algorithms,
        beam search, and Bayesian MCMC.
      </p>
      <router-link to="/projects" class="btn btn-primary">
        Get Started
      </router-link>
    </div>

    <!-- Animated Workflow Diagram -->
    <section class="workflow">
      <h2>How It Works</h2>
      <div class="pipeline">
        <div class="pipe-step" v-for="(step, i) in pipelineSteps" :key="i" :style="{ animationDelay: (i * 0.15) + 's' }">
          <div class="pipe-icon">{{ step.icon }}</div>
          <div class="pipe-label">{{ step.label }}</div>
          <div class="pipe-desc">{{ step.desc }}</div>
        </div>
      </div>
    </section>

    <!-- Feature cards -->
    <div class="features">
      <div class="feature-card">
        <h3>Upload Data</h3>
        <p>Import your omics/metagenomics matrices (TSV/CSV) with flexible row or column orientation.</p>
      </div>
      <div class="feature-card">
        <h3>Configure & Run</h3>
        <p>Choose algorithms (GA, Beam, MCMC), languages (binary, ternary, ratio), and tune parameters.</p>
      </div>
      <div class="feature-card">
        <h3>Explore Results</h3>
        <p>Browse model populations, inspect feature importance, and compare across runs.</p>
      </div>
    </div>

    <!-- Use Case Examples -->
    <section class="use-cases">
      <h2>Real-World Use Cases</h2>
      <div class="case-grid">
        <div class="case-card" v-for="uc in useCases" :key="uc.title">
          <div class="case-icon">{{ uc.icon }}</div>
          <h3>{{ uc.title }}</h3>
          <p class="case-desc">{{ uc.description }}</p>
          <div class="case-stats">
            <span v-for="(val, label) in uc.stats" :key="label" class="case-stat">
              <strong>{{ val }}</strong> {{ label }}
            </span>
          </div>
          <div class="case-ref" v-if="uc.reference">{{ uc.reference }}</div>
        </div>
      </div>
    </section>

    <!-- Tech highlights -->
    <section class="tech">
      <h2>Built for Performance</h2>
      <div class="tech-grid">
        <div class="tech-item">
          <div class="tech-val">Rust</div>
          <div class="tech-label">Core Engine</div>
        </div>
        <div class="tech-item">
          <div class="tech-val">3</div>
          <div class="tech-label">Algorithms</div>
        </div>
        <div class="tech-item">
          <div class="tech-val">3</div>
          <div class="tech-label">Model Languages</div>
        </div>
        <div class="tech-item">
          <div class="tech-val">GPU</div>
          <div class="tech-label">Acceleration</div>
        </div>
      </div>
    </section>

    <div class="status" v-if="health">
      <small>
        API: {{ health.status }} | Engine: {{ health.gpredomicspy_available ? 'ready' : 'mock mode' }} | v{{ health.version }}
      </small>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import axios from 'axios'

const health = ref(null)

const pipelineSteps = [
  { icon: '\u{1F4C2}', label: 'Data Input', desc: 'Upload omics matrices' },
  { icon: '\u{1F50D}', label: 'Feature Selection', desc: 'Statistical filtering' },
  { icon: '\u{1F9EC}', label: 'Evolutionary Search', desc: 'GA / Beam / MCMC' },
  { icon: '\u{1F4CA}', label: 'Model Evaluation', desc: 'AUC, sensitivity, specificity' },
  { icon: '\u{1F3AF}', label: 'Jury Voting', desc: 'Ensemble consensus' },
]

const useCases = [
  {
    icon: '\u{1FA7A}',
    title: 'Cirrhosis Prediction',
    description: 'Predict liver cirrhosis from gut microbiome composition using metagenomic species abundance profiles.',
    stats: { 'AUC': '0.94', 'features': 'k=8', 'samples': '232' },
    reference: 'Qin et al., Nature 2014',
  },
  {
    icon: '\u{1F9EC}',
    title: 'Cancer Classification',
    description: 'Classify colorectal cancer status from stool metagenomic data using sparse ternary models.',
    stats: { 'AUC': '0.92', 'features': 'k=12', 'samples': '156' },
    reference: 'Zeller et al., Mol. Syst. Biol. 2014',
  },
  {
    icon: '\u{1F48A}',
    title: 'Treatment Response',
    description: 'Predict immunotherapy response from baseline gut microbiome in melanoma patients.',
    stats: { 'AUC': '0.87', 'features': 'k=5', 'samples': '112' },
    reference: 'Gopalakrishnan et al., Science 2018',
  },
  {
    icon: '\u{1F3E5}',
    title: 'Metabolic Disease',
    description: 'Identify type 2 diabetes biomarkers from metagenome-wide association studies.',
    stats: { 'AUC': '0.89', 'features': 'k=10', 'samples': '345' },
    reference: 'Karlsson et al., Nature 2013',
  },
]

onMounted(async () => {
  try {
    const { data } = await axios.get('/health')
    health.value = data
  } catch (e) {
    console.error('Health check failed:', e)
  }
})
</script>

<style scoped>
.home { text-align: center; }

.hero {
  padding: 3rem 1rem 2rem;
}

.hero h1 {
  font-size: 2.5rem;
  color: var(--text-primary);
  margin-bottom: 0.5rem;
}

.subtitle {
  font-size: 1.2rem;
  color: var(--text-secondary);
  margin-bottom: 1rem;
}

.description {
  max-width: 600px;
  margin: 0 auto 2rem;
  color: var(--text-muted);
  line-height: 1.6;
}

.btn {
  display: inline-block;
  padding: 0.75rem 2rem;
  border-radius: 6px;
  text-decoration: none;
  font-weight: 600;
  transition: background 0.2s;
}

.btn-primary {
  background: var(--accent);
  color: var(--accent-text);
}

.btn-primary:hover {
  background: var(--accent-hover);
}

/* Animated Workflow */
.workflow {
  margin: 2rem 0 3rem;
}
.workflow h2 {
  color: var(--text-primary);
  margin-bottom: 1.5rem;
  font-size: 1.3rem;
}

.pipeline {
  display: flex;
  justify-content: center;
  gap: 0;
  flex-wrap: wrap;
  max-width: 900px;
  margin: 0 auto;
}

.pipe-step {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 1rem 1.25rem;
  position: relative;
  opacity: 0;
  animation: fadeSlideIn 0.5s ease forwards;
}

@keyframes fadeSlideIn {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

.pipe-step:not(:last-child)::after {
  content: '\u279C';
  position: absolute;
  right: -8px;
  top: 1.2rem;
  color: var(--text-faint);
  font-size: 1rem;
}

.pipe-icon {
  font-size: 2rem;
  margin-bottom: 0.4rem;
}

.pipe-label {
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 0.15rem;
}

.pipe-desc {
  font-size: 0.72rem;
  color: var(--text-muted);
}

/* Feature cards */
.features {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 1.5rem;
  margin: 2rem 0 3rem;
}

.feature-card {
  background: var(--bg-card);
  padding: 1.5rem;
  border-radius: 8px;
  box-shadow: var(--shadow);
  text-align: left;
}

.feature-card h3 {
  margin-bottom: 0.5rem;
  color: var(--text-primary);
}

.feature-card p {
  color: var(--text-muted);
  font-size: 0.9rem;
  line-height: 1.5;
}

/* Use Cases */
.use-cases {
  margin: 3rem 0;
}
.use-cases h2 {
  color: var(--text-primary);
  margin-bottom: 1.5rem;
  font-size: 1.3rem;
}

.case-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 1.25rem;
  text-align: left;
}

.case-card {
  background: var(--bg-card);
  padding: 1.25rem 1.5rem;
  border-radius: 10px;
  box-shadow: var(--card-shadow);
  transition: box-shadow 0.2s;
}
.case-card:hover {
  box-shadow: var(--card-shadow-hover);
}

.case-icon {
  font-size: 1.8rem;
  margin-bottom: 0.5rem;
}

.case-card h3 {
  font-size: 0.95rem;
  color: var(--text-primary);
  margin-bottom: 0.35rem;
}

.case-desc {
  font-size: 0.82rem;
  color: var(--text-secondary);
  line-height: 1.5;
  margin-bottom: 0.75rem;
}

.case-stats {
  display: flex;
  gap: 1rem;
  margin-bottom: 0.5rem;
}

.case-stat {
  font-size: 0.78rem;
  color: var(--text-muted);
}
.case-stat strong {
  color: var(--accent);
  font-weight: 700;
}

.case-ref {
  font-size: 0.7rem;
  color: var(--text-faint);
  font-style: italic;
}

/* Tech highlights */
.tech {
  margin: 3rem 0 2rem;
}
.tech h2 {
  color: var(--text-primary);
  margin-bottom: 1.5rem;
  font-size: 1.3rem;
}

.tech-grid {
  display: flex;
  justify-content: center;
  gap: 3rem;
  flex-wrap: wrap;
}

.tech-item {
  text-align: center;
}
.tech-val {
  font-size: 1.8rem;
  font-weight: 800;
  color: var(--accent);
}
.tech-label {
  font-size: 0.78rem;
  color: var(--text-muted);
  margin-top: 0.2rem;
}

.status {
  margin-top: 2rem;
  padding-bottom: 1rem;
  color: var(--text-faint);
}

@media (max-width: 700px) {
  .pipe-step:not(:last-child)::after { display: none; }
  .pipeline { gap: 0.5rem; }
  .tech-grid { gap: 1.5rem; }
}
</style>
