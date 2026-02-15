<template>
  <Teleport to="body">
    <div v-if="visible" class="tour-overlay" @click.self="dismiss">
      <div class="tour-card">
        <button class="tour-close" @click="dismiss">&times;</button>

        <div class="tour-step-icon">{{ steps[step].icon }}</div>
        <h3 class="tour-title">{{ steps[step].title }}</h3>
        <p class="tour-desc">{{ steps[step].description }}</p>

        <!-- Step indicators -->
        <div class="tour-dots">
          <span
            v-for="(s, i) in steps"
            :key="i"
            class="dot"
            :class="{ active: i === step, done: i < step }"
            @click="step = i"
          />
        </div>

        <div class="tour-actions">
          <button v-if="step > 0" class="tour-btn secondary" @click="step--">Back</button>
          <span v-else />
          <button v-if="step < steps.length - 1" class="tour-btn primary" @click="step++">Next</button>
          <button v-else class="tour-btn primary" @click="dismiss">Get Started</button>
        </div>

        <label class="tour-dismiss-label">
          <input type="checkbox" v-model="dontShowAgain" />
          Don't show this again
        </label>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, onMounted } from 'vue'

const STORAGE_KEY = 'predomics_onboarding_dismissed'

const visible = ref(false)
const step = ref(0)
const dontShowAgain = ref(false)

const steps = [
  {
    icon: '\u{1F44B}',
    title: 'Welcome to PredomicsApp',
    description: 'This quick tour will walk you through the main workflow: from uploading your data to viewing analysis results. It only takes a moment!',
  },
  {
    icon: '\u{1F4C1}',
    title: 'Step 1: Create a Project',
    description: 'Start by clicking the "+" button in the Projects page to create a new project. Projects organize your datasets, parameters, and analysis results together.',
  },
  {
    icon: '\u{1F4E4}',
    title: 'Step 2: Upload Your Data',
    description: 'In the Data tab, upload your training and test files (Xtrain, Ytrain, Xtest, Ytest). Supported formats: TSV, CSV. You can also manage datasets in the Dataset Library.',
  },
  {
    icon: '\u{2699}\u{FE0F}',
    title: 'Step 3: Configure Parameters',
    description: 'Switch to the "Parameters & Run" tab to configure the analysis. Adjust algorithm settings (GA, BEAM, MCMC), cross-validation, and feature importance options — or use the defaults.',
  },
  {
    icon: '\u{1F680}',
    title: 'Step 4: Launch Analysis',
    description: 'Click "Launch Job" to start the analysis. A live console shows real-time progress. You\'ll be notified when it completes — feel free to navigate away.',
  },
  {
    icon: '\u{1F4CA}',
    title: 'Step 5: Explore Results',
    description: 'View detailed results in the Results tab: model summaries, feature importance charts, performance metrics, and prediction plots. Export as CSV, HTML report, or a reproducible notebook.',
  },
]

function dismiss() {
  visible.value = false
  if (dontShowAgain.value) {
    localStorage.setItem(STORAGE_KEY, 'true')
  }
}

onMounted(() => {
  const dismissed = localStorage.getItem(STORAGE_KEY)
  if (!dismissed) {
    visible.value = true
  }
})
</script>

<style scoped>
.tour-overlay {
  position: fixed;
  inset: 0;
  z-index: 10000;
  background: rgba(0, 0, 0, 0.55);
  display: flex;
  align-items: center;
  justify-content: center;
  animation: fadeIn 0.2s ease;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

.tour-card {
  background: var(--bg-card, #fff);
  border-radius: 16px;
  padding: 2rem 2.5rem;
  max-width: 440px;
  width: 90%;
  position: relative;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.25);
  text-align: center;
  animation: slideUp 0.25s ease;
}

@keyframes slideUp {
  from { transform: translateY(20px); opacity: 0; }
  to { transform: translateY(0); opacity: 1; }
}

.tour-close {
  position: absolute;
  top: 0.75rem;
  right: 0.75rem;
  background: none;
  border: none;
  font-size: 1.3rem;
  color: var(--text-faint, #999);
  cursor: pointer;
  line-height: 1;
  padding: 0.25rem;
}
.tour-close:hover { color: var(--text-primary, #333); }

.tour-step-icon {
  font-size: 2.5rem;
  margin-bottom: 0.75rem;
}

.tour-title {
  font-size: 1.15rem;
  color: var(--text-primary, #1a1a2e);
  margin-bottom: 0.5rem;
}

.tour-desc {
  font-size: 0.88rem;
  color: var(--text-secondary, #546e7a);
  line-height: 1.55;
  margin-bottom: 1.25rem;
}

.tour-dots {
  display: flex;
  justify-content: center;
  gap: 0.4rem;
  margin-bottom: 1.25rem;
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--border, #cfd8dc);
  cursor: pointer;
  transition: all 0.2s;
}
.dot.active {
  background: var(--accent, #1a1a2e);
  transform: scale(1.3);
}
.dot.done {
  background: var(--success, #4caf50);
}

.tour-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 1rem;
}

.tour-btn {
  padding: 0.5rem 1.5rem;
  border-radius: 8px;
  font-size: 0.88rem;
  cursor: pointer;
  border: none;
  transition: all 0.15s;
}

.tour-btn.primary {
  background: var(--accent, #1a1a2e);
  color: var(--accent-text, #fff);
}
.tour-btn.primary:hover {
  background: var(--accent-hover, #16213e);
}

.tour-btn.secondary {
  background: none;
  color: var(--text-muted, #78909c);
  border: 1px solid var(--border, #cfd8dc);
}
.tour-btn.secondary:hover {
  color: var(--text-primary, #333);
  border-color: var(--text-muted);
}

.tour-dismiss-label {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.4rem;
  font-size: 0.76rem;
  color: var(--text-faint, #90a4ae);
  cursor: pointer;
}

.tour-dismiss-label input {
  cursor: pointer;
}
</style>
