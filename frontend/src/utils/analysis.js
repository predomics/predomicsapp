/** Small facts about analyses shared by the Data, Parameters and Results tabs. */

/** Fit functions that mean the target is continuous (regression). */
export const REGRESSION_FITS = new Set(['spearman', 'pearson', 'rmse', 'mutual_information'])

/** Standard machine-learning baselines (no gpredomics-specific options). */
export const SKLEARN_ALGOS = new Set(['rf', 'svm', 'logistic', 'xgboost', 'lightgbm', 'extra_trees', 'adaboost', 'knn'])

/** All files of a project's datasets, each tagged with its dataset id. */
export function allProjectFiles(datasets) {
  return (datasets || []).flatMap(ds => (ds.files || []).map(f => ({ ...f, datasetId: ds.id })))
}

/** The file holding a given role ('xtrain', 'ytrain', 'xtest', 'ytest', 'metadata', 'clinical'). */
export function findFileByRole(datasets, role) {
  return allProjectFiles(datasets).find(f => f.role === role) || null
}
