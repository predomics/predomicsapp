"""Automated experiment insights — synthesizes findings across all analyses.

Analyzes model performance, population robustness, biological context,
jury assessment, and generates actionable recommendations.
"""

from __future__ import annotations

import logging
from typing import Any

from .enrichment import filter_fbm_python

logger = logging.getLogger(__name__)


def compute_insights(
    results: dict,
    annotations: dict[str, dict[str, Any]],
    enrichment_results: dict | None,
    job_config: dict | None,
) -> dict:
    """Compute all insights for a completed job.

    Returns dict with 'insights' list, 'scores' per category, and 'summary' counts.
    """
    population = results.get("population", [])
    sample_count = len(results.get("sample_names", []))

    all_insights: list[dict] = []
    all_insights.extend(analyze_performance(results))
    all_insights.extend(analyze_overfitting(results, job_config))
    all_insights.extend(analyze_threshold(results, population, sample_count))
    all_insights.extend(analyze_robustness(results, population, sample_count))
    all_insights.extend(analyze_biology(results, annotations, enrichment_results))
    all_insights.extend(analyze_jury(results))
    all_insights.extend(
        generate_recommendations(all_insights, results, job_config)
    )

    scores = compute_health_scores(all_insights)
    summary = {
        "total": len(all_insights),
        "success": sum(1 for i in all_insights if i["severity"] == "success"),
        "info": sum(1 for i in all_insights if i["severity"] == "info"),
        "warning": sum(1 for i in all_insights if i["severity"] == "warning"),
        "critical": sum(1 for i in all_insights if i["severity"] == "critical"),
    }

    return {"insights": all_insights, "scores": scores, "summary": summary}


# ---------------------------------------------------------------------------
# Performance analyzer
# ---------------------------------------------------------------------------

def analyze_performance(results: dict) -> list[dict]:
    insights = []
    best = results.get("best_individual", {})
    auc = best.get("auc", 0)
    sensitivity = best.get("sensitivity", 0)
    specificity = best.get("specificity", 0)
    k = best.get("k", 0)
    accuracy = best.get("accuracy", 0)

    # AUC quality
    if auc >= 0.9:
        insights.append(_insight(
            "performance", "auc_quality", "success",
            "Excellent discrimination",
            f"Best model AUC = {auc:.4f}, indicating excellent classification performance.",
            value=f"{auc:.4f}",
        ))
    elif auc >= 0.8:
        insights.append(_insight(
            "performance", "auc_quality", "info",
            "Good discrimination",
            f"Best model AUC = {auc:.4f}, indicating good classification performance.",
            value=f"{auc:.4f}",
        ))
    elif auc >= 0.7:
        insights.append(_insight(
            "performance", "auc_quality", "warning",
            "Moderate discrimination",
            f"Best model AUC = {auc:.4f}. Consider tuning parameters or increasing epochs.",
            value=f"{auc:.4f}",
        ))
    else:
        insights.append(_insight(
            "performance", "auc_quality", "critical",
            "Poor discrimination",
            f"Best model AUC = {auc:.4f}. The model struggles to separate classes.",
            value=f"{auc:.4f}",
        ))

    # Sensitivity/specificity balance
    if sensitivity > 0 and specificity > 0:
        gap = abs(sensitivity - specificity)
        if gap > 0.15:
            biased = "sensitivity" if sensitivity > specificity else "specificity"
            insights.append(_insight(
                "performance", "class_bias", "warning",
                "Class prediction bias",
                f"Sensitivity ({sensitivity:.3f}) and specificity ({specificity:.3f}) differ by {gap:.3f}. "
                f"Model is biased toward {biased}.",
                value=f"{gap:.3f}",
            ))
        else:
            insights.append(_insight(
                "performance", "class_bias", "success",
                "Balanced predictions",
                f"Sensitivity ({sensitivity:.3f}) and specificity ({specificity:.3f}) are well balanced.",
            ))

    # Train vs test gap (overfitting)
    gen_tracking = results.get("generation_tracking", [])
    if gen_tracking:
        last_gen = gen_tracking[-1]
        test_auc = last_gen.get("best_auc_test")
        train_auc = last_gen.get("best_auc", auc)
        if test_auc is not None and test_auc > 0:
            gap = train_auc - test_auc
            if gap > 0.10:
                insights.append(_insight(
                    "performance", "overfitting", "critical",
                    "Likely overfitting",
                    f"Train AUC ({train_auc:.4f}) exceeds test AUC ({test_auc:.4f}) by {gap:.4f}.",
                    value=f"{gap:.4f}",
                ))
            elif gap > 0.05:
                insights.append(_insight(
                    "performance", "overfitting", "warning",
                    "Possible overfitting",
                    f"Train AUC ({train_auc:.4f}) exceeds test AUC ({test_auc:.4f}) by {gap:.4f}.",
                    value=f"{gap:.4f}",
                ))
            else:
                insights.append(_insight(
                    "performance", "overfitting", "success",
                    "Good generalization",
                    f"Train AUC ({train_auc:.4f}) and test AUC ({test_auc:.4f}) are close (gap {gap:.4f}).",
                ))

    # Model complexity
    sample_count = len(results.get("sample_names", []))
    if k == 1:
        insights.append(_insight(
            "performance", "complexity", "info",
            "Minimal model",
            "The best model uses a single feature. This is highly interpretable but may lack robustness.",
            value="k=1",
        ))
    elif k > 50:
        insights.append(_insight(
            "performance", "complexity", "warning",
            "High complexity model",
            f"The best model uses {k} features. Consider if a simpler model might generalize better.",
            value=f"k={k}",
        ))
    elif k > 0:
        insights.append(_insight(
            "performance", "complexity", "info",
            "Model complexity",
            f"The best model uses {k} features with accuracy {accuracy:.3f}.",
            value=f"k={k}",
        ))

    # Convergence
    if len(gen_tracking) >= 5:
        total = len(gen_tracking)
        tail_start = max(0, total - max(int(total * 0.2), 3))
        tail_aucs = [g.get("best_auc", 0) for g in gen_tracking[tail_start:]]
        if tail_aucs:
            auc_range = max(tail_aucs) - min(tail_aucs)
            if auc_range < 0.001:
                insights.append(_insight(
                    "performance", "convergence", "success",
                    "Algorithm converged",
                    f"Best AUC stabilized over the last {total - tail_start} generations (range < 0.001).",
                ))
            elif auc_range < 0.005:
                insights.append(_insight(
                    "performance", "convergence", "info",
                    "Near convergence",
                    f"Best AUC nearly stable over the last {total - tail_start} generations (range {auc_range:.4f}).",
                ))
            else:
                insights.append(_insight(
                    "performance", "convergence", "warning",
                    "May need more epochs",
                    f"Best AUC still improving in the last {total - tail_start} generations (range {auc_range:.4f}). "
                    "Consider increasing max_epochs.",
                ))

    return insights


