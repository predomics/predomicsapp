<template>
  <div class="empty-state">
    <div class="empty-icon" aria-hidden="true">&#128202;</div>
    <h3>{{ title || $t('projects.noProjectSelected') }}</h3>
    <p>{{ message || $t('projects.selectOrCreate') }}</p>
    <slot />
  </div>
</template>

<script setup>
defineProps({
  title: { type: String, default: '' },
  message: { type: String, default: '' },
})
</script>

<style scoped>
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  min-height: 300px;
  text-align: center;
  padding: 2rem;
}

.empty-icon {
  font-size: 3rem;
  margin-bottom: 1rem;
  opacity: 0.4;
}

.empty-state h3 {
  color: var(--text-secondary);
  font-size: 1.1rem;
  margin-bottom: 0.5rem;
}

.empty-state p {
  color: var(--text-muted);
  font-size: 0.85rem;
  max-width: 320px;
}
</style>
