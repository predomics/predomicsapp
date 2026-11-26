<template>
  <div class="results-tab" ref="rootEl">
    <AsyncState
      v-if="jobsLoading || jobsError"
      :loading="jobsLoading"
      :error="jobsError"
      :retry="() => loadJobList()"
      :loading-text="$t('results.loadingJobs')"
      :error-title="$t('results.jobsLoadFailed')"
    />
    <!-- Job management table -->
    <div class="job-table-section" v-if="jobs.length > 0">
      <div class="job-table-header">
        <h3>{{ $t('results.jobs') }}</h3>
        <span class="job-count">{{ filteredJobs.length }}<template v-if="jobSearch"> / {{ jobs.length }}</template> {{ $t('results.job', jobs.length) }}</span>
        <span v-if="hasLiveJobs" class="live-note" role="status"><span class="live-dot" aria-hidden="true"></span>{{ $t('results.autoRefreshing') }}</span>
        <input
          type="search"
          v-model="jobSearch"
          class="job-search"
          :placeholder="$t('results.searchJobs')"
          :aria-label="$t('results.searchJobs')"
        />
        <button type="button" class="btn-sm btn-outline" @click="findDuplicates" :disabled="duplicatesLoading" v-if="jobs.length >= 2">
          {{ duplicatesLoading ? $t('results.checking') : $t('results.findDuplicates') }}
        </button>
      </div>
      <!-- Duplicate groups panel -->
      <div v-if="duplicateGroups.length > 0" class="duplicates-panel">
        <div class="duplicates-header">
          <strong>{{ $t('results.duplicateGroupsFound', { n: duplicateGroups.length }) }}</strong>
          <button class="btn-sm btn-danger" @click="cleanupDuplicates">{{ $t('results.deleteDuplicates') }}</button>
          <button class="btn-sm btn-outline" @click="duplicateGroups = []">{{ $t('results.dismiss') }}</button>
        </div>
        <div v-for="(g, gi) in duplicateGroups" :key="gi" class="dup-group">
          <div class="dup-group-label">{{ g.config_summary }} ({{ $t('results.nJobs', { n: g.jobs.length }) }})</div>
          <div v-for="dj in g.jobs" :key="dj.job_id" class="dup-job" :class="{ 'dup-keep': dj.keep }">
            <span class="dup-name">{{ dj.name || dj.job_id.slice(0, 8) }}</span>
            <span class="status-badge" :class="dj.status">{{ statusLabel(dj.status) }}</span>
            <span v-if="dj.best_auc != null">{{ fitMetricLabel }} {{ dj.best_auc.toFixed(4) }}</span>
            <span class="dup-tag" v-if="dj.keep">{{ $t('results.keep') }}</span>
            <span class="dup-tag dup-remove" v-else>{{ $t('results.remove') }}</span>
          </div>
        </div>
      </div>
      <div class="job-table-wrap">
        <table class="job-table">
          <thead>
            <tr>
              <th scope="col" class="col-name" :aria-sort="jobAriaSort('name')"><button type="button" class="sort-btn" @click="toggleJobSort('name')">{{ $t('results.colName') }} <span v-if="jobSortKey === 'name'" aria-hidden="true">{{ jobSortAsc ? '▲' : '▼' }}</span></button></th>
              <th scope="col" class="col-status" :aria-sort="jobAriaSort('status')"><button type="button" class="sort-btn" @click="toggleJobSort('status')">{{ $t('results.colStatus') }} <span v-if="jobSortKey === 'status'" aria-hidden="true">{{ jobSortAsc ? '▲' : '▼' }}</span></button></th>
              <th scope="col" class="col-auc" :aria-sort="jobAriaSort('best_auc')"><button type="button" class="sort-btn" @click="toggleJobSort('best_auc')">{{ isRegressionJob ? $t('results.fitMetric') : $t('results.colAuc') }} <span v-if="jobSortKey === 'best_auc'" aria-hidden="true">{{ jobSortAsc ? '▲' : '▼' }}</span></button></th>
              <th scope="col" class="col-k" :aria-sort="jobAriaSort('best_k')"><button type="button" class="sort-btn" @click="toggleJobSort('best_k')">{{ $t('results.colK') }} <span v-if="jobSortKey === 'best_k'" aria-hidden="true">{{ jobSortAsc ? '▲' : '▼' }}</span></button></th>
              <th scope="col" class="col-lang">{{ $t('results.colLanguage') }}</th>
              <th scope="col" class="col-pop">{{ $t('results.colPop') }}</th>
              <th scope="col" class="col-config">{{ $t('results.colConfig') }}</th>
              <th scope="col" class="col-size" :aria-sort="jobAriaSort('disk_size_bytes')"><button type="button" class="sort-btn" @click="toggleJobSort('disk_size_bytes')">{{ $t('results.colSize') }} <span v-if="jobSortKey === 'disk_size_bytes'" aria-hidden="true">{{ jobSortAsc ? '▲' : '▼' }}</span></button></th>
              <th scope="col" class="col-duration" :aria-sort="jobAriaSort('duration_seconds')"><button type="button" class="sort-btn" @click="toggleJobSort('duration_seconds')">{{ $t('results.colDuration') }} <span v-if="jobSortKey === 'duration_seconds'" aria-hidden="true">{{ jobSortAsc ? '▲' : '▼' }}</span></button></th>
              <th scope="col" class="col-created" :aria-sort="jobAriaSort('created_at')"><button type="button" class="sort-btn" @click="toggleJobSort('created_at')">{{ $t('results.colCreated') }} <span v-if="jobSortKey === 'created_at'" aria-hidden="true">{{ jobSortAsc ? '▲' : '▼' }}</span></button></th>
              <th scope="col" class="col-user">{{ $t('results.colUser') }}</th>
              <th scope="col" class="col-actions">{{ $t('results.colActions') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="j in paginatedJobs"
              :key="j.job_id"
              :class="{ 'row-selected': selectedJobId === j.job_id, ['row-' + j.status]: true }"
              :aria-selected="selectedJobId === j.job_id ? 'true' : 'false'"
              tabindex="0"
              @click="selectJob(j.job_id)"
              @keydown.enter.self.prevent="selectJob(j.job_id)"
            >
              <td class="col-name" :title="j.job_id">{{ j.name || j.job_id.slice(0, 8) }}</td>
              <td class="col-status"><span class="status-badge" :class="j.status"><span aria-hidden="true">{{ statusGlyph(j.status) }}</span> {{ statusLabel(j.status) }}</span></td>
              <td class="col-auc">{{ j.best_auc != null ? j.best_auc.toFixed(4) : '—' }}</td>
              <td class="col-k">{{ j.best_k ?? '—' }}</td>
              <td class="col-lang">{{ j.language || '—' }}</td>
              <td class="col-pop">{{ j.population_size ?? '—' }}</td>
              <td class="col-config" :title="j.config_summary || ''">
                <span class="config-hash" v-if="j.config_hash">{{ j.config_hash.slice(0, 6) }}</span>
                <span class="config-detail" v-if="j.config_summary">{{ j.config_summary }}</span>
              </td>
              <td class="col-size">{{ formatSize(j.disk_size_bytes) }}</td>
              <td class="col-duration">{{ formatDuration(j.duration_seconds ?? j.execution_time) }}</td>
              <td class="col-created">{{ formatDate(j.created_at) }}</td>
              <td class="col-user">{{ j.user_name || '—' }}</td>
              <td class="col-actions">
                <button v-if="isLive(j.status)" type="button" class="btn-icon btn-cancel" @click.stop="cancelJob(j)" :title="$t('console.cancelJob')" :aria-label="$t('console.cancelJob')" :disabled="cancellingId === j.job_id"><span aria-hidden="true">&#9632;</span></button>
                <button type="button" class="btn-icon" @click.stop="openLog(j)" :title="$t('results.viewLog')" :aria-label="$t('results.viewLog')"><SvgIcon name="eye" :size="14" /></button>
                <button type="button" class="btn-icon" @click.stop="rerunJob(j)" :title="$t('results.rerun')" :aria-label="$t('results.rerun')" :disabled="rerunLoading || isLive(j.status)"><SvgIcon name="refresh" :size="14" /></button>
                <button type="button" class="btn-icon" @click.stop="duplicateJob(j)" :title="$t('results.duplicate')" :aria-label="$t('results.duplicate')"><SvgIcon name="copy" :size="14" /></button>
                <button type="button" class="btn-icon btn-delete" @click.stop="confirmDeleteJob(j)" :title="isLive(j.status) ? $t('results.deleteLiveHint') : $t('results.deleteJob')" :aria-label="$t('results.deleteJob')" :disabled="isLive(j.status)"><SvgIcon name="trash" :size="14" /></button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <!-- Job table pagination -->
      <div class="job-pagination" v-if="filteredJobs.length > jobPageSize">
        <button type="button" @click="jobPage = Math.max(0, jobPage - 1)" :disabled="jobPage === 0">&laquo; {{ $t('results.prev') }}</button>
        <span>{{ jobPage * jobPageSize + 1 }}&ndash;{{ Math.min((jobPage + 1) * jobPageSize, filteredJobs.length) }} {{ $t('results.of') }} {{ filteredJobs.length }}</span>
        <button type="button" @click="jobPage++" :disabled="(jobPage + 1) * jobPageSize >= filteredJobs.length">{{ $t('results.next') }} &raquo;</button>
      </div>
    </div>

    <!-- Failed job error panel -->
    <div v-if="selectedJobInfo && (selectedJobInfo.status === 'failed' || selectedJobInfo.status === 'cancelled') && !detail" class="failed-job-panel">
      <div class="failed-header">
        <span class="failed-icon" aria-hidden="true">&#9888;</span>
        <h3>{{ selectedJobInfo.status === 'cancelled' ? $t('results.jobCancelled') : $t('results.jobFailed') }}</h3>
        <span class="failed-name" v-if="selectedJobInfo.name">{{ selectedJobInfo.name }}</span>
      </div>
      <div class="failed-details">
        <div class="failed-row" v-if="selectedJobInfo.error_message">
          <strong>{{ $t('results.error') }}</strong>
          <pre class="error-message">{{ selectedJobInfo.error_message }}</pre>
        </div>
        <div class="failed-row" v-if="selectedJobInfo.created_at">
          <strong>{{ $t('results.started') }}</strong> {{ formatDate(selectedJobInfo.created_at) }}
        </div>
        <div class="failed-row" v-if="selectedJobInfo.duration_seconds">
          <strong>{{ $t('results.duration') }}</strong> {{ formatDuration(selectedJobInfo.duration_seconds) }}
        </div>
        <div class="failed-row" v-if="selectedJobInfo.config_summary">
          <strong>{{ $t('results.config') }}</strong> {{ selectedJobInfo.config_summary }}
        </div>
      </div>
      <div v-if="failedJobLog" class="failed-log">
        <strong>{{ $t('results.consoleLast50') }}</strong>
        <pre class="log-content">{{ failedJobLog }}</pre>
      </div>
      <div v-else class="failed-log-hint">
        <button type="button" class="btn-sm btn-outline" @click="loadFailedJobLog">{{ $t('results.showConsoleLog') }}</button>
        <button type="button" class="btn-sm btn-outline" @click="rerunJob(selectedJobInfo)" :disabled="rerunLoading">{{ $t('results.rerun') }}</button>
      </div>
    </div>

    <!-- Pending/running job info panel -->
    <div v-else-if="selectedJobInfo && (selectedJobInfo.status === 'pending' || selectedJobInfo.status === 'running') && !detail" class="pending-job-panel">
      <div class="pending-header">
        <span class="pending-icon" aria-hidden="true">&#9203;</span>
        <h3>{{ selectedJobInfo.status === 'running' ? $t('results.jobRunning') : $t('results.jobPending') }}</h3>
        <span class="pending-name" v-if="selectedJobInfo.name">{{ selectedJobInfo.name }}</span>
      </div>
      <p class="pending-text">{{ $t('results.resultsWillAppear') }}</p>
      <div class="pending-actions">
        <button type="button" class="btn-sm btn-outline" @click="showLiveConsole(selectedJobInfo)">{{ $t('results.showLiveConsole') }}</button>
        <button type="button" class="btn-sm btn-outline" @click="cancelJob(selectedJobInfo)" :disabled="cancellingId === selectedJobInfo.job_id">{{ $t('console.cancelJob') }}</button>
      </div>
    </div>

    <!-- Sub-tabs -->
    <div class="sub-tabs" v-if="detail" role="tablist" :aria-label="$t('results.sectionsLabel')">
      <button type="button" role="tab" :aria-selected="subTab === 'insights'" :class="{ active: subTab === 'insights' }" @click="subTab = 'insights'">{{ $t('results.insights') }}</button>
      <button type="button" role="tab" :aria-selected="subTab === 'summary'" :class="{ active: subTab === 'summary' }" @click="subTab = 'summary'">{{ $t('results.summary') }}</button>
      <button type="button" role="tab" :aria-selected="subTab === 'bestmodel'" :class="{ active: subTab === 'bestmodel' }" @click="subTab = 'bestmodel'">{{ $t('results.bestModel') }}</button>
      <button type="button" role="tab" :aria-selected="subTab === 'population'" :class="{ active: subTab === 'population' }" @click="subTab = 'population'">{{ $t('results.population') }}</button>
      <button type="button" role="tab" :aria-selected="subTab === 'jury'" v-if="juryData" :class="{ active: subTab === 'jury' }" @click="subTab = 'jury'">{{ $t('results.jury') }}</button>
      <button type="button" role="tab" :aria-selected="subTab === 'comparative'" :class="{ active: subTab === 'comparative' }" @click="subTab = 'comparative'">{{ $t('results.comparative') }}</button>
      <button type="button" role="tab" :aria-selected="subTab === 'copresence'" v-if="population.length > 1" :class="{ active: subTab === 'copresence' }" @click="subTab = 'copresence'">{{ $t('results.copresence') }}</button>
      <button type="button" role="tab" :aria-selected="subTab === 'enrichment'" :class="{ active: subTab === 'enrichment' }" @click="subTab = 'enrichment'">{{ $t('results.enrichment') }}</button>
      <button type="button" role="tab" :aria-selected="subTab === 'ecosystem'" :class="{ active: subTab === 'ecosystem' }" @click="subTab = 'ecosystem'">{{ $t('results.ecosystem') }}</button>
      <button type="button" role="tab" :aria-selected="subTab === 'stability'" v-if="population.length > 1" :class="{ active: subTab === 'stability' }" @click="subTab = 'stability'">{{ $t('results.stability') }}</button>
      <button type="button" role="tab" :aria-selected="subTab === 'pheromone'" v-if="pheromoneData && pheromoneData.length > 0" :class="{ active: subTab === 'pheromone' }" @click="subTab = 'pheromone'">{{ $t('results.pheromone') }}</button>
      <button type="button" role="tab" :aria-selected="subTab === 'exploration'" v-if="hasExplorationData" :class="{ active: subTab === 'exploration' }" @click="subTab = 'exploration'">{{ $t('results.exploration') }}</button>
      <button type="button" role="tab" :aria-selected="subTab === 'basket'" :class="{ active: subTab === 'basket' }" @click="subTab = 'basket'">{{ $t('results.basket') }}<span v-if="basketCount > 0" class="basket-badge">{{ basketCount }}</span></button>
      <button type="button" role="tab" :aria-selected="subTab === 'console'" :class="{ active: subTab === 'console' }" @click="subTab = 'console'; loadConsoleLog()">{{ $t('results.console') }}</button>
      <div class="export-dropdown-wrap" v-if="detail" ref="exportWrapEl" @keydown.escape="exportMenuOpen = false">
        <button type="button" class="btn-sm btn-export" aria-haspopup="true" :aria-expanded="exportMenuOpen ? 'true' : 'false'" @click="exportMenuOpen = !exportMenuOpen">
          <span aria-hidden="true">&#8615;</span> {{ exporting ? $t('results.exporting') : $t('results.export') }}
        </button>
        <div class="export-menu" v-if="exportMenuOpen" role="menu">
          <button type="button" role="menuitem" @click="doExport('report')">{{ $t('results.htmlReport') }}</button>
          <button type="button" role="menuitem" @click="doExport('pdf')">{{ $t('results.pdfReport') }}</button>
          <button type="button" role="menuitem" @click="doExport('json')">{{ $t('results.fullJson') }}</button>
          <hr />
          <button type="button" role="menuitem" @click="doExport('csv', 'best_model')">{{ $t('results.csvBestModel') }}</button>
          <button type="button" role="menuitem" @click="doExport('csv', 'population')">{{ $t('results.csvPopulation') }}</button>
          <button type="button" role="menuitem" @click="doExport('csv', 'generation_tracking')">{{ $t('results.csvGenerations') }}</button>
          <button type="button" role="menuitem" v-if="juryData" @click="doExport('csv', 'jury_predictions')">{{ $t('results.csvJuryPredictions') }}</button>
          <hr />
          <button type="button" role="menuitem" @click="doExport('notebook', 'python')">{{ $t('results.pythonNotebook') }}</button>
          <button type="button" role="menuitem" @click="doExport('notebook', 'r')">{{ $t('results.rNotebook') }}</button>
        </div>
      </div>
    </div>
    <div class="fold-controls" v-if="detail && foldableCount > 0">
      <button type="button" @click="setAllSections(false)">{{ $t('results.foldAll') }}</button>
      <button type="button" @click="setAllSections(true)">{{ $t('results.unfoldAll') }}</button>
    </div>

    <!-- ============================================================ -->
    <!-- INSIGHTS SUB-TAB                                             -->
    <!-- ============================================================ -->
    <div v-if="detail && subTab === 'insights'" class="sub-content">
      <InsightsTab
        :projectId="route.params.id"
        :jobId="selectedJobId || ''"
        :population="population"
        :juryData="juryData"
        :detail="detail"
        :mspAnnotations="mspAnnotations"
        :active="subTab === 'insights'"
      />
    </div>

    <!-- ============================================================ -->
    <!-- SUMMARY SUB-TAB                                              -->
    <!-- ============================================================ -->
    <SummaryTab v-if="detail && subTab === 'summary'" />

    <!-- ============================================================ -->
    <!-- BEST MODEL SUB-TAB                                           -->
    <!-- ============================================================ -->
    <BestModelTab v-if="detail && subTab === 'bestmodel'" />

    <!-- ============================================================ -->
    <!-- POPULATION SUB-TAB                                           -->
    <!-- ============================================================ -->
    <PopulationTab v-if="detail && subTab === 'population'" />

    <!-- ============================================================ -->
    <!-- JURY SUB-TAB                                                 -->
    <!-- ============================================================ -->
    <JuryTab v-if="detail && subTab === 'jury'" />

    <!-- ============================================================ -->
    <!-- COMPARATIVE SUB-TAB                                          -->
    <!-- ============================================================ -->
    <ComparativeTab v-if="detail && subTab === 'comparative'" />

    <!-- ============================================================ -->
    <!-- CO-PRESENCE SUB-TAB                                         -->
    <!-- ============================================================ -->
    <CoPresenceTab v-if="detail && subTab === 'copresence'" />

    <!-- ============================================================ -->
    <!-- ENRICHMENT SUB-TAB                                          -->
    <!-- ============================================================ -->
    <div v-if="detail && subTab === 'enrichment'" class="sub-content">
      <EnrichmentTab
        :projectId="route.params.id"
        :jobId="selectedJobId || ''"
        :population="population"
        :juryData="juryData"
        :detail="detail"
        :mspAnnotations="mspAnnotations"
        :active="subTab === 'enrichment'"
      />
    </div>

    <!-- ============================================================ -->
    <!-- ECOSYSTEM SUB-TAB                                           -->
    <!-- ============================================================ -->
    <div v-if="detail && subTab === 'ecosystem'" class="sub-content">
      <EcosystemTab
        :projectId="route.params.id"
        :jobId="selectedJobId || ''"
        :population="population"
        :classLabels="[classNameFor(0), classNameFor(1)]"
        :active="subTab === 'ecosystem'"
        @module-filter-applied="onModuleFilterApplied"
      />
    </div>

    <!-- ============================================================ -->
    <!-- STABILITY SUB-TAB                                            -->
    <!-- ============================================================ -->
    <div v-if="detail && subTab === 'stability'" class="sub-content">
      <StabilityTab
        :projectId="route.params.id"
        :jobId="selectedJobId || ''"
        :population="population"
        :active="subTab === 'stability'"
      />
    </div>

    <!-- ============================================================ -->
    <!-- EXPLORATION SUB-TAB                                          -->
    <!-- ============================================================ -->
    <ExplorationTab v-if="detail && subTab === 'exploration' && hasExplorationData" />

    <!-- ============================================================ -->
    <!-- PHEROMONE SUB-TAB (ACO only)                                 -->
    <!-- ============================================================ -->
    <PheromoneTab v-if="detail && subTab === 'pheromone' && pheromoneData" />

    <!-- ============================================================ -->
    <!-- BASKET SUB-TAB                                               -->
    <!-- ============================================================ -->
    <BasketTab v-if="subTab === 'basket'" />

    <!-- ============================================================ -->
    <!-- CONSOLE LOG SUB-TAB                                          -->
    <!-- ============================================================ -->
    <ConsoleLogTab v-if="detail && subTab === 'console'" />

    <!-- Empty states -->
    <AsyncState
      v-if="loading || resultsError"
      :loading="loading"
      :error="resultsError"
      :retry="loadJobResults"
      :loading-text="$t('results.loadingResults')"
      :slow-text="$t('results.loadingResultsSlow')"
      :error-title="$t('results.resultsLoadFailed')"
    />
    <div v-else-if="!detail && jobsLoaded && !jobsError && jobs.length === 0" class="empty">
      <p>{{ $t('results.noJobsYet') }}</p>
      <router-link :to="`/project/${route.params.id}/parameters`" class="btn-sm btn-outline">{{ $t('results.goToParameters') }}</router-link>
    </div>
    <div v-else-if="!detail && jobs.length > 0 && !selectedJobInfo" class="empty">
      {{ $t('results.selectCompletedJob') }}
    </div>
    <p v-if="resultsPartial" class="partial-note" role="status">{{ $t('results.partialResults') }}</p>
  </div>
</template>

<script setup>
import { mountedSections, setAllSections } from '../composables/useSections'
/**
 * Results view: job list, job-level panels and the sub-tab bar.
 * State lives in composables/useResultsTab.js; each sub-tab is its own
 * component, fetched the first time it is opened.
 */
import { computed, defineAsyncComponent, provide, getCurrentInstance } from 'vue'
import { createResultsState, RESULTS_KEY } from '../composables/useResultsTab'
import SvgIcon from '../components/SvgIcon.vue'
import AsyncState from '../components/AsyncState.vue'

const EcosystemTab = defineAsyncComponent(() => import('../components/results/EcosystemTab.vue'))
const EnrichmentTab = defineAsyncComponent(() => import('../components/results/EnrichmentTab.vue'))
const InsightsTab = defineAsyncComponent(() => import('../components/results/InsightsTab.vue'))
const StabilityTab = defineAsyncComponent(() => import('../components/results/StabilityTab.vue'))
const SummaryTab = defineAsyncComponent(() => import('../components/results/tabs/SummaryTab.vue'))
const BestModelTab = defineAsyncComponent(() => import('../components/results/tabs/BestModelTab.vue'))
const PopulationTab = defineAsyncComponent(() => import('../components/results/tabs/PopulationTab.vue'))
const JuryTab = defineAsyncComponent(() => import('../components/results/tabs/JuryTab.vue'))
const ComparativeTab = defineAsyncComponent(() => import('../components/results/tabs/ComparativeTab.vue'))
const CoPresenceTab = defineAsyncComponent(() => import('../components/results/tabs/CoPresenceTab.vue'))
const ExplorationTab = defineAsyncComponent(() => import('../components/results/tabs/ExplorationTab.vue'))
const PheromoneTab = defineAsyncComponent(() => import('../components/results/tabs/PheromoneTab.vue'))
const BasketTab = defineAsyncComponent(() => import('../components/results/tabs/BasketTab.vue'))
const ConsoleLogTab = defineAsyncComponent(() => import('../components/results/tabs/ConsoleLogTab.vue'))

const state = createResultsState()
// Sub-tab components render with this view's style scope (see useResults()).
state.__scopeId = getCurrentInstance()?.type.__scopeId
provide(RESULTS_KEY, state)

const {
  basketCount,
  cancelJob,
  cancellingId,
  classNameFor,
  cleanupDuplicates,
  confirmDeleteJob,
  detail,
  doExport,
  duplicateGroups,
  duplicateJob,
  duplicatesLoading,
  exportMenuOpen,
  exportWrapEl,
  exporting,
  failedJobLog,
  filteredJobs,
  findDuplicates,
  fitMetricLabel,
  formatDate,
  formatDuration,
  formatSize,
  hasExplorationData,
  hasLiveJobs,
  isLive,
  isRegressionJob,
  jobAriaSort,
  jobPage,
  jobPageSize,
  jobSearch,
  jobSortAsc,
  jobSortKey,
  jobs,
  jobsError,
  jobsLoaded,
  jobsLoading,
  juryData,
  loadConsoleLog,
  loadFailedJobLog,
  loadJobList,
  loadJobResults,
  loading,
  mspAnnotations,
  onModuleFilterApplied,
  openLog,
  paginatedJobs,
  pheromoneData,
  population,
  rerunJob,
  rerunLoading,
  resultsError,
  resultsPartial,
  rootEl,
  route,
  selectJob,
  selectedJobId,
  selectedJobInfo,
  showLiveConsole,
  statusGlyph,
  statusLabel,
  subTab,
  toggleJobSort,
} = state

// Number of foldable sections on the current sub-tab (shows the fold/unfold buttons).
const foldableCount = computed(() => mountedSections().length)
</script>

<style scoped>
/* Failed job panel */
.failed-job-panel {
  background: var(--danger-bg, #2d1b1b);
  border: 1px solid var(--danger-dark, #e06c75);
  border-radius: 8px;
  padding: 1.25rem;
  margin-bottom: 1.5rem;
}
.failed-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.75rem;
}
.failed-header h3 { margin: 0; color: var(--danger-dark, #e06c75); font-size: 1rem; }
.failed-icon { font-size: 1.2rem; }
.failed-name { color: var(--text-muted); font-size: 0.85rem; }
.failed-details { margin-bottom: 0.75rem; }
.failed-row { margin-bottom: 0.4rem; font-size: 0.85rem; color: var(--text-secondary); }
.failed-row strong { color: var(--text-primary); }
.error-message {
  margin: 0.25rem 0 0;
  padding: 0.5rem 0.75rem;
  background: rgba(0,0,0,0.2);
  border-radius: 4px;
  font-size: 0.78rem;
  color: #e06c75;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 120px;
  overflow-y: auto;
}
.failed-log { margin-top: 0.75rem; }
.failed-log strong { font-size: 0.8rem; color: var(--text-muted); display: block; margin-bottom: 0.3rem; }
.log-content {
  margin: 0;
  padding: 0.5rem 0.75rem;
  background: rgba(0,0,0,0.3);
  border-radius: 4px;
  font-size: 0.75rem;
  color: var(--text-secondary);
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 200px;
  overflow-y: auto;
  font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;
}
.failed-log-hint { margin-top: 0.5rem; }

/* Flamegraph */
.flamegraph-panel {
  margin-bottom: 1.5rem;
  padding: 1rem;
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: 8px;
}
.flamegraph-panel h3 {
  margin: 0 0 0.75rem 0;
  font-size: 0.95rem;
  color: var(--text-primary);
}
.flamegraph-bar {
  display: flex;
  height: 36px;
  border-radius: 6px;
  overflow: hidden;
  border: 1px solid var(--border);
}
.flamegraph-segment {
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 2px;
  cursor: default;
  transition: opacity 0.15s;
}
.flamegraph-segment:hover { opacity: 0.8; }
.flamegraph-label {
  font-size: 0.75rem;
  font-weight: 600;
  color: #000;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  padding: 0 4px;
}
.flamegraph-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  margin-top: 0.75rem;
  align-items: center;
}
.flamegraph-legend-item {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  font-size: 0.75rem;
  color: var(--text-secondary);
}
.flamegraph-swatch {
  width: 10px;
  height: 10px;
  border-radius: 2px;
  flex-shrink: 0;
}
.flamegraph-legend-label { font-weight: 500; }
.flamegraph-legend-value { color: var(--text-muted); }
.flamegraph-total {
  margin-left: auto;
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--text-primary);
}

/* Console log viewer */
.console-log-panel { }
.console-header {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 1rem; flex-wrap: wrap; gap: 0.5rem;
}
.console-header h3 { margin: 0; font-size: 1rem; }
.console-actions { display: flex; gap: 0.5rem; }
.console-log-info {
  display: flex; gap: 1.5rem; font-size: 0.78rem; color: var(--text-muted);
  margin-bottom: 0.5rem; flex-wrap: wrap;
}
.console-log-info strong { color: var(--text-primary); }
.console-log-info .completed { color: var(--success, #98c379); }
.console-log-info .failed { color: #e06c75; }
.console-log-info .running { color: var(--info, #61afef); }
.console-log-viewer { }
.console-log-content {
  margin: 0; padding: 1rem;
  background: #0c0e1a;
  border: 1px solid var(--border, rgba(255,255,255,0.06));
  border-radius: 8px;
  font-size: 0.75rem; line-height: 1.6;
  color: var(--text-secondary);
  white-space: pre-wrap; word-break: break-all;
  max-height: 70vh; overflow-y: auto;
  font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;
}

/* Pending/running job panel */
.pending-job-panel {
  background: var(--info-bg, #1b2d3d);
  border: 1px solid var(--info, #61afef);
  border-radius: 8px;
  padding: 1.25rem;
  margin-bottom: 1.5rem;
}
.pending-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
}
.pending-header h3 { margin: 0; color: var(--info, #61afef); font-size: 1rem; }
.pending-icon { font-size: 1.2rem; }
.pending-name { color: var(--text-muted); font-size: 0.85rem; }
.pending-text { margin: 0; color: var(--text-muted); font-size: 0.85rem; }

/* Job management table */
.job-table-section {
  margin-bottom: 1.5rem;
}
.job-table-header {
  display: flex;
  align-items: baseline;
  gap: 0.75rem;
  margin-bottom: 0.5rem;
}
.job-table-header h3 {
  margin: 0;
  font-size: 1rem;
  color: var(--text-primary);
}
.job-count {
  font-size: 0.78rem;
  color: var(--text-faint);
}
.job-table-wrap {
  overflow-x: auto;
  border: 1px solid var(--border-light);
  border-radius: 8px;
}
.job-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.8rem;
}
.job-table th {
  background: var(--bg-card);
  padding: 0.5rem 0.6rem;
  text-align: left;
  font-weight: 600;
  color: var(--text-secondary);
  border-bottom: 2px solid var(--border-light);
  cursor: pointer;
  white-space: nowrap;
  user-select: none;
}
.job-table th:hover {
  color: var(--text-primary);
}
.job-table td {
  padding: 0.45rem 0.6rem;
  border-bottom: 1px solid var(--border-lighter, var(--border-light));
  color: var(--text-body);
  white-space: nowrap;
}
.job-table tbody tr {
  cursor: pointer;
  transition: background 0.1s;
}
.job-table tbody tr:hover {
  background: var(--bg-hover, rgba(0,0,0,0.03));
}
.job-table tbody tr.row-selected {
  background: var(--brand-bg, rgba(99,102,241,0.08));
  border-left: 3px solid var(--brand, #6366f1);
}
.job-table tbody tr.row-failed td {
  opacity: 0.7;
}
.col-name { max-width: 180px; overflow: hidden; text-overflow: ellipsis; font-weight: 500; }
.col-status { width: 80px; }
.col-auc { width: 70px; text-align: right; font-variant-numeric: tabular-nums; }
.col-k { width: 40px; text-align: right; }
.col-lang { max-width: 100px; overflow: hidden; text-overflow: ellipsis; }
.col-pop { width: 50px; text-align: right; }
.col-config { max-width: 160px; overflow: hidden; text-overflow: ellipsis; }
.col-size { width: 70px; text-align: right; }
.col-duration { width: 70px; text-align: right; }
.col-created { width: 110px; }
.col-user { max-width: 90px; overflow: hidden; text-overflow: ellipsis; }
.col-actions { width: 40px; text-align: center; }

.config-hash {
  display: inline-block;
  padding: 0.05rem 0.3rem;
  border-radius: 4px;
  font-family: monospace;
  font-size: 0.75rem;
  background: var(--bg-badge, rgba(0,0,0,0.06));
  color: var(--text-muted);
  margin-right: 0.3rem;
}
.config-detail {
  font-size: 0.75rem;
  color: var(--text-faint);
}

.job-search {
  padding: 0.25rem 0.5rem;
  font-size: 0.78rem;
  border: 1px solid var(--border);
  border-radius: 5px;
  background: var(--bg-input, var(--bg-card));
  color: var(--text-body);
  min-width: 160px;
  transition: border-color 0.15s;
}
.job-search:focus {
  border-color: var(--brand, #6366f1);
}
.job-search::placeholder {
  color: var(--text-faint);
}

.job-pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.75rem;
  margin-top: 0.5rem;
  font-size: 0.78rem;
  color: var(--text-secondary);
}
.job-pagination button {
  padding: 0.2rem 0.6rem;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--bg-card);
  color: var(--text-body);
  cursor: pointer;
  font-size: 0.75rem;
}
.job-pagination button:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.status-badge {
  display: inline-block;
  padding: 0.1rem 0.4rem;
  border-radius: 8px;
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
}
.status-badge.completed { background: var(--success-bg); color: var(--success-dark, #2e7d32); }
.status-badge.running { background: var(--info-bg); color: var(--info, #1976d2); }
.status-badge.failed { background: var(--danger-bg); color: var(--danger-dark, #c62828); }
.status-badge.pending { background: var(--warning-bg); color: var(--warning-dark, #e65100); }

.btn-icon {
  width: 24px;
  height: 24px;
  border: none;
  background: transparent;
  cursor: pointer;
  border-radius: 4px;
  font-size: 0.75rem;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s;
  color: var(--text-secondary);
}
.btn-icon:hover:not(:disabled) {
  background: var(--bg-card-hover);
  color: var(--text-primary);
}
.btn-delete {
  color: var(--text-muted);
}
.btn-delete:hover:not(:disabled) {
  background: var(--danger-bg);
  color: var(--danger-dark, #c62828);
}
.btn-delete:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

/* Small buttons */
.btn-sm {
  padding: 0.25rem 0.6rem;
  font-size: 0.75rem;
  border-radius: 5px;
  cursor: pointer;
  font-weight: 500;
  border: 1px solid var(--border);
  transition: all 0.15s;
}
.btn-outline {
  background: transparent;
  color: var(--text-secondary);
}
.btn-outline:hover {
  border-color: var(--brand);
  color: var(--brand);
}
.btn-outline:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.btn-danger {
  background: var(--danger-bg);
  color: var(--danger-dark, #c62828);
  border-color: transparent;
}
.btn-danger:hover {
  opacity: 0.85;
}

/* Duplicates panel */
.duplicates-panel {
  margin: 0.75rem 0;
  padding: 0.75rem;
  border: 1px solid var(--warning-dark, #e65100);
  border-radius: 8px;
  background: var(--warning-bg, #fff3e0);
}
.duplicates-header {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 0.5rem;
  font-size: 0.82rem;
}
.dup-group {
  margin-top: 0.5rem;
  padding: 0.4rem 0.6rem;
  background: var(--bg-card);
  border-radius: 6px;
  border: 1px solid var(--border-light);
}
.dup-group-label {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--text-secondary);
  margin-bottom: 0.3rem;
}
.dup-job {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.2rem 0;
  font-size: 0.78rem;
}
.dup-job.dup-keep {
  font-weight: 600;
}
.dup-name {
  min-width: 80px;
}
.dup-tag {
  padding: 0.05rem 0.35rem;
  border-radius: 6px;
  font-size: 0.75rem;
  font-weight: 700;
  text-transform: uppercase;
  background: var(--success-bg);
  color: var(--success-dark, #2e7d32);
}
.dup-tag.dup-remove {
  background: var(--danger-bg);
  color: var(--danger-dark, #c62828);
}

/* Sub-tabs: a segmented control that stays visible while the page scrolls */
.sub-tabs {
  position: sticky;
  top: 0;
  z-index: 20;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.25rem;
  padding: 0.3rem;
  margin-bottom: 1.5rem;
  background: var(--bg-tab-switcher);
  border: 1px solid var(--border);
  border-radius: 10px;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.08);
}
.sub-tabs > button {
  padding: 0.45rem 0.85rem;
  border: none;
  border-radius: 7px;
  background: transparent;
  color: var(--text-body);
  font-size: 0.85rem;
  font-weight: 600;
  white-space: nowrap;
  cursor: pointer;
  transition: background 0.12s, color 0.12s;
}
.sub-tabs > button:hover { background: var(--bg-card); color: var(--text-primary); }
.sub-tabs > button.active {
  background: var(--accent);
  color: var(--accent-text);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.25);
}
.sub-tabs > button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.sub-tabs > button.active .basket-badge { background: var(--accent-text); color: var(--accent); }
.export-dropdown-wrap { margin-left: auto; }
.fold-controls {
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
  margin: -1rem 0 0.75rem;
}
.fold-controls > button {
  padding: 0.15rem 0;
  border: none;
  background: none;
  color: var(--text-secondary);
  font-size: 0.8rem;
  text-decoration: underline;
  text-underline-offset: 2px;
  cursor: pointer;
}
.fold-controls > button:hover { color: var(--text-primary); }
.fold-controls > button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; border-radius: 3px; }
@media (prefers-reduced-motion: reduce) { .sub-tabs > button { transition: none; } }

/* Summary stat cards */
.summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 1rem;
  margin-bottom: 1.5rem;
}
.stat-card {
  background: var(--bg-card);
  padding: 1.25rem;
  border-radius: 8px;
  box-shadow: var(--shadow);
  text-align: center;
}
.stat-value {
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--text-primary);
}
.stat-label {
  font-size: 0.8rem;
  color: var(--text-faint);
  margin-top: 0.25rem;
}

/* Sections */
.section {
  background: var(--bg-card);
  padding: 1.5rem;
  border-radius: 8px;
  box-shadow: var(--shadow);
  margin-bottom: 1.5rem;
}
.section h3 {
  margin-bottom: 1rem;
  color: var(--text-primary);
  font-size: 0.95rem;
}

/* Charts */
.plotly-chart {
  width: 100%;
  min-height: 250px;
}
.plotly-chart-tall {
  min-height: 400px;
}

/* Vote string display */
.vote-str { max-width: 200px; overflow: hidden; text-overflow: ellipsis; }
.vote-mono { font-family: monospace; font-size: 0.75rem; letter-spacing: -0.5px; color: var(--text-muted); }
.chart-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1.5rem;
}
.chart-half {
  min-width: 0;
}
.jury-cm-stack {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.jury-cm-stack .section {
  margin-bottom: 0;
}

/* Best model layout */
.best-model-layout {
  display: grid;
  grid-template-columns: 320px 1fr;
  gap: 2rem;
  align-items: start;
}
.metrics-col { min-width: 0; }
.coefficients-col { min-width: 0; }

/* Metrics table */
.metrics-table {
  width: 100%;
  max-width: 300px;
}
.metrics-table td {
  padding: 0.4rem 0;
  border-bottom: 1px solid var(--border-lighter);
}
.metric-name {
  color: var(--text-muted);
  font-size: 0.9rem;
}
.metric-value {
  text-align: right;
  font-weight: 600;
  color: var(--text-primary);
}

/* Feature chips */
.feature-list { display: flex; flex-wrap: wrap; gap: 0.5rem; }
.feature-chip {
  padding: 0.35rem 0.75rem;
  border-radius: 20px;
  font-size: 0.8rem;
  font-weight: 500;
}
.feature-chip.positive { background: var(--success-bg); color: var(--success-dark); }
.feature-chip.negative { background: var(--danger-bg); color: var(--danger-dark); }

/* Population controls */
.pop-controls {
  margin-bottom: 1rem;
  background: var(--bg-card);
  padding: 1rem 1.25rem;
  border-radius: 8px;
  box-shadow: var(--shadow);
}
.pop-controls-row {
  display: flex;
  align-items: center;
  gap: 1.5rem;
  margin-bottom: 0.5rem;
}
.topn-control {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  font-size: 0.82rem;
  color: var(--text-secondary);
}
.topn-input {
  width: 56px;
  padding: 0.2rem 0.3rem;
  font-size: 0.82rem;
  text-align: center;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--bg-input);
  color: var(--text-body);
}
.fbm-toggle {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  font-size: 0.82rem;
  color: var(--text-secondary);
  cursor: pointer;
}
.fbm-toggle input[type="checkbox"] { width: auto; }
.fbm-badge {
  font-size: 0.75rem;
  background: var(--accent);
  color: #fff;
  padding: 0.1rem 0.5rem;
  border-radius: 10px;
  font-weight: 600;
}
.fbm-method-select {
  font-size: 0.8rem;
  padding: 0.15rem 0.4rem;
  border-radius: 4px;
  border: 1px solid var(--border);
  background: var(--bg-secondary);
  color: var(--text);
  margin-left: 0.5rem;
}
/* Basket */
.col-basket { width: 36px; text-align: center; padding: 0 4px !important; }
.btn-basket {
  font-size: 1.1rem;
  color: var(--text-faint, #888);
  transition: color 0.15s, transform 0.15s;
  cursor: pointer;
  background: none;
  border: none;
  padding: 0;
  line-height: 1;
}
.btn-basket.in-basket { color: var(--accent, #00BFFF); }
.btn-basket:hover:not(:disabled) { transform: scale(1.25); }
.btn-basket:disabled { opacity: 0.3; cursor: default; }
.basket-badge {
  display: inline-block;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  margin-left: 4px;
  border-radius: 8px;
  background: var(--accent, #00BFFF);
  color: #fff;
  font-size: 0.75rem;
  font-weight: 700;
  line-height: 16px;
  text-align: center;
  vertical-align: middle;
}
.basket-header {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-bottom: 1rem;
}
.basket-count-label {
  font-size: 0.85rem;
  color: var(--text-muted);
  font-weight: 600;
}
.basket-feature-stats {
  display: flex;
  gap: 0.75rem;
  margin-bottom: 0.75rem;
  flex-wrap: wrap;
}
.stat-pill {
  font-size: 0.78rem;
  padding: 0.2rem 0.6rem;
  border-radius: 10px;
  background: var(--bg-secondary);
  color: var(--text-muted);
  border: 1px solid var(--border);
}
.basket-consensus {
  margin-bottom: 1rem;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.82rem;
}
.filter-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-top: 0.4rem;
  flex-wrap: wrap;
}
.filter-label {
  font-size: 0.78rem;
  color: var(--text-muted);
  font-weight: 600;
  min-width: 70px;
}
.filter-check {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  font-size: 0.8rem;
  color: var(--text-body);
  cursor: pointer;
}
.filter-check input[type="checkbox"] { width: auto; }
.filter-clear {
  font-size: 0.75rem;
  color: var(--text-faint);
  background: none;
  border: none;
  cursor: pointer;
  text-decoration: underline;
  padding: 0;
}

/* Population table */
.pop-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.85rem;
}
.pop-table th {
  text-align: left;
  padding: 0.5rem;
  border-bottom: 2px solid var(--border-light);
  color: var(--text-secondary);
  font-weight: 600;
}
.pop-table td {
  padding: 0.5rem;
  border-bottom: 1px solid var(--border-lighter);
  color: var(--text-body);
  /* long text (a full feature name, a path) wraps instead of widening the page */
  overflow-wrap: anywhere;
}
.clickable-row { cursor: pointer; }
.clickable-row:hover { background: var(--bg-card-hover); }
.detail-row td {
  background: var(--bg-badge);
  padding: 1rem;
}
.row-error td { color: var(--danger-dark); }

/* Module filter highlight */
.module-filtered {
  background: rgba(25, 118, 210, 0.06);
}
.module-filtered:hover {
  background: rgba(25, 118, 210, 0.12);
}
.module-badge {
  display: inline-block;
  background: var(--primary, #1976d2);
  color: white;
  font-size: 0.75rem;
  font-weight: 700;
  padding: 0.1rem 0.3rem;
  border-radius: 3px;
  margin-left: 0.3rem;
  vertical-align: middle;
  line-height: 1;
}

.pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 1rem;
  margin-top: 1rem;
  font-size: 0.85rem;
}
.pagination button {
  padding: 0.3rem 0.75rem;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--bg-card);
  color: var(--text-body);
  cursor: pointer;
}
.pagination button:disabled { opacity: 0.5; cursor: not-allowed; }

/* Comparative */
.job-checkboxes {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
}
.job-check {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  font-size: 0.85rem;
  color: var(--text-body);
  cursor: pointer;
}
.job-check input[type="checkbox"] {
  width: auto;
}
.job-check-label {
  display: flex;
  align-items: center;
  gap: 0.3rem;
}
.job-check-auc {
  font-size: 0.75rem;
  color: var(--text-faint);
}

/* Common */
.info-text { color: var(--text-faint); font-size: 0.85rem; font-style: italic; }
.empty { text-align: center; padding: 3rem; color: var(--text-faint); }
.loading { text-align: center; padding: 3rem; color: var(--text-faint); }

/* Comparative: metrics table */
.compare-table-wrap {
  overflow-x: auto;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  margin-bottom: 1rem;
}
.compare-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.82rem;
}
.compare-table th {
  background: var(--bg-card);
  padding: 0.5rem 0.75rem;
  font-weight: 600;
  color: var(--text-secondary);
  border-bottom: 2px solid var(--border-light);
  white-space: nowrap;
}
.compare-table td {
  padding: 0.45rem 0.75rem;
  border-bottom: 1px solid var(--border-lighter, var(--border-light));
  text-align: center;
}
.compare-table td.metric-name {
  text-align: left;
  font-weight: 500;
  color: var(--text-secondary);
  white-space: nowrap;
}
.compare-table td.best-val {
  color: var(--accent, #00BFFF);
  font-weight: 700;
}
.compare-table td.diff-val {
  background: rgba(255, 165, 0, 0.08);
  color: var(--text-primary);
}
.config-diff-table td {
  font-family: monospace;
  font-size: 0.78rem;
}

/* Feature analysis */
.feature-analysis {
  display: flex;
  gap: 1.5rem;
  margin-bottom: 0.75rem;
  flex-wrap: wrap;
}
.feature-stat {
  display: flex;
  gap: 0.4rem;
  align-items: baseline;
}
.fa-label {
  color: var(--text-muted);
  font-size: 0.82rem;
}
.fa-value {
  font-weight: 600;
  font-size: 0.88rem;
}
.common-features {
  display: flex;
  flex-wrap: wrap;
  gap: 0.3rem;
  align-items: center;
  font-size: 0.82rem;
  margin-top: 0.5rem;
}

/* Export dropdown */
.export-dropdown-wrap {
  position: relative;
  margin-left: auto;
}
.btn-export {
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  color: var(--text-secondary);
  border-radius: 6px;
  padding: 0.35rem 0.75rem;
  cursor: pointer;
  font-size: 0.8rem;
  white-space: nowrap;
  transition: background 0.15s, color 0.15s;
}
.btn-export:hover {
  background: var(--accent, #00BFFF);
  color: #fff;
  border-color: var(--accent, #00BFFF);
}
.export-menu {
  position: absolute;
  right: 0;
  top: 100%;
  margin-top: 4px;
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: 8px;
  padding: 0.25rem 0;
  min-width: 180px;
  box-shadow: 0 4px 16px rgba(0,0,0,0.3);
  z-index: 100;
}
.export-menu button {
  display: block;
  width: 100%;
  text-align: left;
  padding: 0.45rem 0.9rem;
  border: none;
  background: transparent;
  color: var(--text-body);
  font-size: 0.8rem;
  cursor: pointer;
  transition: background 0.1s;
}
.export-menu button:hover {
  background: var(--bg-hover, rgba(0,191,255,0.1));
  color: var(--text-primary);
}
.export-menu hr {
  border: none;
  border-top: 1px solid var(--border-light);
  margin: 0.25rem 0;
}

/* Co-presence network header */
.network-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-bottom: 0.25rem;
}
.network-header h3 { margin: 0; }

.layout-selector {
  display: flex;
  gap: 0.25rem;
}
.layout-option {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.25rem 0.6rem;
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 0.78rem;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.15s;
  user-select: none;
}
.layout-option input[type="radio"] { display: none; }
.layout-option.active {
  border-color: var(--accent);
  background: color-mix(in srgb, var(--accent) 12%, transparent);
  color: var(--text-primary);
}
.layout-option:hover { border-color: var(--accent); }

/* Functional annotation badges */
.func-badge {
  display: inline-block;
  padding: 0.1rem 0.45rem;
  border-radius: 8px;
  font-size: 0.75rem;
  font-weight: 600;
}
.func-positive {
  background: rgba(100, 200, 100, 0.15);
  color: var(--positive, #98c379);
}
.func-negative {
  background: rgba(200, 80, 80, 0.15);
  color: var(--negative, #e06c75);
}
.func-neutral {
  background: rgba(186, 85, 211, 0.15);
  color: var(--accent, #BA55D3);
}
.func-warn {
  background: rgba(229, 192, 123, 0.15);
  color: var(--warn, #e5c07b);
}

/* Co-presence badges */
.cooccur-type {
  display: inline-block;
  padding: 0.15rem 0.5rem;
  border-radius: 10px;
  font-size: 0.75rem;
  font-weight: 600;
}
.cooccur-type.positive {
  background: rgba(100, 200, 100, 0.15);
  color: var(--positive, #98c379);
}
.cooccur-type.negative {
  background: rgba(200, 80, 80, 0.15);
  color: var(--negative, #e06c75);
}

/* Deploy API box */
.deploy-box {
  background: var(--bg-primary); border: 1px solid var(--border-color);
  border-radius: 8px; padding: 0.75rem 1rem; margin-top: 0.5rem;
}
.deploy-endpoint {
  display: flex; align-items: center; gap: 0.75rem; flex-wrap: wrap;
}
.deploy-endpoint code {
  font-size: 0.85rem; color: var(--accent); background: rgba(0,191,255,0.08);
  padding: 0.3rem 0.6rem; border-radius: 4px;
}
.deploy-example { margin-top: 0.75rem; font-size: 0.8rem; color: var(--text-faint); }
.deploy-example summary { cursor: pointer; }
.code-block {
  background: var(--bg-card); border: 1px solid var(--border-color);
  border-radius: 6px; padding: 0.75rem; margin-top: 0.5rem;
  font-size: 0.75rem; overflow-x: auto; white-space: pre-wrap; word-break: break-all;
}

/* SHAP explanations */
.shap-tabs {
  display: flex;
  gap: 0.25rem;
  margin: 0.75rem 0;
}
.shap-tabs button {
  padding: 0.35rem 0.9rem;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: transparent;
  color: var(--text-secondary);
  font-size: 0.8rem;
  cursor: pointer;
  transition: all 0.15s;
}
.shap-tabs button.active {
  background: var(--accent);
  color: var(--accent-text, #fff);
  border-color: var(--accent);
}
.shap-tabs button:hover:not(.active) {
  border-color: var(--accent);
  color: var(--text-primary);
}
.shap-control-row {
  margin-top: 0.5rem;
}
.shap-control-row label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.85rem;
  color: var(--text-secondary);
  margin-bottom: 0.5rem;
}
.shap-select {
  padding: 0.3rem 0.5rem;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg-input);
  color: var(--text-body);
  font-size: 0.82rem;
  max-width: 300px;
}

/* PCoA in Population */
.pcoa-controls {
  display: flex;
  align-items: flex-end;
  gap: 1rem;
  margin-bottom: 0.75rem;
  flex-wrap: wrap;
}
.pcoa-control-item {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
  font-size: 0.75rem;
  color: var(--text-secondary);
}
.pcoa-control-item select { min-width: 120px; }
.pcoa-dim-toggle { display: flex; }
.pcoa-dim-toggle button {
  padding: 0.3rem 0.7rem;
  border: 1px solid var(--border);
  background: var(--bg-input);
  color: var(--text-body);
  font-size: 0.8rem;
  cursor: pointer;
}
.pcoa-dim-toggle button:first-child { border-radius: 4px 0 0 4px; }
.pcoa-dim-toggle button:last-child { border-radius: 0 4px 4px 0; border-left: none; }
.pcoa-dim-toggle button.active { background: var(--accent); color: #fff; border-color: var(--accent); }
.pcoa-stats-row {
  display: flex;
  align-items: center;
  gap: 1rem;
  flex-wrap: wrap;
  margin-bottom: 0.5rem;
}
.pcoa-info { font-size: 0.78rem; color: var(--text-faint); }
.pcoa-permanova {
  font-size: 0.78rem;
  color: var(--text-secondary);
  background: var(--bg-badge);
  padding: 0.2rem 0.6rem;
  border-radius: 6px;
  font-family: monospace;
}
.pcoa-permanova.significant { color: var(--success-dark); background: var(--success-bg-alt); }
.sig-star { color: var(--danger); font-weight: 700; margin-left: 0.2rem; }
.plotly-chart-pcoa { min-height: 500px; }

@media (max-width: 900px) {
  .best-model-layout { grid-template-columns: 1fr; }
  .chart-row { grid-template-columns: 1fr; }
}
.sort-btn { background: none; border: none; padding: 0; font: inherit; font-weight: inherit; color: inherit; cursor: pointer; white-space: nowrap; }
.live-note { display: inline-flex; align-items: center; gap: 0.35rem; font-size: 0.75rem; color: var(--text-secondary); }
.live-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--status-running); animation: live-pulse 1.4s ease-in-out infinite; }
@keyframes live-pulse { 50% { opacity: 0.3; } }
.btn-cancel { color: var(--danger-dark); }
.pending-actions { display: flex; gap: 0.5rem; margin-top: 0.75rem; flex-wrap: wrap; }
.partial-note { margin: 0.5rem 0; padding: 0.5rem 0.75rem; background: var(--warning-bg); color: var(--warning-dark); border-radius: 6px; font-size: 0.85rem; }
.status-badge.cancelled { background: var(--bg-badge); color: var(--text-secondary); }
.job-table-wrap { overflow-x: auto; }
@media (max-width: 1100px) {
  .job-table .col-lang, .job-table .col-pop, .job-table .col-config,
  .job-table .col-size, .job-table .col-user { display: none; }
}
@media (max-width: 700px) {
  .job-table .col-duration, .job-table .col-created { display: none; }
  .job-table-header { flex-wrap: wrap; gap: 0.4rem; }
}
.chart-summary { font-size: 0.82rem; color: var(--text-secondary); margin: 0 0 0.5rem; }
</style>