# ---------------------------------------------------------------------------
# Overfitting analyzer
# ---------------------------------------------------------------------------

def analyze_overfitting(results: dict, job_config: dict | None) -> list[dict]:
    """Analyze overfitting protection settings and their effectiveness."""
    insights = []
    config = job_config or {}

    general_cfg = config.get("general", {})
    cv_cfg = config.get("cv", {})
    ga_cfg = config.get("ga", {})

    cv_enabled = general_cfg.get("cv", False)
    overfit_penalty = cv_cfg.get("overfit_penalty", 0)
    inner_folds = cv_cfg.get("inner_folds", 5)
    random_sampling = ga_cfg.get("random_sampling_pct", 0)
    random_sampling_epochs = ga_cfg.get("random_sampling_epochs", 1)
    bootstrap_n = general_cfg.get("threshold_ci_n_bootstrap", 0)
    bootstrap_penalty = general_cfg.get("threshold_ci_penalty", 0.5)
    bootstrap_alpha = general_cfg.get("threshold_ci_alpha", 0.05)
    holdout = config.get("data", {}).get("holdout_ratio", 0)

    # Count active protections
    protections = []

    # 1. Cross-validation
    if cv_enabled:
        outer_folds = cv_cfg.get("outer_folds", 5)
        fit_on_valid = cv_cfg.get("fit_on_valid", True)
        insights.append(_insight(
            "overfitting", "cv_enabled", "success",
            "Cross-validation active",
            f"Outer {outer_folds}-fold CV is enabled. "
            f"FBM selection based on {'validation' if fit_on_valid else 'training'} fold performance.",
            value=f"{outer_folds}-fold",
        ))
        protections.append("CV")
    else:
        insights.append(_insight(
            "overfitting", "cv_disabled", "info",
            "No cross-validation",
            "Cross-validation is disabled. The model is trained on the full training set without fold-based validation.",
        ))

    # 2. Internal overfitting penalty (inner CV)
    if overfit_penalty > 0:
        insights.append(_insight(
            "overfitting", "overfit_penalty", "success",
            "Overfitting penalty active",
            f"Inner {inner_folds}-fold CV penalizes train/validation gaps "
            f"(penalty weight = {overfit_penalty}). "
            "Models with poor generalization are penalized during evolution.",
            value=f"{overfit_penalty}",
        ))
        protections.append("overfit_penalty")
    else:
        insights.append(_insight(
            "overfitting", "overfit_penalty_off", "info",
            "No overfitting penalty",
            f"Inner fold overfitting penalty is disabled (overfit_penalty = 0). "
            "Consider setting overfit_penalty > 0 with inner_folds to penalize "
            "models whose train performance doesn't generalize to held-out folds.",
        ))

    # 3. Random sampling (stochastic regularization)
    if random_sampling > 0:
        insights.append(_insight(
            "overfitting", "random_sampling", "success",
            "Stochastic subsampling active",
            f"Each generation uses {random_sampling}% of samples "
            f"(reshuffled every {random_sampling_epochs} epoch(s)). "
            "This prevents models from memorizing the full training set.",
            value=f"{random_sampling}%",
        ))
        protections.append("random_sampling")

    # 4. Bootstrap threshold CI
    if bootstrap_n > 0:
        insights.append(_insight(
            "overfitting", "bootstrap_ci", "success",
            "Bootstrap threshold CI active",
            f"Threshold stability assessed via {bootstrap_n} bootstrap resamples "
            f"(alpha = {bootstrap_alpha}). "
            f"Models with unstable thresholds are penalized (weight = {bootstrap_penalty}).",
            value=f"n={bootstrap_n}",
        ))
        protections.append("bootstrap_CI")
    else:
        insights.append(_insight(
            "overfitting", "bootstrap_ci_off", "info",
            "No threshold bootstrap CI",
            "Bootstrap confidence interval for thresholds is disabled "
            "(threshold_ci_n_bootstrap = 0). Enable to detect models whose "
            "decision boundary is fragile under resampling.",
        ))

    # 5. Holdout / test data
    gen_tracking = results.get("generation_tracking", [])
    has_test = False
    if gen_tracking:
        has_test = gen_tracking[-1].get("best_auc_test") is not None
    if has_test:
        insights.append(_insight(
            "overfitting", "holdout_test", "success",
            "Independent test set available",
            "An independent test set is used to monitor generalization during evolution.",
        ))
        protections.append("test_set")
    elif holdout > 0:
        insights.append(_insight(
            "overfitting", "holdout_split", "info",
            "Holdout split configured",
            f"A {holdout*100:.0f}% holdout was requested but no test AUC appears in generation tracking.",
            value=f"{holdout*100:.0f}%",
        ))

    # 6. Overall protection assessment
    if len(protections) >= 3:
        insights.append(_insight(
            "overfitting", "protection_level", "success",
            "Strong overfitting protection",
            f"Active protections: {', '.join(protections)}. "
            "Multiple complementary mechanisms guard against overfitting.",
            value=f"{len(protections)} active",
        ))
    elif len(protections) >= 1:
        insights.append(_insight(
            "overfitting", "protection_level", "info",
            "Moderate overfitting protection",
            f"Active protections: {', '.join(protections)}. "
            "Consider adding more mechanisms for improved generalization.",
            value=f"{len(protections)} active",
        ))
    else:
        insights.append(_insight(
            "overfitting", "protection_level", "warning",
            "No overfitting protection",
            "No active overfitting protection mechanisms detected. "
            "Consider enabling CV, overfit_penalty, random_sampling, or bootstrap threshold CI.",
            value="0 active",
        ))

    return insights


