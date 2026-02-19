"""Taxonomic and functional enrichment analysis for microbial signatures.

Implements Over-Representation Analysis (ORA) using Fisher's exact test
with Benjamini-Hochberg FDR correction. Compares the taxonomic/functional
composition of a signature (model, FBM, or jury features) against the
full background of available features.

References:
    - Fisher, R.A. (1922). On the interpretation of chi-squared from
      contingency tables. J. Royal Stat. Soc. 85(1):87-94.
    - Benjamini, Y. & Hochberg, Y. (1995). Controlling the false discovery
      rate. J. Royal Stat. Soc. B 57(1):289-300.
"""

from __future__ import annotations

import logging
import math
from typing import Any

from scipy.stats import fisher_exact, norm

logger = logging.getLogger(__name__)


def benjamini_hochberg(pvalues: list[float]) -> list[float]:
    """Benjamini-Hochberg FDR correction.

    Returns adjusted p-values in the same order as the input.
    """
    n = len(pvalues)
    if n == 0:
        return []
    indexed = sorted(enumerate(pvalues), key=lambda x: x[1])
    fdr = [0.0] * n
    cum_min = 1.0
    for rank_from_end in range(n - 1, -1, -1):
        orig_idx, pval = indexed[rank_from_end]
        rank = rank_from_end + 1
        adjusted = pval * n / rank
        cum_min = min(cum_min, adjusted)
        fdr[orig_idx] = min(cum_min, 1.0)
    return fdr


def filter_fbm_python(
    population: list[dict], sample_count: int, method: str = "wilson"
) -> list[dict]:
    """Filter population to Family of Best Models using binomial CI.

    Python port of the Wilson/Wald CI logic used in Rust and JS.
    """
    if not population:
        return []
    best_fit = population[0].get("metrics", {}).get("fit", 0)
    if best_fit is None or best_fit <= 0:
        return population

    n = sample_count or len(population)
    alpha = 0.05
    z = -norm.ppf(alpha / 2)  # ~1.96
    p = best_fit

    if method == "wald":
        se = math.sqrt(p * (1 - p) / n)
        lower = p - z * se
    elif method == "wald_continuity":
        se = math.sqrt(p * (1 - p) / n)
        lower = p - (0.5 / n + z * se)
    elif method == "wilson":
        denom = 1 + z * z / n
        center = p + z * z / (2 * n)
        margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
        lower = (center - margin) / denom
    elif method == "agresti_coull":
        nt = n + z * z
        pt = (p * n + z * z / 2) / nt
        lower = pt - z * math.sqrt(pt * (1 - pt) / nt)
    elif method == "clopper_pearson":
        from scipy.stats import beta as beta_dist

        x = round(p * n)
        lower = beta_dist.ppf(alpha / 2, x, n - x + 1) if x > 0 else 0.0
    else:
        se = math.sqrt(p * (1 - p) / n)
        lower = p - z * se

    threshold = max(0.0, lower)
    return [
        ind
        for ind in population
        if (ind.get("metrics", {}).get("fit", 0) or 0) >= threshold
    ]


