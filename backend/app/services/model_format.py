"""Human-readable form of a BTR model, shared by the exports (CSV, HTML, PDF).

A model is a dict as stored in ``results.json``: ``named_features`` (name ->
coefficient) or ``features`` (index -> coefficient) plus ``language`` and
``data_type`` (either at the top level, as in ``best_individual``, or under
``metrics``, as in ``population``). OR-language models also carry
``named_clauses`` ([{"coef": c, "features": [names]}]) or ``clauses``
([[index, ...]]); each clause is one term of the formula, written ``(A ∨ B)``.

The spelling follows the engine's ``Individual::display``: terms are ordered by
feature index when it is known, a prevalence model marks its features with a
``⁰``, a log model wraps them in ``ln(...)``, Pow2 coefficients are written
``2*A`` and the Ratio languages read ``(pos) / (neg + ε)``.
"""

from __future__ import annotations

from typing import Any, Iterable

OR_SYMBOL = " ∨ "  # " ∨ "


def _metric(model: dict, key: str, default=None):
    if key in model and model[key] is not None:
        return model[key]
    return (model.get("metrics") or {}).get(key, default)


def _language_family(language) -> str:
    """'binary', 'ternary', 'pow2' or 'ratio', for a language name or alias (OR variants included)."""
    key = str(language or "").strip().lower()
    for suffix in ("-or", "_or"):
        if key.endswith(suffix):
            key = key[: -len(suffix)]
    return {
        "bin": "binary", "binary": "binary", "0": "binary",
        "ter": "ternary", "ternary": "ternary", "1": "ternary",
        "pow2": "pow2", "2": "pow2",
        "ratio": "ratio", "3": "ratio",
    }.get(key, "ternary")


def model_terms(model: dict, feature_names: list[str] | None = None) -> list[dict[str, Any]]:
    """The terms of a model: ``[{"features": [name, ...], "coef": int}, ...]``.

    One term per clause for an OR model, one per feature otherwise. Terms are
    ordered by feature index when ``features`` (index -> coefficient) is
    available, else by name.
    """
    feature_names = feature_names or []

    def name_of(idx) -> str:
        idx = int(idx)
        return str(feature_names[idx]) if idx < len(feature_names) else f"feature_{idx}"

    named_clauses = model.get("named_clauses")
    if named_clauses:
        return [
            {"features": [str(n) for n in c.get("features", [])], "coef": int(c.get("coef", 0))}
            for c in named_clauses
            if c.get("features")
        ]

    features = model.get("features") or {}
    clauses = model.get("clauses")
    if clauses and features:
        coef_of = {int(i): int(c) for i, c in features.items()}
        return [
            {"features": [name_of(i) for i in clause], "coef": coef_of.get(int(clause[0]), 0)}
            for clause in clauses
            if clause
        ]

    if features:
        items = sorted(((int(i), int(c)) for i, c in features.items()), key=lambda p: p[0])
        return [{"features": [name_of(i)], "coef": c} for i, c in items]

    named = model.get("named_features") or {}
    return [{"features": [str(n)], "coef": int(c)} for n, c in sorted(named.items())]


def _term_text(term: dict, data_type: str) -> str:
    names: Iterable[str] = term["features"]
    if data_type in ("prev", "prevalence"):
        names = [f"{n}⁰" for n in names]
    elif data_type == "log":
        names = [f"ln({n})" for n in names]
    names = list(names)
    if len(names) == 1:
        return names[0]
    return "(" + OR_SYMBOL.join(names) + ")"


def format_model_formula(model: dict, feature_names: list[str] | None = None,
                         with_threshold: bool = False) -> str:
    """Formula of a model, e.g. ``((A ∨ B) + C) - (D ∨ E)`` or ``(A + B) / (C + ε)``.

    ``with_threshold`` appends ``≥ threshold`` when the model has one.
    """
    terms = model_terms(model, feature_names)
    if not terms:
        return ""
    family = _language_family(_metric(model, "language"))
    data_type = str(_metric(model, "data_type", "raw") or "raw").strip().lower()

    positive, negative = [], []
    for term in terms:
        coef = term["coef"]
        if coef == 0:
            continue
        text = _term_text(term, data_type)
        if family == "pow2" and abs(coef) != 1:
            text = f"{abs(coef)}*{text}"
        (positive if coef > 0 else negative).append(text)

    # A side with several terms is parenthesised; a lone term (a feature or a
    # clause, which has its own parentheses) is not.
    def side(parts: list[str]) -> str:
        return parts[0] if len(parts) == 1 else "(" + " + ".join(parts) + ")"

    pos = side(positive) if positive else "0"
    if family == "ratio":
        formula = f"{pos} / {side(negative + ['ε'])}"
    elif negative:
        formula = f"{pos} - {side(negative)}"
    else:
        formula = " + ".join(positive) if positive else "0"

    threshold = _metric(model, "threshold")
    if with_threshold and threshold is not None:
        try:
            formula = f"{formula} ≥ {float(threshold):.4g}"
        except (TypeError, ValueError):
            pass
    return formula