# ---------------------------------------------------------------------------
# Threshold analyzer
# ---------------------------------------------------------------------------

def analyze_threshold(
    results: dict, population: list[dict], sample_count: int
) -> list[dict]:
    """Analyze threshold stability and generalizability."""
    insights = []
    best = results.get("best_individual", {})
    best_threshold = best.get("threshold")

    if best_threshold is None or not population:
        return insights

    # 1. Best model threshold CI (if bootstrap was enabled)
    best_ci = best.get("threshold_ci")
    if best_ci and isinstance(best_ci, dict):
        lower = best_ci.get("lower", 0)
        upper = best_ci.get("upper", 0)
        rejection = best_ci.get("rejection_rate", 0)
        ci_width = upper - lower

        insights.append(_insight(
            "threshold", "best_ci", "info",
            "Threshold confidence interval",
            f"Best model threshold = {best_threshold:.4f}, "
            f"95% CI = [{lower:.4f}, {upper:.4f}] (width = {ci_width:.4f}).",
            value=f"[{lower:.4f}, {upper:.4f}]",
            details={"threshold": best_threshold, "lower": lower, "upper": upper,
                     "width": ci_width, "rejection_rate": rejection},
        ))

        # CI width relative to threshold
        if best_threshold != 0:
            relative_width = ci_width / abs(best_threshold)
            if relative_width > 0.5:
                insights.append(_insight(
                    "threshold", "ci_wide", "critical",
                    "Very wide threshold CI",
                    f"CI width ({ci_width:.4f}) is {relative_width*100:.0f}% of the threshold value. "
                    "The decision boundary is highly unstable under resampling.",
                    value=f"{relative_width*100:.0f}%",
                ))
            elif relative_width > 0.2:
                insights.append(_insight(
                    "threshold", "ci_moderate", "warning",
                    "Moderate threshold uncertainty",
                    f"CI width ({ci_width:.4f}) is {relative_width*100:.0f}% of the threshold. "
                    "The decision boundary has meaningful uncertainty.",
                    value=f"{relative_width*100:.0f}%",
                ))
            else:
                insights.append(_insight(
                    "threshold", "ci_narrow", "success",
                    "Stable threshold",
                    f"CI width is only {relative_width*100:.0f}% of the threshold value. "
                    "The decision boundary is well-determined.",
                    value=f"{relative_width*100:.0f}%",
                ))

        # Rejection rate from CI
        if rejection > 0.15:
            insights.append(_insight(
                "threshold", "ci_rejection", "warning",
                "High CI rejection rate",
                f"{rejection*100:.1f}% of samples fall in the uncertainty zone between "
                f"lower ({lower:.4f}) and upper ({upper:.4f}) threshold bounds.",
                value=f"{rejection*100:.1f}%",
            ))
        elif rejection > 0:
            insights.append(_insight(
                "threshold", "ci_rejection", "info",
                "Some samples in uncertainty zone",
                f"{rejection*100:.1f}% of samples fall between the CI bounds.",
                value=f"{rejection*100:.1f}%",
            ))

    # 2. Threshold variability across FBM population
    fbm = filter_fbm_python(population, sample_count)
    if len(fbm) >= 3:
        thresholds = [
            ind.get("metrics", {}).get("threshold", 0) for ind in fbm
        ]
        thresholds = [t for t in thresholds if t is not None]

        if thresholds:
            t_min = min(thresholds)
            t_max = max(thresholds)
            t_mean = sum(thresholds) / len(thresholds)
            t_std = (sum((t - t_mean) ** 2 for t in thresholds) / len(thresholds)) ** 0.5

            insights.append(_insight(
                "threshold", "fbm_variability", "info",
                "Threshold across FBM",
                f"Across {len(fbm)} FBM models: mean = {t_mean:.4f}, "
                f"range = [{t_min:.4f}, {t_max:.4f}], std = {t_std:.4f}.",
                value=f"std={t_std:.4f}",
                details={"mean": round(t_mean, 4), "min": round(t_min, 4),
                         "max": round(t_max, 4), "std": round(t_std, 4),
                         "count": len(fbm)},
            ))

            # Assess variability severity
            if t_mean != 0:
                cv = t_std / abs(t_mean)  # coefficient of variation
                if cv > 0.5:
                    insights.append(_insight(
                        "threshold", "fbm_threshold_unstable", "critical",
                        "Highly variable thresholds in FBM",
                        f"Coefficient of variation = {cv:.2f}. "
                        "Equivalent models have very different decision boundaries. "
                        "This is typical of compositional data where relative "
                        "abundances shift between cohorts.",
                        value=f"CV={cv:.2f}",
                    ))
                elif cv > 0.2:
                    insights.append(_insight(
                        "threshold", "fbm_threshold_variable", "warning",
                        "Variable thresholds in FBM",
                        f"Coefficient of variation = {cv:.2f}. "
                        "FBM models use different decision boundaries, "
                        "which may reduce reproducibility on new cohorts.",
                        value=f"CV={cv:.2f}",
                    ))
                else:
                    insights.append(_insight(
                        "threshold", "fbm_threshold_stable", "success",
                        "Stable thresholds in FBM",
                        f"Coefficient of variation = {cv:.2f}. "
                        "FBM models agree on the decision boundary.",
                        value=f"CV={cv:.2f}",
                    ))

    # 3. Threshold symmetry analysis
    # For compositional data (sums, ratios), threshold should ideally be near 0
    # for ternary/binary models. Large absolute thresholds can indicate
    # the model captures a batch effect rather than a biological signal.
    if best_threshold is not None and best.get("k", 0) > 0:
        language = ""
        if population:
            language = population[0].get("metrics", {}).get("language", "")

        # For binary/ternary models, features are signed (+1/-1),
        # so threshold should be moderate relative to k
        k = best.get("k", 1)
        if language in ("bin", "ter", "pow2") and k > 0:
            ratio = abs(best_threshold) / k
            if ratio > 2.0:
                insights.append(_insight(
                    "threshold", "threshold_magnitude", "warning",
                    "Large threshold relative to model size",
                    f"|threshold| / k = {ratio:.2f}. For {language} models, "
                    "a threshold much larger than the feature count may indicate "
                    "the model is capturing a systematic shift rather than "
                    "differential features.",
                    value=f"|t|/k={ratio:.2f}",
                ))

    # 4. Compositional data warning
    # Metagenomic abundances are compositional (sum-constrained), which affects
    # threshold generalizability across studies with different sequencing depths.
    feature_names = results.get("feature_names", [])
    msp_features = [f for f in feature_names if f.lower().startswith("msp_")]
    if msp_features and not best.get("threshold_ci"):
        insights.append(_insight(
            "threshold", "compositional_warning", "warning",
            "Compositional data without threshold CI",
            "MSP features are compositional (relative abundances). "
            "Thresholds derived from compositional data are sensitive to sequencing depth "
            "and normalization. Enable bootstrap threshold CI "
            "(threshold_ci_n_bootstrap > 0) to quantify this uncertainty "
            "and penalize models with fragile decision boundaries.",
        ))

    # 5. Threshold sign analysis across FBM
    if len(fbm) >= 5:
        thresholds = [
            ind.get("metrics", {}).get("threshold", 0) for ind in fbm
        ]
        pos_count = sum(1 for t in thresholds if t > 0)
        neg_count = sum(1 for t in thresholds if t < 0)
        total = len(thresholds)

        if pos_count > 0 and neg_count > 0:
            minority_pct = min(pos_count, neg_count) / total * 100
            if minority_pct > 20:
                insights.append(_insight(
                    "threshold", "threshold_sign_flip", "warning",
                    "Threshold sign inconsistency",
                    f"{pos_count} FBM models have positive thresholds and {neg_count} have negative. "
                    "This suggests the feature score distribution overlaps with zero, "
                    "making the decision boundary direction unstable.",
                    value=f"+{pos_count}/−{neg_count}",
                ))

    return insights


