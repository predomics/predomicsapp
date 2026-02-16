"""PDF biomarker report generation using reportlab."""

from __future__ import annotations

import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak,
)


def generate_pdf(
    job_id: str,
    job_name: str,
    results: dict,
    config: dict | None = None,
) -> bytes:
    """Generate a PDF biomarker report and return the bytes."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=20 * mm, bottomMargin=20 * mm,
    )

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        "SectionTitle", parent=styles["Heading2"],
        spaceAfter=8, spaceBefore=16,
        textColor=colors.HexColor("#0088CC"),
    ))
    styles.add(ParagraphStyle(
        "SmallText", parent=styles["Normal"],
        fontSize=8, textColor=colors.grey,
    ))

    story = []
    best = results.get("best_individual", {})
    feature_names = results.get("feature_names", [])
    config = config or {}
    gen_config = config.get("general", {})
    ga_config = config.get("ga", {})

    # ── Title ──
    story.append(Paragraph("Predomics Biomarker Discovery Report", styles["Title"]))
    story.append(Paragraph(
        f"Job: {_esc(job_name)} &bull; ID: {job_id[:12]} &bull; "
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        styles["SmallText"],
    ))
    story.append(Spacer(1, 12))

    # ── Page 1: Performance metrics ──
    story.append(Paragraph("Performance Metrics", styles["SectionTitle"]))

    metrics_data = [
        ["Metric", "Value"],
        ["AUC", _fmt(best.get("auc"))],
        ["Accuracy", _fmt(best.get("accuracy"))],
        ["Sensitivity", _fmt(best.get("sensitivity"))],
        ["Specificity", _fmt(best.get("specificity"))],
        ["Threshold", _fmt(best.get("threshold"))],
        ["Features (k)", str(best.get("k", "—"))],
        ["Language", str(best.get("language", "—"))],
        ["Data Type", str(best.get("data_type", "—"))],
        ["Epoch", str(best.get("epoch", "—"))],
    ]
    t = Table(metrics_data, colWidths=[55 * mm, 55 * mm])
    t.setStyle(_table_style())
    story.append(t)
    story.append(Spacer(1, 8))

    # Summary stats
    story.append(Paragraph("Analysis Summary", styles["SectionTitle"]))
    summary_data = [
        ["Statistic", "Value"],
        ["Total features in dataset", str(len(feature_names))],
        ["Total samples", str(len(results.get("sample_names", [])))],
        ["Generations", str(results.get("generation_count", "—"))],
        ["Execution time", _time_str(results.get("execution_time", 0))],
        ["Population size", str(results.get("population_size", "—"))],
    ]
    t2 = Table(summary_data, colWidths=[55 * mm, 55 * mm])
    t2.setStyle(_table_style())
    story.append(t2)

    # Jury metrics if available
    jury = results.get("jury")
    if jury:
        story.append(Spacer(1, 8))
        story.append(Paragraph("Jury Voting Results", styles["SectionTitle"]))
        jury_rows = [["Metric", "Train", "Test"]]
        train = jury.get("train", {})
        test = jury.get("test", {})
        for m in ["auc", "accuracy", "sensitivity", "specificity", "rejection_rate"]:
            jury_rows.append([
                m.replace("_", " ").title(),
                _fmt(train.get(m)),
                _fmt(test.get(m)) if test else "—",
            ])
        jt = Table(jury_rows, colWidths=[40 * mm, 35 * mm, 35 * mm])
        jt.setStyle(_table_style())
        story.append(jt)

    # ── Page 2: Feature table ──
    story.append(PageBreak())
    story.append(Paragraph("Biomarker Features", styles["SectionTitle"]))
    story.append(Paragraph(
        f"The best model uses <b>{best.get('k', '?')}</b> features with "
        f"<b>{best.get('language', '?')}</b> encoding.",
        styles["Normal"],
    ))
    story.append(Spacer(1, 6))

    features = best.get("features", {})
    feat_rows = [["#", "Feature", "Coefficient", "Direction"]]
    for i, (idx_str, coef) in enumerate(
        sorted(features.items(), key=lambda x: int(x[0])), 1
    ):
        idx = int(idx_str)
        name = feature_names[idx] if idx < len(feature_names) else f"feature_{idx}"
        coef_val = int(coef)
        direction = "Positive" if coef_val > 0 else "Negative"
        feat_rows.append([str(i), _esc(name), str(coef_val), direction])

    ft = Table(feat_rows, colWidths=[10 * mm, 70 * mm, 25 * mm, 25 * mm])
    ft.setStyle(_table_style(highlight_direction=True))
    story.append(ft)

    # ── Page 3: Configuration ──
    story.append(PageBreak())
    story.append(Paragraph("Configuration", styles["SectionTitle"]))

    cfg_data = [
        ["Parameter", "Value"],
        ["Algorithm", str(gen_config.get("algo", "ga"))],
        ["Language", str(gen_config.get("language", ""))],
        ["Data Type", str(gen_config.get("data_type", ""))],
        ["Fit Function", str(gen_config.get("fit", "auc"))],
        ["Seed", str(gen_config.get("seed", ""))],
        ["Population Size", str(ga_config.get("population_size", ""))],
        ["Max Epochs", str(ga_config.get("max_epochs", ""))],
        ["k Range", f"{ga_config.get('k_min', ga_config.get('kmin', ''))} – {ga_config.get('k_max', ga_config.get('kmax', ''))}"],
        ["Threads", str(gen_config.get("thread_number", ""))],
        ["k Penalty", str(gen_config.get("k_penalty", ""))],
    ]
    ct = Table(cfg_data, colWidths=[55 * mm, 55 * mm])
    ct.setStyle(_table_style())
    story.append(ct)

    # Generation tracking highlights
    tracking = results.get("generation_tracking", [])
    if tracking:
        story.append(Spacer(1, 8))
        story.append(Paragraph("Generation Tracking Highlights", styles["SectionTitle"]))
        first = tracking[0] if tracking else {}
        last = tracking[-1] if tracking else {}
        mid_idx = len(tracking) // 2
        mid = tracking[mid_idx] if tracking else {}

        gt_data = [
            ["Generation", "Best AUC", "Best k", "Population"],
            [
                str(first.get("generation", 0)),
                _fmt(first.get("best_auc")),
                str(first.get("best_k", "")),
                str(first.get("population_size", "")),
            ],
            [
                str(mid.get("generation", "")),
                _fmt(mid.get("best_auc")),
                str(mid.get("best_k", "")),
                str(mid.get("population_size", "")),
            ],
            [
                str(last.get("generation", "")),
                _fmt(last.get("best_auc")),
                str(last.get("best_k", "")),
                str(last.get("population_size", "")),
            ],
        ]
        gt = Table(gt_data, colWidths=[30 * mm, 35 * mm, 25 * mm, 30 * mm])
        gt.setStyle(_table_style())
        story.append(gt)

    # Footer
    story.append(Spacer(1, 20))
    story.append(Paragraph(
        "Generated by <b>PredomicsApp</b> — Predictive Models from Omics Data",
        styles["SmallText"],
    ))

    doc.build(story)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _esc(s: str) -> str:
    """Escape XML entities for reportlab Paragraphs."""
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _fmt(val, decimals=4) -> str:
    if val is None:
        return "—"
    if isinstance(val, (int, float)):
        return f"{val:.{decimals}f}"
    return str(val)


def _time_str(secs) -> str:
    if not secs:
        return "—"
    if secs < 60:
        return f"{secs:.1f}s"
    return f"{int(secs // 60)}m {int(secs % 60)}s"


def _table_style(highlight_direction=False):
    """Build a consistent TableStyle for report tables."""
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0088CC")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("FONTSIZE", (0, 0), (-1, 0), 10),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F5F5")]),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]

    if highlight_direction:
        # Color the Direction column — will be applied row by row after build
        # For simplicity, we color via static styles
        pass

    return TableStyle(style)
