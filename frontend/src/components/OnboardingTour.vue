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
          <button v-if="step > 0" class="tour-btn secondary" @click="step--">{{ $t('components.back') }}</button>
          <span v-else />
          <button v-if="step < steps.length - 1" class="tour-btn primary" @click="step++">{{ $t('components.next') }}</button>
          <button v-else class="tour-btn primary" @click="dismiss">{{ $t('components.getStarted') }}</button>
        </div>

        <label class="tour-dismiss-label">
          <input type="checkbox" v-model="dontShowAgain" />
          {{ $t('components.dontShowAgain') }}
        </label>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const STORAGE_KEY = 'predomics_onboarding_dismissed'

const visible = ref(false)
const step = ref(0)
const dontShowAgain = ref(false)

const steps = computed(() => [
  {
    icon: '\u{1F44B}',
    title: t('components.tourWelcomeTitle'),
    description: t('components.tourWelcomeDesc'),
  },
  {
    icon: '\u{1F4C1}',
    title: t('components.tourStep1Title'),
    description: t('components.tourStep1Desc'),
  },
  {
    icon: '\u{1F4E4}',
    title: t('components.tourStep2Title'),
    description: t('components.tourStep2Desc'),
  },
  {
    icon: '\u{2699}\u{FE0F}',
    title: t('components.tourStep3Title'),
    description: t('components.tourStep3Desc'),
  },
  {
    icon: '\u{1F680}',
    title: t('components.tourStep4Title'),
    description: t('components.tourStep4Desc'),
  },
  {
    icon: '\u{1F4CA}',
    title: t('components.tourStep5Title'),
    description: t('components.tourStep5Desc'),
  },
])

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