# ---------------------------------------------------------------------------
# Robustness analyzer
# ---------------------------------------------------------------------------

def analyze_robustness(
    results: dict, population: list[dict], sample_count: int
) -> list[dict]:
    insights = []
    if not population:
        return insights

    # FBM size
    fbm = filter_fbm_python(population, sample_count)
    fbm_size = len(fbm)
    pop_size = len(population)

    if fbm_size >= 20:
        insights.append(_insight(
            "robustness", "fbm_size", "success",
            "Large FBM",
            f"{fbm_size} models in the Family of Best Models ({fbm_size}/{pop_size}). "
            "Many statistically equivalent solutions exist.",
            value=str(fbm_size),
        ))
    elif fbm_size >= 5:
        insights.append(_insight(
            "robustness", "fbm_size", "info",
            "Moderate FBM",
            f"{fbm_size} models in the Family of Best Models ({fbm_size}/{pop_size}).",
            value=str(fbm_size),
        ))
    elif fbm_size >= 2:
        insights.append(_insight(
            "robustness", "fbm_size", "warning",
            "Small FBM",
            f"Only {fbm_size} models in the FBM. The best model may be somewhat unique.",
            value=str(fbm_size),
        ))
    else:
        insights.append(_insight(
            "robustness", "fbm_size", "warning",
            "Single best model",
            "Only 1 model in the FBM. No statistically equivalent alternatives found.",
            value="1",
        ))

    # Core consensus features in FBM
    if fbm_size >= 2:
        feature_counts: dict[str, int] = {}
        feature_signs: dict[str, dict[int, int]] = {}  # feat -> {sign: count}
        for ind in fbm:
            for feat, coef in ind.get("named_features", {}).items():
                feature_counts[feat] = feature_counts.get(feat, 0) + 1
                sign = 1 if (isinstance(coef, (int, float)) and coef > 0) else -1
                signs = feature_signs.setdefault(feat, {})
                signs[sign] = signs.get(sign, 0) + 1

        threshold_80 = int(fbm_size * 0.8)
        core_features = [f for f, c in feature_counts.items() if c >= threshold_80]

        if len(core_features) >= 3:
            # Check direction consistency
            consistent = sum(
                1 for f in core_features
                if len(feature_signs.get(f, {})) == 1
            )
            insights.append(_insight(
                "robustness", "core_features", "success",
                "Strong feature consensus",
                f"{len(core_features)} features appear in >80% of FBM models. "
                f"{consistent}/{len(core_features)} have consistent sign direction.",
                value=str(len(core_features)),
                details={"core_features": core_features[:15]},
            ))
        elif len(core_features) >= 1:
            insights.append(_insight(
                "robustness", "core_features", "info",
                "Partial feature consensus",
                f"{len(core_features)} feature(s) appear in >80% of FBM models.",
                value=str(len(core_features)),
                details={"core_features": core_features[:15]},
            ))
        else:
            insights.append(_insight(
                "robustness", "core_features", "warning",
                "No feature consensus",
                "No feature appears in >80% of FBM models. The signature varies across equivalent models.",
            ))

    # Language diversity
    languages = set()
    for ind in population[:50]:
        lang = ind.get("metrics", {}).get("language", "")
        if lang:
            languages.add(lang)
    if len(languages) > 1:
        insights.append(_insight(
            "robustness", "language_diversity", "info",
            "Multiple model languages",
            f"Top models use {len(languages)} different languages: {', '.join(sorted(languages))}.",
            value=str(len(languages)),
        ))
    elif len(languages) == 1:
        insights.append(_insight(
            "robustness", "language_diversity", "info",
            "Single language dominates",
            f"All top models use the '{list(languages)[0]}' language.",
            value=list(languages)[0],
        ))

    # Population convergence (top-10 AUC spread)
    if len(population) >= 10:
        top10_aucs = [
            ind.get("metrics", {}).get("auc", 0) for ind in population[:10]
        ]
        spread = max(top10_aucs) - min(top10_aucs)
        if spread < 0.001:
            insights.append(_insight(
                "robustness", "pop_convergence", "info",
                "Population highly converged",
                f"Top 10 models have AUC spread of only {spread:.5f}.",
            ))

    return insights


