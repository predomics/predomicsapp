/**
 * State and behaviour of the Results view.
 *
 * views/ResultsTab.vue calls createResultsState() once and provides it; each
 * sub-tab component (components/results/tabs/*) picks what its template needs
 * with useResults(). Keeping everything in one closure preserves the behaviour
 * of the former single-file component: watchers, URL sync and chart rendering
 * are unchanged, only the markup moved.
 */
import { densityGrid } from '../utils/density'
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick , inject, getCurrentInstance } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useProjectStore } from '../stores/project'
import { useConfigStore } from '../stores/config'
import { useChartTheme, withAlpha, signCells } from '../composables/useChartTheme'
import { useShapValues } from '../composables/useShapValues'
import { api, http } from '../api'
import { ct } from '../utils/chartText'
import { classLabel } from '../utils/classNames'
import { timeAgo } from '../utils/time'
import { loadPlotlyLib, loadPlotly3d, usePlotlyCleanup } from '../utils/plotly'
import { useI18n } from 'vue-i18n'
import { useDebugMode } from '../composables/useDebugMode'
import { useModelBasket } from '../composables/useModelBasket'
import { useToast } from '../composables/useToast'
import { useConfirm } from '../composables/useConfirm'
import { apiError, ignoreError } from '../utils/apiError'
import { LONG_TIMEOUT_MS } from '../utils/http'
import { statusLabel, statusGlyph, isLive, normalizeJobs } from '../utils/jobStatus'

export const RESULTS_KEY = Symbol('results-state')

/**
 * Called from a sub-tab's setup(). Besides returning the shared state, it makes
 * the sub-tab render with the Results view's style scope: the view's
 * `<style scoped>` rules were written for one template and must keep applying
 * to the markup that moved into sub-tab components. (Vue stamps elements with
 * the rendering component's `__scopeId`; sub-tabs have no scoped styles of
 * their own, so they borrow the parent's.)
 */
export function useResults() {
  const state = inject(RESULTS_KEY)
  if (!state) throw new Error('useResults() must be used inside the Results view')
  const inst = getCurrentInstance()
  if (inst && state.__scopeId && !inst.type.__scopeId) inst.type.__scopeId = state.__scopeId
  return state
}