def compute_enrichment(
    signature_features: list[str],
    background_features: list[str],
    annotations: dict[str, dict[str, Any]],
    annotation_type: str,
) -> dict:
    """Compute enrichment of a signature vs. background for a given annotation type.

    Args:
        signature_features: Feature names in the signature.
        background_features: All feature names in the experiment.
        annotations: MSP annotations dict (feature_name -> annotation dict).
        annotation_type: One of "phylum", "family", "butyrate", "inflammation",
                         "transit", "oralisation".

    Returns:
        Dict with enrichment results, summary stats, and per-category test results.
    """
    sig_set = set(signature_features)
    bg_set = set(background_features)

    # Categorize features
    is_functional = annotation_type in ("butyrate", "inflammation", "transit", "oralisation")

    def get_categories(feature: str) -> list[str]:
        """Get the category labels for a feature under the given annotation type."""
        ann = annotations.get(feature, {})
        if not ann:
            return []
        if is_functional:
            val = ann.get(annotation_type)
            if val is None:
                return []
            # Binary (butyrate, oralisation): test value=1
            if annotation_type in ("butyrate", "oralisation"):
                return [f"{annotation_type}=1"] if int(val) == 1 else []
            # Ternary (inflammation, transit): each non-zero level
            ival = int(val)
            if ival != 0:
                return [f"{annotation_type}={ival:+d}"]
            return []
        else:
            # Taxonomic: phylum or family
            val = ann.get(annotation_type, "")
            if val and isinstance(val, str) and val.strip():
                return [val.strip()]
            return []

    # Build category counts for signature and background
    sig_annotated = set()
    bg_annotated = set()
    sig_cats: dict[str, set[str]] = {}  # category -> set of signature features
    bg_cats: dict[str, set[str]] = {}  # category -> set of ALL background features

    for feat in bg_set:
        cats = get_categories(feat)
        if cats or feat in annotations:
            bg_annotated.add(feat)
        for cat in cats:
            bg_cats.setdefault(cat, set()).add(feat)

    for feat in sig_set:
        cats = get_categories(feat)
        if cats or feat in annotations:
            sig_annotated.add(feat)
        for cat in cats:
            sig_cats.setdefault(cat, set()).add(feat)

    # Total annotated features
    n_sig_annotated = len(sig_annotated)
    n_bg_annotated = len(bg_annotated)
    # Non-signature background features
    nonsig_annotated = bg_annotated - sig_annotated

    if n_bg_annotated == 0 or n_sig_annotated == 0:
        return {
            "annotation_type": annotation_type,
            "signature_size": len(sig_set),
            "background_size": len(bg_set),
            "annotated_signature": n_sig_annotated,
            "annotated_background": n_bg_annotated,
            "results": [],
        }

    # All categories present in background
    all_categories = sorted(bg_cats.keys())

    results = []
    pvalues = []

    for cat in all_categories:
        # 2x2 contingency table
        sig_in = len(sig_cats.get(cat, set()))
        sig_out = n_sig_annotated - sig_in
        nonsig_in = len(bg_cats.get(cat, set()) - sig_set)
        nonsig_out = len(nonsig_annotated) - nonsig_in

        table = [[sig_in, sig_out], [nonsig_in, nonsig_out]]
        _, pval = fisher_exact(table, alternative="two-sided")
        pval = float(pval)  # convert numpy.float64 to native float

        pct_sig = (sig_in / n_sig_annotated * 100) if n_sig_annotated > 0 else 0
        pct_bg = (
            (len(bg_cats.get(cat, set())) / n_bg_annotated * 100)
            if n_bg_annotated > 0
            else 0
        )

        # Fold enrichment
        expected_pct = pct_bg if pct_bg > 0 else 0.001
        fold = pct_sig / expected_pct if expected_pct > 0 else float("inf")

        direction = "enriched" if pct_sig >= pct_bg else "depleted"

        results.append(
            {
                "category": cat,
                "count_in_signature": sig_in,
                "count_in_background": len(bg_cats.get(cat, set())),
                "pct_in_signature": round(pct_sig, 1),
                "pct_in_background": round(pct_bg, 1),
                "fold_enrichment": round(fold, 2),
                "p_value": pval,
                "direction": direction,
            }
        )
        pvalues.append(pval)

    # BH FDR correction
    fdr_values = benjamini_hochberg(pvalues)
    for i, row in enumerate(results):
        row["fdr"] = float(round(fdr_values[i], 4))
        row["p_value"] = float(round(row["p_value"], 6))
        row["significant"] = bool(fdr_values[i] < 0.05)

    # Sort by p-value
    results.sort(key=lambda r: r["p_value"])

    return {
        "annotation_type": annotation_type,
        "signature_size": len(sig_set),
        "background_size": len(bg_set),
        "annotated_signature": n_sig_annotated,
        "annotated_background": n_bg_annotated,
        "results": results,
    }