# ---------------------------------------------------------------------------
# Biology analyzer
# ---------------------------------------------------------------------------

def analyze_biology(
    results: dict,
    annotations: dict[str, dict[str, Any]],
    enrichment_results: dict | None,
) -> list[dict]:
    insights = []
    best = results.get("best_individual", {})
    population = results.get("population", [])
    feature_names = results.get("feature_names", [])

    # Get best model features
    if population:
        sig_features = list(population[0].get("named_features", {}).keys())
    else:
        sig_features = []

    if not sig_features:
        return insights

    # Taxonomic coverage
    msp_features = [f for f in sig_features if f.lower().startswith("msp_")]
    annotated = [f for f in msp_features if f in annotations and annotations[f]]

    if not msp_features:
        insights.append(_insight(
            "biology", "taxonomy_coverage", "info",
            "Non-MSP features",
            "Feature names do not follow MSP format. Taxonomic annotations are not available.",
        ))
        return insights

    coverage_pct = len(annotated) / len(msp_features) * 100 if msp_features else 0
    if coverage_pct >= 80:
        insights.append(_insight(
            "biology", "taxonomy_coverage", "success",
            "Good taxonomic coverage",
            f"{len(annotated)}/{len(msp_features)} signature features ({coverage_pct:.0f}%) have taxonomic annotations.",
            value=f"{coverage_pct:.0f}%",
        ))
    elif coverage_pct >= 50:
        insights.append(_insight(
            "biology", "taxonomy_coverage", "info",
            "Partial taxonomic coverage",
            f"{len(annotated)}/{len(msp_features)} signature features ({coverage_pct:.0f}%) have annotations.",
            value=f"{coverage_pct:.0f}%",
        ))
    else:
        insights.append(_insight(
            "biology", "taxonomy_coverage", "warning",
            "Low taxonomic coverage",
            f"Only {len(annotated)}/{len(msp_features)} signature features ({coverage_pct:.0f}%) have annotations.",
            value=f"{coverage_pct:.0f}%",
        ))

    # Phylum distribution of signature
    phylum_counts: dict[str, int] = {}
    for feat in sig_features:
        ann = annotations.get(feat, {})
        phylum = ann.get("phylum", "")
        if phylum and isinstance(phylum, str) and phylum.strip():
            phylum_counts[phylum.strip()] = phylum_counts.get(phylum.strip(), 0) + 1

    if phylum_counts:
        total_annotated = sum(phylum_counts.values())
        sorted_phyla = sorted(phylum_counts.items(), key=lambda x: -x[1])
        top_phylum, top_count = sorted_phyla[0]
        dominance = top_count / total_annotated * 100

        if dominance > 50:
            insights.append(_insight(
                "biology", "phylum_dominance", "info",
                "Taxonomically focused signature",
                f"{top_phylum} dominates the signature ({top_count}/{total_annotated} features, {dominance:.0f}%).",
                value=top_phylum,
                details={"phylum_distribution": dict(sorted_phyla[:8])},
            ))
        else:
            insights.append(_insight(
                "biology", "phylum_diversity", "info",
                "Taxonomically diverse signature",
                f"Signature spans {len(phylum_counts)} phyla. "
                f"Top: {top_phylum} ({dominance:.0f}%).",
                value=f"{len(phylum_counts)} phyla",
                details={"phylum_distribution": dict(sorted_phyla[:8])},
            ))

    # Functional annotations summary
    func_counts = {"butyrate": 0, "inflammation_pos": 0, "inflammation_neg": 0,
                   "transit_pos": 0, "transit_neg": 0, "oralisation": 0}
    for feat in sig_features:
        ann = annotations.get(feat, {})
        if ann.get("butyrate") and int(ann["butyrate"]) == 1:
            func_counts["butyrate"] += 1
        infl = ann.get("inflammation")
        if infl is not None:
            if int(infl) == 1:
                func_counts["inflammation_pos"] += 1
            elif int(infl) == -1:
                func_counts["inflammation_neg"] += 1
        transit = ann.get("transit")
        if transit is not None:
            if int(transit) == 1:
                func_counts["transit_pos"] += 1
            elif int(transit) == -1:
                func_counts["transit_neg"] += 1
        if ann.get("oralisation") and int(ann["oralisation"]) == 1:
            func_counts["oralisation"] += 1

    active_funcs = {k: v for k, v in func_counts.items() if v > 0}
    if active_funcs:
        parts = []
        if func_counts["butyrate"] > 0:
            parts.append(f"{func_counts['butyrate']} butyrate producers")
        if func_counts["inflammation_pos"] > 0:
            parts.append(f"{func_counts['inflammation_pos']} inflammation-enriched")
        if func_counts["inflammation_neg"] > 0:
            parts.append(f"{func_counts['inflammation_neg']} inflammation-depleted")
        if func_counts["oralisation"] > 0:
            parts.append(f"{func_counts['oralisation']} oral-origin species")

        insights.append(_insight(
            "biology", "functional_profile", "info",
            "Functional annotations",
            f"Signature includes: {', '.join(parts)}.",
            details=func_counts,
        ))

    # Enrichment highlights
    if enrichment_results and enrichment_results.get("results"):
        sig_enriched = [
            r for r in enrichment_results["results"]
            if r.get("significant") and r.get("direction") == "enriched"
        ]
        sig_depleted = [
            r for r in enrichment_results["results"]
            if r.get("significant") and r.get("direction") == "depleted"
        ]
        if sig_enriched:
            top = sig_enriched[0]
            insights.append(_insight(
                "biology", "enrichment_highlight", "success",
                "Significant taxonomic enrichment",
                f"{len(sig_enriched)} enriched categories found. "
                f"Top: {top['category']} ({top['fold_enrichment']}x, FDR={top['fdr']}).",
                details={"enriched": [r["category"] for r in sig_enriched[:5]]},
            ))
        if sig_depleted:
            insights.append(_insight(
                "biology", "depletion_highlight", "info",
                "Taxonomic depletion detected",
                f"{len(sig_depleted)} depleted categories: "
                f"{', '.join(r['category'] for r in sig_depleted[:3])}.",
            ))

    return insights


