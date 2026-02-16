<template>
  <div class="results-tab">
    <!-- Job management table -->
    <div class="job-table-section" v-if="jobs.length > 0">
      <div class="job-table-header">
        <h3>Jobs</h3>
        <span class="job-count">{{ filteredJobs.length }}<template v-if="jobSearch"> / {{ jobs.length }}</template> job{{ jobs.length !== 1 ? 's' : '' }}</span>
        <input
          type="text"
          v-model="jobSearch"
          class="job-search"
          placeholder="Search jobs..."
        />
        <button class="btn-sm btn-outline" @click="findDuplicates" :disabled="duplicatesLoading" v-if="jobs.length >= 2">
          {{ duplicatesLoading ? 'Checking...' : 'Find Duplicates' }}
        </button>
      </div>
      <!-- Duplicate groups panel -->
      <div v-if="duplicateGroups.length > 0" class="duplicates-panel">
        <div class="duplicates-header">
          <strong>{{ duplicateGroups.length }} duplicate group{{ duplicateGroups.length !== 1 ? 's' : '' }} found</strong>
          <button class="btn-sm btn-danger" @click="cleanupDuplicates">Delete duplicates (keep best)</button>
          <button class="btn-sm btn-outline" @click="duplicateGroups = []">Dismiss</button>
        </div>
        <div v-for="(g, gi) in duplicateGroups" :key="gi" class="dup-group">
          <div class="dup-group-label">{{ g.config_summary }} ({{ g.jobs.length }} jobs)</div>
          <div v-for="dj in g.jobs" :key="dj.job_id" class="dup-job" :class="{ 'dup-keep': dj.keep }">
            <span class="dup-name">{{ dj.name || dj.job_id.slice(0, 8) }}</span>
            <span class="status-badge" :class="dj.status">{{ dj.status }}</span>
            <span v-if="dj.best_auc != null">AUC {{ dj.best_auc.toFixed(4) }}</span>
            <span class="dup-tag" v-if="dj.keep">KEEP</span>
            <span class="dup-tag dup-remove" v-else>REMOVE</span>
          </div>
        </div>
      </div>
      <div class="job-table-wrap">
        <table class="job-table">
          <thead>
            <tr>
              <th class="col-name" @click="toggleJobSort('name')">Name <span v-if="jobSortKey === 'name'">{{ jobSortAsc ? '▲' : '▼' }}</span></th>
              <th class="col-status" @click="toggleJobSort('status')">Status <span v-if="jobSortKey === 'status'">{{ jobSortAsc ? '▲' : '▼' }}</span></th>
              <th class="col-auc" @click="toggleJobSort('best_auc')">AUC <span v-if="jobSortKey === 'best_auc'">{{ jobSortAsc ? '▲' : '▼' }}</span></th>
              <th class="col-k" @click="toggleJobSort('best_k')">k <span v-if="jobSortKey === 'best_k'">{{ jobSortAsc ? '▲' : '▼' }}</span></th>
              <th class="col-lang">Language</th>
              <th class="col-pop">Pop</th>
              <th class="col-config">Config</th>
              <th class="col-size" @click="toggleJobSort('disk_size_bytes')">Size <span v-if="jobSortKey === 'disk_size_bytes'">{{ jobSortAsc ? '▲' : '▼' }}</span></th>
              <th class="col-duration" @click="toggleJobSort('duration_seconds')">Duration <span v-if="jobSortKey === 'duration_seconds'">{{ jobSortAsc ? '▲' : '▼' }}</span></th>
              <th class="col-created" @click="toggleJobSort('created_at')">Created <span v-if="jobSortKey === 'created_at'">{{ jobSortAsc ? '▲' : '▼' }}</span></th>
              <th class="col-user">User</th>
              <th class="col-actions">Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="j in paginatedJobs"
              :key="j.job_id"
              :class="{ 'row-selected': selectedJobId === j.job_id, ['row-' + j.status]: true }"
              @click="selectJob(j.job_id)"
            >
              <td class="col-name" :title="j.job_id">{{ j.name || j.job_id.slice(0, 8) }}</td>
              <td class="col-status"><span class="status-badge" :class="j.status">{{ j.status }}</span></td>
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
                <button class="btn-icon btn-delete" @click.stop="confirmDeleteJob(j)" title="Delete job" :disabled="j.status === 'running'">&#10005;</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <!-- Job table pagination -->
      <div class="job-pagination" v-if="filteredJobs.length > jobPageSize">
        <button @click="jobPage = Math.max(0, jobPage - 1)" :disabled="jobPage === 0">&laquo; Prev</button>
        <span>{{ jobPage * jobPageSize + 1 }}&ndash;{{ Math.min((jobPage + 1) * jobPageSize, filteredJobs.length) }} of {{ filteredJobs.length }}</span>
        <button @click="jobPage++" :disabled="(jobPage + 1) * jobPageSize >= filteredJobs.length">Next &raquo;</button>
      </div>
    </div>

    <!-- Failed job error panel -->
    <div v-if="selectedJobInfo && selectedJobInfo.status === 'failed' && !detail" class="failed-job-panel">
      <div class="failed-header">
        <span class="failed-icon">&#9888;</span>
        <h3>Job Failed</h3>
        <span class="failed-name" v-if="selectedJobInfo.name">{{ selectedJobInfo.name }}</span>
      </div>
      <div class="failed-details">
        <div class="failed-row" v-if="selectedJobInfo.error_message">
          <strong>Error:</strong>
          <pre class="error-message">{{ selectedJobInfo.error_message }}</pre>
        </div>
        <div class="failed-row" v-if="selectedJobInfo.created_at">
          <strong>Started:</strong> {{ formatDate(selectedJobInfo.created_at) }}
        </div>
        <div class="failed-row" v-if="selectedJobInfo.duration_seconds">
          <strong>Duration:</strong> {{ formatDuration(selectedJobInfo.duration_seconds) }}
        </div>
        <div class="failed-row" v-if="selectedJobInfo.config_summary">
          <strong>Config:</strong> {{ selectedJobInfo.config_summary }}
        </div>
      </div>
      <div v-if="failedJobLog" class="failed-log">
        <strong>Console output (last 50 lines):</strong>
        <pre class="log-content">{{ failedJobLog }}</pre>
      </div>
      <div v-else class="failed-log-hint">
        <button class="btn-sm btn-outline" @click="loadFailedJobLog">Show console log</button>
      </div>
    </div>

    <!-- Pending/running job info panel -->
    <div v-else-if="selectedJobInfo && (selectedJobInfo.status === 'pending' || selectedJobInfo.status === 'running') && !detail" class="pending-job-panel">
      <div class="pending-header">
        <span class="pending-icon">&#9203;</span>
        <h3>Job {{ selectedJobInfo.status === 'running' ? 'Running' : 'Pending' }}</h3>
        <span class="pending-name" v-if="selectedJobInfo.name">{{ selectedJobInfo.name }}</span>
      </div>
      <p class="pending-text">Results will appear here once the job completes.</p>
    </div>

    <!-- Sub-tabs -->
    <nav class="sub-tabs" v-if="detail">
      <button :class="{ active: subTab === 'summary' }" @click="subTab = 'summary'">Summary</button>
      <button :class="{ active: subTab === 'bestmodel' }" @click="subTab = 'bestmodel'">Best Model</button>
      <button :class="{ active: subTab === 'population' }" @click="subTab = 'population'">Population</button>
      <button v-if="juryData" :class="{ active: subTab === 'jury' }" @click="subTab = 'jury'">Jury</button>
      <button :class="{ active: subTab === 'comparative' }" @click="subTab = 'comparative'">Comparative</button>
      <button v-if="population.length > 1" :class="{ active: subTab === 'copresence' }" @click="subTab = 'copresence'">Co-presence</button>
      <div class="export-dropdown-wrap" v-if="detail">
        <button class="btn-sm btn-export" @click="exportMenuOpen = !exportMenuOpen">
          &#8615; Export
        </button>
        <div class="export-menu" v-if="exportMenuOpen" @mouseleave="exportMenuOpen = false">
          <button @click="doExport('report')">HTML Report</button>
          <button @click="doExport('json')">Full JSON</button>
          <hr />
          <button @click="doExport('csv', 'best_model')">CSV: Best Model</button>
          <button @click="doExport('csv', 'population')">CSV: Population</button>
          <button @click="doExport('csv', 'generation_tracking')">CSV: Generations</button>
          <button v-if="juryData" @click="doExport('csv', 'jury_predictions')">CSV: Jury Predictions</button>
          <hr />
          <button @click="doExport('notebook', 'python')">Python Notebook (.ipynb)</button>
          <button @click="doExport('notebook', 'r')">R Notebook (.Rmd)</button>
        </div>
      </div>
    </nav>

    <!-- ============================================================ -->
    <!-- SUMMARY SUB-TAB                                              -->
    <!-- ============================================================ -->
    <div v-if="detail && subTab === 'summary'" class="sub-content">
      <div class="summary-grid">
        <div class="stat-card">
          <div class="stat-value">{{ detail.best_auc?.toFixed(4) || '—' }}</div>
          <div class="stat-label">Best AUC</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ detail.best_k || '—' }}</div>
          <div class="stat-label">Features (k)</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ detail.execution_time?.toFixed(1) }}s</div>
          <div class="stat-label">Time</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ detail.generation_count }}</div>
          <div class="stat-label">Generations</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ detail.feature_count }}</div>
          <div class="stat-label">Total Features</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ detail.sample_count }}</div>
          <div class="stat-label">Samples</div>
        </div>
      </div>

      <!-- Convergence chart -->
      <section class="section" v-if="generationTracking.length > 0">
        <h3>AUC Evolution (Train vs Test)</h3>
        <div ref="convergenceChartEl" class="plotly-chart"></div>
      </section>

      <!-- Feature count + fit evolution -->
      <div class="chart-row" v-if="generationTracking.length > 0">
        <section class="section chart-half">
          <h3>Model Complexity (k)</h3>
          <div ref="featureCountChartEl" class="plotly-chart"></div>
        </section>
        <section class="section chart-half">
          <h3>Fit vs AUC</h3>
          <div ref="fitEvolutionChartEl" class="plotly-chart"></div>
        </section>
      </div>
    </div>

    <!-- ============================================================ -->
    <!-- BEST MODEL SUB-TAB                                           -->
    <!-- ============================================================ -->
    <div v-if="detail && subTab === 'bestmodel'" class="sub-content">
      <section class="section" v-if="detail.best_individual">
        <div class="best-model-layout">
          <!-- Left column: metrics + radar -->
          <div class="metrics-col">
            <h3>Metrics</h3>
            <table class="metrics-table">
              <tr v-for="(val, key) in bestMetrics" :key="key">
                <td class="metric-name">{{ key }}</td>
                <td class="metric-value">{{ typeof val === 'number' ? val.toFixed(4) : val }}</td>
              </tr>
            </table>
            <div ref="radarChartEl" class="plotly-chart" style="margin-top: 1rem;"></div>
          </div>
          <!-- Right column: coefficients bar chart -->
          <div class="coefficients-col">
            <h3>Model Coefficients</h3>
            <div ref="coefficientsChartEl" class="plotly-chart"></div>
          </div>
        </div>
      </section>

      <!-- Feature importance -->
      <section class="section" v-if="importanceData && importanceData.length > 0">
        <h3>Feature Importance (MDA)</h3>
        <div ref="importanceChartEl" class="plotly-chart"></div>
      </section>
      <p v-else-if="detail.best_individual" class="info-text">
        Feature importance not available. Enable "Compute importance" in the Parameters tab to include MDA analysis.
      </p>

      <!-- Coefficient direction chart -->
      <section class="section" v-if="detail.best_individual">
        <h3>Coefficient Direction</h3>
        <div ref="directionChartEl" class="plotly-chart"></div>
      </section>

      <!-- Feature contribution waterfall -->
      <section class="section" v-if="detail.best_individual">
        <h3>Feature Contribution Waterfall</h3>
        <div ref="waterfallChartEl" class="plotly-chart"></div>
      </section>

      <!-- Per-sample contribution heatmap -->
      <section class="section" v-if="detail.best_individual">
        <h3>Per-Sample Feature Contributions</h3>
        <button v-if="!contributionData && !contributionLoading" class="btn-sm btn-outline" @click="loadContributionHeatmap">
          Compute Contributions
        </button>
        <div v-if="contributionLoading" class="loading">Computing per-sample contributions...</div>
        <div v-if="contributionData" ref="contributionHeatmapEl" class="plotly-chart plotly-chart-tall"></div>
      </section>
    </div>

    <!-- ============================================================ -->
    <!-- POPULATION SUB-TAB                                           -->
    <!-- ============================================================ -->
    <div v-if="detail && subTab === 'population'" class="sub-content">
      <!-- Controls -->
      <div class="pop-controls">
        <div class="pop-controls-row">
          <label class="topn-control">
            Top
            <input type="number" v-model.number="topNModels" :min="5" :max="filteredPopulation.length" step="5" class="topn-input" />
            / {{ filteredPopulation.length }} models
          </label>
          <label class="fbm-toggle">
            <input type="checkbox" v-model="fbmEnabled" />
            FBM only
            <span class="fbm-badge" v-if="fbmEnabled">{{ fbmCount }} / {{ population.length }}</span>
          </label>
        </div>

        <!-- Language filter -->
        <div class="filter-row" v-if="availableLanguages.length > 1">
          <span class="filter-label">Language:</span>
          <label v-for="lang in availableLanguages" :key="lang" class="filter-check">
            <input type="checkbox" :value="lang" v-model="selectedLanguages" />
            {{ lang }}
          </label>
          <button v-if="selectedLanguages.length > 0" class="filter-clear" @click="selectedLanguages = []">clear</button>
        </div>

        <!-- Data type filter -->
        <div class="filter-row" v-if="availableDataTypes.length > 1">
          <span class="filter-label">Data type:</span>
          <label v-for="dt in availableDataTypes" :key="dt" class="filter-check">
            <input type="checkbox" :value="dt" v-model="selectedDataTypes" />
            {{ dt }}
          </label>
          <button v-if="selectedDataTypes.length > 0" class="filter-clear" @click="selectedDataTypes = []">clear</button>
        </div>
      </div>

      <!-- Language / Data Type composition -->
      <div class="chart-row" v-if="filteredPopulation.length > 0">
        <section class="section chart-half">
          <h3>Composition by Language &times; Data Type</h3>
          <div ref="compositionChartEl" class="plotly-chart"></div>
        </section>
        <section class="section chart-half">
          <h3>AUC Distribution by Type</h3>
          <div ref="metricsByTypeEl" class="plotly-chart"></div>
        </section>
      </div>

      <!-- Feature-model heatmap -->
      <section class="section" v-if="filteredPopulation.length > 0">
        <h3>Feature-Model Coefficients</h3>
        <div ref="featureHeatmapEl" class="plotly-chart"></div>
      </section>

      <!-- Feature prevalence + pop metrics side by side -->
      <div class="chart-row" v-if="filteredPopulation.length > 0">
        <section class="section chart-half">
          <h3>Feature Prevalence</h3>
          <div ref="featurePrevalenceEl" class="plotly-chart"></div>
        </section>
        <section class="section chart-half">
          <h3>Population Metrics</h3>
          <div ref="popMetricsEl" class="plotly-chart"></div>
        </section>
      </div>

      <!-- Population table -->
      <section class="section" v-if="filteredPopulation.length > 0">
        <h3>Population Table ({{ filteredPopulation.length }} individuals)</h3>
        <table class="pop-table">
          <thead>
            <tr>
              <th>#</th>
              <th>AUC</th>
              <th>Fit</th>
              <th>Accuracy</th>
              <th>k</th>
              <th>Language</th>
              <th>Data Type</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="ind in paginatedPopulation" :key="ind.rank">
              <tr @click="toggleExpand(ind.rank)" class="clickable-row">
                <td>{{ ind.rank + 1 }}</td>
                <td>{{ ind.metrics.auc?.toFixed(4) }}</td>
                <td>{{ ind.metrics.fit?.toFixed(4) }}</td>
                <td>{{ ind.metrics.accuracy?.toFixed(4) }}</td>
                <td>{{ ind.metrics.k }}</td>
                <td>{{ ind.metrics.language }}</td>
                <td>{{ ind.metrics.data_type }}</td>
              </tr>
              <tr v-if="expandedRank === ind.rank" class="detail-row">
                <td colspan="7">
                  <div class="feature-list">
                    <div
                      v-for="[name, coef] in sortedFeatures(ind.named_features)"
                      :key="name"
                      class="feature-chip"
                      :class="{ positive: coef > 0, negative: coef < 0 }"
                    >
                      {{ featureLabel(name) }} ({{ coef > 0 ? '+1' : '-1' }})
                    </div>
                  </div>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
        <div class="pagination" v-if="filteredPopulation.length > popPageSize">
          <button @click="popPage = Math.max(0, popPage - 1)" :disabled="popPage === 0">&laquo; Prev</button>
          <span>Page {{ popPage + 1 }} / {{ Math.ceil(filteredPopulation.length / popPageSize) }}</span>
          <button @click="popPage++" :disabled="(popPage + 1) * popPageSize >= filteredPopulation.length">Next &raquo;</button>
        </div>
      </section>
      <p v-if="population.length === 0" class="info-text">Population data not available for this job.</p>
      <p v-else-if="filteredPopulation.length === 0" class="info-text">No models match the current filters.</p>
    </div>

    <!-- ============================================================ -->
    <!-- JURY SUB-TAB                                                 -->
    <!-- ============================================================ -->
    <div v-if="detail && subTab === 'jury'" class="sub-content">
      <template v-if="juryData">
        <!-- Jury summary cards -->
        <div class="summary-grid">
          <div class="stat-card">
            <div class="stat-value">{{ juryData.method }}</div>
            <div class="stat-label">Voting Method</div>
          </div>
          <div class="stat-card">
            <div class="stat-value">{{ juryData.expert_count }}</div>
            <div class="stat-label">Experts</div>
          </div>
          <div class="stat-card">
            <div class="stat-value">{{ juryData.test?.auc?.toFixed(4) || '—' }}</div>
            <div class="stat-label">Test AUC</div>
          </div>
          <div class="stat-card">
            <div class="stat-value">{{ juryData.test?.accuracy?.toFixed(4) || '—' }}</div>
            <div class="stat-label">Test Accuracy</div>
          </div>
          <div class="stat-card">
            <div class="stat-value">{{ juryData.test?.sensitivity?.toFixed(4) || '—' }}</div>
            <div class="stat-label">Test Sensitivity</div>
          </div>
          <div class="stat-card">
            <div class="stat-value">{{ juryData.test?.specificity?.toFixed(4) || '—' }}</div>
            <div class="stat-label">Test Specificity</div>
          </div>
        </div>

        <!-- Jury vs Best Model comparison -->
        <section class="section">
          <h3>Jury vs Best Individual</h3>
          <div ref="juryComparisonEl" class="plotly-chart"></div>
        </section>

        <!-- Concordance + Confusion matrices -->
        <div class="chart-row">
          <section class="section chart-half" v-if="juryData.sample_predictions?.length || juryData.confusion_train">
            <h3>Classification Concordance</h3>
            <div ref="juryConcordanceEl" class="plotly-chart"></div>
          </section>
          <div class="chart-half jury-cm-stack">
            <section class="section" v-if="juryData.confusion_train">
              <h3>Confusion Matrix (Train)</h3>
              <div ref="juryConfusionTrainEl" class="plotly-chart"></div>
            </section>
            <section class="section" v-if="juryData.confusion_test">
              <h3>Confusion Matrix (Test)</h3>
              <div ref="juryConfusionTestEl" class="plotly-chart"></div>
            </section>
          </div>
        </div>

        <!-- Vote Matrix Heatmap -->
        <section class="section" v-if="juryData.vote_matrix">
          <h3>Vote Matrix ({{ juryData.vote_matrix.sample_names?.length }} samples × {{ juryData.vote_matrix.n_experts }} experts)</h3>
          <div ref="voteMatrixEl" class="plotly-chart plotly-chart-tall"></div>
        </section>

        <!-- Per-sample predictions visual (paginated, ordered by error rate) -->
        <section class="section" v-if="juryData.sample_predictions?.length > 0">
          <h3>Sample Predictions ({{ juryData.sample_predictions.length }} samples — sorted by error rate)</h3>
          <div ref="samplePredictionsEl" class="plotly-chart"></div>
          <div class="pagination" v-if="juryData.sample_predictions.length > samplePredPageSize">
            <button @click="changeSamplePredPage(samplePredPage - 1)" :disabled="samplePredPage === 0">&laquo; Prev</button>
            <span>Page {{ samplePredPage + 1 }} / {{ Math.ceil(juryData.sample_predictions.length / samplePredPageSize) }}</span>
            <button @click="changeSamplePredPage(samplePredPage + 1)" :disabled="(samplePredPage + 1) * samplePredPageSize >= juryData.sample_predictions.length">Next &raquo;</button>
          </div>
        </section>

        <!-- FBM info -->
        <section class="section" v-if="juryData.fbm">
          <h3>FBM Expert Population ({{ juryData.fbm.count }} models)</h3>
          <table class="metrics-table" style="max-width: 100%;">
            <tr>
              <td class="metric-name"></td>
              <td class="metric-value" style="font-size: 0.75rem; color: var(--text-muted);">Train</td>
              <td class="metric-value" style="font-size: 0.75rem; color: var(--text-muted);">Test</td>
            </tr>
            <tr v-for="m in ['auc', 'accuracy', 'sensitivity', 'specificity']" :key="m">
              <td class="metric-name">{{ m.charAt(0).toUpperCase() + m.slice(1) }}</td>
              <td class="metric-value">{{ juryData.fbm.train[m]?.toFixed(4) }}</td>
              <td class="metric-value">{{ juryData.fbm.test[m]?.toFixed(4) }}</td>
            </tr>
          </table>
        </section>
      </template>
      <p v-else class="info-text">
        Jury data not available. Enable "Voting" in the Parameters tab and re-run.
      </p>
    </div>

    <!-- ============================================================ -->
    <!-- COMPARATIVE SUB-TAB                                          -->
    <!-- ============================================================ -->
    <div v-if="detail && subTab === 'comparative'" class="sub-content">
      <!-- Job checkboxes -->
      <section class="section" v-if="completedJobs.length > 1">
        <h3>Select Jobs to Compare</h3>
        <div class="job-checkboxes">
          <label v-for="j in completedJobs" :key="j.job_id" class="job-check">
            <input type="checkbox" :value="j.job_id" v-model="compareJobIds" />
            <span class="job-check-label">
              {{ j.name || j.job_id.slice(0, 8) }}
              <span v-if="j.best_auc" class="job-check-auc">AUC {{ j.best_auc.toFixed(4) }}</span>
            </span>
          </label>
        </div>
      </section>

      <!-- Comparison charts -->
      <template v-if="compareData.length >= 2">
        <!-- Side-by-side metrics table -->
        <section class="section">
          <h3>Metrics Comparison</h3>
          <div class="compare-table-wrap">
            <table class="compare-table">
              <thead>
                <tr>
                  <th>Metric</th>
                  <th v-for="d in compareData" :key="d.job_id">{{ d.name || d.job_id.slice(0, 8) }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="m in ['auc', 'fit', 'accuracy', 'sensitivity', 'specificity', 'threshold', 'k', 'language', 'data_type']" :key="m">
                  <td class="metric-name">{{ m === 'data_type' ? 'Data Type' : m === 'k' ? 'k (features)' : m.charAt(0).toUpperCase() + m.slice(1) }}</td>
                  <td v-for="d in compareData" :key="d.job_id"
                    :class="{ 'best-val': compareBestMetric(m) === d.job_id }">
                    {{ formatMetricVal(d.best, m) }}
                  </td>
                </tr>
                <tr>
                  <td class="metric-name">Time</td>
                  <td v-for="d in compareData" :key="d.job_id">{{ d.execution_time ? formatDuration(d.execution_time) : '—' }}</td>
                </tr>
                <tr>
                  <td class="metric-name">Generations</td>
                  <td v-for="d in compareData" :key="d.job_id">{{ d.generation_count || '—' }}</td>
                </tr>
                <tr>
                  <td class="metric-name">Population</td>
                  <td v-for="d in compareData" :key="d.job_id">{{ d.population?.length || '—' }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <!-- Config diff -->
        <section class="section" v-if="configDiffs.length > 0">
          <h3>Configuration Differences</h3>
          <div class="compare-table-wrap">
            <table class="compare-table config-diff-table">
              <thead>
                <tr>
                  <th>Parameter</th>
                  <th v-for="d in compareData" :key="d.job_id">{{ d.name || d.job_id.slice(0, 8) }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="diff in configDiffs" :key="diff.path">
                  <td class="metric-name">{{ diff.label }}</td>
                  <td v-for="(val, i) in diff.values" :key="i" :class="{ 'diff-val': val !== diff.values[0] }">
                    {{ val ?? '—' }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <p v-if="configDiffs.length === 0" class="info-text">All selected jobs have identical configuration.</p>
        </section>

        <section class="section">
          <h3>Performance Comparison</h3>
          <div ref="comparisonBarEl" class="plotly-chart"></div>
        </section>

        <!-- Feature analysis -->
        <section class="section">
          <h3>Feature Analysis</h3>
          <div class="feature-analysis">
            <div class="feature-stat">
              <span class="fa-label">Common to all jobs:</span>
              <span class="fa-value">{{ featureIntersection.length }} features</span>
            </div>
            <div class="feature-stat">
              <span class="fa-label">Union (any job):</span>
              <span class="fa-value">{{ featureUnion.length }} features</span>
            </div>
            <div class="feature-stat" v-if="featureIntersection.length > 0">
              <span class="fa-label">Overlap ratio:</span>
              <span class="fa-value">{{ (featureIntersection.length / featureUnion.length * 100).toFixed(1) }}%</span>
            </div>
          </div>
          <div v-if="featureIntersection.length > 0" class="common-features">
            <strong>Common features:</strong>
            <span v-for="f in featureIntersection" :key="f" class="feature-chip positive">{{ featureLabel(f) }}</span>
          </div>
        </section>

        <section class="section">
          <h3>Convergence Overlay</h3>
          <div ref="comparisonConvergenceEl" class="plotly-chart"></div>
        </section>

        <section class="section">
          <h3>Feature Overlap</h3>
          <div ref="featureOverlapEl" class="plotly-chart"></div>
        </section>
      </template>

      <p v-if="completedJobs.length < 2" class="info-text">
        Run at least 2 completed jobs to enable comparative analysis.
      </p>
      <p v-else-if="compareData.length < 2" class="info-text">
        Select at least 2 jobs above to compare.
      </p>
    </div>

    <!-- ============================================================ -->
    <!-- CO-PRESENCE SUB-TAB                                         -->
    <!-- ============================================================ -->
    <div v-if="detail && subTab === 'copresence'" class="sub-content">
      <!-- Controls -->
      <div class="pop-controls">
        <div class="pop-controls-row">
          <label class="fbm-toggle">
            <input type="checkbox" v-model="copresenceFBM" />
            FBM only
            <span class="fbm-badge" v-if="copresenceFBM">{{ fbmCount }} / {{ population.length }}</span>
          </label>
          <label class="topn-control" style="margin-left: 1rem;">
            Min prevalence
            <input type="number" v-model.number="copresenceMinPrev" :min="2" :max="population.length" step="1" class="topn-input" />
            models
          </label>
          <label class="topn-control" style="margin-left: 1rem;">
            p-value &le;
            <select v-model.number="copresenceAlpha" class="topn-input" style="width: 5rem;">
              <option :value="0.2">0.20</option>
              <option :value="0.1">0.10</option>
              <option :value="0.05">0.05</option>
              <option :value="0.01">0.01</option>
            </select>
          </label>
        </div>
      </div>

      <!-- Feature prevalence in population -->
      <section class="section" v-if="copresencePopulation.length > 1">
        <h3>Feature Prevalence in Population ({{ copresencePopulation.length }} models)</h3>
        <div ref="copresencePrevalenceEl" class="plotly-chart"></div>
      </section>

      <!-- Functional annotation summary -->
      <section class="section" v-if="copresencePopulation.length > 1 && Object.keys(mspAnnotations).length > 0">
        <h3>Functional Annotations</h3>
        <p class="info-text" style="margin-bottom: 0.5rem;">
          Functional properties of features present in the population, from biobanks.gmt.bio.
        </p>
        <div ref="funcAnnotChartEl" class="plotly-chart"></div>
        <!-- Annotation table per feature -->
        <details class="advanced-toggle" style="margin-top: 0.75rem;">
          <summary>Feature annotation details ({{ funcAnnotatedFeatures.length }} annotated)</summary>
          <table class="pop-table" style="margin-top: 0.5rem;">
            <thead>
              <tr>
                <th>Feature</th>
                <th>Taxonomy</th>
                <th>Butyrate</th>
                <th>Inflammation</th>
                <th>Transit</th>
                <th>Oral</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="f in funcAnnotatedFeatures" :key="f.name">
                <td>{{ f.name }}</td>
                <td style="font-style: italic; font-size: 0.78rem;">{{ f.species }}</td>
                <td><span v-if="f.butyrate === 1" class="func-badge func-positive">Producer</span></td>
                <td>
                  <span v-if="f.inflammation === 1" class="func-badge func-negative">Enriched</span>
                  <span v-else-if="f.inflammation === -1" class="func-badge func-positive">Depleted</span>
                </td>
                <td>
                  <span v-if="f.transit === 1" class="func-badge func-neutral">Fast</span>
                  <span v-else-if="f.transit === -1" class="func-badge func-neutral">Slow</span>
                </td>
                <td><span v-if="f.oralisation === 1" class="func-badge func-warn">Oral</span></td>
              </tr>
            </tbody>
          </table>
        </details>
      </section>

      <!-- Co-occurrence heatmap -->
      <section class="section" v-if="copresencePopulation.length > 1">
        <h3>Feature Co-occurrence Matrix</h3>
        <p class="info-text" style="margin-bottom: 0.5rem;">
          Ratio of observed to expected co-occurrence. Higher values (yellow) indicate features that co-occur more often than expected;
          lower values (purple) indicate mutual exclusion.
        </p>
        <div ref="copresenceHeatmapEl" class="plotly-chart"></div>
      </section>

      <!-- Co-occurrence network -->
      <section class="section" v-if="copresencePopulation.length > 1">
        <div class="network-header">
          <h3>Co-occurrence Network</h3>
          <div class="layout-selector">
            <label v-for="opt in networkLayoutOptions" :key="opt.value" class="layout-option" :class="{ active: networkLayout === opt.value }">
              <input type="radio" :value="opt.value" v-model="networkLayout" />
              {{ opt.label }}
            </label>
          </div>
        </div>
        <p class="info-text" style="margin-bottom: 0.5rem;">
          Nodes sized by prevalence. Edges connect features that co-occur significantly more (green)
          or less (red dashed) than expected. Edge width = strength of association.
        </p>
        <div ref="copresenceNetworkEl" class="plotly-chart"></div>
      </section>

      <!-- Co-occurrence statistics table -->
      <section class="section" v-if="copresenceStats.length > 0">
        <h3>Significant Co-occurrence Pairs ({{ copresenceStats.length }})</h3>
        <table class="pop-table">
          <thead>
            <tr>
              <th>Feature 1</th>
              <th>Feature 2</th>
              <th>Observed</th>
              <th>Expected</th>
              <th>Ratio</th>
              <th>p-value</th>
              <th>Type</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, ri) in copresenceStatsPaginated" :key="ri">
              <td>{{ featureLabel(row.f1) }}</td>
              <td>{{ featureLabel(row.f2) }}</td>
              <td>{{ row.observed }}</td>
              <td>{{ row.expected.toFixed(1) }}</td>
              <td :style="{ color: row.ratio > 1 ? 'var(--positive, #98c379)' : 'var(--negative, #e06c75)' }">
                {{ row.ratio === Infinity ? '∞' : row.ratio.toFixed(2) }}
              </td>
              <td>{{ row.pvalue < 0.001 ? row.pvalue.toExponential(1) : row.pvalue.toFixed(3) }}</td>
              <td>
                <span class="cooccur-type" :class="row.type">{{ row.type === 'positive' ? 'Co-occur' : 'Exclude' }}</span>
              </td>
            </tr>
          </tbody>
        </table>
        <div class="pagination" v-if="copresenceStats.length > copresencePageSize">
          <button @click="copresencePage = Math.max(0, copresencePage - 1)" :disabled="copresencePage === 0">&laquo; Prev</button>
          <span>Page {{ copresencePage + 1 }} / {{ Math.ceil(copresenceStats.length / copresencePageSize) }}</span>
          <button @click="copresencePage++" :disabled="(copresencePage + 1) * copresencePageSize >= copresenceStats.length">Next &raquo;</button>
        </div>
      </section>

      <p v-if="population.length < 2" class="info-text">
        Co-presence analysis requires at least 2 models in the population.
      </p>
    </div>

    <!-- Empty states -->
    <div v-if="!detail && jobs.length === 0" class="empty">
      No analysis jobs yet. Go to Data &amp; Run to launch an analysis.
    </div>
    <div v-if="!detail && jobs.length > 0 && !loading" class="empty">
      Select a completed job above to view results.
    </div>
    <div v-if="loading" class="loading">Loading results...</div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { useProjectStore } from '../stores/project'
import { useChartTheme } from '../composables/useChartTheme'
import axios from 'axios'
// Lazy-load Plotly for better initial page load
let Plotly = null
async function ensurePlotly() {
  if (!Plotly) {
    const mod = await import('plotly.js-dist-min')
    Plotly = mod.default
  }
  return Plotly
}

const route = useRoute()
const store = useProjectStore()
const { themeStore, chartColors, chartLayout, featureLabel: _featureLabel, FUNC_PROPS } = useChartTheme()

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
const loading = ref(false)
const detail = ref(null)
const fullResults = ref(null)
const population = ref([])
const generationTracking = ref([])
const mspAnnotations = ref({})
const subTab = ref('summary')
const selectedJobId = ref('')
const expandedRank = ref(null)
const popPage = ref(0)
const popPageSize = 10
const topNModels = ref(50)

// Jury & importance state
const juryData = ref(null)
const importanceData = ref(null)

// Population filter state (P2.2 + P2.3)
const selectedLanguages = ref([])
const selectedDataTypes = ref([])
const fbmEnabled = ref(false)

// Comparative state
const compareJobIds = ref([])
const compareData = ref([])

// Job table state: sort, search, pagination
const jobSortKey = ref('created_at')
const jobSortAsc = ref(false)
const jobSearch = ref('')
const jobPage = ref(0)
const jobPageSize = 10

// Duplicate detection state
const duplicateGroups = ref([])
const duplicatesLoading = ref(false)

// Export menu state
const exportMenuOpen = ref(false)

// Chart element refs — Summary
const convergenceChartEl = ref(null)
const featureCountChartEl = ref(null)
const fitEvolutionChartEl = ref(null)
// Best Model
const radarChartEl = ref(null)
const coefficientsChartEl = ref(null)
const importanceChartEl = ref(null)
const directionChartEl = ref(null)
const waterfallChartEl = ref(null)
const contributionHeatmapEl = ref(null)
const contributionData = ref(null)
const contributionLoading = ref(false)
// Population
const featureHeatmapEl = ref(null)
const featurePrevalenceEl = ref(null)
const popMetricsEl = ref(null)
const compositionChartEl = ref(null)
const metricsByTypeEl = ref(null)
// Jury
const juryComparisonEl = ref(null)
const juryConcordanceEl = ref(null)
const juryConfusionTrainEl = ref(null)
const juryConfusionTestEl = ref(null)
const samplePredictionsEl = ref(null)
const samplePredPage = ref(0)
const samplePredPageSize = 20
const voteMatrixEl = ref(null)
// Comparative
const comparisonBarEl = ref(null)
const comparisonConvergenceEl = ref(null)
const featureOverlapEl = ref(null)
// Co-presence
const copresencePrevalenceEl = ref(null)
const copresenceHeatmapEl = ref(null)
const copresenceNetworkEl = ref(null)
const copresenceFBM = ref(true)
const copresenceMinPrev = ref(2)
const copresenceAlpha = ref(0.1)
const funcAnnotChartEl = ref(null)
const copresencePage = ref(0)
const copresencePageSize = 20
const networkLayout = ref('force')
const networkLayoutOptions = [
  { value: 'force', label: 'Force-directed' },
  { value: 'circle', label: 'Circle' },
  { value: 'grid', label: 'Grid' },
  { value: 'radial', label: 'Radial' },
]

// ---------------------------------------------------------------------------
// Computed
// ---------------------------------------------------------------------------
const jobs = computed(() => {
  const allJobs = store.current?.jobs || []
  return allJobs.map(j => typeof j === 'string' ? { job_id: j, status: 'unknown' } : j)
})

const selectedJobInfo = computed(() => {
  return jobs.value.find(j => j.job_id === selectedJobId.value) || null
})

const failedJobLog = ref('')

const filteredJobs = computed(() => {
  let arr = [...jobs.value]
  // Text search across name, status, language, config_summary, user_name, config_hash
  const q = jobSearch.value.trim().toLowerCase()
  if (q) {
    arr = arr.filter(j => {
      const fields = [
        j.name, j.job_id, j.status, j.language, j.config_summary,
        j.user_name, j.config_hash, j.data_type,
      ]
      return fields.some(f => f && String(f).toLowerCase().includes(q))
    })
  }
  // Sort
  const key = jobSortKey.value
  const asc = jobSortAsc.value
  arr.sort((a, b) => {
    let va = a[key], vb = b[key]
    if (va == null && vb == null) return 0
    if (va == null) return 1
    if (vb == null) return -1
    if (typeof va === 'string') va = va.toLowerCase()
    if (typeof vb === 'string') vb = vb.toLowerCase()
    if (va < vb) return asc ? -1 : 1
    if (va > vb) return asc ? 1 : -1
    return 0
  })
  return arr
})

const paginatedJobs = computed(() => {
  const start = jobPage.value * jobPageSize
  return filteredJobs.value.slice(start, start + jobPageSize)
})

// Keep backward compat: sortedJobs used in some places
const sortedJobs = filteredJobs

const completedJobs = computed(() => jobs.value.filter(j => j.status === 'completed'))

const paginatedPopulation = computed(() => {
  const start = popPage.value * popPageSize
  return filteredPopulation.value.slice(start, start + popPageSize)
})

// Available languages and data types from population
const availableLanguages = computed(() =>
  [...new Set(population.value.map(i => i.metrics?.language).filter(Boolean))].sort()
)
const availableDataTypes = computed(() =>
  [...new Set(population.value.map(i => i.metrics?.data_type).filter(Boolean))].sort()
)

// FBM filter function (P2.3)
function filterFBM(pop) {
  if (pop.length === 0) return []
  const bestFit = pop[0].metrics?.fit
  if (bestFit == null) return pop
  // Use sample count from detail if available, otherwise use population size
  const n = detail.value?.sample_count || pop.length
  const z = 1.96 // for alpha=0.05
  const se = Math.sqrt(bestFit * (1 - bestFit) / n)
  const threshold = bestFit - z * se
  return pop.filter(ind => ind.metrics?.fit >= threshold)
}

// Filtered population: language + data_type checkboxes, then optional FBM
const filteredPopulation = computed(() => {
  let pop = population.value
  if (selectedLanguages.value.length > 0) {
    pop = pop.filter(i => selectedLanguages.value.includes(i.metrics?.language))
  }
  if (selectedDataTypes.value.length > 0) {
    pop = pop.filter(i => selectedDataTypes.value.includes(i.metrics?.data_type))
  }
  if (fbmEnabled.value) {
    pop = filterFBM(pop)
  }
  return pop
})

const fbmCount = computed(() => {
  let pop = population.value
  if (selectedLanguages.value.length > 0) {
    pop = pop.filter(i => selectedLanguages.value.includes(i.metrics?.language))
  }
  if (selectedDataTypes.value.length > 0) {
    pop = pop.filter(i => selectedDataTypes.value.includes(i.metrics?.data_type))
  }
  return filterFBM(pop).length
})

// Co-presence: population to analyse (optionally FBM-filtered)
const copresencePopulation = computed(() => {
  return copresenceFBM.value ? filterFBM(population.value) : population.value
})

// Hypergeometric p-value (Fisher's exact test for co-occurrence)
// Uses log-factorial to avoid overflow: P(X=k) = C(K,k)*C(N-K,n-k)/C(N,n)
// where N=total models, K=models with feature i, n=models with feature j, k=co-occurrences
function _logFact(n) {
  let s = 0
  for (let i = 2; i <= n; i++) s += Math.log(i)
  return s
}
// Cache log-factorials up to max N
let _lfCache = [0, 0]
function logFact(n) {
  if (n < _lfCache.length) return _lfCache[n]
  let s = _lfCache[_lfCache.length - 1]
  for (let i = _lfCache.length; i <= n; i++) {
    s += Math.log(i)
    _lfCache.push(s)
  }
  return _lfCache[n]
}

function hypergeomPMF(k, N, K, n) {
  // P(X=k) = C(K,k) * C(N-K, n-k) / C(N,n)
  if (k < 0 || k > Math.min(K, n) || (n - k) > (N - K)) return 0
  return Math.exp(
    logFact(K) - logFact(k) - logFact(K - k) +
    logFact(N - K) - logFact(n - k) - logFact(N - K - n + k) -
    logFact(N) + logFact(n) + logFact(N - n)
  )
}

// p-value for positive co-occurrence: P(X >= observed)
function pvalueGreater(observed, N, ni, nj) {
  let p = 0
  const maxK = Math.min(ni, nj)
  for (let k = observed; k <= maxK; k++) p += hypergeomPMF(k, N, ni, nj)
  return Math.min(1, p)
}

// p-value for negative co-occurrence: P(X <= observed)
function pvalueLess(observed, N, ni, nj) {
  let p = 0
  for (let k = 0; k <= observed; k++) p += hypergeomPMF(k, N, ni, nj)
  return Math.min(1, p)
}

// Co-presence: compute pairwise co-occurrence statistics
const copresenceData = computed(() => {
  const pop = copresencePopulation.value
  if (pop.length < 2) return { features: [], prevalence: {}, matrix: [], pairs: [] }

  // Build feature prevalence (count of models containing each feature)
  const prevalence = {}
  for (const ind of pop) {
    for (const name of Object.keys(ind.named_features || {})) {
      prevalence[name] = (prevalence[name] || 0) + 1
    }
  }

  // Filter features by minimum prevalence
  const minPrev = copresenceMinPrev.value || 2
  const features = Object.entries(prevalence)
    .filter(([, count]) => count >= minPrev)
    .sort((a, b) => b[1] - a[1])
    .map(([name]) => name)

  if (features.length < 2) return { features, prevalence, matrix: [], pairs: [] }

  const N = pop.length
  const fSet = new Set(features)

  // Warm up log-factorial cache
  logFact(N)

  // Build binary presence per model (only for filtered features)
  const presenceByModel = pop.map(ind => {
    const s = new Set()
    for (const name of Object.keys(ind.named_features || {})) {
      if (fSet.has(name)) s.add(name)
    }
    return s
  })

  // Compute pairwise co-occurrence
  const cooccurCounts = {}
  for (let i = 0; i < features.length; i++) {
    for (let j = i + 1; j < features.length; j++) {
      let count = 0
      for (const ps of presenceByModel) {
        if (ps.has(features[i]) && ps.has(features[j])) count++
      }
      cooccurCounts[`${i},${j}`] = count
    }
  }

  // Build matrix and pairs with stats using hypergeometric test
  const matrix = features.map(() => features.map(() => 1))
  const pairs = []
  const alpha = copresenceAlpha.value

  for (let i = 0; i < features.length; i++) {
    for (let j = i + 1; j < features.length; j++) {
      const ni = prevalence[features[i]]
      const nj = prevalence[features[j]]
      const observed = cooccurCounts[`${i},${j}`]
      const expected = (ni * nj) / N

      // Ratio of observed to expected
      const ratio = expected > 0 ? observed / expected : (observed > 0 ? Infinity : 1)

      matrix[i][j] = ratio
      matrix[j][i] = ratio

      // Hypergeometric test (same as R cooccur package)
      const pGt = pvalueGreater(observed, N, ni, nj)  // positive co-occurrence
      const pLt = pvalueLess(observed, N, ni, nj)      // negative (exclusion)
      const pval = Math.min(pGt, pLt)
      const type = pGt < pLt ? 'positive' : 'negative'

      if (pval <= alpha) {
        pairs.push({
          f1: features[i],
          f2: features[j],
          observed,
          expected,
          ratio,
          pvalue: pval,
          type,
          strength: -Math.log10(Math.max(pval, 1e-300)),
        })
      }
    }
    matrix[i][i] = prevalence[features[i]] / N // diagonal = self-prevalence
  }

  // Sort pairs by strength descending
  pairs.sort((a, b) => b.strength - a.strength)

  return { features, prevalence, matrix, pairs }
})

const copresenceStats = computed(() => copresenceData.value.pairs)
const copresenceStatsPaginated = computed(() => {
  const start = copresencePage.value * copresencePageSize
  return copresenceStats.value.slice(start, start + copresencePageSize)
})

// Functional annotations for features in the population
const funcAnnotatedFeatures = computed(() => {
  const { features, prevalence } = copresenceData.value
  const ann = mspAnnotations.value
  if (!features.length || !Object.keys(ann).length) return []
  return features
    .filter(f => ann[f] && ann[f].species)
    .sort((a, b) => (prevalence[b] || 0) - (prevalence[a] || 0))
    .map(f => ({
      name: f,
      species: ann[f].species || '',
      butyrate: ann[f].butyrate ?? 0,
      inflammation: ann[f].inflammation ?? 0,
      transit: ann[f].transit ?? 0,
      oralisation: ann[f].oralisation ?? 0,
      prevalence: prevalence[f] || 0,
    }))
})

// Comparative: feature intersection/union
const featureIntersection = computed(() => {
  if (compareData.value.length < 2) return []
  const sets = compareData.value.map(d => {
    const feats = d.best_individual?.features || d.best?.features || {}
    const names = d.feature_names || []
    return new Set(Object.keys(feats).map(idx => names[parseInt(idx)] || `f_${idx}`))
  })
  let common = sets[0]
  for (let i = 1; i < sets.length; i++) {
    common = new Set([...common].filter(f => sets[i].has(f)))
  }
  return [...common].sort()
})

const featureUnion = computed(() => {
  if (compareData.value.length < 2) return []
  const all = new Set()
  for (const d of compareData.value) {
    const feats = d.best_individual?.features || d.best?.features || {}
    const names = d.feature_names || []
    for (const idx of Object.keys(feats)) {
      all.add(names[parseInt(idx)] || `f_${idx}`)
    }
  }
  return [...all].sort()
})

// Config diff: find parameters that differ across selected jobs
const configDiffs = computed(() => {
  if (compareData.value.length < 2) return []
  // We need job configs. Fetch from job summaries.
  const jobConfigs = compareData.value.map(d => {
    const meta = jobs.value.find(j => j.job_id === d.job_id || j.job_id === d.jobId) || {}
    return meta
  })
  // Compare numeric/string fields from summaries
  const fields = [
    { key: 'language', label: 'Language' },
    { key: 'data_type', label: 'Data Type' },
    { key: 'population_size', label: 'Population Size' },
    { key: 'config_summary', label: 'Config' },
  ]
  const diffs = []
  for (const f of fields) {
    const vals = jobConfigs.map(jc => jc[f.key] ?? null)
    const unique = new Set(vals.map(String))
    if (unique.size > 1) {
      diffs.push({ path: f.key, label: f.label, values: vals })
    }
  }
  return diffs
})

function compareBestMetric(metric) {
  if (compareData.value.length < 2) return null
  const numericMetrics = ['auc', 'fit', 'accuracy', 'sensitivity', 'specificity']
  if (!numericMetrics.includes(metric)) return null
  let bestId = null, bestVal = -Infinity
  for (const d of compareData.value) {
    const v = d.best?.[metric] ?? d.best_individual?.[metric]
    if (v != null && v > bestVal) { bestVal = v; bestId = d.job_id || d.jobId }
  }
  return bestId
}

function formatMetricVal(best, metric) {
  if (!best) return '—'
  const v = best[metric]
  if (v == null) return '—'
  if (typeof v === 'number') return v.toFixed(4)
  return String(v)
}

const bestMetrics = computed(() => {
  if (!detail.value?.best_individual) return {}
  const b = detail.value.best_individual
  return {
    AUC: b.auc,
    Fit: b.fit,
    Accuracy: b.accuracy,
    Sensitivity: b.sensitivity,
    Specificity: b.specificity,
    Threshold: b.threshold,
    Language: b.language,
    'Data Type': b.data_type,
    Epoch: b.epoch,
  }
})

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function featureName(idx) {
  if (detail.value?.feature_names?.length > idx) return detail.value.feature_names[idx]
  return `feature_${idx}`
}

function featureLabel(name) {
  return _featureLabel(name, mspAnnotations.value)
}

function toggleExpand(rank) {
  expandedRank.value = expandedRank.value === rank ? null : rank
}

// ---------------------------------------------------------------------------
// MSP Annotations
// ---------------------------------------------------------------------------
async function loadMspAnnotations() {
  // Collect features actually used in population models + best individual,
  // not the entire feature_names array (which can be 2000+ and was causing a 500 cap miss)
  const used = new Set()
  for (const ind of population.value) {
    for (const name of Object.keys(ind.named_features || {})) {
      if (name.startsWith('msp_')) used.add(name)
    }
  }
  const best = detail.value?.best_individual?.features || {}
  const featureNames = detail.value?.feature_names || []
  for (const idx of Object.keys(best)) {
    const name = featureNames[parseInt(idx)]
    if (name?.startsWith('msp_')) used.add(name)
  }
  const names = [...used]
  if (names.length === 0) return
  try {
    const { data } = await axios.post('/api/data-explore/msp-annotations', { features: names })
    mspAnnotations.value = data.annotations || {}
  } catch (e) {
    console.error('Failed to load MSP annotations:', e)
  }
}

// ---------------------------------------------------------------------------
// SUMMARY CHARTS
// ---------------------------------------------------------------------------
async function renderConvergenceChart() {
  await nextTick()
  if (!convergenceChartEl.value || generationTracking.value.length === 0) return

  const c = chartColors()
  const gens = generationTracking.value.map(g => g.generation)
  const trainAuc = generationTracking.value.map(g => g.best_auc)
  const hasTest = generationTracking.value.some(g => g.best_auc_test != null)
  const testAuc = hasTest ? generationTracking.value.map(g => g.best_auc_test) : null

  const traces = [{
    x: gens, y: trainAuc, name: 'Train AUC', type: 'scatter', mode: 'lines+markers',
    line: { color: c.class0, width: 2 }, marker: { size: 4 },
  }]
  if (testAuc) {
    traces.push({
      x: gens, y: testAuc, name: 'Test AUC', type: 'scatter', mode: 'lines+markers',
      line: { color: c.danger, width: 2, dash: 'dash' }, marker: { size: 4 },
    })
  }

  const allValues = [...trainAuc, ...(testAuc || [])]
  Plotly.newPlot(convergenceChartEl.value, traces, chartLayout({
    xaxis: { title: { text: 'Generation', font: { color: c.text } }, dtick: Math.max(1, Math.floor(gens.length / 10)), gridcolor: c.grid, color: c.text },
    yaxis: { title: { text: 'AUC', font: { color: c.text } }, range: [Math.max(0, Math.min(...allValues) - 0.05), Math.min(1, Math.max(...allValues) + 0.02)], gridcolor: c.grid, color: c.text },
    legend: { orientation: 'h', y: 1.12, font: { color: c.text } },
    height: 280,
    margin: { t: 20, b: 50, l: 60, r: 20 },
  }), { responsive: true, displayModeBar: false })
}

async function renderFeatureCountChart() {
  await nextTick()
  if (!featureCountChartEl.value || generationTracking.value.length === 0) return

  const c = chartColors()
  const gens = generationTracking.value.map(g => g.generation)
  const ks = generationTracking.value.map(g => g.best_k)

  Plotly.newPlot(featureCountChartEl.value, [{
    x: gens, y: ks, type: 'scatter', mode: 'lines+markers',
    line: { color: c.accent, width: 2 }, marker: { size: 4 },
    name: 'k (features)',
  }], chartLayout({
    xaxis: { title: { text: 'Generation', font: { color: c.text } }, dtick: Math.max(1, Math.floor(gens.length / 10)), gridcolor: c.grid, color: c.text },
    yaxis: { title: { text: 'k', font: { color: c.text } }, gridcolor: c.grid, color: c.text, dtick: 1 },
    height: 240,
    margin: { t: 10, b: 50, l: 50, r: 20 },
    showlegend: false,
  }), { responsive: true, displayModeBar: false })
}

async function renderFitEvolutionChart() {
  await nextTick()
  if (!fitEvolutionChartEl.value || generationTracking.value.length === 0) return

  const c = chartColors()
  const gens = generationTracking.value.map(g => g.generation)
  const fits = generationTracking.value.map(g => g.best_fit)
  const aucs = generationTracking.value.map(g => g.best_auc)

  Plotly.newPlot(fitEvolutionChartEl.value, [
    { x: gens, y: aucs, name: 'AUC', type: 'scatter', mode: 'lines', line: { color: c.class0, width: 2 } },
    { x: gens, y: fits, name: 'Fit', type: 'scatter', mode: 'lines', line: { color: c.warn, width: 2, dash: 'dot' } },
  ], chartLayout({
    xaxis: { title: { text: 'Generation', font: { color: c.text } }, dtick: Math.max(1, Math.floor(gens.length / 10)), gridcolor: c.grid, color: c.text },
    yaxis: { title: { text: 'Value', font: { color: c.text } }, gridcolor: c.grid, color: c.text },
    legend: { orientation: 'h', y: 1.12, font: { color: c.text } },
    height: 240,
    margin: { t: 10, b: 50, l: 50, r: 20 },
  }), { responsive: true, displayModeBar: false })
}

function renderSummaryCharts() {
  renderConvergenceChart()
  renderFeatureCountChart()
  renderFitEvolutionChart()
}

// ---------------------------------------------------------------------------
// BEST MODEL CHARTS
// ---------------------------------------------------------------------------
async function renderCoefficientsChart() {
  await nextTick()
  if (!coefficientsChartEl.value || !detail.value?.best_individual) return

  const c = chartColors()
  const b = detail.value.best_individual
  const entries = Object.entries(b.features).map(([idx, coef]) => ({
    name: featureLabel(featureName(parseInt(idx))),
    coef: parseInt(coef),
  }))
  // Sort by coefficient, then by name
  entries.sort((a, bb) => bb.coef - a.coef || a.name.localeCompare(bb.name))

  const colors = entries.map(e => e.coef > 0 ? c.positiveAlpha : c.negativeAlpha)
  const borderColors = entries.map(e => e.coef > 0 ? c.positive : c.negative)

  Plotly.newPlot(coefficientsChartEl.value, [{
    type: 'bar',
    orientation: 'h',
    y: entries.map(e => e.name),
    x: entries.map(e => e.coef),
    marker: { color: colors, line: { color: borderColors, width: 1.5 } },
    hovertemplate: '%{y}: %{x}<extra></extra>',
  }], chartLayout({
    xaxis: {
      title: { text: 'Coefficient', font: { color: c.text } },
      gridcolor: c.grid, color: c.text,
      zeroline: true, zerolinecolor: c.text, zerolinewidth: 1,
      dtick: 1,
    },
    yaxis: { automargin: true, color: c.text },
    height: Math.max(250, entries.length * 30 + 60),
    margin: { t: 10, b: 50, l: 180, r: 20 },
    showlegend: false,
    annotations: [{
      text: `${b.language} | ${b.data_type} | k=${b.k}`,
      xref: 'paper', yref: 'paper', x: 1, y: 1.06,
      showarrow: false, font: { color: c.text, size: 11 },
    }],
  }), { responsive: true, displayModeBar: false })
}

async function renderRadarChart() {
  await nextTick()
  if (!radarChartEl.value || !detail.value?.best_individual) return

  const c = chartColors()
  const b = detail.value.best_individual
  const categories = ['AUC', 'Accuracy', 'Sensitivity', 'Specificity']
  const values = [b.auc, b.accuracy, b.sensitivity, b.specificity]

  Plotly.newPlot(radarChartEl.value, [{
    type: 'scatterpolar',
    r: [...values, values[0]],
    theta: [...categories, categories[0]],
    fill: 'toself',
    fillcolor: c.class0Alpha,
    line: { color: c.class0, width: 2 },
    marker: { size: 5, color: c.class0 },
    name: 'Best Model',
  }], {
    polar: {
      radialaxis: { visible: true, range: [0, 1], color: c.text, gridcolor: c.grid },
      angularaxis: { color: c.text },
      bgcolor: c.paper,
    },
    font: { family: 'system-ui, sans-serif', size: 12, color: c.text },
    paper_bgcolor: c.paper,
    showlegend: false,
    height: 280,
    margin: { t: 30, b: 30, l: 60, r: 60 },
  }, { responsive: true, displayModeBar: false })
}

async function renderImportanceChart() {
  await nextTick()
  if (!importanceChartEl.value || !importanceData.value?.length) return

  const c = chartColors()
  const items = [...importanceData.value].sort((a, b) => Math.abs(a.importance) - Math.abs(b.importance))

  Plotly.newPlot(importanceChartEl.value, [{
    type: 'bar',
    orientation: 'h',
    y: items.map(i => featureLabel(i.feature)),
    x: items.map(i => i.importance),
    marker: {
      color: items.map(i => i.importance >= 0 ? c.positiveAlpha : c.negativeAlpha),
      line: { color: items.map(i => i.importance >= 0 ? c.positive : c.negative), width: 1.5 },
    },
    hovertemplate: '%{y}: %{x:.4f}<extra></extra>',
  }], chartLayout({
    xaxis: { title: { text: 'Importance (MDA)', font: { color: c.text } }, gridcolor: c.grid, color: c.text },
    yaxis: { automargin: true, color: c.text },
    height: Math.max(250, items.length * 25 + 60),
    margin: { t: 10, b: 50, l: 180, r: 20 },
    showlegend: false,
  }), { responsive: true, displayModeBar: false })
}

async function renderDirectionChart() {
  await nextTick()
  if (!directionChartEl.value || !detail.value?.best_individual) return
  const c = chartColors()
  const b = detail.value.best_individual
  const entries = Object.entries(b.features).map(([idx, coef]) => ({
    name: featureLabel(featureName(parseInt(idx))),
    coef: parseFloat(coef),
  }))
  entries.sort((a, bb) => a.coef - bb.coef)

  const posEntries = entries.filter(e => e.coef > 0)
  const negEntries = entries.filter(e => e.coef <= 0)
  const traces = []
  if (negEntries.length) {
    traces.push({
      type: 'bar', orientation: 'h', name: 'Negative',
      y: negEntries.map(e => e.name), x: negEntries.map(e => e.coef),
      marker: { color: c.negativeAlpha, line: { color: c.negative, width: 1.5 } },
      hovertemplate: '%{y}: %{x}<extra></extra>',
    })
  }
  if (posEntries.length) {
    traces.push({
      type: 'bar', orientation: 'h', name: 'Positive',
      y: posEntries.map(e => e.name), x: posEntries.map(e => e.coef),
      marker: { color: c.positiveAlpha, line: { color: c.positive, width: 1.5 } },
      hovertemplate: '%{y}: %{x}<extra></extra>',
    })
  }
  Plotly.newPlot(directionChartEl.value, traces, chartLayout({
    xaxis: { title: { text: 'Coefficient', font: { color: c.text } }, gridcolor: c.grid, color: c.text, zeroline: true, zerolinecolor: c.text, zerolinewidth: 1 },
    yaxis: { automargin: true, color: c.text },
    height: Math.max(250, entries.length * 28 + 60),
    margin: { t: 10, b: 50, l: 180, r: 20 },
    barmode: 'relative',
    showlegend: true,
    legend: { orientation: 'h', y: 1.08, font: { color: c.text } },
  }), { responsive: true, displayModeBar: false })
}

async function renderWaterfallChart() {
  await nextTick()
  if (!waterfallChartEl.value || !detail.value?.best_individual) return
  const c = chartColors()
  const b = detail.value.best_individual
  const entries = Object.entries(b.features).map(([idx, coef]) => ({
    name: featureLabel(featureName(parseInt(idx))),
    coef: parseFloat(coef),
  }))
  entries.sort((a, bb) => Math.abs(bb.coef) - Math.abs(a.coef))

  Plotly.newPlot(waterfallChartEl.value, [{
    type: 'waterfall', orientation: 'v',
    x: [...entries.map(e => e.name), 'Total'],
    y: [...entries.map(e => e.coef), null],
    measure: [...entries.map(() => 'relative'), 'total'],
    connector: { line: { color: c.grid, width: 1 } },
    increasing: { marker: { color: c.positiveAlpha, line: { color: c.positive, width: 1.5 } } },
    decreasing: { marker: { color: c.negativeAlpha, line: { color: c.negative, width: 1.5 } } },
    totals: { marker: { color: c.accent + '66', line: { color: c.accent, width: 1.5 } } },
    hovertemplate: '%{x}: %{y}<extra></extra>',
  }], chartLayout({
    xaxis: { color: c.text, tickangle: -45 },
    yaxis: { title: { text: 'Cumulative Contribution', font: { color: c.text } }, gridcolor: c.grid, color: c.text },
    height: 350,
    margin: { t: 20, b: 120, l: 60, r: 20 },
    showlegend: false,
  }), { responsive: true, displayModeBar: false })
}

async function loadContributionHeatmap() {
  if (!detail.value?.best_individual) return
  contributionLoading.value = true
  try {
    const pid = route.params.id
    const b = detail.value.best_individual
    const featureNames = Object.entries(b.features).map(([idx]) => featureName(parseInt(idx)))
    const { data } = await axios.get(`/api/data-explore/${pid}/barcode-data`, {
      params: { features: featureNames.join(','), max_samples: 200 }
    })
    // Compute contribution matrix: coefficient × feature_value
    const coeffMap = {}
    for (const [idx, coef] of Object.entries(b.features)) {
      coeffMap[featureName(parseInt(idx))] = parseFloat(coef)
    }
    const features = data.features || []
    const samples = data.sample_names || []
    const matrix = (data.matrix || []).map((row, fi) =>
      row.map(val => val * (coeffMap[features[fi]] || 0))
    )
    contributionData.value = { features, samples, matrix }
    await nextTick()
    renderContributionHeatmap()
  } catch (e) {
    console.error('Failed to load contribution data:', e)
  } finally {
    contributionLoading.value = false
  }
}

async function renderContributionHeatmap() {
  await nextTick()
  if (!contributionHeatmapEl.value || !contributionData.value) return
  const c = chartColors()
  const { features, samples, matrix } = contributionData.value
  Plotly.newPlot(contributionHeatmapEl.value, [{
    type: 'heatmap',
    z: matrix,
    x: samples,
    y: features.map(f => featureLabel(f)),
    colorscale: [[0, '#2166ac'], [0.5, '#f7f7f7'], [1, '#b2182b']],
    zmid: 0,
    hovertemplate: 'Sample: %{x}<br>Feature: %{y}<br>Contribution: %{z:.4f}<extra></extra>',
  }], chartLayout({
    xaxis: { color: c.text, showticklabels: samples.length <= 100, tickangle: -90, tickfont: { size: 8 } },
    yaxis: { automargin: true, color: c.text },
    height: Math.max(300, features.length * 25 + 100),
    margin: { t: 10, b: 80, l: 180, r: 20 },
  }), { responsive: true, displayModeBar: false })
}

function renderBestModelCharts() {
  renderCoefficientsChart()
  renderRadarChart()
  renderImportanceChart()
  renderDirectionChart()
  renderWaterfallChart()
  if (contributionData.value) renderContributionHeatmap()
}

// ---------------------------------------------------------------------------
// POPULATION CHARTS
// ---------------------------------------------------------------------------

/** Build feature-model matrix from top N filtered population individuals */
function buildFeatureModelMatrix() {
  const topN = Math.min(topNModels.value, filteredPopulation.value.length)
  const models = filteredPopulation.value.slice(0, topN)

  // Count feature occurrences and directions
  const featureInfo = {}
  for (const ind of models) {
    for (const [name, coef] of Object.entries(ind.named_features || {})) {
      if (!featureInfo[name]) featureInfo[name] = { count: 0, pos: 0, neg: 0 }
      featureInfo[name].count++
      if (coef > 0) featureInfo[name].pos++
      else featureInfo[name].neg++
    }
  }

  // Sort features by prevalence (most common at top of chart = last in array for Plotly)
  const sortedFeatures = Object.entries(featureInfo)
    .sort((a, b) => a[1].count - b[1].count)
    .map(([name]) => name)

  // Build matrix — also sort models so same-language models cluster
  const sortedModels = [...models].sort((a, b) => {
    const la = a.metrics?.language || '', lb = b.metrics?.language || ''
    if (la !== lb) return la.localeCompare(lb)
    const da = a.metrics?.data_type || '', db = b.metrics?.data_type || ''
    return da.localeCompare(db)
  })

  const matrix = sortedFeatures.map(fname =>
    sortedModels.map(ind => (ind.named_features || {})[fname] || 0)
  )

  return { sortedFeatures, matrix, featureInfo, topN }
}

async function renderCompositionChart() {
  await nextTick()
  if (!compositionChartEl.value || filteredPopulation.value.length === 0) return

  const c = chartColors()
  const counts = {}
  for (const ind of filteredPopulation.value) {
    const lang = ind.metrics?.language || 'unknown'
    const dt = ind.metrics?.data_type || 'unknown'
    const key = `${lang}|${dt}`
    counts[key] = (counts[key] || 0) + 1
  }

  // Group by language, bars per data_type
  const languages = [...new Set(filteredPopulation.value.map(i => i.metrics?.language || 'unknown'))].sort()
  const dataTypes = [...new Set(filteredPopulation.value.map(i => i.metrics?.data_type || 'unknown'))].sort()
  const dtColors = [c.class0Light, c.class1Light, c.accent, c.warn, '#008080']

  const traces = dataTypes.map((dt, i) => ({
    type: 'bar',
    name: dt,
    x: languages,
    y: languages.map(lang => counts[`${lang}|${dt}`] || 0),
    marker: { color: dtColors[i % dtColors.length] },
  }))

  Plotly.newPlot(compositionChartEl.value, traces, chartLayout({
    barmode: 'group',
    xaxis: { title: { text: 'Language', font: { color: c.text } }, color: c.text },
    yaxis: { title: { text: 'Count', font: { color: c.text } }, gridcolor: c.grid, color: c.text },
    legend: { orientation: 'h', y: 1.12, font: { color: c.text } },
    height: 300,
    margin: { t: 30, b: 50, l: 60, r: 20 },
  }), { responsive: true, displayModeBar: false })
}

async function renderMetricsByType() {
  await nextTick()
  if (!metricsByTypeEl.value || filteredPopulation.value.length === 0) return

  const c = chartColors()
  // Group AUC by language
  const byLang = {}
  for (const ind of filteredPopulation.value) {
    const lang = ind.metrics?.language || 'unknown'
    if (!byLang[lang]) byLang[lang] = []
    if (ind.metrics?.auc != null) byLang[lang].push(ind.metrics.auc)
  }

  const languages = Object.keys(byLang).sort()
  const langColors = [c.class0Light, c.class1Light, c.accent, c.warn, '#008080', c.dimmed]

  const traces = languages.map((lang, i) => ({
    type: 'violin',
    y: byLang[lang],
    name: lang,
    line: { color: langColors[i % langColors.length] },
    fillcolor: langColors[i % langColors.length] + '33',
    points: 'all',
    pointpos: 0,
    jitter: 0.3,
    marker: { color: langColors[i % langColors.length], size: 3, opacity: 0.6 },
    meanline: { visible: true },
    box: { visible: false },
  }))

  Plotly.newPlot(metricsByTypeEl.value, traces, chartLayout({
    yaxis: { title: { text: 'AUC', font: { color: c.text } }, range: [0, 1.05], gridcolor: c.grid, color: c.text },
    xaxis: { color: c.text },
    height: 300,
    margin: { t: 20, b: 50, l: 50, r: 20 },
    showlegend: false,
  }), { responsive: true, displayModeBar: false })
}

async function renderFeatureHeatmap() {
  await nextTick()
  if (!featureHeatmapEl.value || filteredPopulation.value.length === 0) return

  const c = chartColors()
  const { sortedFeatures, matrix, featureInfo, topN } = buildFeatureModelMatrix()

  if (sortedFeatures.length === 0) return

  // predomicspkg heatmap gradient: deepskyblue1 → white → firebrick1 (with transparency)
  const colorscale = [
    [0, 'rgba(0, 191, 255, 0.55)'],     // deepskyblue1 transparent
    [0.5, c.paper],
    [1, 'rgba(255, 48, 48, 0.55)'],      // firebrick1 transparent
  ]

  // Prevalence annotations on right
  const annotations = sortedFeatures.map((name, i) => ({
    text: `${((featureInfo[name].count / topN) * 100).toFixed(0)}%`,
    x: topN + 0.5,
    y: i,
    xref: 'x', yref: 'y',
    showarrow: false,
    font: { color: c.dimmed, size: 9 },
  }))

  Plotly.newPlot(featureHeatmapEl.value, [{
    type: 'heatmap',
    z: matrix,
    x: Array.from({ length: topN }, (_, i) => i + 1),
    y: sortedFeatures.map(n => featureLabel(n)),
    colorscale,
    zmin: -1, zmax: 1,
    showscale: true,
    colorbar: {
      title: { text: 'Coeff', font: { color: c.text, size: 10 } },
      tickvals: [-1, 0, 1], ticktext: ['-1', '0', '+1'],
      tickfont: { color: c.text, size: 9 },
      len: 0.5, thickness: 12,
    },
    xgap: 0.5,
    ygap: 0.5,
    hovertemplate: 'Feature: %{y}<br>Model #%{x}<br>Coeff: %{z}<extra></extra>',
  }], chartLayout({
    xaxis: { title: { text: 'Model Rank', font: { color: c.text } }, gridcolor: c.grid, color: c.text },
    yaxis: { automargin: true, color: c.text },
    height: Math.max(300, sortedFeatures.length * 18 + 80),
    margin: { t: 20, b: 50, l: 180, r: 60 },
    annotations,
  }), { responsive: true, displayModeBar: true })
}

async function renderFeaturePrevalence() {
  await nextTick()
  if (!featurePrevalenceEl.value || filteredPopulation.value.length === 0) return

  const c = chartColors()
  const { sortedFeatures, featureInfo } = buildFeatureModelMatrix()

  // sortedFeatures: ascending by count → last = most prevalent = top of Plotly y-axis
  const features = sortedFeatures
  if (features.length === 0) return

  Plotly.newPlot(featurePrevalenceEl.value, [
    {
      type: 'bar', orientation: 'h', name: 'Positive (+1)',
      y: features.map(n => featureLabel(n)),
      x: features.map(n => featureInfo[n].pos),
      marker: { color: c.positiveAlpha, line: { color: c.positive, width: 1 } },
    },
    {
      type: 'bar', orientation: 'h', name: 'Negative (-1)',
      y: features.map(n => featureLabel(n)),
      x: features.map(n => featureInfo[n].neg),
      marker: { color: c.negativeAlpha, line: { color: c.negative, width: 1 } },
    },
  ], chartLayout({
    barmode: 'stack',
    xaxis: { title: { text: 'Count (models)', font: { color: c.text } }, gridcolor: c.grid, color: c.text },
    yaxis: { automargin: true, color: c.text },
    height: Math.max(300, features.length * 18 + 80),
    margin: { t: 20, b: 50, l: 180, r: 20 },
    legend: { orientation: 'h', y: 1.08, font: { color: c.text } },
  }), { responsive: true, displayModeBar: false })
}

async function renderPopMetrics() {
  await nextTick()
  if (!popMetricsEl.value || filteredPopulation.value.length === 0) return

  const c = chartColors()
  const metricNames = ['auc', 'accuracy', 'sensitivity', 'specificity']
  const colors = [c.class0Light, c.class1Light, c.accent, c.warn]

  const traces = metricNames.map((m, i) => ({
    type: 'violin',
    y: filteredPopulation.value.map(ind => ind.metrics[m]).filter(v => v != null),
    name: m.charAt(0).toUpperCase() + m.slice(1),
    line: { color: colors[i] },
    fillcolor: colors[i] + '33',
    points: 'all',
    pointpos: 0,
    jitter: 0.3,
    marker: { color: colors[i], size: 3, opacity: 0.6 },
    meanline: { visible: true },
    box: { visible: false },
  }))

  Plotly.newPlot(popMetricsEl.value, traces, chartLayout({
    yaxis: { title: { text: 'Value', font: { color: c.text } }, range: [0, 1.05], gridcolor: c.grid, color: c.text },
    xaxis: { color: c.text },
    height: 350,
    margin: { t: 20, b: 50, l: 50, r: 20 },
    showlegend: false,
  }), { responsive: true, displayModeBar: false })
}

function renderPopulationCharts() {
  renderCompositionChart()
  renderMetricsByType()
  renderFeatureHeatmap()
  renderFeaturePrevalence()
  renderPopMetrics()
}

// ---------------------------------------------------------------------------
// JURY CHARTS
// ---------------------------------------------------------------------------
async function renderJuryComparison() {
  await nextTick()
  if (!juryComparisonEl.value || !juryData.value || !detail.value?.best_individual) return

  const c = chartColors()
  const b = detail.value.best_individual
  const j = juryData.value
  const metricNames = ['auc', 'accuracy', 'sensitivity', 'specificity']
  const labels = ['AUC', 'Accuracy', 'Sensitivity', 'Specificity']

  const traces = [
    {
      type: 'bar', name: 'Best Individual (Train)',
      x: labels, y: metricNames.map(m => b[m] ?? 0),
      marker: { color: c.class0Alpha, line: { color: c.class0, width: 1.5 } },
    },
    {
      type: 'bar', name: 'Jury (Train)',
      x: labels, y: metricNames.map(m => j.train?.[m] ?? 0),
      marker: { color: c.accentAlpha, line: { color: c.accent, width: 1.5 } },
    },
    {
      type: 'bar', name: 'Jury (Test)',
      x: labels, y: metricNames.map(m => j.test?.[m] ?? 0),
      marker: { color: c.class1Alpha, line: { color: c.class1, width: 1.5 } },
    },
  ]

  Plotly.newPlot(juryComparisonEl.value, traces, chartLayout({
    barmode: 'group',
    yaxis: { title: { text: 'Value', font: { color: c.text } }, range: [0, 1.05], gridcolor: c.grid, color: c.text },
    xaxis: { color: c.text },
    height: 320,
    legend: { orientation: 'h', y: 1.15, font: { color: c.text } },
    margin: { t: 40, b: 50, l: 50, r: 20 },
  }), { responsive: true, displayModeBar: false })
}

async function renderJuryConcordance() {
  await nextTick()
  if (!juryConcordanceEl.value || !juryData.value?.sample_predictions) return

  const c = chartColors()
  const preds = juryData.value.sample_predictions

  // Tally per class: correct, error, rejected (predicted == -1 or abstain)
  const tally = { 0: { correct: 0, error: 0, rejected: 0 }, 1: { correct: 0, error: 0, rejected: 0 } }
  for (const s of preds) {
    const cls = s.real
    if (!(cls in tally)) tally[cls] = { correct: 0, error: 0, rejected: 0 }
    if (s.predicted === -1 || s.predicted === 2) {
      tally[cls].rejected++
    } else if (s.correct) {
      tally[cls].correct++
    } else {
      tally[cls].error++
    }
  }

  // Also count from confusion matrix abstain if no rejected in predictions
  const cm = juryData.value.confusion_train
  if (cm && tally[1].rejected === 0 && tally[0].rejected === 0 && (cm.abstain_1 > 0 || cm.abstain_0 > 0)) {
    tally[1].rejected = cm.abstain_1 || 0
    tally[0].rejected = cm.abstain_0 || 0
    // Adjust correct/error counts from confusion matrix
    tally[1].correct = cm.tp
    tally[1].error = cm.fn
    tally[0].correct = cm.tn
    tally[0].error = cm.fp
  }

  const classes = Object.keys(tally).sort()
  const xLabels = classes.map(cl => `Class ${cl}`)

  const traces = [
    {
      type: 'bar', name: 'Correct',
      x: xLabels, y: classes.map(cl => tally[cl].correct),
      marker: { color: c.class0Alpha, line: { color: c.class0, width: 1.5 } },
    },
    {
      type: 'bar', name: 'Error',
      x: xLabels, y: classes.map(cl => tally[cl].error),
      marker: { color: c.class1Alpha, line: { color: c.class1, width: 1.5 } },
    },
    {
      type: 'bar', name: 'Rejected',
      x: xLabels, y: classes.map(cl => tally[cl].rejected),
      marker: { color: 'rgba(255, 215, 0, 0.40)', line: { color: '#DAA520', width: 1.5 } },
    },
  ]

  Plotly.newPlot(juryConcordanceEl.value, traces, chartLayout({
    barmode: 'stack',
    yaxis: { title: { text: 'Samples', font: { color: c.text } }, gridcolor: c.grid, color: c.text },
    xaxis: { color: c.text },
    height: 200,
    legend: { orientation: 'h', y: 1.2, font: { color: c.text } },
    margin: { t: 30, b: 40, l: 50, r: 10 },
  }), { responsive: true, displayModeBar: false })
}

async function renderConfusionMatrix(el, cmData, title) {
  await nextTick()
  if (!el || !cmData) return

  const c = chartColors()
  const hasAbstain = (cmData.abstain_1 != null && cmData.abstain_1 > 0) ||
                     (cmData.abstain_0 != null && cmData.abstain_0 > 0)

  // Main confusion cells (Pred 1, Pred 0)
  const traces = [{
    type: 'heatmap',
    z: [[cmData.tp, cmData.fn], [cmData.fp, cmData.tn]],
    x: ['Pred 1', 'Pred 0'],
    y: ['Real 1', 'Real 0'],
    text: [[String(cmData.tp), String(cmData.fn)], [String(cmData.fp), String(cmData.tn)]],
    texttemplate: '%{text}',
    colorscale: [[0, c.paper], [1, 'rgba(0, 191, 255, 0.50)']],
    showscale: false,
    xgap: 2, ygap: 2,
    hovertemplate: '%{y} / %{x}: %{z}<extra></extra>',
  }]

  const xLabels = ['Pred 1', 'Pred 0']

  // Add rejection column if present
  if (hasAbstain) {
    xLabels.push('Rejected')
    traces[0].z[0].push(cmData.abstain_1 || 0)
    traces[0].z[1].push(cmData.abstain_0 || 0)
    traces[0].text[0].push(String(cmData.abstain_1 || 0))
    traces[0].text[1].push(String(cmData.abstain_0 || 0))
    traces[0].x = xLabels
    // Custom colorscale won't highlight the column, so overlay rejection with shapes
  }

  const layout = chartLayout({
    xaxis: { color: c.text, side: 'bottom' },
    yaxis: { color: c.text, autorange: 'reversed' },
    height: 200,
    margin: { t: 10, b: 40, l: 60, r: 10 },
    shapes: [],
    annotations: [],
  })

  // Add yellow highlight rectangles behind rejection column
  if (hasAbstain) {
    layout.shapes.push(
      {
        type: 'rect', xref: 'x', yref: 'y',
        x0: 1.5, x1: 2.5, y0: -0.5, y1: 0.5,
        fillcolor: 'rgba(255, 215, 0, 0.25)', line: { width: 0 }, layer: 'below',
      },
      {
        type: 'rect', xref: 'x', yref: 'y',
        x0: 1.5, x1: 2.5, y0: 0.5, y1: 1.5,
        fillcolor: 'rgba(255, 215, 0, 0.25)', line: { width: 0 }, layer: 'below',
      }
    )
  }

  Plotly.newPlot(el, traces, layout, { responsive: true, displayModeBar: false })
}

function changeSamplePredPage(page) {
  samplePredPage.value = page
  renderSamplePredictions()
}

async function renderSamplePredictions() {
  await nextTick()
  if (!samplePredictionsEl.value || !juryData.value?.sample_predictions) return

  const c = chartColors()
  const allPreds = [...juryData.value.sample_predictions]

  // Sort: rejected first, then errors, then correct — within each group by ascending consistency
  allPreds.sort((a, b) => {
    const aRejected = a.predicted === -1 || a.predicted === 2
    const bRejected = b.predicted === -1 || b.predicted === 2
    const aError = !a.correct && !aRejected
    const bError = !b.correct && !bRejected
    // Priority: rejected > error > correct
    const aPriority = aRejected ? 0 : aError ? 1 : 2
    const bPriority = bRejected ? 0 : bError ? 1 : 2
    if (aPriority !== bPriority) return aPriority - bPriority
    // Within same group: lowest consistency first (worst first)
    return a.consistency - b.consistency
  })

  // Paginate
  const start = samplePredPage.value * samplePredPageSize
  const preds = allPreds.slice(start, start + samplePredPageSize)

  const sampleNames = preds.map(s => s.name)

  // One trace per group for a proper legend
  const groups = [
    { label: 'Correct (class 0)', filter: s => s.correct && s.real === 0, color: c.class0Light, symbol: 'circle' },
    { label: 'Correct (class 1)', filter: s => s.correct && s.real === 1, color: c.class1Light, symbol: 'circle' },
    { label: 'Error', filter: s => !s.correct && s.predicted !== -1 && s.predicted !== 2, color: c.class1Light, symbol: 'x' },
    { label: 'Rejected', filter: s => s.predicted === -1 || s.predicted === 2, color: 'rgba(255, 215, 0, 0.85)', symbol: 'diamond' },
  ]

  const traces = groups.map(g => {
    const items = preds.filter(g.filter)
    if (items.length === 0) return null
    return {
      type: 'scatter',
      mode: 'markers',
      name: g.label,
      y: items.map(s => s.name),
      x: items.map(s => s.consistency),
      marker: {
        color: g.color,
        symbol: g.symbol,
        size: 10,
        line: { color: g.symbol === 'x' ? c.class1 : 'rgba(0,0,0,0.2)', width: 1 },
      },
      hovertemplate: '%{y}<br>Consistency: %{x:.1f}%<extra>' + g.label + '</extra>',
    }
  }).filter(Boolean)

  const chartHeight = Math.max(200, preds.length * 22 + 60)

  Plotly.newPlot(samplePredictionsEl.value, traces, chartLayout({
    xaxis: {
      title: { text: 'Consistency (%)', font: { color: c.text } },
      range: [0, 105], gridcolor: c.grid, color: c.text,
    },
    yaxis: {
      color: c.text, autorange: 'reversed',
      categoryorder: 'array', categoryarray: sampleNames,
      tickfont: { size: 10 },
    },
    height: chartHeight,
    margin: { t: 10, b: 50, l: 120, r: 20 },
    legend: { orientation: 'h', y: 1.05, font: { color: c.text, size: 11 } },
  }), { responsive: true, displayModeBar: false })
}

async function renderVoteMatrix() {
  await nextTick()
  if (!voteMatrixEl.value || !juryData.value?.vote_matrix) return
  const c = chartColors()
  const vm = juryData.value.vote_matrix

  // Sort samples: group by real class, then by consistency (misclassified first)
  const preds = juryData.value.sample_predictions || []
  const indices = vm.sample_names.map((_, i) => i)
  indices.sort((a, b) => {
    const pa = preds[a], pb = preds[b]
    if (!pa || !pb) return 0
    if (pa.real !== pb.real) return pa.real - pb.real
    if (pa.correct !== pb.correct) return pa.correct ? 1 : -1
    return pa.consistency - pb.consistency
  })

  const sortedNames = indices.map(i => vm.sample_names[i])
  const sortedVotes = indices.map(i => vm.votes[i])
  const sortedClasses = indices.map(i => vm.real_classes[i])

  // Build annotations for class separators
  const classLabels = sortedNames.map((n, i) => ({
    x: -0.5,
    y: i,
    text: `<b>${sortedClasses[i]}</b>`,
    showarrow: false,
    font: { size: 8, color: c.text },
    xanchor: 'right',
  }))

  // predomicspkg colorscale: 0=deepskyblue (class 0), 1=firebrick (class 1) with transparency
  const colorscale = [
    [0, c.isDark ? 'rgba(0, 191, 255, 0.45)' : 'rgba(0, 191, 255, 0.30)'],
    [1, c.isDark ? 'rgba(255, 48, 48, 0.55)' : 'rgba(255, 48, 48, 0.40)'],
  ]

  // Expert labels: include AUC if available
  const expertLabels = vm.expert_aucs
    ? Array.from({ length: vm.n_experts }, (_, i) => `E${i + 1} (${vm.expert_aucs[i]?.toFixed(2) || '?'})`)
    : Array.from({ length: vm.n_experts }, (_, i) => `E${i + 1}`)

  Plotly.newPlot(voteMatrixEl.value, [{
    type: 'heatmap',
    z: sortedVotes,
    x: expertLabels,
    y: sortedNames,
    colorscale,
    zmin: 0, zmax: 1,
    showscale: true,
    colorbar: {
      tickvals: [0, 1], ticktext: ['0', '1'],
      tickfont: { color: c.text, size: 9 }, len: 0.4, thickness: 10,
    },
    hovertemplate: 'Sample: %{y}<br>Expert: %{x}<br>Vote: %{z}<extra></extra>',
    xgap: 0.5,
    ygap: 0.5,
  }], chartLayout({
    xaxis: {
      title: { text: 'Experts', font: { color: c.text, size: 11 } },
      color: c.text,
      tickfont: { size: 7 },
      showticklabels: vm.n_experts <= 50,
    },
    yaxis: {
      color: c.text,
      automargin: true,
      tickfont: { size: 8 },
    },
    height: Math.max(300, sortedNames.length * 14 + 100),
    margin: { t: 20, b: 50, l: 120, r: 60 },
  }), { responsive: true, displayModeBar: false })
}

function renderJuryCharts() {
  renderJuryComparison()
  renderJuryConcordance()
  if (juryData.value?.confusion_train) renderConfusionMatrix(juryConfusionTrainEl.value, juryData.value.confusion_train)
  if (juryData.value?.confusion_test) renderConfusionMatrix(juryConfusionTestEl.value, juryData.value.confusion_test)
  renderSamplePredictions()
  renderVoteMatrix()
}

// ---------------------------------------------------------------------------
// CO-PRESENCE CHARTS
// ---------------------------------------------------------------------------
async function renderCopresencePrevalence() {
  await nextTick()
  if (!copresencePrevalenceEl.value) return
  const { features, prevalence } = copresenceData.value
  if (features.length === 0) return

  const c = chartColors()
  // Sort ascending so most prevalent is at top of horizontal bar chart
  const sorted = [...features].sort((a, b) => prevalence[a] - prevalence[b])
  const N = copresencePopulation.value.length

  Plotly.newPlot(copresencePrevalenceEl.value, [{
    type: 'bar',
    orientation: 'h',
    y: sorted.map(n => featureLabel(n)),
    x: sorted.map(n => prevalence[n]),
    text: sorted.map(n => `${((prevalence[n] / N) * 100).toFixed(0)}%`),
    textposition: 'outside',
    marker: {
      color: sorted.map(n => {
        const pct = prevalence[n] / N
        return pct > 0.75 ? c.accent : pct > 0.5 ? c.class0Light : c.class1Light
      }),
    },
    hovertemplate: '%{y}: %{x} models (%{text})<extra></extra>',
  }], chartLayout({
    xaxis: { title: { text: 'Models containing feature', font: { color: c.text } }, gridcolor: c.grid, color: c.text },
    yaxis: { automargin: true, color: c.text },
    height: Math.max(300, sorted.length * 22 + 80),
    margin: { t: 20, b: 50, l: 200, r: 60 },
    showlegend: false,
  }), { responsive: true, displayModeBar: false })
}

async function renderCopresenceHeatmap() {
  await nextTick()
  if (!copresenceHeatmapEl.value) return
  const { features, matrix } = copresenceData.value
  if (features.length < 2) return

  const c = chartColors()
  const labels = features.map(n => featureLabel(n))

  // Cap max ratio for readability
  let maxRatio = 2
  for (let i = 0; i < features.length; i++) {
    for (let j = 0; j < features.length; j++) {
      if (i !== j && isFinite(matrix[i][j])) {
        maxRatio = Math.max(maxRatio, matrix[i][j])
      }
    }
  }
  maxRatio = Math.min(maxRatio, 5)

  // Cap matrix values for display
  const displayMatrix = matrix.map(row => row.map(v => Math.min(isFinite(v) ? v : maxRatio, maxRatio)))

  const size = Math.max(400, features.length * 28 + 120)

  Plotly.newPlot(copresenceHeatmapEl.value, [{
    type: 'heatmap',
    z: displayMatrix,
    x: labels,
    y: labels,
    colorscale: 'Viridis',
    zmin: 0,
    zmax: maxRatio,
    showscale: true,
    colorbar: {
      title: { text: 'Obs/Exp', font: { color: c.text, size: 10 } },
      tickfont: { color: c.text, size: 9 },
      len: 0.5, thickness: 12,
    },
    xgap: 1,
    ygap: 1,
    hovertemplate: '%{y} × %{x}<br>Obs/Exp: %{z:.2f}<extra></extra>',
  }], chartLayout({
    xaxis: { automargin: true, color: c.text, tickangle: -45 },
    yaxis: { automargin: true, color: c.text },
    height: size,
    width: size,
    margin: { t: 20, b: 120, l: 200, r: 60 },
  }), { responsive: true, displayModeBar: true })
}

// --- Network layout algorithms ---
function layoutCircle(nNodes) {
  const x = [], y = []
  for (let i = 0; i < nNodes; i++) {
    x.push(Math.cos(2 * Math.PI * i / nNodes) * 100)
    y.push(Math.sin(2 * Math.PI * i / nNodes) * 100)
  }
  return { x, y }
}

function layoutGrid(nNodes) {
  const cols = Math.ceil(Math.sqrt(nNodes))
  const x = [], y = []
  for (let i = 0; i < nNodes; i++) {
    x.push((i % cols) * 40)
    y.push(Math.floor(i / cols) * 40)
  }
  return { x, y }
}

function layoutRadial(nNodes, prevalence, features) {
  // High-prevalence nodes in center, low-prevalence on outer rings
  const maxPrev = Math.max(...features.map(f => prevalence[f]))
  const sorted = features
    .map((f, i) => ({ i, prev: prevalence[f] }))
    .sort((a, b) => b.prev - a.prev)

  const x = new Array(nNodes).fill(0)
  const y = new Array(nNodes).fill(0)

  // Place most prevalent node at center
  x[sorted[0].i] = 0
  y[sorted[0].i] = 0

  // Distribute others in concentric rings
  let ring = 1, placed = 1
  while (placed < nNodes) {
    const ringCapacity = Math.max(1, Math.floor(6 * ring))
    const radius = ring * 50
    for (let k = 0; k < ringCapacity && placed < nNodes; k++, placed++) {
      const angle = (2 * Math.PI * k) / ringCapacity
      x[sorted[placed].i] = Math.cos(angle) * radius
      y[sorted[placed].i] = Math.sin(angle) * radius
    }
    ring++
  }
  return { x, y }
}

function layoutForceDirected(nNodes, features, prevalence, pairs) {
  // Start from circle
  const pos = layoutCircle(nNodes)
  const nodeX = pos.x, nodeY = pos.y

  const featureIdx = {}
  features.forEach((f, i) => { featureIdx[f] = i })

  for (let iter = 0; iter < 80; iter++) {
    const fx = new Array(nNodes).fill(0)
    const fy = new Array(nNodes).fill(0)

    // Repulsion between all nodes
    for (let i = 0; i < nNodes; i++) {
      for (let j = i + 1; j < nNodes; j++) {
        const dx = nodeX[i] - nodeX[j]
        const dy = nodeY[i] - nodeY[j]
        const dist = Math.max(Math.sqrt(dx * dx + dy * dy), 1)
        const force = 500 / (dist * dist)
        fx[i] += force * dx / dist
        fy[i] += force * dy / dist
        fx[j] -= force * dx / dist
        fy[j] -= force * dy / dist
      }
    }

    // Attraction/repulsion along edges
    for (const pair of pairs) {
      const i = featureIdx[pair.f1]
      const j = featureIdx[pair.f2]
      if (i === undefined || j === undefined) continue
      const dx = nodeX[j] - nodeX[i]
      const dy = nodeY[j] - nodeY[i]
      const dist = Math.max(Math.sqrt(dx * dx + dy * dy), 1)
      const sign = pair.type === 'positive' ? 1 : -1
      const force = sign * pair.strength * 0.05
      fx[i] += force * dx / dist
      fy[i] += force * dy / dist
      fx[j] -= force * dx / dist
      fy[j] -= force * dy / dist
    }

    const damping = 0.8 / (1 + iter * 0.05)
    for (let i = 0; i < nNodes; i++) {
      nodeX[i] += fx[i] * damping
      nodeY[i] += fy[i] * damping
    }
  }
  return { x: nodeX, y: nodeY }
}

async function renderCopresenceNetwork() {
  await nextTick()
  if (!copresenceNetworkEl.value) return
  const { features, prevalence, pairs } = copresenceData.value
  if (features.length < 2 || pairs.length === 0) return

  const c = chartColors()
  const N = copresencePopulation.value.length
  const nNodes = features.length

  // Compute layout based on selected algorithm
  let pos
  switch (networkLayout.value) {
    case 'circle':
      pos = layoutCircle(nNodes)
      break
    case 'grid':
      pos = layoutGrid(nNodes)
      break
    case 'radial':
      pos = layoutRadial(nNodes, prevalence, features)
      break
    case 'force':
    default:
      pos = layoutForceDirected(nNodes, features, prevalence, pairs)
      break
  }
  const nodeX = pos.x, nodeY = pos.y

  const featureIdx = {}
  features.forEach((f, i) => { featureIdx[f] = i })

  // Draw edges
  const edgeTraces = []
  for (const pair of pairs) {
    const i = featureIdx[pair.f1]
    const j = featureIdx[pair.f2]
    if (i === undefined || j === undefined) continue
    const isPos = pair.type === 'positive'
    edgeTraces.push({
      type: 'scatter', mode: 'lines',
      x: [nodeX[i], nodeX[j], null],
      y: [nodeY[i], nodeY[j], null],
      line: {
        color: isPos ? 'rgba(100, 200, 100, 0.5)' : 'rgba(200, 80, 80, 0.4)',
        width: Math.min(4, 1 + pair.strength * 0.3),
        dash: isPos ? 'solid' : 'dash',
      },
      hoverinfo: 'skip',
      showlegend: false,
    })
  }

  // Draw nodes
  const maxPrev = Math.max(...features.map(f => prevalence[f]))
  const nodeTrace = {
    type: 'scatter', mode: 'markers+text',
    x: nodeX,
    y: nodeY,
    text: features.map(f => featureLabel(f)),
    textposition: 'top center',
    textfont: { color: c.text, size: 9 },
    marker: {
      size: features.map(f => 10 + (prevalence[f] / maxPrev) * 25),
      color: features.map(f => {
        const pct = prevalence[f] / N
        return pct > 0.75 ? c.accent : pct > 0.5 ? c.class0Light : c.class1Light
      }),
      line: { color: c.text, width: 1 },
      opacity: 0.85,
    },
    hovertemplate: '%{text}<br>Prevalence: %{customdata} models<extra></extra>',
    customdata: features.map(f => prevalence[f]),
    showlegend: false,
  }

  Plotly.newPlot(copresenceNetworkEl.value, [...edgeTraces, nodeTrace], chartLayout({
    xaxis: { visible: false, showgrid: false, zeroline: false },
    yaxis: { visible: false, showgrid: false, zeroline: false, scaleanchor: 'x' },
    height: 550,
    margin: { t: 20, b: 20, l: 20, r: 20 },
    hovermode: 'closest',
  }), { responsive: true, displayModeBar: false })
}

async function renderFuncAnnotChart() {
  await nextTick()
  if (!funcAnnotChartEl.value) return
  const features = funcAnnotatedFeatures.value
  if (features.length === 0) return

  const c = chartColors()
  const N = copresencePopulation.value.length

  // Count features by functional property
  const props = FUNC_PROPS
  const propColors = [c.class0Light, '#e06c75', c.accent, c.warn]

  // For each property, count: positive (+1), negative (-1), zero
  const traces = []
  for (let pi = 0; pi < props.length; pi++) {
    const prop = props[pi]
    const posCount = features.filter(f => f[prop.key] === 1).length
    const negCount = features.filter(f => f[prop.key] === -1).length

    if (posCount > 0) {
      const desc = prop.desc['1'] || '+1'
      traces.push({
        type: 'bar', name: `${prop.label} (${desc})`,
        x: [prop.label], y: [posCount],
        marker: { color: propColors[pi], opacity: 0.85 },
        text: [String(posCount)], textposition: 'outside',
        showlegend: true,
      })
    }
    if (negCount > 0) {
      const desc = prop.desc['-1'] || '-1'
      traces.push({
        type: 'bar', name: `${prop.label} (${desc})`,
        x: [prop.label], y: [negCount],
        marker: { color: propColors[pi], opacity: 0.45, line: { color: propColors[pi], width: 2, dash: 'dash' } },
        text: [String(negCount)], textposition: 'outside',
        showlegend: true,
      })
    }
  }

  // Also add a stacked horizontal bar per feature showing its functional profile
  // Use a grouped bar: one group per functional prop, bars = number of features with that property
  const featureLabels = features.map(f => featureLabel(f.name))
  const funcTraces = props.map((prop, pi) => ({
    type: 'bar', orientation: 'h',
    name: prop.label,
    y: featureLabels,
    x: features.map(f => f[prop.key]),
    marker: { color: propColors[pi] },
    hovertemplate: `%{y}<br>${prop.label}: %{x}<extra></extra>`,
  }))

  Plotly.newPlot(funcAnnotChartEl.value, funcTraces, chartLayout({
    barmode: 'group',
    xaxis: {
      title: { text: 'Annotation value (-1, 0, +1)', font: { color: c.text } },
      gridcolor: c.grid, color: c.text,
      dtick: 1, range: [-1.5, 1.5],
    },
    yaxis: { automargin: true, color: c.text },
    height: Math.max(350, features.length * 20 + 100),
    margin: { t: 20, b: 50, l: 200, r: 20 },
    legend: { orientation: 'h', y: 1.08, font: { color: c.text } },
  }), { responsive: true, displayModeBar: false })
}

function renderCoPresenceCharts() {
  renderCopresencePrevalence()
  renderFuncAnnotChart()
  renderCopresenceHeatmap()
  renderCopresenceNetwork()
}

// ---------------------------------------------------------------------------
// COMPARATIVE CHARTS
// ---------------------------------------------------------------------------
// predomicspkg-inspired palette: deepskyblue, firebrick, darkorchid, darkgoldenrod, teal, coral, slateblue, seagreen
const JOB_COLORS = ['#00BFFF', '#FF3030', '#BA55D3', '#B8860B', '#008080', '#FF7F50', '#6A5ACD', '#2E8B57']

function jobLabel(jobId) {
  const j = jobs.value.find(x => x.job_id === jobId)
  return j?.name || jobId.slice(0, 8)
}

async function loadCompareData() {
  if (compareJobIds.value.length < 2) {
    compareData.value = []
    return
  }
  const pid = route.params.id
  const results = []
  for (const jid of compareJobIds.value) {
    try {
      const { data } = await axios.get(`/api/analysis/${pid}/jobs/${jid}/results`)
      // Find job metadata (name, config) from job list
      const jobMeta = jobs.value.find(j => j.job_id === jid) || {}
      results.push({
        job_id: jid, jobId: jid,
        name: jobMeta.name,
        config_summary: jobMeta.config_summary,
        best: data.best_individual || {},
        ...data,
      })
    } catch { /* skip */ }
  }
  compareData.value = results
}

async function renderComparisonBar() {
  await nextTick()
  if (!comparisonBarEl.value || compareData.value.length < 2) return

  const c = chartColors()
  const metricNames = ['auc', 'accuracy', 'sensitivity', 'specificity']
  const labels = ['AUC', 'Accuracy', 'Sensitivity', 'Specificity']

  const traces = compareData.value.map((job, i) => {
    const col = JOB_COLORS[i % JOB_COLORS.length]
    // Convert hex to rgba with transparency
    const r = parseInt(col.slice(1, 3), 16), g = parseInt(col.slice(3, 5), 16), b = parseInt(col.slice(5, 7), 16)
    return {
      type: 'bar',
      name: jobLabel(job.jobId),
      x: labels,
      y: metricNames.map(m => job.best_individual?.[m] ?? 0),
      marker: { color: `rgba(${r},${g},${b},0.35)`, line: { color: col, width: 1.5 } },
    }
  })

  Plotly.newPlot(comparisonBarEl.value, traces, chartLayout({
    barmode: 'group',
    yaxis: { title: { text: 'Value', font: { color: c.text } }, range: [0, 1.05], gridcolor: c.grid, color: c.text },
    xaxis: { color: c.text },
    height: 320,
    legend: { orientation: 'h', y: 1.12, font: { color: c.text } },
    margin: { t: 30, b: 50, l: 50, r: 20 },
  }), { responsive: true, displayModeBar: false })
}

async function renderComparisonConvergence() {
  await nextTick()
  if (!comparisonConvergenceEl.value || compareData.value.length < 2) return

  const c = chartColors()
  const traces = compareData.value.map((job, i) => {
    const gt = job.generation_tracking || []
    return {
      x: gt.map(g => g.generation),
      y: gt.map(g => g.best_auc),
      name: jobLabel(job.jobId),
      type: 'scatter', mode: 'lines+markers',
      line: { color: JOB_COLORS[i % JOB_COLORS.length], width: 2 },
      marker: { size: 4 },
    }
  })

  Plotly.newPlot(comparisonConvergenceEl.value, traces, chartLayout({
    xaxis: { title: { text: 'Generation', font: { color: c.text } }, gridcolor: c.grid, color: c.text },
    yaxis: { title: { text: 'Best AUC', font: { color: c.text } }, gridcolor: c.grid, color: c.text },
    legend: { orientation: 'h', y: 1.12, font: { color: c.text } },
    height: 300,
    margin: { t: 30, b: 50, l: 60, r: 20 },
  }), { responsive: true, displayModeBar: false })
}

async function renderFeatureOverlap() {
  await nextTick()
  if (!featureOverlapEl.value || compareData.value.length < 2) return

  const c = chartColors()

  // Collect features from each job's best individual
  const jobFeatures = compareData.value.map(job => {
    const b = job.best_individual || {}
    const fnames = job.feature_names || []
    const feats = {}
    for (const [idx, coef] of Object.entries(b.features || {})) {
      const name = fnames[parseInt(idx)] || `f_${idx}`
      feats[name] = parseInt(coef)
    }
    return feats
  })

  // Union of all features
  const allFeatures = [...new Set(jobFeatures.flatMap(f => Object.keys(f)))]
  allFeatures.sort()

  // Build matrix
  const matrix = allFeatures.map(fname =>
    jobFeatures.map(jf => jf[fname] || 0)
  )

  // predomicspkg heatmap gradient: deepskyblue1 → white → firebrick1 (transparent + fine grid)
  const colorscale = [
    [0, 'rgba(0, 191, 255, 0.55)'],
    [0.5, c.paper],
    [1, 'rgba(255, 48, 48, 0.55)'],
  ]

  Plotly.newPlot(featureOverlapEl.value, [{
    type: 'heatmap',
    z: matrix,
    x: compareData.value.map(j => jobLabel(j.jobId)),
    y: allFeatures.map(n => featureLabel(n)),
    colorscale,
    zmin: -1, zmax: 1,
    showscale: true,
    colorbar: {
      tickvals: [-1, 0, 1], ticktext: ['-1', '0', '+1'],
      tickfont: { color: c.text, size: 9 }, len: 0.5, thickness: 12,
    },
    xgap: 1,
    ygap: 1,
    hovertemplate: '%{y}<br>Job %{x}: %{z}<extra></extra>',
  }], chartLayout({
    xaxis: { title: { text: 'Job', font: { color: c.text } }, color: c.text },
    yaxis: { automargin: true, color: c.text },
    height: Math.max(250, allFeatures.length * 22 + 80),
    margin: { t: 20, b: 50, l: 180, r: 60 },
  }), { responsive: true, displayModeBar: false })
}

function renderComparativeCharts() {
  renderComparisonBar()
  renderComparisonConvergence()
  renderFeatureOverlap()
}

async function loadFailedJobLog() {
  if (!selectedJobId.value) return
  const pid = route.params.id
  try {
    const { data } = await axios.get(`/api/analysis/${pid}/jobs/${selectedJobId.value}/logs`)
    const lines = (data.log || '').split('\n')
    failedJobLog.value = lines.slice(-50).join('\n')
  } catch {
    failedJobLog.value = 'Unable to load console log.'
  }
}

// ---------------------------------------------------------------------------
// Job table helpers
// ---------------------------------------------------------------------------
function selectJob(jobId) {
  selectedJobId.value = jobId
  failedJobLog.value = ''
  loadJobResults()
}

function toggleJobSort(key) {
  if (jobSortKey.value === key) {
    jobSortAsc.value = !jobSortAsc.value
  } else {
    jobSortKey.value = key
    jobSortAsc.value = key === 'name' || key === 'status'
  }
}

function formatDuration(seconds) {
  if (seconds == null) return '—'
  if (seconds < 60) return `${seconds.toFixed(1)}s`
  const mins = Math.floor(seconds / 60)
  const secs = Math.round(seconds % 60)
  return `${mins}m ${secs}s`
}

function formatDate(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  const now = new Date()
  const diff = now - d
  if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

function formatSize(bytes) {
  if (bytes == null) return '—'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`
}

function sortedFeatures(namedFeatures) {
  if (!namedFeatures) return []
  const entries = Object.entries(namedFeatures)
  // Group: negative first, then positive; within each group sort alphabetically
  return entries.sort((a, b) => {
    if (a[1] !== b[1]) return a[1] - b[1] // neg (-1) before pos (+1)
    return a[0].localeCompare(b[0])
  })
}

async function findDuplicates() {
  duplicatesLoading.value = true
  const pid = route.params.id
  try {
    const { data } = await axios.get(`/api/analysis/${pid}/jobs/duplicates`)
    duplicateGroups.value = data
    if (data.length === 0) alert('No duplicate jobs found.')
  } catch (e) {
    console.error('Failed to find duplicates:', e)
  } finally {
    duplicatesLoading.value = false
  }
}

async function cleanupDuplicates() {
  const toDelete = duplicateGroups.value.flatMap(g => g.jobs.filter(j => !j.keep).map(j => j.job_id))
  if (toDelete.length === 0) return
  if (!confirm(`Delete ${toDelete.length} duplicate job${toDelete.length !== 1 ? 's' : ''}? This cannot be undone.`)) return
  const pid = route.params.id
  let deleted = 0
  for (const jid of toDelete) {
    try {
      await axios.delete(`/api/analysis/${pid}/jobs/${jid}`)
      deleted++
    } catch { /* skip running jobs */ }
  }
  duplicateGroups.value = []
  await loadJobList()
  if (selectedJobId.value && toDelete.includes(selectedJobId.value)) {
    selectedJobId.value = ''
    detail.value = null
  }
  alert(`Deleted ${deleted} duplicate job${deleted !== 1 ? 's' : ''}.`)
}

// ---------------------------------------------------------------------------
// Export
// ---------------------------------------------------------------------------
async function doExport(format, section) {
  exportMenuOpen.value = false
  const pid = route.params.id
  const jid = selectedJobId.value
  if (!jid) return

  let url
  if (format === 'csv') {
    url = `/api/export/${pid}/jobs/${jid}/csv?section=${section}`
  } else if (format === 'report') {
    url = `/api/export/${pid}/jobs/${jid}/report`
  } else if (format === 'json') {
    url = `/api/export/${pid}/jobs/${jid}/json`
  } else if (format === 'notebook') {
    url = `/api/export/${pid}/jobs/${jid}/notebook?lang=${section}`
  }

  try {
    const { data, headers } = await axios.get(url, { responseType: 'blob' })
    // Extract filename from Content-Disposition header
    const disposition = headers['content-disposition'] || ''
    const match = disposition.match(/filename="?([^"]+)"?/)
    const filename = match ? match[1] : `export.${format === 'csv' ? 'csv' : format === 'json' ? 'json' : 'html'}`

    // Trigger browser download
    const blob = new Blob([data])
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = filename
    link.click()
    URL.revokeObjectURL(link.href)
  } catch (e) {
    console.error('Export failed:', e)
    alert('Export failed: ' + (e.response?.data?.detail || e.message))
  }
}

function truncateVotes(votes) {
  if (!votes) return '—'
  return votes.length > 30 ? votes.slice(0, 30) + '...' : votes
}

async function confirmDeleteJob(job) {
  if (job.status === 'running') return
  if (!confirm(`Delete job "${job.name || job.job_id.slice(0, 8)}"? This cannot be undone.`)) return
  const pid = route.params.id
  try {
    await axios.delete(`/api/analysis/${pid}/jobs/${job.job_id}`)
    await loadJobList()
    if (selectedJobId.value === job.job_id) {
      selectedJobId.value = ''
      detail.value = null
    }
  } catch (e) {
    alert('Delete failed: ' + (e.response?.data?.detail || e.message))
  }
}

// ---------------------------------------------------------------------------
// Data loading
// ---------------------------------------------------------------------------
async function loadJobResults() {
  if (!selectedJobId.value) return
  loading.value = true
  const pid = route.params.id
  const jid = selectedJobId.value

  try {
    const { data } = await axios.get(`/api/analysis/${pid}/jobs/${jid}/detail`)
    detail.value = data

    try {
      const { data: raw } = await axios.get(`/api/analysis/${pid}/jobs/${jid}/results`)
      fullResults.value = raw
      population.value = raw.population || []
      generationTracking.value = raw.generation_tracking || []
      juryData.value = raw.jury || null
      importanceData.value = raw.importance || null
      contributionData.value = null
      // Reset filters for new job
      selectedLanguages.value = []
      selectedDataTypes.value = []
      fbmEnabled.value = false
      popPage.value = 0
      samplePredPage.value = 0
    } catch {
      fullResults.value = null
      population.value = []
      generationTracking.value = []
      juryData.value = null
      importanceData.value = null
    }

    await loadMspAnnotations()
    await nextTick()
    renderActiveTab()
  } catch (e) {
    console.error('Failed to load results:', e)
    detail.value = null
  } finally {
    loading.value = false
  }
}

async function loadJobList() {
  const pid = route.params.id
  try {
    const { data } = await axios.get(`/api/analysis/${pid}/jobs`)
    if (store.current) store.current.jobs = data

    const jobIdFromRoute = route.params.jobId
    if (jobIdFromRoute) {
      selectedJobId.value = jobIdFromRoute
    } else if (data.length > 0) {
      const completed = data.find(j => j.status === 'completed')
      if (completed) selectedJobId.value = completed.job_id
    }
    if (selectedJobId.value) loadJobResults()
  } catch (e) {
    console.error('Failed to load jobs:', e)
  }
}

async function renderActiveTab() {
  await ensurePlotly()
  if (subTab.value === 'summary') renderSummaryCharts()
  else if (subTab.value === 'bestmodel') renderBestModelCharts()
  else if (subTab.value === 'population') renderPopulationCharts()
  else if (subTab.value === 'jury') renderJuryCharts()
  else if (subTab.value === 'comparative') renderComparativeCharts()
  else if (subTab.value === 'copresence') renderCoPresenceCharts()
}

// ---------------------------------------------------------------------------
// Watchers
// ---------------------------------------------------------------------------
watch(subTab, async () => {
  await nextTick()
  renderActiveTab()
})

watch(() => themeStore.isDark, () => renderActiveTab())

watch(() => route.params.jobId, (newId) => {
  if (newId && newId !== selectedJobId.value) {
    selectedJobId.value = newId
    loadJobResults()
  }
})

// Reset job page on search change
watch(jobSearch, () => { jobPage.value = 0 })

// Re-render population charts when topN or filters change
let _popFilterTimer = null
function debouncedPopRender() {
  clearTimeout(_popFilterTimer)
  _popFilterTimer = setTimeout(() => {
    popPage.value = 0
    if (subTab.value === 'population') renderPopulationCharts()
  }, 300)
}
watch(topNModels, debouncedPopRender)
watch(selectedLanguages, debouncedPopRender, { deep: true })
watch(selectedDataTypes, debouncedPopRender, { deep: true })
watch(fbmEnabled, debouncedPopRender)

// Re-render co-presence charts when controls change
let _copresenceTimer = null
function debouncedCopresenceRender() {
  clearTimeout(_copresenceTimer)
  _copresenceTimer = setTimeout(() => {
    copresencePage.value = 0
    if (subTab.value === 'copresence') renderCoPresenceCharts()
  }, 300)
}
watch(copresenceFBM, debouncedCopresenceRender)
watch(copresenceMinPrev, debouncedCopresenceRender)
watch(copresenceAlpha, debouncedCopresenceRender)
watch(networkLayout, () => {
  if (subTab.value === 'copresence') renderCopresenceNetwork()
})

// Load compare data when selection changes
watch(compareJobIds, async () => {
  await loadCompareData()
  await nextTick()
  if (subTab.value === 'comparative') renderComparativeCharts()
}, { deep: true })

// Auto-select all completed jobs for comparison
watch(completedJobs, (cj) => {
  if (compareJobIds.value.length === 0 && cj.length >= 2) {
    compareJobIds.value = cj.slice(0, 4).map(j => j.job_id)
  }
}, { immediate: true })

// Auto-refresh job list when project store data changes (e.g. job completed)
let _lastJobCount = -1
watch(() => store.current?.jobs?.length, (newLen) => {
  if (newLen != null && _lastJobCount >= 0 && newLen !== _lastJobCount) {
    loadJobList()
  }
  if (newLen != null) _lastJobCount = newLen
})

// Auto-reload selected job results when its status changes to completed
watch(() => {
  const activeJob = store.current?.jobs?.find(j => j.job_id === selectedJobId.value)
  return activeJob?.status
}, (newStatus, oldStatus) => {
  if (newStatus === 'completed' && oldStatus && oldStatus !== 'completed') {
    loadJobResults()
  }
})

onMounted(loadJobList)
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
  font-size: 0.72rem;
  color: var(--text-secondary);
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 200px;
  overflow-y: auto;
  font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;
}
.failed-log-hint { margin-top: 0.5rem; }

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
  font-size: 0.68rem;
  background: var(--bg-badge, rgba(0,0,0,0.06));
  color: var(--text-muted);
  margin-right: 0.3rem;
}
.config-detail {
  font-size: 0.72rem;
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
  outline: none;
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
  font-size: 0.7rem;
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
}
.btn-delete {
  color: var(--text-faint);
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
  font-size: 0.65rem;
  font-weight: 700;
  text-transform: uppercase;
  background: var(--success-bg);
  color: var(--success-dark, #2e7d32);
}
.dup-tag.dup-remove {
  background: var(--danger-bg);
  color: var(--danger-dark, #c62828);
}

/* Sub-tabs */
.sub-tabs {
  display: flex;
  gap: 0;
  margin-bottom: 1.5rem;
  border-bottom: 1px solid var(--border-light);
}
.sub-tabs > button {
  padding: 0.5rem 1.25rem;
  border: none;
  background: none;
  color: var(--text-muted);
  font-size: 0.85rem;
  font-weight: 500;
  cursor: pointer;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
}
.sub-tabs > button.active {
  color: var(--text-primary);
  border-bottom-color: var(--accent);
}
.sub-tabs {
  align-items: center;
}

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
.vote-mono { font-family: monospace; font-size: 0.72rem; letter-spacing: -0.5px; color: var(--text-muted); }
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
  font-size: 0.72rem;
  background: var(--accent);
  color: #fff;
  padding: 0.1rem 0.5rem;
  border-radius: 10px;
  font-weight: 600;
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
  font-size: 0.72rem;
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
}
.clickable-row { cursor: pointer; }
.clickable-row:hover { background: var(--bg-card-hover); }
.detail-row td {
  background: var(--bg-badge);
  padding: 1rem;
}
.row-error td { color: var(--danger-dark); }

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
  font-size: 0.7rem;
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
  font-size: 0.72rem;
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

@media (max-width: 900px) {
  .best-model-layout { grid-template-columns: 1fr; }
  .chart-row { grid-template-columns: 1fr; }
}
</style>