export function createResultsState() {
  // Lazy-load Plotly for better initial page load
  let Plotly = null
  usePlotlyCleanup()
  async function ensurePlotly() {
    if (!Plotly) {
      Plotly = await loadPlotlyLib()
    }
    return Plotly
  }

  const route = useRoute()
  const router = useRouter()
  const store = useProjectStore()
  const configStore = useConfigStore()
  const { themeStore, chartColors, chartLayout, classStyle, featureLabel: _featureLabel, FUNC_PROPS } = useChartTheme()
  const { computeShapMatrix } = useShapValues()
  const { t, te } = useI18n()

  /** Name of a class in charts and tables: the project's own label when one was given. */
  function classNameFor(cls) {
    return classLabel(cls, store.current?.class_names)
  }
  const { debugMode } = useDebugMode()
  const {
    basketItems, basketCount, basketFull,
    isInBasket, addToBasket, removeFromBasket, clearBasket, toggleBasket,
    MAX_BASKET_SIZE,
  } = useModelBasket(route.params.id)

  // Flamegraph colors for timing phases
  const flamegraphColors = computed(() => chartColors().series)

  // ---------------------------------------------------------------------------
  // State
  // ---------------------------------------------------------------------------
  const { toast, addToast } = useToast()
  const { confirmDialog } = useConfirm()

  const rootEl = ref(null)
  const exportWrapEl = ref(null)
  const exporting = ref(false)
  const loading = ref(false)
  const jobsLoading = ref(false)
  const jobsLoaded = ref(false)
  const jobsError = ref('')
  const resultsError = ref('')
  const resultsPartial = ref(false)
  const cancellingId = ref('')
  const detail = ref(null)
  const fullResults = ref(null)
  const population = ref([])
  const generationTracking = ref([])
  const mspAnnotations = ref({})
  const moduleFilterData = ref(null)
  const SUB_TABS = ['insights', 'summary', 'bestmodel', 'population', 'jury', 'comparative', 'copresence',
    'enrichment', 'ecosystem', 'stability', 'pheromone', 'exploration', 'basket', 'console']
  // The open section is part of the URL (?tab=…): it survives a refresh and the back button.
  const subTab = ref(SUB_TABS.includes(route.query.tab) ? route.query.tab : 'insights')
  const selectedJobId = ref('')
  const expandedRank = ref(null)
  const popPage = ref(0)
  const popPageSize = 10
  const topNModels = ref(50)

  // Jury, importance & pheromone state
  const juryData = ref(null)
  const importanceData = ref(null)
  const pheromoneData = ref(null)
  const pheromoneTopN = ref(30)
  const pheromoneChartEl = ref(null)
  const pheromoneTimelineEl = ref(null)
  const entropyChartEl = ref(null)
  const cooccurrenceChartEl = ref(null)
  const discoveryChartEl = ref(null)
  const explorationChartEl = ref(null)
  const explorationGen = ref(-1) // -1 = all generations
  const hasExplorationData = computed(() => {
    return generationTracking.value.some(g => g.k_fit_sample && g.k_fit_sample.length > 0)
  })

  // Population filter state (P2.2 + P2.3)
  const selectedLanguages = ref([])
  const selectedDataTypes = ref([])
  const fbmEnabled = ref(false)
  const fbmMethod = ref('wilson')

  // PCoA on FBM features state
  const popPcoaData = ref(null)
  const loadingPopPcoa = ref(false)
  const popPcoaMethod = ref('pcoa')
  const popPcoaMetric = ref('braycurtis')
  const popPcoaDim = ref('2d')
  const popPcoaShowEllipses = ref(true)
  const popTsnePerplexity = ref(30)
  const popUmapNeighbors = ref(15)
  const popUmapMinDist = ref(0.1)

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

  // Validate modal state
  const showValidateModal = ref(false)

  // Deploy API state
  const apiBaseUrl = window.location.origin
  const deployCopied = ref(false)

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
  // SHAP explanations
  const shapData = ref(null)
  const shapLoading = ref(false)
  const shapView = ref('beeswarm')
  const shapSampleIdx = ref(0)
  const shapFeatureIdx = ref(0)
  const beeswarmChartEl = ref(null)
  const forceChartEl = ref(null)
  const dependenceChartEl = ref(null)
  // Population
  const featureHeatmapEl = ref(null)
  const featurePrevalenceEl = ref(null)
  const popMetricsEl = ref(null)
  const compositionChartEl = ref(null)
  const metricsByTypeEl = ref(null)
  const popPcoaChartEl = ref(null)
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
  const copresenceWeighted = ref(false)
  const copresenceMinPrev = ref(2)
  const copresenceTopN = ref(50)   // features drawn in the co-presence charts (0 = all)
  const copresenceAlpha = ref(0.1)
  const funcAnnotChartEl = ref(null)
  const copresencePage = ref(0)
  const copresencePageSize = 20
  const networkLayout = ref('force')
  const networkLayoutOptions = computed(() => [
    { value: 'force', label: t('results.forceDirected') },
    { value: 'circle', label: t('results.circle') },
    { value: 'grid', label: t('results.grid') },
    { value: 'radial', label: t('results.radial') },
  ])
  // Basket
  const basketMetricsChartEl = ref(null)
  const basketFeatureOverlapEl = ref(null)
  const basketHeatmapEl = ref(null)
  const basketExpandedId = ref(null)

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

  // Regression mode detection for the selected job
  const isRegressionJob = computed(() => {
    return fullResults.value?.regression === true
  })
  const fitMetricLabel = computed(() => {
    if (!isRegressionJob.value) return 'AUC'
    return t('results.correlation')
  })

  const failedJobLog = ref('')

  // Console log viewer state
  const consoleLogContent = ref('')
  const consoleLogLoading = ref(false)
  const consoleLogCopied = ref(false)
  const consoleLogEl = ref(null)
  const consoleLogLines = computed(() => consoleLogContent.value ? consoleLogContent.value.split('\n').length : 0)

  // Timing data for flamegraph (from results.timing stored by worker)
  const timingData = computed(() => {
    const raw = fullResults.value?.timing
    if (!raw || !raw.phases || !raw.phases.length) return null
    return raw
  })

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

  // FBM filter function — 5 binomial CI methods
  // Computes the lower bound of the CI for the best model's accuracy,
  // then keeps all models whose fit >= that lower bound.
  function filterFBM(pop) {
    if (pop.length === 0) return []
    const bestFit = pop[0].metrics?.fit
    if (bestFit == null) return pop
    const n = detail.value?.sample_count || pop.length
    const alpha = 0.05
    const z = 1.96 // normal quantile for alpha/2 = 0.025
    const p = bestFit
    const se = Math.sqrt(p * (1 - p) / n)

    let lower
    switch (fbmMethod.value) {
      case 'wald':
        lower = p - z * se
        break
      case 'wald_continuity':
        lower = p - (0.5 / n + z * se)
        break
      case 'wilson':
        lower = (p + z * z / (2 * n) - z * Math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / (1 + z * z / n)
        break
      case 'agresti_coull': {
        const nt = n + z * z
        const pt = (p * n + z * z / 2) / nt
        lower = pt - z * Math.sqrt(pt * (1 - pt) / nt)
        break
      }
      case 'clopper_pearson': {
        // Exact CI using Beta distribution inverse CDF
        const x = Math.round(p * n)
        if (x === 0) { lower = 0 }
        else { lower = jstatBetaInv(alpha / 2, x, n - x + 1) }
        break
      }
      default:
        lower = p - z * se
    }
    const threshold = Math.max(0, lower)
    return pop.filter(ind => ind.metrics?.fit >= threshold)
  }

  // Minimal Beta distribution inverse CDF for Clopper-Pearson CI
  // Uses the regularized incomplete beta function via Newton's method
  function jstatBetaInv(p, a, b) {
    // Approximation of Beta quantile using bisection
    let lo = 0, hi = 1
    for (let i = 0; i < 100; i++) {
      const mid = (lo + hi) / 2
      if (betaRegularized(mid, a, b) < p) lo = mid
      else hi = mid
    }
    return (lo + hi) / 2
  }

  function betaRegularized(x, a, b) {
    // Regularized incomplete beta function I_x(a,b) via continued fraction
    if (x <= 0) return 0
    if (x >= 1) return 1
    if (x > (a + 1) / (a + b + 2)) return 1 - betaRegularized(1 - x, b, a)
    const lnBeta = lnGamma(a) + lnGamma(b) - lnGamma(a + b)
    const front = Math.exp(Math.log(x) * a + Math.log(1 - x) * b - lnBeta) / a
    // Lentz's continued fraction
    let f = 1, c = 1, d = 1 - (a + b) * x / (a + 1)
    if (Math.abs(d) < 1e-30) d = 1e-30
    d = 1 / d; f = d
    for (let m = 1; m <= 200; m++) {
      let num = m * (b - m) * x / ((a + 2 * m - 1) * (a + 2 * m))
      d = 1 + num * d; if (Math.abs(d) < 1e-30) d = 1e-30; d = 1 / d
      c = 1 + num / c; if (Math.abs(c) < 1e-30) c = 1e-30
      f *= d * c
      num = -(a + m) * (a + b + m) * x / ((a + 2 * m) * (a + 2 * m + 1))
      d = 1 + num * d; if (Math.abs(d) < 1e-30) d = 1e-30; d = 1 / d
      c = 1 + num / c; if (Math.abs(c) < 1e-30) c = 1e-30
      const delta = d * c; f *= delta
      if (Math.abs(delta - 1) < 1e-10) break
    }
    return front * f
  }

  function lnGamma(z) {
    // Lanczos approximation for ln(Gamma(z))
    const g = 7
    const coef = [0.99999999999980993, 676.5203681218851, -1259.1392167224028,
      771.32342877765313, -176.61502916214059, 12.507343278686905,
      -0.13857109526572012, 9.9843695780195716e-6, 1.5056327351493116e-7]
    if (z < 0.5) return Math.log(Math.PI / Math.sin(Math.PI * z)) - lnGamma(1 - z)
    z -= 1
    let x = coef[0]
    for (let i = 1; i < g + 2; i++) x += coef[i] / (z + i)
    const t = z + g + 0.5
    return 0.5 * Math.log(2 * Math.PI) + (z + 0.5) * Math.log(t) - t + Math.log(x)
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
    if (pop.length < 2) return { features: [], prevalence: {}, accuracy: {}, matrix: [], pairs: [] }

    // Build feature prevalence and accuracy sums
    const prevalence = {}
    const accSum = {}
    for (const ind of pop) {
      const acc = ind.metrics?.fit || 0
      for (const name of Object.keys(ind.named_features || {})) {
        prevalence[name] = (prevalence[name] || 0) + 1
        accSum[name] = (accSum[name] || 0) + acc
      }
    }

    // Per-feature mean accuracy
    const accuracy = {}
    for (const [name, count] of Object.entries(prevalence)) {
      accuracy[name] = count > 0 ? accSum[name] / count : 0
    }

    // Filter features by minimum prevalence
    const minPrev = copresenceMinPrev.value || 2
    const features = Object.entries(prevalence)
      .filter(([, count]) => count >= minPrev)
      .sort((a, b) => b[1] - a[1])
      .map(([name]) => name)

    if (features.length < 2) return { features, prevalence, accuracy, matrix: [], pairs: [] }

    const N = pop.length
    const fSet = new Set(features)
    const weighted = copresenceWeighted.value

    // Warm up log-factorial cache
    logFact(N)

    // Build presence per model and model accuracies
    const presenceByModel = pop.map(ind => {
      const s = new Set()
      for (const name of Object.keys(ind.named_features || {})) {
        if (fSet.has(name)) s.add(name)
      }
      return s
    })
    const modelAccuracies = pop.map(ind => ind.metrics?.fit || 0)

    // Compute pairwise co-occurrence (binary + weighted)
    const cooccurCounts = {}
    const cooccurWeighted = {}
    for (let i = 0; i < features.length; i++) {
      for (let j = i + 1; j < features.length; j++) {
        let count = 0
        let wCount = 0
        for (let m = 0; m < presenceByModel.length; m++) {
          if (presenceByModel[m].has(features[i]) && presenceByModel[m].has(features[j])) {
            count++
            wCount += modelAccuracies[m]
          }
        }
        const key = `${i},${j}`
        cooccurCounts[key] = count
        cooccurWeighted[key] = wCount
      }
    }

    // Build matrix and pairs with stats using hypergeometric test
    const matrix = features.map(() => features.map(() => 1))
    const pairs = []
    const alpha = copresenceAlpha.value
    const totalAccSum = modelAccuracies.reduce((a, b) => a + b, 0)

    for (let i = 0; i < features.length; i++) {
      for (let j = i + 1; j < features.length; j++) {
        const ni = prevalence[features[i]]
        const nj = prevalence[features[j]]
        const observed = cooccurCounts[`${i},${j}`]
        const expected = (ni * nj) / N
        const ratio = expected > 0 ? observed / expected : (observed > 0 ? Infinity : 1)

        // Accuracy-weighted ratio
        const wObs = cooccurWeighted[`${i},${j}`]
        const wExp = totalAccSum > 0 ? (accSum[features[i]] * accSum[features[j]]) / totalAccSum : 0
        const wRatio = wExp > 0 ? wObs / wExp : (wObs > 0 ? Infinity : 1)

        const displayRatio = weighted ? wRatio : ratio
        matrix[i][j] = displayRatio
        matrix[j][i] = displayRatio

        // Hypergeometric test (always on integer counts)
        const pGt = pvalueGreater(observed, N, ni, nj)
        const pLt = pvalueLess(observed, N, ni, nj)
        const pval = Math.min(pGt, pLt)
        const type = pGt < pLt ? 'positive' : 'negative'

        if (pval <= alpha) {
          pairs.push({
            f1: features[i],
            f2: features[j],
            observed,
            expected,
            ratio,
            wObserved: Math.round(wObs * 100) / 100,
            wRatio: Math.round(wRatio * 100) / 100,
            pvalue: pval,
            type,
            strength: -Math.log10(Math.max(pval, 1e-300)),
          })
        }
      }
      matrix[i][i] = prevalence[features[i]] / N
    }

    pairs.sort((a, b) => b.strength - a.strength)

    return { features, prevalence, accuracy, matrix, pairs }
  })

  /**
   * What the co-presence charts draw: the `copresenceTopN` most prevalent features
   * (statistics are still computed on all of them, and the pairs table lists all
   * significant pairs). Keeps each chart to one screen instead of one row per feature.
   */
  const copresenceView = computed(() => {
    const data = copresenceData.value
    const n = Math.floor(Number(copresenceTopN.value) || 0)
    if (n <= 0 || n >= data.features.length) return data
    const features = data.features.slice(0, n) // already sorted by prevalence
    const kept = new Set(features)
    return {
      ...data,
      features,
      matrix: data.matrix.slice(0, n).map(row => row.slice(0, n)),
      pairs: data.pairs.filter(p => kept.has(p.f1) && kept.has(p.f2)),
    }
  })

  const copresenceStats = computed(() => copresenceData.value.pairs)
  const copresenceStatsPaginated = computed(() => {
    const start = copresencePage.value * copresencePageSize
    return copresenceStats.value.slice(start, start + copresencePageSize)
  })

  // Functional annotations for features in the population
  const funcAnnotatedFeatures = computed(() => {
    const { features, prevalence } = copresenceView.value
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
      { key: 'language', label: t('results.language') },
      { key: 'data_type', label: t('results.dataType') },
      { key: 'population_size', label: t('results.populationSize') },
      { key: 'config_summary', label: t('results.config') },
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
      [isRegressionJob.value ? fitMetricLabel.value : 'AUC']: b.auc,
      [ct('Fit')]: b.fit,
      [ct('Accuracy')]: b.accuracy,
      [ct('Sensitivity')]: b.sensitivity,
      [ct('Specificity')]: b.specificity,
      [ct('Threshold')]: b.threshold,
      [ct('Language')]: b.language,
      [ct('Data type')]: b.data_type,
      [ct('Epoch')]: b.epoch,
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

  // Module filter integration
  const moduleFilteredIndices = computed(() => {
    if (!moduleFilterData.value) return null
    return new Set(moduleFilterData.value.filtered_models.map(m => m.index))
  })

  function onModuleFilterApplied(data) {
    moduleFilterData.value = data
  }

  function toggleExpand(rank) {
    expandedRank.value = expandedRank.value === rank ? null : rank
  }

  function toggleBasketExpand(id) {
    basketExpandedId.value = basketExpandedId.value === id ? null : id
  }

  async function confirmClearBasket() {
    if (await confirmDialog({ message: t('results.basketConfirmClear'), danger: true })) {
      clearBasket()
    }
  }

  const basketFeatureIntersection = computed(() => {
    if (basketItems.value.length < 2) return []
    const sets = basketItems.value.map(item => new Set(Object.keys(item.named_features || {})))
    let common = new Set(sets[0])
    for (let i = 1; i < sets.length; i++) {
      common = new Set([...common].filter(f => sets[i].has(f)))
    }
    return [...common].sort()
  })

  const basketFeatureUnion = computed(() => {
    if (basketItems.value.length < 2) return []
    const all = new Set()
    for (const item of basketItems.value) {
      for (const name of Object.keys(item.named_features || {})) all.add(name)
    }
    return [...all].sort()
  })

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
      const { data } = await api.dataExplore.mspAnnotations({ features: names }, { silentError: true })
      mspAnnotations.value = data.annotations || {}
    } catch (e) {
      ignoreError(e) // species names are optional
    }
  }

  // ---------------------------------------------------------------------------
  // SUMMARY CHARTS
  // Text equivalents of the key charts: what the picture shows, in a sentence.
  const convergenceSummary = computed(() => {
    const g = generationTracking.value
    if (!g.length) return ''
    const metric = isRegressionJob.value ? fitMetricLabel.value : 'AUC'
    const fmt = v => (typeof v === 'number' ? v.toFixed(3) : '—')
    const first = g[0], last = g[g.length - 1]
    const base = t('results.summaryConvergence', { n: g.length, metric, from: fmt(first.best_auc), to: fmt(last.best_auc) })
    return last.best_auc_test != null ? `${base} ${t('results.summaryConvergenceTest', { metric, value: fmt(last.best_auc_test) })}` : base
  })

  const complexitySummary = computed(() => {
    const ks = generationTracking.value.map(g => g.best_k).filter(k => typeof k === 'number')
    if (!ks.length) return ''
    return t('results.summaryComplexity', { from: ks[0], to: ks[ks.length - 1], min: Math.min(...ks), max: Math.max(...ks) })
  })

  const coefficientsSummary = computed(() => {
    const feats = detail.value?.best_individual?.features
    if (!feats) return ''
    const coefs = Object.values(feats).map(Number)
    if (!coefs.length) return ''
    return t('results.summaryCoefficients', { n: coefs.length, pos: coefs.filter(c => c > 0).length, neg: coefs.filter(c => c < 0).length })
  })

  // ---------------------------------------------------------------------------
  async function renderConvergenceChart() {
    await nextTick()
    if (!convergenceChartEl.value || generationTracking.value.length === 0) return

    const c = chartColors()
    const gens = generationTracking.value.map(g => g.generation)
    const trainAuc = generationTracking.value.map(g => g.best_auc)
    const hasTest = generationTracking.value.some(g => g.best_auc_test != null)
    const testAuc = hasTest ? generationTracking.value.map(g => g.best_auc_test) : null

    const metricName = isRegressionJob.value ? fitMetricLabel.value : 'AUC'
    const traces = [{
      x: gens, y: trainAuc, name: t('charts.trainMetric', { metric: metricName }), type: 'scatter', mode: 'lines+markers',
      line: { color: c.class0, width: 2 }, marker: { size: 4 },
    }]
    if (testAuc) {
      traces.push({
        x: gens, y: testAuc, name: t('charts.testMetric', { metric: metricName }), type: 'scatter', mode: 'lines+markers',
        line: { color: c.danger, width: 2, dash: 'dash' }, marker: { size: 4 },
      })
    }

    const allValues = [...trainAuc, ...(testAuc || [])]
    Plotly.newPlot(convergenceChartEl.value, traces, chartLayout({
      xaxis: { title: { text: ct('Generation'), font: { color: c.text } }, dtick: Math.max(1, Math.floor(gens.length / 10)), gridcolor: c.grid, color: c.text },
      yaxis: { title: { text: metricName, font: { color: c.text } }, range: [Math.max(0, Math.min(...allValues) - 0.05), Math.min(1, Math.max(...allValues) + 0.02)], gridcolor: c.grid, color: c.text },
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
      name: ct('k (features)'),
    }], chartLayout({
      xaxis: { title: { text: ct('Generation'), font: { color: c.text } }, dtick: Math.max(1, Math.floor(gens.length / 10)), gridcolor: c.grid, color: c.text },
      // nticks, not dtick: 1 — with k up to 200 a tick per integer is unreadable.
      yaxis: { title: { text: 'k', font: { color: c.text } }, gridcolor: c.grid, color: c.text, nticks: 8, tickformat: 'd', rangemode: 'tozero' },
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

    const aucLabel = isRegressionJob.value ? fitMetricLabel.value : 'AUC'
    Plotly.newPlot(fitEvolutionChartEl.value, [
      { x: gens, y: aucs, name: aucLabel, type: 'scatter', mode: 'lines', line: { color: c.class0, width: 2 } },
      { x: gens, y: fits, name: ct('Fit'), type: 'scatter', mode: 'lines', line: { color: c.warn, width: 2, dash: 'dot' } },
    ], chartLayout({
      xaxis: { title: { text: ct('Generation'), font: { color: c.text } }, dtick: Math.max(1, Math.floor(gens.length / 10)), gridcolor: c.grid, color: c.text },
      yaxis: { title: { text: ct('Value'), font: { color: c.text } }, gridcolor: c.grid, color: c.text },
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
        title: { text: ct('Coefficient'), font: { color: c.text } },
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
    const categories = [isRegressionJob.value ? fitMetricLabel.value : 'AUC', ct('Accuracy'), ct('Sensitivity'), ct('Specificity')]
    const values = [b.auc, b.accuracy, b.sensitivity, b.specificity]

    Plotly.newPlot(radarChartEl.value, [{
      type: 'scatterpolar',
      r: [...values, values[0]],
      theta: [...categories, categories[0]],
      fill: 'toself',
      fillcolor: c.class0Alpha,
      line: { color: c.class0, width: 2 },
      marker: { size: 5, color: c.class0 },
      name: ct('Best Model'),
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
      xaxis: { title: { text: ct('Importance (MDA)'), font: { color: c.text } }, gridcolor: c.grid, color: c.text },
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
        type: 'bar', orientation: 'h', name: ct('Negative'),
        y: negEntries.map(e => e.name), x: negEntries.map(e => e.coef),
        marker: { color: c.negativeAlpha, line: { color: c.negative, width: 1.5 } },
        hovertemplate: '%{y}: %{x}<extra></extra>',
      })
    }
    if (posEntries.length) {
      traces.push({
        type: 'bar', orientation: 'h', name: ct('Positive'),
        y: posEntries.map(e => e.name), x: posEntries.map(e => e.coef),
        marker: { color: c.positiveAlpha, line: { color: c.positive, width: 1.5 } },
        hovertemplate: '%{y}: %{x}<extra></extra>',
      })
    }
    Plotly.newPlot(directionChartEl.value, traces, chartLayout({
      xaxis: { title: { text: ct('Coefficient'), font: { color: c.text } }, gridcolor: c.grid, color: c.text, zeroline: true, zerolinecolor: c.text, zerolinewidth: 1 },
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
      x: [...entries.map(e => e.name), ct('Total')],
      y: [...entries.map(e => e.coef), null],
      measure: [...entries.map(() => 'relative'), 'total'],
      connector: { line: { color: c.grid, width: 1 } },
      increasing: { marker: { color: c.positiveAlpha, line: { color: c.positive, width: 1.5 } } },
      decreasing: { marker: { color: c.negativeAlpha, line: { color: c.negative, width: 1.5 } } },
      totals: { marker: { color: c.accent + '66', line: { color: c.accent, width: 1.5 } } },
      hovertemplate: '%{x}: %{y}<extra></extra>',
    }], chartLayout({
      xaxis: { color: c.text, tickangle: -45 },
      yaxis: { title: { text: ct('Cumulative Contribution'), font: { color: c.text } }, gridcolor: c.grid, color: c.text },
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
      const { data } = await api.dataExplore.barcode(pid, {
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
      toast.error(t('results.contributionFailed', { error: apiError(e) }))
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
      ...signCells(matrix),
      x: samples,
      y: features.map(f => featureLabel(f)),
      colorscale: c.diverging,
      zmid: 0,
      hovertemplate: `${ct('Sample')}: %{x}<br>${ct('Feature')}: %{y}<br>${ct('Contribution')}: %{z:.4f}<extra></extra>`,
    }], chartLayout({
      xaxis: { color: c.text, showticklabels: samples.length <= 100, tickangle: -90, tickfont: { size: 10 } },
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
    if (shapData.value) renderShapActiveView()
  }

  // ---------------------------------------------------------------------------
  // SHAP EXPLANATIONS
  // ---------------------------------------------------------------------------

  async function loadShapData() {
    if (!detail.value?.best_individual) return
    shapLoading.value = true
    try {
      const pid = route.params.id
      const b = detail.value.best_individual
      const fNames = Object.entries(b.features).map(([idx]) => featureName(parseInt(idx)))
      const { data } = await api.dataExplore.barcode(pid, {
        params: { features: fNames.join(','), max_samples: 500 }
      })
      const allFeatureNames = detail.value.feature_names || fullResults.value?.feature_names || []
      shapData.value = computeShapMatrix(data, b, allFeatureNames)
      shapSampleIdx.value = 0
      shapFeatureIdx.value = shapData.value.featureImportance[0]?.index || 0
      await nextTick()
      renderShapActiveView()
    } catch (e) {
      toast.error(t('results.shapFailed', { error: apiError(e) }))
    } finally {
      shapLoading.value = false
    }
  }

  function renderShapActiveView() {
    if (!shapData.value) return
    if (shapView.value === 'beeswarm') renderBeeswarmChart()
    else if (shapView.value === 'force') renderForceChart()
    else if (shapView.value === 'dependence') renderDependenceChart()
  }

  async function renderBeeswarmChart() {
    await nextTick()
    if (!beeswarmChartEl.value || !shapData.value) return
    const c = chartColors()
    const { shapMatrix, featureValues, featureImportance } = shapData.value

    // Order features by importance (most important at top)
    const ordered = [...featureImportance].reverse()
    const traces = []

    for (const { name, index: fi } of ordered) {
      const shapRow = shapMatrix[fi]
      const valRow = featureValues[fi]
      // Add small vertical jitter for visibility
      const jitter = shapRow.map(() => (Math.random() - 0.5) * 0.3)

      traces.push({
        type: 'scatter',
        mode: 'markers',
        name: featureLabel(name),
        x: shapRow,
        y: jitter.map(j => featureImportance.length - 1 - ordered.indexOf(ordered.find(o => o.name === name)) + j),
        marker: {
          size: 4,
          color: valRow,
          colorscale: c.scaleUniform,
          opacity: 0.7,
          colorbar: traces.length === 0 ? { title: ct('Feature value'), thickness: 12, len: 0.5 } : undefined,
        },
        hovertemplate: `${featureLabel(name)}<br>SHAP: %{x:.4f}<br>${ct('Value')}: %{marker.color:.4f}<extra></extra>`,
        showlegend: false,
      })
    }

    const yLabels = ordered.map(f => featureLabel(f.name))
    Plotly.newPlot(beeswarmChartEl.value, traces, chartLayout({
      xaxis: { title: ct('SHAP value (impact on prediction)'), color: c.text, gridcolor: c.grid, zeroline: true, zerolinecolor: c.grid },
      yaxis: {
        tickvals: ordered.map((_, i) => i),
        ticktext: yLabels,
        color: c.text,
        automargin: true,
      },
      height: Math.max(300, ordered.length * 30 + 100),
      margin: { t: 10, b: 50, l: 180, r: 80 },
    }), { responsive: true, displayModeBar: false })
  }

  async function renderForceChart() {
    await nextTick()
    if (!forceChartEl.value || !shapData.value) return
    const c = chartColors()
    const { shapMatrix, featureImportance } = shapData.value
    const si = shapSampleIdx.value

    // Get SHAP values for this sample, sorted by absolute value
    const contributions = featureImportance.map(f => ({
      name: f.name,
      shap: shapMatrix[f.index][si],
    })).sort((a, b) => Math.abs(b.shap) - Math.abs(a.shap))

    const labels = contributions.map(c => featureLabel(c.name))
    const values = contributions.map(c => c.shap)
    const shapColors = chartColors()
    const colors = values.map(v => v >= 0 ? shapColors.class1 : shapColors.class0)

    // Waterfall: cumulative from base=0
    const base = []
    let cumulative = 0
    for (const v of values) {
      base.push(v >= 0 ? cumulative : cumulative + v)
      cumulative += v
    }

    Plotly.newPlot(forceChartEl.value, [{
      type: 'bar',
      orientation: 'h',
      x: values.map(Math.abs),
      y: labels,
      base: base,
      marker: { color: colors },
      hovertemplate: '%{y}<br>SHAP: %{x:.4f}<extra></extra>',
    }], chartLayout({
      xaxis: { title: ct('Cumulative SHAP value'), color: c.text, gridcolor: c.grid },
      yaxis: { automargin: true, color: c.text, autorange: 'reversed' },
      height: Math.max(250, contributions.length * 25 + 80),
      margin: { t: 10, b: 50, l: 180, r: 20 },
      annotations: [{
        x: cumulative, y: -0.5,
        text: `${ct('Score')}: ${cumulative.toFixed(4)}`,
        showarrow: false, font: { color: c.text, size: 11 },
        yref: 'paper', yanchor: 'top',
      }],
    }), { responsive: true, displayModeBar: false })
  }

  async function renderDependenceChart() {
    await nextTick()
    if (!dependenceChartEl.value || !shapData.value) return
    const c = chartColors()
    const { shapMatrix, featureNames, featureValues, sampleClasses } = shapData.value
    const fi = shapFeatureIdx.value
    if (fi >= featureNames.length) return

    const xVals = featureValues[fi]
    const yVals = shapMatrix[fi]
    const classLabels = sampleClasses.map(cl => classNameFor(cl === 0 ? 0 : 1))
    const classColors = sampleClasses.map(cl => classStyle(cl === 0 ? 0 : 1).color)
    const classSymbols = sampleClasses.map(cl => classStyle(cl === 0 ? 0 : 1).symbol)

    Plotly.newPlot(dependenceChartEl.value, [{
      type: 'scatter',
      mode: 'markers',
      x: xVals,
      y: yVals,
      marker: { size: 6, color: classColors, symbol: classSymbols, opacity: 0.7 },
      text: classLabels,
      hovertemplate: `${ct('Value')}: %{x:.4f}<br>SHAP: %{y:.4f}<br>%{text}<extra></extra>`,
    }], chartLayout({
      xaxis: { title: featureLabel(featureNames[fi]), color: c.text, gridcolor: c.grid },
      yaxis: { title: ct('SHAP value'), color: c.text, gridcolor: c.grid },
      height: 350,
      margin: { t: 10, b: 50, l: 60, r: 20 },
    }), { responsive: true, displayModeBar: false })
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
    const dtColors = c.series

    const traces = dataTypes.map((dt, i) => ({
      type: 'bar',
      name: dt,
      x: languages,
      y: languages.map(lang => counts[`${lang}|${dt}`] || 0),
      marker: { color: dtColors[i % dtColors.length] },
    }))

    Plotly.newPlot(compositionChartEl.value, traces, chartLayout({
      barmode: 'group',
      xaxis: { title: { text: ct('Language'), font: { color: c.text } }, color: c.text },
      yaxis: { title: { text: ct('Count'), font: { color: c.text } }, gridcolor: c.grid, color: c.text },
      legend: { orientation: 'h', y: 1.12, font: { color: c.text } },
      height: 300,
      margin: { t: 30, b: 50, l: 60, r: 20 },
    }), { responsive: true, displayModeBar: false })
  }

  async function renderMetricsByType() {
    await nextTick()
    if (!metricsByTypeEl.value || filteredPopulation.value.length === 0) return

    const c = chartColors()
    // Group metric by language
    const byLang = {}
    for (const ind of filteredPopulation.value) {
      const lang = ind.metrics?.language || 'unknown'
      if (!byLang[lang]) byLang[lang] = []
      if (ind.metrics?.auc != null) byLang[lang].push(ind.metrics.auc)
    }

    const languages = Object.keys(byLang).sort()
    const langColors = c.series

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
      yaxis: { title: { text: isRegressionJob.value ? fitMetricLabel.value : 'AUC', font: { color: c.text } }, range: [0, 1.05], gridcolor: c.grid, color: c.text },
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
    const colorscale = c.divergingSoft

    // Prevalence annotations on right
    const annotations = sortedFeatures.map((name, i) => ({
      text: `${((featureInfo[name].count / topN) * 100).toFixed(0)}%`,
      x: topN + 0.5,
      y: i,
      xref: 'x', yref: 'y',
      showarrow: false,
      font: { color: c.dimmed, size: 10 },
    }))

    Plotly.newPlot(featureHeatmapEl.value, [{
      type: 'heatmap',
      z: matrix,
      ...signCells(matrix),
      x: Array.from({ length: topN }, (_, i) => i + 1),
      y: sortedFeatures.map(n => featureLabel(n)),
      colorscale,
      zmin: -1, zmax: 1,
      showscale: true,
      colorbar: {
        title: { text: ct('Coeff'), font: { color: c.text, size: 10 } },
        tickvals: [-1, 0, 1], ticktext: ['-1', '0', '+1'],
        tickfont: { color: c.text, size: 10 },
        len: 0.5, thickness: 12,
      },
      xgap: 0.5,
      ygap: 0.5,
      hovertemplate: `${ct('Feature')}: %{y}<br>${ct('Model')} #%{x}<br>${ct('Coeff')}: %{z}<extra></extra>`,
    }], chartLayout({
      xaxis: { title: { text: ct('Model Rank'), font: { color: c.text } }, gridcolor: c.grid, color: c.text },
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
        type: 'bar', orientation: 'h', name: ct('Positive (+1)'),
        y: features.map(n => featureLabel(n)),
        x: features.map(n => featureInfo[n].pos),
        marker: { color: c.positiveAlpha, line: { color: c.positive, width: 1 } },
      },
      {
        type: 'bar', orientation: 'h', name: ct('Negative (-1)'),
        y: features.map(n => featureLabel(n)),
        x: features.map(n => featureInfo[n].neg),
        marker: { color: c.negativeAlpha, line: { color: c.negative, width: 1 } },
      },
    ], chartLayout({
      barmode: 'stack',
      xaxis: { title: { text: ct('Count (models)'), font: { color: c.text } }, gridcolor: c.grid, color: c.text },
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
      yaxis: { title: { text: ct('Value'), font: { color: c.text } }, range: [0, 1.05], gridcolor: c.grid, color: c.text },
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
    loadPopPcoa()
  }

  // ---------------------------------------------------------------------------
  // PCoA on FBM features (in Population sub-tab)
  // ---------------------------------------------------------------------------
  async function loadPopPcoa() {
    const pop = filteredPopulation.value
    if (pop.length === 0) return

    // Collect unique feature names from the filtered population
    const nameSet = new Set()
    for (const ind of pop) {
      if (ind.named_features) {
        Object.keys(ind.named_features).forEach(f => nameSet.add(f))
      }
    }
    const featureNames = [...nameSet]
    if (featureNames.length === 0) return

    const pid = route.params.id
    loadingPopPcoa.value = true
    try {
      const params = { method: popPcoaMethod.value, metric: popPcoaMetric.value, features: featureNames.join(',') }
      if (popPcoaMethod.value === 'tsne') {
        params.perplexity = popTsnePerplexity.value
      } else if (popPcoaMethod.value === 'umap') {
        params.n_neighbors = popUmapNeighbors.value
        params.min_dist = popUmapMinDist.value
      }
      if (popPcoaDim.value === '3d') params.n_components = 3
      const { data } = await api.dataExplore.ordination(pid, { params, timeout: LONG_TIMEOUT_MS })
      popPcoaData.value = data
      await nextTick()
      renderPopPcoaChart()
    } catch (e) {
      toast.error(t('results.ordinationFailed', { error: apiError(e) }))
      popPcoaData.value = null
    } finally {
      loadingPopPcoa.value = false
    }
  }

  async function renderPopPcoaChart() {
    await nextTick()
    const P = await ensurePlotly()
    if (!popPcoaChartEl.value || !popPcoaData.value) return
    const c = chartColors()
    // A response without class labels (unlabelled or partial data) must not break the chart.
    const d = { ...popPcoaData.value, class_labels: popPcoaData.value.class_labels || [] }
    const ve = d.variance_explained
    const method = d.method || popPcoaMethod.value

    const axisLabel = (dim) => {
      if (method === 'pcoa' && ve) return `PCo${dim} (${ve[dim - 1]}%)`
      if (method === 'tsne') return `t-SNE ${dim}`
      if (method === 'umap') return `UMAP ${dim}`
      return `${ct('Dim')} ${dim}`
    }
    const hoverPrefix = method === 'pcoa' ? 'PCo' : method === 'tsne' ? 't-SNE ' : method === 'umap' ? 'UMAP ' : `${ct('Dim')} `

    // Colour and marker symbol per class: the symbol keeps classes apart without colour.
    const classColorMap = {}
    const classSymbolMap = {}
    d.class_labels.forEach((lbl, i) => {
      const style = classStyle(i)
      classColorMap[lbl] = style.color
      classSymbolMap[lbl] = style.symbol
    })

    if (popPcoaDim.value === '3d') {
      await loadPlotly3d()
      if (!popPcoaChartEl.value) return
      const traces = d.class_labels.map(cls => {
        const mask = d.sample_classes.map((sc, i) => String(sc) === cls ? i : -1).filter(i => i >= 0)
        return {
          x: mask.map(i => d.coords[i][0]),
          y: mask.map(i => d.coords[i][1]),
          z: mask.map(i => d.coords[i][2]),
          text: mask.map(i => d.sample_names[i]),
          mode: 'markers', type: 'scatter3d',
          name: classNameFor(cls),
          marker: { color: classColorMap[cls], symbol: classSymbolMap[cls], size: 4, opacity: 0.85 },
          hovertemplate: `%{text}<br>${hoverPrefix}1: %{x:.3f}<br>${hoverPrefix}2: %{y:.3f}<br>${hoverPrefix}3: %{z:.3f}<extra></extra>`,
        }
      })
      P.newPlot(popPcoaChartEl.value, traces, {
        ...chartLayout({ height: 550 }),
        scene: {
          xaxis: { title: { text: axisLabel(1), font: { color: c.text } }, gridcolor: c.grid, color: c.text },
          yaxis: { title: { text: axisLabel(2), font: { color: c.text } }, gridcolor: c.grid, color: c.text },
          zaxis: { title: { text: axisLabel(3), font: { color: c.text } }, gridcolor: c.grid, color: c.text },
          bgcolor: c.paper,
        },
        legend: { orientation: 'h', y: -0.05, font: { color: c.text } },
      }, { responsive: true, displayModeBar: true })
    } else {
      const traces = d.class_labels.map(cls => {
        const mask = d.sample_classes.map((sc, i) => String(sc) === cls ? i : -1).filter(i => i >= 0)
        return {
          x: mask.map(i => d.coords[i][0]),
          y: mask.map(i => d.coords[i][1]),
          text: mask.map(i => d.sample_names[i]),
          mode: 'markers', type: 'scatter',
          name: classNameFor(cls),
          marker: { color: classColorMap[cls], symbol: classSymbolMap[cls], size: 7, opacity: 0.8, line: { color: classColorMap[cls], width: 0.5 } },
          hovertemplate: `%{text}<br>${hoverPrefix}1: %{x:.3f}<br>${hoverPrefix}2: %{y:.3f}<extra></extra>`,
        }
      })

      // Confidence ellipses
      if (popPcoaShowEllipses.value && d.ellipses) {
        for (const cls of d.class_labels) {
          const ell = d.ellipses[cls]
          if (!ell) continue
          traces.push({
            x: ell.x, y: ell.y,
            mode: 'lines', type: 'scatter',
            name: t('charts.ciForClass', { name: classNameFor(cls) }),
            line: { color: classColorMap[cls], width: 2, dash: 'dash' },
            fill: 'toself',
            fillcolor: classColorMap[cls] + '18',
            hoverinfo: 'skip', showlegend: false,
          })
        }
      }

      P.newPlot(popPcoaChartEl.value, traces, chartLayout({
        xaxis: { title: { text: axisLabel(1), font: { color: c.text } }, gridcolor: c.grid, color: c.text, zeroline: true, zerolinecolor: c.grid },
        yaxis: { title: { text: axisLabel(2), font: { color: c.text } }, gridcolor: c.grid, color: c.text, zeroline: true, zerolinecolor: c.grid },
        legend: { orientation: 'h', y: 1.12, font: { color: c.text } },
        height: 500,
      }), { responsive: true, displayModeBar: false })
    }
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
    const labels = [isRegressionJob.value ? fitMetricLabel.value : 'AUC', ct('Accuracy'), ct('Sensitivity'), ct('Specificity')]

    const traces = [
      {
        type: 'bar', name: ct('Best Individual (Train)'),
        x: labels, y: metricNames.map(m => b[m] ?? 0),
        marker: { color: c.class0Alpha, line: { color: c.class0, width: 1.5 } },
      },
      {
        type: 'bar', name: ct('Jury (Train)'),
        x: labels, y: metricNames.map(m => j.train?.[m] ?? 0),
        marker: { color: c.accentAlpha, line: { color: c.accent, width: 1.5 } },
      },
      {
        type: 'bar', name: ct('Jury (Test)'),
        x: labels, y: metricNames.map(m => j.test?.[m] ?? 0),
        marker: { color: c.class1Alpha, line: { color: c.class1, width: 1.5 } },
      },
    ]

    Plotly.newPlot(juryComparisonEl.value, traces, chartLayout({
      barmode: 'group',
      yaxis: { title: { text: ct('Value'), font: { color: c.text } }, range: [0, 1.05], gridcolor: c.grid, color: c.text },
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
    const xLabels = classes.map(cl => classNameFor(cl))

    const traces = [
      {
        type: 'bar', name: ct('Correct'),
        x: xLabels, y: classes.map(cl => tally[cl].correct),
        marker: { color: c.class0Alpha, line: { color: c.class0, width: 1.5 } },
      },
      {
        type: 'bar', name: ct('Error'),
        x: xLabels, y: classes.map(cl => tally[cl].error),
        marker: { color: c.class1Alpha, line: { color: c.class1, width: 1.5 }, pattern: { shape: '/', fgcolor: c.class1, fgopacity: 0.6, size: 6 } },
      },
      {
        type: 'bar', name: ct('Rejected'),
        x: xLabels, y: classes.map(cl => tally[cl].rejected),
        marker: { color: c.highlightAlpha, line: { color: c.highlight, width: 1.5 }, pattern: { shape: 'x', fgcolor: c.highlight, fgopacity: 0.5, size: 6 } },
      },
    ]

    Plotly.newPlot(juryConcordanceEl.value, traces, chartLayout({
      barmode: 'stack',
      yaxis: { title: { text: ct('Samples'), font: { color: c.text } }, gridcolor: c.grid, color: c.text },
      xaxis: { color: c.text },
      height: 200,
      legend: { orientation: 'h', y: 1.2, font: { color: c.text } },
      margin: { t: 30, b: 40, l: 50, r: 10 },
    }), { responsive: true, displayModeBar: false })
  }

  async function renderConfusionMatrix(el, cmData) {
    await nextTick()
    if (!el || !cmData) return

    const c = chartColors()
    const hasAbstain = (cmData.abstain_1 != null && cmData.abstain_1 > 0) ||
                       (cmData.abstain_0 != null && cmData.abstain_0 > 0)

    // Main confusion cells (predicted class 1, predicted class 0)
    const predLabels = [t('charts.predictedClass', { name: classNameFor(1) }), t('charts.predictedClass', { name: classNameFor(0) })]
    const traces = [{
      type: 'heatmap',
      z: [[cmData.tp, cmData.fn], [cmData.fp, cmData.tn]],
      x: predLabels.slice(),
      y: [t('charts.actualClass', { name: classNameFor(1) }), t('charts.actualClass', { name: classNameFor(0) })],
      text: [[String(cmData.tp), String(cmData.fn)], [String(cmData.fp), String(cmData.tn)]],
      texttemplate: '%{text}',
      colorscale: [[0, c.paper], [1, c.class0Alpha]],
      showscale: false,
      xgap: 2, ygap: 2,
      hovertemplate: '%{y} / %{x}: %{z}<extra></extra>',
    }]

    const xLabels = predLabels.slice()

    // Add rejection column if present
    if (hasAbstain) {
      xLabels.push(ct('Rejected'))
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
          fillcolor: c.highlightAlpha, line: { width: 0 }, layer: 'below',
        },
        {
          type: 'rect', xref: 'x', yref: 'y',
          x0: 1.5, x1: 2.5, y0: 0.5, y1: 1.5,
          fillcolor: c.highlightAlpha, line: { width: 0 }, layer: 'below',
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
      { label: t('charts.correctFor', { name: classNameFor(0) }), filter: s => s.correct && s.real === 0, color: c.class0Light, symbol: 'circle' },
      { label: t('charts.correctFor', { name: classNameFor(1) }), filter: s => s.correct && s.real === 1, color: c.class1Light, symbol: 'circle' },
      { label: ct('Error'), filter: s => !s.correct && s.predicted !== -1 && s.predicted !== 2, color: c.class1Light, symbol: 'x' },
      { label: ct('Rejected'), filter: s => s.predicted === -1 || s.predicted === 2, color: c.highlight, symbol: 'diamond' },
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
          line: { color: g.symbol === 'x' ? c.class1 : c.edge, width: 1 },
        },
        hovertemplate: `%{y}<br>${ct('Consistency')}: %{x:.1f}%<extra>${g.label}</extra>`,
      }
    }).filter(Boolean)

    const chartHeight = Math.max(200, preds.length * 22 + 60)

    Plotly.newPlot(samplePredictionsEl.value, traces, chartLayout({
      xaxis: {
        title: { text: ct('Consistency (%)'), font: { color: c.text } },
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

    // Build annotations for class separators

    // predomicspkg colorscale: 0=deepskyblue (class 0), 1=firebrick (class 1) with transparency
    const colorscale = [
      [0, c.class0Alpha],
      [1, c.class1Alpha],
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
        tickvals: [0, 1], ticktext: [classNameFor(0), classNameFor(1)],
        tickfont: { color: c.text, size: 10 }, len: 0.4, thickness: 10,
      },
      hovertemplate: `${ct('Sample')}: %{y}<br>${ct('Expert')}: %{x}<br>${ct('Vote')}: %{z}<extra></extra>`,
      xgap: 0.5,
      ygap: 0.5,
    }], chartLayout({
      xaxis: {
        title: { text: ct('Experts'), font: { color: c.text, size: 11 } },
        color: c.text,
        tickfont: { size: 10 },
        showticklabels: vm.n_experts <= 50,
      },
      yaxis: {
        color: c.text,
        automargin: true,
        tickfont: { size: 10 },
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
    const { features, prevalence, accuracy } = copresenceView.value
    if (features.length === 0) return

    const c = chartColors()
    const sorted = [...features].sort((a, b) => prevalence[a] - prevalence[b])
    const N = copresencePopulation.value.length
    const weighted = copresenceWeighted.value

    const traces = [{
      type: 'bar',
      orientation: 'h',
      y: sorted.map(n => featureLabel(n)),
      x: sorted.map(n => prevalence[n]),
      text: sorted.map(n => `${((prevalence[n] / N) * 100).toFixed(0)}%`),
      textposition: 'outside',
      name: t('results.minPrevalence'),
      marker: {
        color: sorted.map(n => {
          const pct = prevalence[n] / N
          return pct > 0.75 ? c.accent : pct > 0.5 ? c.class0Light : c.class1Light
        }),
      },
      hovertemplate: `%{y}: %{x} ${ct('models')} (%{text})<extra></extra>`,
    }]

    const layout = {
      xaxis: { title: { text: ct('Models containing feature'), font: { color: c.text } }, gridcolor: c.grid, color: c.text },
      yaxis: { automargin: true, color: c.text },
      height: Math.max(300, sorted.length * 22 + 80),
      margin: { t: 20, b: 50, l: 200, r: weighted ? 80 : 60 },
      showlegend: weighted,
    }

    if (weighted) {
      traces.push({
        type: 'scatter',
        mode: 'markers',
        y: sorted.map(n => featureLabel(n)),
        x: sorted.map(n => accuracy[n]),
        name: t('results.meanAccuracy'),
        xaxis: 'x2',
        marker: { color: c.danger, size: 7, symbol: 'diamond' },
        hovertemplate: `%{y}: ${ct('Mean accuracy')} = %{x:.3f}<extra></extra>`,
      })
      layout.xaxis2 = {
        title: { text: t('results.meanAccuracy'), font: { color: c.danger } },
        overlaying: 'x', side: 'top', gridcolor: 'transparent', color: c.danger,
        range: [0, 1],
      }
      layout.legend = { orientation: 'h', y: -0.15, font: { color: c.text } }
    }

    Plotly.newPlot(copresencePrevalenceEl.value, traces, chartLayout(layout), { responsive: true, displayModeBar: false })
  }

  async function renderCopresenceHeatmap() {
    await nextTick()
    if (!copresenceHeatmapEl.value) return
    const { features, matrix } = copresenceView.value
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
      colorscale: c.scaleUniform,
      zmin: 0,
      zmax: maxRatio,
      showscale: true,
      colorbar: {
        title: { text: ct('Obs/Exp'), font: { color: c.text, size: 10 } },
        tickfont: { color: c.text, size: 10 },
        len: 0.5, thickness: 12,
      },
      xgap: 1,
      ygap: 1,
      hovertemplate: `%{y} × %{x}<br>${ct('Observed / expected')}: %{z:.2f}<extra></extra>`,
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
    const { features, prevalence, accuracy, pairs } = copresenceView.value
    if (features.length < 2 || pairs.length === 0) return

    const c = chartColors()
    const N = copresencePopulation.value.length
    const nNodes = features.length
    const weighted = copresenceWeighted.value

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

    // Draw edges (width based on weighted ratio when in weighted mode)
    const edgeTraces = []
    for (const pair of pairs) {
      const i = featureIdx[pair.f1]
      const j = featureIdx[pair.f2]
      if (i === undefined || j === undefined) continue
      const isPos = pair.type === 'positive'
      const edgeStrength = weighted ? Math.max(0.5, pair.wRatio) : pair.strength
      edgeTraces.push({
        type: 'scatter', mode: 'lines',
        x: [nodeX[i], nodeX[j], null],
        y: [nodeY[i], nodeY[j], null],
        line: {
          color: isPos ? withAlpha(chartColors().good, 0.5) : chartColors().edgeNegative,
          width: weighted ? Math.min(5, 1 + edgeStrength * 0.8) : Math.min(4, 1 + pair.strength * 0.3),
          dash: isPos ? 'solid' : 'dash',
        },
        hoverinfo: 'skip',
        showlegend: false,
      })
    }

    // Draw nodes — size by mean accuracy when weighted, prevalence otherwise
    const maxPrev = Math.max(...features.map(f => prevalence[f]))
    const maxAcc = Math.max(...features.map(f => accuracy[f] || 0), 0.01)
    const nodeTrace = {
      type: 'scatter', mode: 'markers+text',
      x: nodeX,
      y: nodeY,
      text: features.map(f => featureLabel(f)),
      textposition: 'top center',
      textfont: { color: c.text, size: 10 },
      marker: {
        size: features.map(f => weighted
          ? 10 + ((accuracy[f] || 0) / maxAcc) * 25
          : 10 + (prevalence[f] / maxPrev) * 25
        ),
        color: features.map(f => {
          if (weighted) {
            const acc = accuracy[f] || 0
            return acc > 0.85 ? c.accent : acc > 0.7 ? c.class0Light : c.class1Light
          }
          const pct = prevalence[f] / N
          return pct > 0.75 ? c.accent : pct > 0.5 ? c.class0Light : c.class1Light
        }),
        line: { color: c.text, width: 1 },
        opacity: 0.85,
      },
      hovertemplate: weighted
        ? `%{text}<br>${ct('Prevalence')}: %{customdata[0]} ${ct('models')}<br>${ct('Mean accuracy')}: %{customdata[1]:.3f}<extra></extra>`
        : `%{text}<br>${ct('Prevalence')}: %{customdata[0]} ${ct('models')}<extra></extra>`,
      customdata: features.map(f => [prevalence[f], accuracy[f] || 0]),
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

    // Count features by functional property
    const props = FUNC_PROPS
    const propColors = [c.series[0], c.series[1], c.series[3], c.series[2]]

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
        title: { text: ct('Annotation value (-1, 0, +1)'), font: { color: c.text } },
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
  /** Colour of the i-th compared job (theme palette, cycles). */
  function jobColor(i) {
    const series = chartColors().series
    return series[i % series.length]
  }
  /** Line dash of the i-th compared job, so overlaid curves differ without colour. */
  const JOB_DASHES = ['solid', 'dash', 'dot', 'dashdot', 'longdash', 'longdashdot']

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
        const { data } = await api.analysis.jobResults(pid, jid)
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
    const labels = [isRegressionJob.value ? fitMetricLabel.value : 'AUC', ct('Accuracy'), ct('Sensitivity'), ct('Specificity')]

    const traces = compareData.value.map((job, i) => {
      const col = jobColor(i)
      return {
        type: 'bar',
        name: jobLabel(job.jobId),
        x: labels,
        y: metricNames.map(m => job.best_individual?.[m] ?? 0),
        marker: { color: withAlpha(col, 0.35), line: { color: col, width: 1.5 } },
      }
    })

    Plotly.newPlot(comparisonBarEl.value, traces, chartLayout({
      barmode: 'group',
      yaxis: { title: { text: ct('Value'), font: { color: c.text } }, range: [0, 1.05], gridcolor: c.grid, color: c.text },
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
        line: { color: jobColor(i), width: 2, dash: JOB_DASHES[i % JOB_DASHES.length] },
        marker: { size: 4 },
      }
    })

    Plotly.newPlot(comparisonConvergenceEl.value, traces, chartLayout({
      xaxis: { title: { text: ct('Generation'), font: { color: c.text } }, gridcolor: c.grid, color: c.text },
      yaxis: { title: { text: isRegressionJob.value ? t('charts.bestMetric', { metric: fitMetricLabel.value }) : t('charts.bestMetric', { metric: 'AUC' }), font: { color: c.text } }, gridcolor: c.grid, color: c.text },
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
    const colorscale = c.divergingSoft

    Plotly.newPlot(featureOverlapEl.value, [{
      type: 'heatmap',
      z: matrix,
      ...signCells(matrix),
      x: compareData.value.map(j => jobLabel(j.jobId)),
      y: allFeatures.map(n => featureLabel(n)),
      colorscale,
      zmin: -1, zmax: 1,
      showscale: true,
      colorbar: {
        tickvals: [-1, 0, 1], ticktext: ['-1', '0', '+1'],
        tickfont: { color: c.text, size: 10 }, len: 0.5, thickness: 12,
      },
      xgap: 1,
      ygap: 1,
      hovertemplate: `%{y}<br>${ct('Job')} %{x}: %{z}<extra></extra>`,
    }], chartLayout({
      xaxis: { title: { text: ct('Job'), font: { color: c.text } }, color: c.text },
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
      const { data } = await api.analysis.jobLogs(pid, selectedJobId.value)
      const lines = (data.log || '').split('\n')
      failedJobLog.value = lines.slice(-50).join('\n')
    } catch (e) {
      failedJobLog.value = t('results.logUnavailable', { error: apiError(e) })
    }
  }

  async function loadConsoleLog() {
    if (!selectedJobId.value) return
    consoleLogLoading.value = true
    consoleLogContent.value = ''
    const pid = route.params.id
    try {
      const { data } = await api.analysis.jobLogs(pid, selectedJobId.value)
      consoleLogContent.value = data.log || ''
    } catch (e) {
      consoleLogContent.value = ''
      toast.error(t('results.logUnavailable', { error: apiError(e) }))
    } finally {
      consoleLogLoading.value = false
    }
  }

  function copyConsoleLog() {
    navigator.clipboard.writeText(consoleLogContent.value)
    consoleLogCopied.value = true
    setTimeout(() => { consoleLogCopied.value = false }, 2000)
  }

  function downloadConsoleLog() {
    const blob = new Blob([consoleLogContent.value], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${selectedJobId.value}_console.log`
    a.click()
    URL.revokeObjectURL(url)
  }

  // ---------------------------------------------------------------------------
  // Job table helpers
  // ---------------------------------------------------------------------------
  function selectJob(jobId, { updateUrl = true } = {}) {
    selectedJobId.value = jobId
    failedJobLog.value = ''
    consoleLogContent.value = ''
    if (updateUrl) syncUrl()
    loadJobResults()
  }

  /** Keep the selected job and section in the URL without adding history entries per click. */
  function syncUrl() {
    const pid = route.params.id
    const query = { ...route.query }
    if (subTab.value && subTab.value !== 'insights') query.tab = subTab.value
    else delete query.tab
    const target = selectedJobId.value
      ? { name: 'ProjectJobResults', params: { id: pid, jobId: selectedJobId.value }, query }
      : { name: 'ProjectResults', params: { id: pid }, query }
    if (route.params.jobId === selectedJobId.value && (route.query.tab || '') === (query.tab || '')) return
    // A different job is a step the Back button should undo; a tab change is not.
    const changedJob = (route.params.jobId || '') !== (selectedJobId.value || '')
    const nav = changedJob && route.params.jobId ? router.push(target) : router.replace(target)
    nav.catch(() => {})
  }

  function metricLabel(m) {
    const key = `results.metricNames.${m}`
    return te(key) ? t(key) : m.charAt(0).toUpperCase() + m.slice(1)
  }

  function jobAriaSort(key) {
    if (jobSortKey.value !== key) return 'none'
    return jobSortAsc.value ? 'ascending' : 'descending'
  }

  function openLog(job) {
    selectJob(job.job_id)
    if (isLive(job.status)) { showLiveConsole(job); return }
    subTab.value = 'console'
    loadConsoleLog()
  }

  function showLiveConsole(job) {
    store.startJob(job.job_id)
  }

  async function cancelJob(job) {
    if (!job || !isLive(job.status)) return
    if (!(await confirmDialog({ message: t('console.cancelConfirm'), confirmLabel: t('console.cancelJob'), cancelLabel: t('console.keepRunning'), danger: true }))) return
    cancellingId.value = job.job_id
    try {
      await api.analysis.cancelJob(route.params.id, job.job_id)
      toast.info(t('console.cancelRequested'))
      await loadJobList({ quiet: true })
    } catch (e) {
      toast.error(t('console.cancelFailed', { error: apiError(e) }))
    } finally {
      cancellingId.value = ''
    }
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
    if (diff < 86400000) return timeAgo(iso)
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
      const { data } = await api.analysis.duplicates(pid)
      duplicateGroups.value = data
      if (data.length === 0) toast.info(t('results.noDuplicates'))
    } catch (e) {
      toast.error(t('results.duplicatesFailed', { error: apiError(e) }))
    } finally {
      duplicatesLoading.value = false
    }
  }

  async function cleanupDuplicates() {
    const toDelete = duplicateGroups.value.flatMap(g => g.jobs.filter(j => !j.keep).map(j => j.job_id))
    if (toDelete.length === 0) return
    if (!(await confirmDialog({ message: t('results.deleteDuplicatesConfirm', toDelete.length), confirmLabel: t('common.delete'), danger: true }))) return
    const pid = route.params.id
    let deleted = 0
    for (const jid of toDelete) {
      try {
        await api.analysis.deleteJob(pid, jid, { silentError: true })
        deleted++
      } catch (e) { ignoreError(e) /* running jobs cannot be deleted: counted below */ }
    }
    duplicateGroups.value = []
    await loadJobList()
    if (selectedJobId.value && toDelete.includes(selectedJobId.value)) {
      selectedJobId.value = ''
      detail.value = null
    }
    if (deleted < toDelete.length) toast.warning(t('results.duplicatesDeletedSome', { n: deleted, total: toDelete.length }))
    else toast.success(t('results.duplicatesDeleted', deleted))
  }

  // ---------------------------------------------------------------------------
  // Export
  // ---------------------------------------------------------------------------
  async function doExport(format, section) {
    exportMenuOpen.value = false
    exporting.value = true
    const pid = route.params.id
    const jid = selectedJobId.value
    if (!jid) return

    let url
    if (format === 'csv') {
      url = `/api/export/${pid}/jobs/${jid}/csv?section=${section}`
    } else if (format === 'report') {
      url = `/api/export/${pid}/jobs/${jid}/report`
    } else if (format === 'pdf') {
      url = `/api/export/${pid}/jobs/${jid}/pdf`
    } else if (format === 'json') {
      url = `/api/export/${pid}/jobs/${jid}/json`
    } else if (format === 'notebook') {
      url = `/api/export/${pid}/jobs/${jid}/notebook?lang=${section}`
    }

    try {
      const { data, headers } = await http.get(url, { responseType: 'blob' })
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
      toast.error(t('results.exportFailed', { error: await blobError(e) }))
    } finally {
      exporting.value = false
    }
  }

  /** Export answers are blobs, so an error body arrives as a blob too: read it. */
  async function blobError(e) {
    const data = e?.response?.data
    if (data && typeof data.text === 'function') {
      try {
        const parsed = JSON.parse(await data.text())
        ignoreError(e)
        return apiError({ response: { status: e.response.status, data: parsed } })
      } catch { /* not JSON: fall through */ }
    }
    return apiError(e)
  }

  function copyDeployUrl() {
    const url = `${apiBaseUrl}/api/predict/${selectedJobId.value}`
    navigator.clipboard.writeText(url).then(() => {
      deployCopied.value = true
      setTimeout(() => { deployCopied.value = false }, 2000)
    })
  }

  function truncateVotes(votes) {
    if (!votes) return '—'
    return votes.length > 30 ? votes.slice(0, 30) + '...' : votes
  }

  async function confirmDeleteJob(job) {
    if (isLive(job.status)) return
    if (!(await confirmDialog({ message: t('results.deleteJobConfirm', { name: job.name || job.job_id.slice(0, 8) }), confirmLabel: t('common.delete'), danger: true }))) return
    const pid = route.params.id
    try {
      await api.analysis.deleteJob(pid, job.job_id)
      await loadJobList()
      if (selectedJobId.value === job.job_id) {
        selectedJobId.value = ''
        detail.value = null
        syncUrl()
      }
    } catch (e) {
      toast.error(t('results.deleteFailed', { error: apiError(e) }))
    }
  }

  // ---------------------------------------------------------------------------
  // Rerun / Duplicate
  // ---------------------------------------------------------------------------
  const rerunLoading = ref(false)

  async function rerunJob(job) {
    if (rerunLoading.value) return
    rerunLoading.value = true
    const pid = route.params.id
    try {
      const { data } = await api.analysis.rerunJob(pid, job.job_id)
      store.startJob(data.job_id)
      await loadJobList()
      selectJob(data.job_id)
    } catch (e) {
      toast.error(t('results.rerunFailed') + ': ' + apiError(e))
    } finally {
      rerunLoading.value = false
    }
  }

  async function duplicateJob(job) {
    const pid = route.params.id
    try {
      const { data } = await api.analysis.jobConfig(pid, job.job_id)
      if (data.config) {
        configStore.loadFromJobConfig(data.config)
        router.push(`/project/${pid}/parameters`)
      }
    } catch (e) {
      toast.error(t('results.duplicateFailed') + ': ' + apiError(e))
    }
  }

  // ---------------------------------------------------------------------------
  // Data loading
  // ---------------------------------------------------------------------------
  let _resultsSeq = 0
  async function loadJobResults() {
    if (!selectedJobId.value) return
    const pid = route.params.id
    const jid = selectedJobId.value
    const mine = ++_resultsSeq
    resultsError.value = ''
    resultsPartial.value = false

    // Only a completed job has results; failed / running / cancelled jobs have their own panel.
    const info = jobs.value.find(j => j.job_id === jid)
    if (info && info.status !== 'completed' && info.status !== 'unknown') {
      detail.value = null
      loading.value = false
      return
    }

    loading.value = true
    try {
      const { data } = await api.analysis.jobDetail(pid, jid, { timeout: LONG_TIMEOUT_MS })
      if (mine !== _resultsSeq) return
      detail.value = data

      try {
        const { data: raw } = await api.analysis.jobResults(pid, jid, { timeout: LONG_TIMEOUT_MS })
        if (mine !== _resultsSeq) return
        fullResults.value = raw
        population.value = raw.population || []
        generationTracking.value = raw.generation_tracking || []
        juryData.value = raw.jury || null
        importanceData.value = raw.importance || null
        pheromoneData.value = raw.pheromone || null
        contributionData.value = null
        shapData.value = null
        // Reset filters for new job
        selectedLanguages.value = []
        selectedDataTypes.value = []
        fbmEnabled.value = false
        popPage.value = 0
        samplePredPage.value = 0
      } catch (e) {
        if (mine !== _resultsSeq) { ignoreError(e); return }
        // The summary loaded but the full results did not: say so instead of drawing empty charts.
        ignoreError(e)
        resultsPartial.value = true
        fullResults.value = null
        population.value = []
        generationTracking.value = []
        juryData.value = null
        importanceData.value = null
        pheromoneData.value = null
      }

      // A section that does not exist for this job (e.g. jury) falls back to the first one.
      if (!tabAvailable(subTab.value)) subTab.value = 'insights'
      await loadMspAnnotations()
      await nextTick()
      renderActiveTab()
    } catch (e) {
      if (mine !== _resultsSeq) { ignoreError(e); return }
      resultsError.value = apiError(e)
      detail.value = null
    } finally {
      if (mine === _resultsSeq) loading.value = false
    }
  }

  function tabAvailable(tab) {
    if (tab === 'jury') return !!juryData.value
    if (tab === 'copresence' || tab === 'stability') return population.value.length > 1
    if (tab === 'pheromone') return !!(pheromoneData.value && pheromoneData.value.length > 0)
    if (tab === 'exploration') return !!hasExplorationData.value
    return true
  }

  async function loadJobList({ quiet = false } = {}) {
    const pid = route.params.id
    if (!quiet) {
      jobsLoading.value = !jobsLoaded.value
      jobsError.value = ''
    }
    try {
      const { data: rawJobs } = await api.analysis.listJobs(pid, quiet ? { silentError: true } : {})
      const data = normalizeJobs(rawJobs)
      if (store.current) store.current.jobs = data
      jobsLoaded.value = true
      jobsError.value = ''

      if (quiet) return
      const jobIdFromRoute = route.params.jobId
      if (jobIdFromRoute && data.some(j => j.job_id === jobIdFromRoute)) {
        selectedJobId.value = jobIdFromRoute
      } else if (jobIdFromRoute) {
        toast.warning(t('results.jobNotFound'))
        selectedJobId.value = ''
      }
      if (!selectedJobId.value && data.length > 0) {
        const completed = data.find(j => j.status === 'completed')
        if (completed) selectedJobId.value = completed.job_id
      }
      if (selectedJobId.value) {
        syncUrl()
        loadJobResults()
      }
    } catch (e) {
      if (quiet) { ignoreError(e); return }
      jobsError.value = apiError(e)
    } finally {
      jobsLoading.value = false
    }
  }

  // While a job is pending or running, keep the list fresh without a manual reload.
  const hasLiveJobs = computed(() => jobs.value.some(j => isLive(j.status)))
  let _pollTimer = null
  function startPolling() {
    if (_pollTimer) return
    _pollTimer = setInterval(() => {
      if (typeof document !== 'undefined' && document.hidden) return
      loadJobList({ quiet: true })
    }, 6000)
  }
  function stopPolling() {
    if (_pollTimer) { clearInterval(_pollTimer); _pollTimer = null }
  }
  watch(hasLiveJobs, (live) => { live ? startPolling() : stopPolling() }, { immediate: true })

  function onDocClick(ev) {
    if (exportMenuOpen.value && exportWrapEl.value && !exportWrapEl.value.contains(ev.target)) exportMenuOpen.value = false
  }

  // ---------------------------------------------------------------------------
  // BASKET CHARTS
  // ---------------------------------------------------------------------------
  async function renderBasketMetricsChart() {
    await nextTick()
    if (!basketMetricsChartEl.value || basketItems.value.length < 2) return
    const c = chartColors()
    const metricNames = ['auc', 'accuracy', 'sensitivity', 'specificity']
    const labels = [isRegressionJob.value ? fitMetricLabel.value : 'AUC', ct('Accuracy'), ct('Sensitivity'), ct('Specificity')]
    const traces = basketItems.value.map((item, i) => {
      const col = jobColor(i)
      return {
        type: 'bar',
        name: `${item.jobName} #${item.rank + 1}`,
        x: labels,
        y: metricNames.map(m => item.metrics?.[m] ?? 0),
        marker: { color: col + '59', line: { color: col, width: 1.5 } },
      }
    })
    Plotly.newPlot(basketMetricsChartEl.value, traces, chartLayout({
      barmode: 'group',
      yaxis: { title: { text: ct('Value'), font: { color: c.text } }, range: [0, 1.05], gridcolor: c.grid, color: c.text },
      xaxis: { color: c.text },
      height: 350,
      legend: { orientation: 'h', y: 1.15, font: { color: c.text, size: 10 } },
      margin: { t: 40, b: 50, l: 50, r: 20 },
    }), { responsive: true, displayModeBar: false })
  }

  async function renderBasketFeatureOverlap() {
    await nextTick()
    if (!basketFeatureOverlapEl.value || basketItems.value.length < 2) return
    const c = chartColors()
    const featureInfo = {}
    for (const item of basketItems.value) {
      for (const [name, coef] of Object.entries(item.named_features || {})) {
        if (!featureInfo[name]) featureInfo[name] = { count: 0, pos: 0, neg: 0 }
        featureInfo[name].count++
        if (coef > 0) featureInfo[name].pos++
        else featureInfo[name].neg++
      }
    }
    const sorted = Object.keys(featureInfo).sort((a, b) => featureInfo[a].count - featureInfo[b].count)
    if (sorted.length === 0) return
    Plotly.newPlot(basketFeatureOverlapEl.value, [
      {
        type: 'bar', orientation: 'h', name: ct('Positive (+)'),
        y: sorted.map(n => featureLabel(n)),
        x: sorted.map(n => featureInfo[n].pos),
        marker: { color: c.positiveAlpha, line: { color: c.positive, width: 1 } },
      },
      {
        type: 'bar', orientation: 'h', name: ct('Negative (-)'),
        y: sorted.map(n => featureLabel(n)),
        x: sorted.map(n => featureInfo[n].neg),
        marker: { color: c.negativeAlpha, line: { color: c.negative, width: 1 }, pattern: { shape: '/', fgcolor: c.negative, fgopacity: 0.6, size: 6 } },
      },
    ], chartLayout({
      barmode: 'stack',
      xaxis: { title: { text: t('results.basketModelCount'), font: { color: c.text } }, gridcolor: c.grid, color: c.text, dtick: 1 },
      yaxis: { automargin: true, color: c.text },
      height: Math.max(300, sorted.length * 20 + 80),
      margin: { t: 20, b: 50, l: 180, r: 20 },
      legend: { orientation: 'h', y: 1.08, font: { color: c.text } },
    }), { responsive: true, displayModeBar: false })
  }

  async function renderBasketHeatmap() {
    await nextTick()
    if (!basketHeatmapEl.value || basketItems.value.length < 2) return
    const c = chartColors()
    const allFeatures = new Set()
    for (const item of basketItems.value) {
      for (const name of Object.keys(item.named_features || {})) allFeatures.add(name)
    }
    const featurePrev = {}
    for (const name of allFeatures) {
      featurePrev[name] = basketItems.value.filter(item => (item.named_features || {})[name] != null).length
    }
    const sortedNames = [...allFeatures].sort((a, b) => featurePrev[a] - featurePrev[b])
    const matrix = sortedNames.map(fname => basketItems.value.map(item => (item.named_features || {})[fname] || 0))
    const modelLabels = basketItems.value.map(item => `${item.jobName} #${item.rank + 1}`)
    Plotly.newPlot(basketHeatmapEl.value, [{
      type: 'heatmap',
      z: matrix,
      ...signCells(matrix),
      x: modelLabels,
      y: sortedNames.map(n => featureLabel(n)),
      colorscale: c.divergingSoft,
      zmin: -1, zmax: 1, showscale: true,
      colorbar: { tickvals: [-1, 0, 1], ticktext: ['-1', '0', '+1'], tickfont: { color: c.text, size: 10 }, len: 0.5, thickness: 12 },
      xgap: 1, ygap: 1,
      hovertemplate: '%{y}<br>%{x}: %{z}<extra></extra>',
    }], chartLayout({
      xaxis: { color: c.text, tickangle: -45 },
      yaxis: { automargin: true, color: c.text },
      height: Math.max(300, sortedNames.length * 22 + 100),
      margin: { t: 20, b: 100, l: 180, r: 60 },
    }), { responsive: true, displayModeBar: true })
  }

  function renderBasketCharts() {
    renderBasketMetricsChart()
    renderBasketFeatureOverlap()
    renderBasketHeatmap()
  }

  const explorationStats = computed(() => {
    if (!generationTracking.value.length) return null
    const totalModels = generationTracking.value.reduce((s, g) => s + (g.population_size || 0), 0)
    const allSamples = generationTracking.value.flatMap(g => g.k_fit_sample || [])
    const uniqueSet = new Set(allSamples.map(([k, f]) => `${k}_${f}`))
    return { totalModels, uniqueSampled: uniqueSet.size, nGens: generationTracking.value.length }
  })

  function renderExplorationChart() {
    if (!explorationChartEl.value || !generationTracking.value.length) return
    if (!Plotly) return

    const c = chartColors()
    const textColor = c.text
    const bgColor = c.transparent

    // Collect data points (all generations, or the one selected)
    const ks = [], fits = []
    const nGens = generationTracking.value.length

    if (explorationGen.value === -1) {
      for (let g = 0; g < nGens; g++) {
        const samples = generationTracking.value[g].k_fit_sample || []
        for (const [k, f] of samples) {
          ks.push(k)
          fits.push(f)
        }
      }
    } else {
      // Single generation
      const samples = generationTracking.value[explorationGen.value]?.k_fit_sample || []
      for (const [k, f] of samples) {
        ks.push(k)
        fits.push(f)
      }
    }

    if (ks.length === 0) return

    // Density of sampled models. Empty bins stay blank (null) so the explored region
    // stands out; colour goes from light (few models) to dark (many).
    const grid = densityGrid(ks, fits, { nx: 40, ny: 40, integerX: true })
    const traces = [{
      type: 'heatmap',
      x: grid.x,
      y: grid.y,
      z: grid.z,
      zmin: 1,
      zmax: Math.max(2, grid.max),
      colorscale: c.scaleDensity,
      xgap: 0,
      ygap: 0,
      hoverongaps: false,
      colorbar: { title: { text: ct('Models'), font: { color: textColor } }, tickfont: { color: textColor } },
      hovertemplate: `k≈%{x:.0f}, fit≈%{y:.3f}<br>${ct('Models')}: %{z}<extra></extra>`,
    }, {
      // individual models, faint, for the outline of sparse regions
      type: 'scatter',
      mode: 'markers',
      x: ks,
      y: fits,
      marker: { size: 2, color: textColor, opacity: 0.18 },
      hoverinfo: 'skip',
      showlegend: false,
    }]

    // Add best trajectory
    const bestKs = generationTracking.value.map(g => g.best_k)
    const bestFits = generationTracking.value.map(g => g.best_fit || g.best_auc)
    traces.push({
      type: 'scatter',
      mode: 'lines+markers',
      x: bestKs,
      y: bestFits,
      name: ct('Best model trajectory'),
      marker: { size: 8, color: c.good, symbol: 'star', line: { color: c.paper, width: 1 } },
      line: { color: c.good, width: 2 },
      hovertemplate: `${ct('Generation')} %{customdata}: k=%{x}, fit=%{y:.4f}<extra>${ct('Best')}</extra>`,
      customdata: generationTracking.value.map((_, i) => i),
    })

    const genLabel = explorationGen.value === -1 ? ct('All generations') : `${ct('Generation')} ${explorationGen.value}`
    const layout = {
      title: { text: t('charts.explorationTitle', { gen: genLabel, n: ks.length }), font: { color: textColor, size: 14 }, x: 0, xanchor: 'left' },
      xaxis: { title: { text: ct('k (model complexity)'), font: { color: textColor } }, tickfont: { color: textColor }, gridcolor: c.grid, zeroline: false },
      yaxis: { title: { text: ct('Penalized fitness'), font: { color: textColor } }, tickfont: { color: textColor }, gridcolor: c.grid, zeroline: false },
      height: 500,
      margin: { l: 60, r: 30, t: 70, b: 50 },
      paper_bgcolor: bgColor,
      plot_bgcolor: bgColor,
      // legend above the plot: the best models sit in the top-left corner
      legend: { font: { color: textColor }, orientation: 'h', x: 1, xanchor: 'right', y: 1.02, yanchor: 'bottom' },
    }

    Plotly.react(explorationChartEl.value, traces, layout, { responsive: true })
  }

  let _animTimer = null
  function animateExploration() {
    if (_animTimer) { clearInterval(_animTimer); _animTimer = null; return }
    explorationGen.value = 0
    _animTimer = setInterval(() => {
      if (explorationGen.value >= generationTracking.value.length - 1) {
        clearInterval(_animTimer)
        _animTimer = null
        explorationGen.value = -1 // show all at end
        return
      }
      explorationGen.value++
    }, 200)
  }

  function renderPheromoneChart() {
    if (!pheromoneData.value || !pheromoneChartEl.value) return
    if (!Plotly) return

    const topN = pheromoneTopN.value || 30
    const data = pheromoneData.value.slice(0, topN).reverse() // reverse for horizontal bar (bottom=highest)

    const features = data.map(d => d.feature || `feature_${d.feature_idx}`)
    const tauPos = data.map(d => d.tau_positive)
    const tauNeg = data.map(d => -d.tau_negative) // negative for left side

    const c = chartColors()
    const textColor = c.text
    const bgColor = c.transparent

    const traces = [
      {
        name: ct('Positive (τ+)'),
        type: 'bar',
        orientation: 'h',
        y: features,
        x: tauPos,
        marker: { color: c.positive },
        hovertemplate: '%{y}: τ+ = %{x:.4f}<extra></extra>',
      },
      {
        name: ct('Negative (τ−)'),
        type: 'bar',
        orientation: 'h',
        y: features,
        x: tauNeg,
        marker: { color: c.negative, pattern: { shape: '/', fgcolor: c.paper, fgopacity: 0.55, size: 6 } },
        hovertemplate: '%{y}: τ− = %{customdata:.4f}<extra></extra>',
        customdata: data.map(d => d.tau_negative),
      },
    ]

    const height = Math.max(400, topN * 22 + 80)

    const layout = {
      barmode: 'overlay',
      title: { text: t('charts.topPheromone', { n: topN }), font: { color: textColor, size: 14 } },
      xaxis: {
        title: { text: ct('Pheromone (τ)'), font: { color: textColor } },
        tickfont: { color: textColor },
        zeroline: true,
        zerolinecolor: c.grid,
      },
      yaxis: {
        tickfont: { color: textColor, size: 10 },
        automargin: true,
      },
      height,
      margin: { l: 200, r: 30, t: 40, b: 50 },
      paper_bgcolor: bgColor,
      plot_bgcolor: bgColor,
      legend: { font: { color: textColor }, x: 0.7, y: 1 },
    }

    Plotly.react(pheromoneChartEl.value, traces, layout, { responsive: true })
  }

  function renderPheromoneTimeline() {
    const timeline = fullResults.value?.pheromone_timeline
    if (!timeline || !pheromoneTimelineEl.value) return
    if (!Plotly) return

    const c = chartColors()
    const textColor = c.text

    // Build feature set from all snapshots
    const featureSet = new Map()
    for (const snap of timeline) {
      for (const f of snap.top_features) {
        if (!featureSet.has(f.feature)) featureSet.set(f.feature, featureSet.size)
      }
    }
    const featureNames = [...featureSet.keys()].slice(0, 30)
    const iterations = timeline.map(s => s.iteration)

    // Build z matrix: features × iterations
    const z = featureNames.map(fname => {
      return iterations.map((_, i) => {
        const snap = timeline[i]
        const f = snap.top_features.find(t => t.feature === fname)
        return f ? f.tau_pos + f.tau_neg : 0
      })
    })

    Plotly.react(pheromoneTimelineEl.value, [{
      type: 'heatmap',
      z,
      x: iterations,
      y: featureNames,
      colorscale: c.sequentialWarm,
      reversescale: true,
      colorbar: { title: { text: 'τ total', font: { color: textColor } }, tickfont: { color: textColor } },
      hovertemplate: `%{y}<br>${ct('Iteration')} %{x}: τ=%{z:.3f}<extra></extra>`,
    }], {
      title: { text: ct('Pheromone Evolution (top 30 features)'), font: { color: textColor, size: 14 } },
      xaxis: { title: { text: ct('Iteration'), font: { color: textColor } }, tickfont: { color: textColor } },
      yaxis: { tickfont: { color: textColor, size: 10 }, automargin: true },
      height: Math.max(400, featureNames.length * 18 + 80),
      margin: { l: 200, r: 30, t: 40, b: 50 },
      paper_bgcolor: c.transparent,
      plot_bgcolor: c.transparent,
    }, { responsive: true })
  }

  function renderEntropyChart() {
    const timeline = fullResults.value?.pheromone_timeline
    if (!timeline || !entropyChartEl.value) return
    if (!Plotly) return

    const c = chartColors()
    const textColor = c.text

    const iterations = timeline.map(s => s.iteration)
    const entropy = timeline.map(s => s.entropy)

    Plotly.react(entropyChartEl.value, [{
      type: 'scatter',
      mode: 'lines+markers',
      x: iterations,
      y: entropy,
      marker: { size: 4, color: c.class1 },
      line: { color: c.class1, width: 2 },
      hovertemplate: `${ct('Iteration')} %{x}: ${ct('entropy')}=%{y:.4f}<extra></extra>`,
    }], {
      title: { text: ct('Pheromone Entropy (1=uniform, 0=converged)'), font: { color: textColor, size: 14 } },
      xaxis: { title: { text: ct('Iteration'), font: { color: textColor } }, tickfont: { color: textColor } },
      yaxis: { title: { text: ct('Entropy'), font: { color: textColor } }, tickfont: { color: textColor }, range: [0, 1.05] },
      height: 300,
      margin: { l: 60, r: 30, t: 40, b: 50 },
      paper_bgcolor: c.transparent,
      plot_bgcolor: c.transparent,
    }, { responsive: true })
  }

  function renderCooccurrenceChart() {
    const cooc = fullResults.value?.feature_cooccurrence
    if (!cooc || !cooccurrenceChartEl.value) return
    if (!Plotly) return

    const c = chartColors()
    const textColor = c.text

    // Build adjacency for force-directed layout approximation
    const nodes = new Map()

    for (const e of cooc.slice(0, 100)) {
      if (!nodes.has(e.feature_a)) nodes.set(e.feature_a, { x: Math.random(), y: Math.random() })
      if (!nodes.has(e.feature_b)) nodes.set(e.feature_b, { x: Math.random(), y: Math.random() })
    }

    // Simple circular layout
    const nodeList = [...nodes.keys()]
    const n = nodeList.length
    nodeList.forEach((name, i) => {
      nodes.get(name).x = Math.cos(2 * Math.PI * i / n)
      nodes.get(name).y = Math.sin(2 * Math.PI * i / n)
    })

    // Edge traces (one per edge for width variation)
    const edgeX = [], edgeY = []
    for (const e of cooc.slice(0, 80)) {
      const a = nodes.get(e.feature_a)
      const b = nodes.get(e.feature_b)
      if (a && b) {
        edgeX.push(a.x, b.x, null)
        edgeY.push(a.y, b.y, null)
      }
    }

    const traces = [
      {
        type: 'scatter', mode: 'lines', x: edgeX, y: edgeY,
        line: { color: c.edge, width: 1 },
        hoverinfo: 'skip', showlegend: false,
      },
      {
        type: 'scatter', mode: 'markers+text', textposition: 'top center',
        x: nodeList.map(n => nodes.get(n).x),
        y: nodeList.map(n => nodes.get(n).y),
        text: nodeList.map(n => n.length > 20 ? n.slice(0, 20) + '…' : n),
        textfont: { size: 10, color: textColor },
        marker: { size: 10, color: c.class0 },
        hovertemplate: '%{text}<extra></extra>',
        showlegend: false,
      },
    ]

    Plotly.react(cooccurrenceChartEl.value, traces, {
      title: { text: t('charts.coSelectionTitle', { features: nodeList.length, edges: Math.min(80, cooc.length) }), font: { color: textColor, size: 14 } },
      xaxis: { visible: false },
      yaxis: { visible: false },
      height: 500,
      margin: { l: 20, r: 20, t: 40, b: 20 },
      paper_bgcolor: c.transparent,
      plot_bgcolor: c.transparent,
    }, { responsive: true })
  }

  function renderDiscoveryChart() {
    const discovery = fullResults.value?.feature_discovery
    if (!discovery || !discoveryChartEl.value) return
    if (!Plotly) return

    const c = chartColors()
    const textColor = c.text

    const top = discovery.slice(0, 30).reverse()
    const features = top.map(d => d.feature)
    const ranks = top.map(d => d.first_rank)

    Plotly.react(discoveryChartEl.value, [{
      type: 'bar',
      orientation: 'h',
      y: features,
      x: ranks,
      marker: {
        color: ranks.map(r => r === 0 ? c.good : r < 5 ? c.class0 : r < 20 ? c.highlight : c.class1),
        symbol: ranks.map(r => r === 0 ? 'star' : r < 5 ? 'circle' : r < 20 ? 'square' : 'diamond'),
      },
      hovertemplate: `%{y}: ${ct('first in model rank')} #%{x}<extra></extra>`,
    }], {
      title: { text: ct('Feature Discovery — First Appearance in Top Models'), font: { color: textColor, size: 14 } },
      xaxis: { title: { text: ct('First appears in model rank #'), font: { color: textColor } }, tickfont: { color: textColor } },
      yaxis: { tickfont: { color: textColor, size: 10 }, automargin: true },
      height: Math.max(350, top.length * 20 + 80),
      margin: { l: 200, r: 30, t: 40, b: 50 },
      paper_bgcolor: c.transparent,
      plot_bgcolor: c.transparent,
    }, { responsive: true })
  }

  async function renderActiveTab() {
    await ensurePlotly()
    if (subTab.value === 'summary') renderSummaryCharts()
    else if (subTab.value === 'bestmodel') renderBestModelCharts()
    else if (subTab.value === 'population') renderPopulationCharts()
    else if (subTab.value === 'jury') renderJuryCharts()
    else if (subTab.value === 'comparative') renderComparativeCharts()
    else if (subTab.value === 'copresence') renderCoPresenceCharts()
    else if (subTab.value === 'exploration') renderExplorationChart()
    else if (subTab.value === 'pheromone') { renderPheromoneChart(); renderPheromoneTimeline(); renderEntropyChart(); renderCooccurrenceChart(); renderDiscoveryChart() }
    else if (subTab.value === 'basket') renderBasketCharts()
  }

  // ---------------------------------------------------------------------------
  // Watchers
  // ---------------------------------------------------------------------------
  watch(subTab, () => { syncUrl() })

  // Back / forward buttons: follow the job in the URL.
  watch(() => route.params.jobId, (jid) => {
    if (jid && jid !== selectedJobId.value && jobs.value.some(j => j.job_id === jid)) selectJob(jid, { updateUrl: false })
  })
  watch(() => route.query.tab, (tab) => {
    if (tab && SUB_TABS.includes(tab) && tab !== subTab.value) subTab.value = tab
    else if (!tab && subTab.value !== 'insights') subTab.value = 'insights'
  })

  watch(subTab, async () => {
    await nextTick()
    renderActiveTab()
  })

  watch(() => themeStore.isDark, () => renderActiveTab())

  // Reset state when switching projects
  watch(() => route.params.id, () => {
    selectedJobId.value = null
    detail.value = null
    population.value = []
    generationTracking.value = []
    juryData.value = null
    importanceData.value = null
    pheromoneData.value = null
    fullResults.value = null
    subTab.value = 'insights'
    loadJobList()
  })

  watch(() => route.params.jobId, (newId) => {
    if (newId && newId !== selectedJobId.value) {
      selectedJobId.value = newId
      loadJobResults()
    }
  })

  // Re-render basket charts when items change
  watch(basketItems, () => {
    if (subTab.value === 'basket') nextTick(() => renderBasketCharts())
  }, { deep: true })

  // Re-render exploration chart when generation slider changes
  watch(explorationGen, () => {
    if (subTab.value === 'exploration') nextTick(() => renderExplorationChart())
  })

  // Re-render pheromone chart when topN changes
  watch(pheromoneTopN, () => {
    if (subTab.value === 'pheromone') nextTick(() => renderPheromoneChart())
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

  // Re-render PCoA when switching 2D/3D
  watch(popPcoaDim, () => { if (popPcoaData.value) renderPopPcoaChart() })

  // Re-render co-presence charts when controls change
  let _copresenceTimer = null
  function debouncedCopresenceRender() {
    clearTimeout(_copresenceTimer)
    _copresenceTimer = setTimeout(() => {
      copresencePage.value = 0
      if (subTab.value === 'copresence') renderCoPresenceCharts()
    }, 300)
  }
  // Re-render SHAP charts when view or selection changes
  watch(shapView, async () => { await nextTick(); renderShapActiveView() })
  watch(shapSampleIdx, async () => { await nextTick(); if (shapView.value === 'force') renderForceChart() })
  watch(shapFeatureIdx, async () => { await nextTick(); if (shapView.value === 'dependence') renderDependenceChart() })

  watch(copresenceFBM, debouncedCopresenceRender)
  watch(copresenceWeighted, debouncedCopresenceRender)
  watch(copresenceMinPrev, debouncedCopresenceRender)
  watch(copresenceTopN, debouncedCopresenceRender)
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

  onMounted(() => {
    loadJobList()
    document.addEventListener('click', onDocClick)
  })

  onBeforeUnmount(() => {
    stopPolling()
    document.removeEventListener('click', onDocClick)
    _resultsSeq++
  })

  return {
    FUNC_PROPS,
    JOB_DASHES,
    MAX_BASKET_SIZE,
    Plotly,
    SUB_TABS,
    _animTimer,
    _copresenceTimer,
    _featureLabel,
    _lastJobCount,
    _lfCache,
    _logFact,
    _pollTimer,
    _popFilterTimer,
    _resultsSeq,
    addToBasket,
    addToast,
    animateExploration,
    apiBaseUrl,
    availableDataTypes,
    availableLanguages,
    basketCount,
    basketExpandedId,
    basketFeatureIntersection,
    basketFeatureOverlapEl,
    basketFeatureUnion,
    basketFull,
    basketHeatmapEl,
    basketItems,
    basketMetricsChartEl,
    beeswarmChartEl,
    bestMetrics,
    betaRegularized,
    blobError,
    buildFeatureModelMatrix,
    cancelJob,
    cancellingId,
    changeSamplePredPage,
    chartColors,
    chartLayout,
    classNameFor,
    classStyle,
    cleanupDuplicates,
    clearBasket,
    coefficientsChartEl,
    coefficientsSummary,
    compareBestMetric,
    compareData,
    compareJobIds,
    comparisonBarEl,
    comparisonConvergenceEl,
    completedJobs,
    complexitySummary,
    compositionChartEl,
    computeShapMatrix,
    configDiffs,
    configStore,
    confirmClearBasket,
    confirmDeleteJob,
    confirmDialog,
    consoleLogContent,
    consoleLogCopied,
    consoleLogEl,
    consoleLogLines,
    consoleLogLoading,
    contributionData,
    contributionHeatmapEl,
    contributionLoading,
    convergenceChartEl,
    convergenceSummary,
    cooccurrenceChartEl,
    copresenceAlpha,
    copresenceData,
    copresenceFBM,
    copresenceHeatmapEl,
    copresenceMinPrev,
    copresenceTopN,
    copresenceNetworkEl,
    copresencePage,
    copresencePageSize,
    copresencePopulation,
    copresencePrevalenceEl,
    copresenceStats,
    copresenceStatsPaginated,
    copresenceWeighted,
    copyConsoleLog,
    copyDeployUrl,
    debouncedCopresenceRender,
    debouncedPopRender,
    debugMode,
    dependenceChartEl,
    deployCopied,
    detail,
    directionChartEl,
    discoveryChartEl,
    doExport,
    downloadConsoleLog,
    duplicateGroups,
    duplicateJob,
    duplicatesLoading,
    ensurePlotly,
    entropyChartEl,
    expandedRank,
    explorationChartEl,
    explorationGen,
    explorationStats,
    exportMenuOpen,
    exportWrapEl,
    exporting,
    failedJobLog,
    fbmCount,
    fbmEnabled,
    fbmMethod,
    featureCountChartEl,
    featureHeatmapEl,
    featureIntersection,
    featureLabel,
    featureName,
    featureOverlapEl,
    featurePrevalenceEl,
    featureUnion,
    filterFBM,
    filteredJobs,
    filteredPopulation,
    findDuplicates,
    fitEvolutionChartEl,
    fitMetricLabel,
    flamegraphColors,
    forceChartEl,
    formatDate,
    formatDuration,
    formatMetricVal,
    formatSize,
    fullResults,
    funcAnnotChartEl,
    funcAnnotatedFeatures,
    generationTracking,
    hasExplorationData,
    hasLiveJobs,
    hypergeomPMF,
    importanceChartEl,
    importanceData,
    isInBasket,
    isLive,
    isRegressionJob,
    jobAriaSort,
    jobColor,
    jobLabel,
    jobPage,
    jobPageSize,
    jobSearch,
    jobSortAsc,
    jobSortKey,
    jobs,
    jobsError,
    jobsLoaded,
    jobsLoading,
    jstatBetaInv,
    juryComparisonEl,
    juryConcordanceEl,
    juryConfusionTestEl,
    juryConfusionTrainEl,
    juryData,
    layoutCircle,
    layoutForceDirected,
    layoutGrid,
    layoutRadial,
    lnGamma,
    loadCompareData,
    loadConsoleLog,
    loadContributionHeatmap,
    loadFailedJobLog,
    loadJobList,
    loadJobResults,
    loadMspAnnotations,
    loadPopPcoa,
    loadShapData,
    loading,
    loadingPopPcoa,
    logFact,
    metricLabel,
    metricsByTypeEl,
    moduleFilterData,
    moduleFilteredIndices,
    mspAnnotations,
    networkLayout,
    networkLayoutOptions,
    onDocClick,
    onModuleFilterApplied,
    openLog,
    paginatedJobs,
    paginatedPopulation,
    pheromoneChartEl,
    pheromoneData,
    pheromoneTimelineEl,
    pheromoneTopN,
    popMetricsEl,
    popPage,
    popPageSize,
    popPcoaChartEl,
    popPcoaData,
    popPcoaDim,
    popPcoaMethod,
    popPcoaMetric,
    popPcoaShowEllipses,
    popTsnePerplexity,
    popUmapMinDist,
    popUmapNeighbors,
    population,
    pvalueGreater,
    pvalueLess,
    radarChartEl,
    removeFromBasket,
    renderActiveTab,
    renderBasketCharts,
    renderBasketFeatureOverlap,
    renderBasketHeatmap,
    renderBasketMetricsChart,
    renderBeeswarmChart,
    renderBestModelCharts,
    renderCoPresenceCharts,
    renderCoefficientsChart,
    renderComparativeCharts,
    renderComparisonBar,
    renderComparisonConvergence,
    renderCompositionChart,
    renderConfusionMatrix,
    renderContributionHeatmap,
    renderConvergenceChart,
    renderCooccurrenceChart,
    renderCopresenceHeatmap,
    renderCopresenceNetwork,
    renderCopresencePrevalence,
    renderDependenceChart,
    renderDirectionChart,
    renderDiscoveryChart,
    renderEntropyChart,
    renderExplorationChart,
    renderFeatureCountChart,
    renderFeatureHeatmap,
    renderFeatureOverlap,
    renderFeaturePrevalence,
    renderFitEvolutionChart,
    renderForceChart,
    renderFuncAnnotChart,
    renderImportanceChart,
    renderJuryCharts,
    renderJuryComparison,
    renderJuryConcordance,
    renderMetricsByType,
    renderPheromoneChart,
    renderPheromoneTimeline,
    renderPopMetrics,
    renderPopPcoaChart,
    renderPopulationCharts,
    renderRadarChart,
    renderSamplePredictions,
    renderShapActiveView,
    renderSummaryCharts,
    renderVoteMatrix,
    renderWaterfallChart,
    rerunJob,
    rerunLoading,
    resultsError,
    resultsPartial,
    rootEl,
    route,
    router,
    samplePredPage,
    samplePredPageSize,
    samplePredictionsEl,
    selectJob,
    selectedDataTypes,
    selectedJobId,
    selectedJobInfo,
    selectedLanguages,
    shapData,
    shapFeatureIdx,
    shapLoading,
    shapSampleIdx,
    shapView,
    showLiveConsole,
    showValidateModal,
    sortedFeatures,
    sortedJobs,
    startPolling,
    statusGlyph,
    statusLabel,
    stopPolling,
    store,
    subTab,
    syncUrl,
    t,
    tabAvailable,
    te,
    themeStore,
    timingData,
    toast,
    toggleBasket,
    toggleBasketExpand,
    toggleExpand,
    toggleJobSort,
    topNModels,
    truncateVotes,
    voteMatrixEl,
    waterfallChartEl,
  }
}