# ---------------------------------------------------------------------------
# Jury analyzer
# ---------------------------------------------------------------------------

def analyze_jury(results: dict) -> list[dict]:
    insights = []
    jury = results.get("jury")
    if not jury:
        return insights

    best = results.get("best_individual", {})
    best_auc = best.get("auc", 0)

    # Jury metrics
    jury_train = jury.get("train", {})
    jury_test = jury.get("test", {})
    jury_metrics = jury_test if jury_test else jury_train
    jury_auc = jury_metrics.get("auc", 0) if jury_metrics else 0
    expert_count = jury.get("expert_count", 0)

    # Expert count
    insights.append(_insight(
        "jury", "expert_count", "info",
        "Jury composition",
        f"Jury consists of {expert_count} expert models using {jury.get('method', 'Majority')} voting.",
        value=str(expert_count),
    ))

    # Jury vs best model
    if jury_auc > 0 and best_auc > 0:
        if jury_auc > best_auc + 0.005:
            insights.append(_insight(
                "jury", "jury_vs_best", "success",
                "Jury outperforms best model",
                f"Jury AUC ({jury_auc:.4f}) exceeds best individual AUC ({best_auc:.4f}).",
                value=f"+{jury_auc - best_auc:.4f}",
            ))
        elif jury_auc >= best_auc - 0.005:
            insights.append(_insight(
                "jury", "jury_vs_best", "info",
                "Jury matches best model",
                f"Jury AUC ({jury_auc:.4f}) is comparable to best individual ({best_auc:.4f}).",
            ))
        else:
            insights.append(_insight(
                "jury", "jury_vs_best", "warning",
                "Jury underperforms",
                f"Jury AUC ({jury_auc:.4f}) is lower than best individual ({best_auc:.4f}). "
                "Consider adjusting voting parameters.",
                value=f"{jury_auc - best_auc:.4f}",
            ))

    # Rejection rate
    rejection = jury_metrics.get("rejection_rate", 0) if jury_metrics else 0
    if rejection > 0.10:
        insights.append(_insight(
            "jury", "rejection_rate", "warning",
            "High sample rejection",
            f"Jury rejects {rejection*100:.1f}% of samples. Consider widening the voting threshold.",
            value=f"{rejection*100:.1f}%",
        ))
    elif rejection > 0:
        insights.append(_insight(
            "jury", "rejection_rate", "info",
            "Some samples rejected",
            f"Jury rejects {rejection*100:.1f}% of samples.",
            value=f"{rejection*100:.1f}%",
        ))

    # Expert agreement from vote_matrix
    vote_matrix = jury.get("vote_matrix", {})
    votes = vote_matrix.get("votes")
    if votes and isinstance(votes, list) and len(votes) > 0:
        # Each row is a sample's votes from experts
        agreements = []
        for row in votes:
            if not row:
                continue
            total = len(row)
            majority = max(sum(1 for v in row if v > 0), sum(1 for v in row if v <= 0))
            agreements.append(majority / total if total > 0 else 0)
        if agreements:
            mean_agree = sum(agreements) / len(agreements)
            if mean_agree > 0.85:
                insights.append(_insight(
                    "jury", "agreement", "success",
                    "High expert agreement",
                    f"Mean agreement across samples: {mean_agree*100:.1f}%.",
                    value=f"{mean_agree*100:.1f}%",
                ))
            elif mean_agree > 0.70:
                insights.append(_insight(
                    "jury", "agreement", "info",
                    "Moderate expert agreement",
                    f"Mean agreement across samples: {mean_agree*100:.1f}%.",
                    value=f"{mean_agree*100:.1f}%",
                ))
            else:
                insights.append(_insight(
                    "jury", "agreement", "warning",
                    "Low expert agreement",
                    f"Mean agreement across samples: {mean_agree*100:.1f}%. Experts disagree frequently.",
                    value=f"{mean_agree*100:.1f}%",
                ))

    return insights


# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------

def generate_recommendations(
    existing_insights: list[dict],
    results: dict,
    job_config: dict | None,
) -> list[dict]:
    recs = []
    keys = {i["key"] for i in existing_insights}
    severities = {i["key"]: i["severity"] for i in existing_insights}
    jury = results.get("jury")
    population = results.get("population", [])
    best = results.get("best_individual", {})

    # No jury and large population
    if not jury and len(population) >= 50:
        recs.append(_insight(
            "recommendation", "enable_jury", "info",
            "Consider enabling jury voting",
            "The population is large enough for ensemble voting. "
            "Jury models often improve generalization by combining multiple experts.",
        ))

    # Overfitting detected
    if severities.get("overfitting") in ("warning", "critical"):
        cv_enabled = False
        if job_config:
            cv_enabled = job_config.get("cv", job_config.get("general", {}).get("cv", False))
        if not cv_enabled:
            recs.append(_insight(
                "recommendation", "enable_cv", "warning",
                "Consider enabling cross-validation",
                "Overfitting was detected. Cross-validation can help penalize models that don't generalize.",
            ))

    # Not converged
    if severities.get("convergence") == "warning":
        recs.append(_insight(
            "recommendation", "more_epochs", "info",
            "Consider increasing max_epochs",
            "The algorithm was still improving when it stopped. More generations may yield better models.",
        ))

    # Very small k
    if best.get("k", 0) == 1:
        recs.append(_insight(
            "recommendation", "increase_kmin", "info",
            "Consider multi-feature models",
            "The best model uses only 1 feature. Increasing kmin may yield more robust signatures.",
        ))

    # No MSP annotations
    feature_names = results.get("feature_names", [])
    msp_features = [f for f in feature_names if f.lower().startswith("msp_")]
    if not msp_features:
        recs.append(_insight(
            "recommendation", "no_msp", "info",
            "Taxonomy unavailable",
            "Feature names don't match MSP format. Biological context analysis is limited.",
        ))

    # Narrow FBM
    if severities.get("fbm_size") in ("warning",):
        recs.append(_insight(
            "recommendation", "fbm_narrow", "info",
            "Consider relaxing FBM criterion",
            "The FBM is very small. A less strict CI method (e.g., Clopper-Pearson) "
            "would include more statistically equivalent models.",
        ))

    # Threshold instability → enable bootstrap CI
    if severities.get("fbm_threshold_unstable") == "critical" or \
       severities.get("fbm_threshold_variable") == "warning":
        bootstrap_off = severities.get("bootstrap_ci_off") is not None
        if bootstrap_off:
            recs.append(_insight(
                "recommendation", "enable_bootstrap_ci", "warning",
                "Enable bootstrap threshold CI",
                "Thresholds vary across FBM models. Enable threshold_ci_n_bootstrap "
                "(e.g., 200-500) to penalize models with unstable decision boundaries "
                "and quantify threshold uncertainty.",
            ))

    # Compositional warning → suggest normalization or CI
    if severities.get("compositional_warning") == "warning":
        recs.append(_insight(
            "recommendation", "compositional_threshold", "warning",
            "Address compositional threshold fragility",
            "With compositional features (MSP), thresholds shift with sequencing depth. "
            "Enable bootstrap threshold CI and consider using prevalence (prev) "
            "or log data_type to reduce sensitivity to total abundance.",
        ))

    # No overfitting protection at all
    if severities.get("protection_level") == "warning":
        recs.append(_insight(
            "recommendation", "add_overfitting_protection", "warning",
            "Add overfitting safeguards",
            "No overfitting protection is active. Consider enabling at least one: "
            "(1) cross-validation (cv: true), "
            "(2) inner fold penalty (overfit_penalty > 0), "
            "(3) stochastic subsampling (random_sampling_pct > 0), or "
            "(4) bootstrap threshold CI (threshold_ci_n_bootstrap > 0).",
        ))

    # Overfitting detected + no inner penalty
    if severities.get("overfitting") in ("warning", "critical"):
        if severities.get("overfit_penalty_off") is not None:
            recs.append(_insight(
                "recommendation", "enable_overfit_penalty", "info",
                "Consider inner fold overfitting penalty",
                "Set overfit_penalty > 0 (e.g., 0.5-1.0) to penalize models whose "
                "performance drops on held-out inner folds during evolution.",
            ))

    return recs


# ---------------------------------------------------------------------------
# Health scores
# ---------------------------------------------------------------------------

def compute_health_scores(insights: list[dict]) -> dict:
    """Compute 0-100 health scores per category."""
    categories = [
        "performance", "overfitting", "threshold",
        "robustness", "biology", "jury", "recommendation",
    ]
    scores = {}

    for cat in categories:
        cat_insights = [i for i in insights if i["category"] == cat]
        if not cat_insights:
            scores[cat] = None
            continue
        score = 100
        for i in cat_insights:
            if i["severity"] == "critical":
                score -= 30
            elif i["severity"] == "warning":
                score -= 15
            elif i["severity"] == "info":
                score -= 5
            # success: no deduction
        scores[cat] = max(0, min(100, score))

    return scores


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _insight(
    category: str,
    key: str,
    severity: str,
    title: str,
    message: str,
    value: str | None = None,
    details: dict | None = None,
) -> dict:
    d = {
        "category": category,
        "key": key,
        "severity": severity,
        "title": title,
        "message": message,
    }
    if value is not None:
        d["value"] = value
    if details is not None:
        d["details"] = details
    return d
