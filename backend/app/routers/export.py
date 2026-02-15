"""Export endpoints — download results as CSV or HTML report."""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.deps import get_current_user, get_project_with_access
from ..models.db_models import User, Job
from ..services import storage

router = APIRouter(prefix="/export", tags=["export"])


async def _get_job_results(project_id: str, job_id: str, user: User, db: AsyncSession):
    """Verify access and load results for a job."""
    await get_project_with_access(project_id, user, db, require_role="viewer")
    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.project_id == project_id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "completed":
        raise HTTPException(status_code=400, detail="Job not completed")

    results = storage.get_job_result(project_id, job_id)
    if not results:
        raise HTTPException(status_code=404, detail="Results not found")

    return job, results


@router.get("/{project_id}/jobs/{job_id}/csv")
async def export_csv(
    project_id: str,
    job_id: str,
    section: str = Query("best_model", description="Section to export: best_model, population, generation_tracking, jury_predictions"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Export a section of job results as CSV."""
    job, results = await _get_job_results(project_id, job_id, user, db)
    feature_names = results.get("feature_names", [])

    buf = io.StringIO()
    writer = csv.writer(buf)

    if section == "best_model":
        best = results.get("best_individual", {})
        if not best:
            raise HTTPException(status_code=404, detail="No best model data")

        writer.writerow(["Metric", "Value"])
        for key in ["auc", "fit", "accuracy", "sensitivity", "specificity", "threshold", "language", "data_type", "k", "epoch"]:
            writer.writerow([key, best.get(key, "")])

        writer.writerow([])
        writer.writerow(["Feature", "Coefficient"])
        features = best.get("features", {})
        for idx_str, coef in sorted(features.items(), key=lambda x: int(x[0])):
            idx = int(idx_str)
            name = feature_names[idx] if idx < len(feature_names) else f"feature_{idx}"
            writer.writerow([name, coef])

        filename = f"best_model_{job_id[:8]}.csv"

    elif section == "population":
        pop = results.get("population", [])
        if not pop:
            raise HTTPException(status_code=404, detail="No population data")

        writer.writerow(["Rank", "AUC", "Fit", "Accuracy", "Sensitivity", "Specificity", "Threshold", "Language", "Data Type", "k", "Epoch", "Features"])
        for ind in pop:
            m = ind.get("metrics", {})
            # Build feature string
            named = ind.get("named_features", {})
            feat_str = "; ".join(f"{name}={coef}" for name, coef in sorted(named.items()))
            writer.writerow([
                ind.get("rank", ""),
                m.get("auc", ""), m.get("fit", ""), m.get("accuracy", ""),
                m.get("sensitivity", ""), m.get("specificity", ""),
                m.get("threshold", ""), m.get("language", ""), m.get("data_type", ""),
                m.get("k", ""), m.get("epoch", ""),
                feat_str,
            ])

        filename = f"population_{job_id[:8]}.csv"

    elif section == "generation_tracking":
        tracking = results.get("generation_tracking", [])
        if not tracking:
            raise HTTPException(status_code=404, detail="No generation tracking data")

        writer.writerow(["Generation", "Best AUC", "Best Fit", "Best k", "Population Size", "Best AUC Test"])
        for g in tracking:
            writer.writerow([
                g.get("generation", ""),
                g.get("best_auc", ""), g.get("best_fit", ""),
                g.get("best_k", ""), g.get("population_size", ""),
                g.get("best_auc_test", ""),
            ])

        filename = f"generation_tracking_{job_id[:8]}.csv"

    elif section == "jury_predictions":
        jury = results.get("jury", {})
        predictions = jury.get("sample_predictions", [])
        if not predictions:
            raise HTTPException(status_code=404, detail="No jury prediction data")

        writer.writerow(["Sample", "Real Class", "Predicted Class", "Correct", "Consistency %", "Votes"])
        for p in predictions:
            writer.writerow([
                p.get("name", ""),
                p.get("real", ""), p.get("predicted", ""),
                p.get("correct", ""), p.get("consistency", ""),
                p.get("votes", ""),
            ])

        filename = f"jury_predictions_{job_id[:8]}.csv"

    else:
        raise HTTPException(status_code=400, detail=f"Unknown section: {section}. Use: best_model, population, generation_tracking, jury_predictions")

    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{project_id}/jobs/{job_id}/report")
async def export_report(
    project_id: str,
    job_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Export a complete HTML report for a job.

    The report is self-contained and can be opened in a browser,
    printed as PDF, or shared as a standalone file.
    """
    job, results = await _get_job_results(project_id, job_id, user, db)

    best = results.get("best_individual", {})
    feature_names = results.get("feature_names", [])
    tracking = results.get("generation_tracking", [])
    pop = results.get("population", [])
    jury = results.get("jury", None)
    importance = results.get("importance", None)

    job_name = job.name or job_id[:8]
    config = job.config or {}
    gen_config = config.get("general", {})
    ga_config = config.get("ga", {})

    # Build feature coefficients for best model
    best_features = []
    for idx_str, coef in sorted(best.get("features", {}).items(), key=lambda x: int(x[0])):
        idx = int(idx_str)
        name = feature_names[idx] if idx < len(feature_names) else f"feature_{idx}"
        best_features.append({"name": name, "coef": int(coef)})

    # Build population summary (top 20)
    pop_top = []
    for ind in pop[:20]:
        m = ind.get("metrics", {})
        named = ind.get("named_features", {})
        pop_top.append({
            "rank": ind.get("rank", 0),
            "auc": m.get("auc"), "fit": m.get("fit"),
            "accuracy": m.get("accuracy"), "k": m.get("k"),
            "language": m.get("language"), "data_type": m.get("data_type"),
            "features": ", ".join(f"{n}({'+'if c>0 else '-'})" for n, c in sorted(named.items())),
        })

    # Format execution time
    exec_time = results.get("execution_time", 0)
    if exec_time < 60:
        time_str = f"{exec_time:.1f}s"
    else:
        time_str = f"{int(exec_time // 60)}m {int(exec_time % 60)}s"

    # Build jury section if available
    jury_html = ""
    if jury:
        jury_html = _build_jury_html(jury)

    # Build importance section if available
    importance_html = ""
    if importance and len(importance) > 0:
        importance_html = _build_importance_html(importance)

    html = _build_report_html(
        job_id=job_id,
        job_name=job_name,
        best=best,
        best_features=best_features,
        results=results,
        feature_names=feature_names,
        tracking=tracking,
        pop=pop,
        pop_top=pop_top,
        gen_config=gen_config,
        ga_config=ga_config,
        time_str=time_str,
        jury_html=jury_html,
        importance_html=importance_html,
    )

    filename = f"predomics_report_{job_id[:8]}.html"
    return StreamingResponse(
        iter([html]),
        media_type="text/html",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{project_id}/jobs/{job_id}/json")
async def export_json(
    project_id: str,
    job_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Export full results as JSON download."""
    job, results = await _get_job_results(project_id, job_id, user, db)

    filename = f"results_{job_id[:8]}.json"
    content = json.dumps(results, indent=2, default=str)
    return StreamingResponse(
        iter([content]),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{project_id}/jobs/{job_id}/notebook")
async def export_notebook(
    project_id: str,
    job_id: str,
    lang: str = Query("python", description="Language: python or r"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate a Jupyter notebook (.ipynb) or R Markdown (.Rmd) that reproduces the analysis."""
    job, results = await _get_job_results(project_id, job_id, user, db)

    config = job.config or {}
    job_name = job.name or job_id[:8]
    best = results.get("best_individual", {})
    feature_names = results.get("feature_names", [])

    # Build feature list for the best model
    best_features = []
    for idx_str, coef in sorted(best.get("features", {}).items(), key=lambda x: int(x[0])):
        idx = int(idx_str)
        name = feature_names[idx] if idx < len(feature_names) else f"feature_{idx}"
        best_features.append({"name": name, "coef": int(coef)})

    if lang == "python":
        notebook = _build_python_notebook(job_name, job_id, config, best, best_features, results)
        filename = f"predomics_analysis_{job_id[:8]}.ipynb"
        content = json.dumps(notebook, indent=1)
        media_type = "application/x-ipynb+json"
    elif lang == "r":
        content = _build_r_notebook(job_name, job_id, config, best, best_features, results)
        filename = f"predomics_analysis_{job_id[:8]}.Rmd"
        media_type = "text/markdown"
    else:
        raise HTTPException(status_code=400, detail="lang must be 'python' or 'r'")

    return StreamingResponse(
        iter([content]),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Report HTML builder
# ---------------------------------------------------------------------------

def _build_report_html(*, job_id, job_name, best, best_features, results,
                       feature_names, tracking, pop, pop_top, gen_config,
                       ga_config, time_str, jury_html, importance_html):
    """Build a self-contained HTML report.

    Uses string concatenation to avoid f-string nesting issues with JavaScript.
    """
    # Feature chips
    chips = []
    for f in best_features:
        cls = "positive" if f["coef"] > 0 else "negative"
        sign = "+" if f["coef"] > 0 else ""
        chips.append(
            '<span class="feature-chip feature-' + cls + '">'
            + _esc(f["name"]) + " (" + sign + str(f["coef"]) + ")</span>"
        )
    chips_html = "".join(chips)

    # Population rows
    pop_rows = ""
    for p in pop_top:
        pop_rows += (
            "<tr><td>" + str(p["rank"] + 1) + "</td>"
            "<td>" + _fmt(p["auc"], 4) + "</td>"
            "<td>" + _fmt(p["fit"], 4) + "</td>"
            "<td>" + _fmt(p["accuracy"], 4) + "</td>"
            "<td>" + str(p["k"]) + "</td>"
            "<td>" + _esc(str(p["language"])) + "</td>"
            "<td>" + _esc(str(p["data_type"])) + "</td>"
            '<td style="font-size:0.75rem">' + _esc(p["features"]) + "</td></tr>\n"
        )

    pop_section = ""
    if pop_top:
        pop_section = (
            '<h2>Population (Top 20 of ' + str(len(pop)) + ')</h2>\n'
            '<table>\n'
            '<tr><th>#</th><th>AUC</th><th>Fit</th><th>Accuracy</th>'
            '<th>k</th><th>Language</th><th>Data Type</th><th>Features</th></tr>\n'
            + pop_rows +
            '</table>\n'
        )

    convergence_div = ""
    if tracking:
        convergence_div = (
            '<h2>AUC Evolution</h2>\n'
            '<div class="chart-container"><div id="convergenceChart"></div></div>\n'
        )

    # JavaScript for charts — built as plain strings to avoid brace conflicts
    features_json = json.dumps([f["name"] for f in best_features])
    coefs_json = json.dumps([f["coef"] for f in best_features])
    tracking_json = json.dumps(tracking) if tracking else "[]"

    coeff_chart_js = (
        "(function() {\n"
        "  var features = " + features_json + ";\n"
        "  var coefs = " + coefs_json + ";\n"
        "  var colors = coefs.map(function(c) { return c > 0 ? 'rgba(0,191,255,0.5)' : 'rgba(255,48,48,0.5)'; });\n"
        "  var borders = coefs.map(function(c) { return c > 0 ? '#00BFFF' : '#FF3030'; });\n"
        "  Plotly.newPlot('coeffChart', [{\n"
        "    type: 'bar', orientation: 'h',\n"
        "    y: features, x: coefs,\n"
        "    marker: { color: colors, line: { color: borders, width: 1.5 } }\n"
        "  }], {\n"
        "    paper_bgcolor: '#1a1f2e', plot_bgcolor: '#1a1f2e',\n"
        "    font: { color: '#d0d0dc', size: 12 },\n"
        "    margin: { t: 10, b: 40, l: 180, r: 20 },\n"
        "    height: Math.max(200, features.length * 30 + 60),\n"
        "    xaxis: { title: 'Coefficient', gridcolor: '#2a2f3e', zeroline: true, zerolinecolor: '#555', dtick: 1 },\n"
        "    yaxis: { automargin: true },\n"
        "    showlegend: false\n"
        "  }, { responsive: true, displayModeBar: false });\n"
        "})();\n"
    )

    convergence_js = ""
    if tracking:
        convergence_js = (
            "(function() {\n"
            "  var data = " + tracking_json + ";\n"
            "  var gens = data.map(function(g) { return g.generation; });\n"
            "  var trainAuc = data.map(function(g) { return g.best_auc; });\n"
            "  var hasTest = data.some(function(g) { return g.best_auc_test != null; });\n"
            "  var testAuc = hasTest ? data.map(function(g) { return g.best_auc_test; }) : null;\n"
            "  var traces = [{\n"
            "    x: gens, y: trainAuc, name: 'Train AUC',\n"
            "    type: 'scatter', mode: 'lines+markers',\n"
            "    line: { color: '#00BFFF', width: 2 }, marker: { size: 4 }\n"
            "  }];\n"
            "  if (testAuc) {\n"
            "    traces.push({\n"
            "      x: gens, y: testAuc, name: 'Test AUC',\n"
            "      type: 'scatter', mode: 'lines+markers',\n"
            "      line: { color: '#FF3030', width: 2, dash: 'dash' }, marker: { size: 4 }\n"
            "    });\n"
            "  }\n"
            "  Plotly.newPlot('convergenceChart', traces, {\n"
            "    paper_bgcolor: '#1a1f2e', plot_bgcolor: '#1a1f2e',\n"
            "    font: { color: '#d0d0dc', size: 12 },\n"
            "    margin: { t: 20, b: 50, l: 60, r: 20 },\n"
            "    height: 300,\n"
            "    xaxis: { title: 'Generation', gridcolor: '#2a2f3e' },\n"
            "    yaxis: { title: 'AUC', gridcolor: '#2a2f3e' },\n"
            "    legend: { orientation: 'h', y: 1.12 }\n"
            "  }, { responsive: true, displayModeBar: false });\n"
            "})();\n"
        )

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Assemble the full HTML using a template with %s placeholders
    # to avoid any f-string / brace issues
    html = _REPORT_TEMPLATE % {
        "title": _esc(job_name),
        "job_name": _esc(job_name),
        "job_id_short": job_id[:12],
        "now": now_str,
        "auc": _fmt(best.get("auc"), 4),
        "k": best.get("k", "—"),
        "time": time_str,
        "generations": results.get("generation_count", "—"),
        "total_features": len(feature_names),
        "samples": len(results.get("sample_names", [])),
        "pop_size": len(pop),
        "language": _esc(str(best.get("language", "—"))),
        "auc2": _fmt(best.get("auc"), 4),
        "fit": _fmt(best.get("fit"), 4),
        "accuracy": _fmt(best.get("accuracy"), 4),
        "sensitivity": _fmt(best.get("sensitivity"), 4),
        "specificity": _fmt(best.get("specificity"), 4),
        "threshold": _fmt(best.get("threshold"), 4),
        "best_language": _esc(str(best.get("language", ""))),
        "best_data_type": _esc(str(best.get("data_type", ""))),
        "best_epoch": best.get("epoch", ""),
        "chips_html": chips_html,
        "convergence_div": convergence_div,
        "importance_html": importance_html,
        "pop_section": pop_section,
        "jury_html": jury_html,
        "algo": _esc(str(gen_config.get("algo", "ga"))),
        "cfg_language": _esc(str(gen_config.get("language", ""))),
        "cfg_data_type": _esc(str(gen_config.get("data_type", ""))),
        "cfg_fit": _esc(str(gen_config.get("fit", "auc"))),
        "cfg_seed": gen_config.get("seed", ""),
        "cfg_pop_size": ga_config.get("population_size", ""),
        "cfg_max_epochs": ga_config.get("max_epochs", ""),
        "cfg_k_min": ga_config.get("k_min", ""),
        "cfg_k_max": ga_config.get("k_max", ""),
        "cfg_threads": gen_config.get("thread_number", ""),
        "cfg_k_penalty": gen_config.get("k_penalty", ""),
        "coeff_chart_js": coeff_chart_js,
        "convergence_js": convergence_js,
    }
    return html


_REPORT_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Predomics Report — %(title)s</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
  :root {
    --primary: #00BFFF; --danger: #FF3030;
    --bg: #0f1219; --bg-card: #1a1f2e;
    --text: #d0d0dc; --text-muted: #8888a0;
    --border: #2a2f3e; --positive: #00BFFF; --negative: #FF3030;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: system-ui, -apple-system, sans-serif;
    background: var(--bg); color: var(--text);
    line-height: 1.6; padding: 2rem; max-width: 1200px; margin: 0 auto;
  }
  h1 { font-size: 1.8rem; margin-bottom: 0.3rem; color: var(--primary); }
  h2 { font-size: 1.3rem; margin: 2rem 0 1rem; padding-bottom: 0.4rem;
       border-bottom: 2px solid var(--border); color: var(--primary); }
  h3 { font-size: 1rem; margin: 1.2rem 0 0.5rem; color: var(--text); }
  .subtitle { color: var(--text-muted); font-size: 0.9rem; margin-bottom: 1.5rem; }
  .stats-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
                gap: 0.75rem; margin-bottom: 1.5rem; }
  .stat-card { background: var(--bg-card); border: 1px solid var(--border);
               border-radius: 8px; padding: 0.75rem 1rem; text-align: center; }
  .stat-value { font-size: 1.4rem; font-weight: 700; color: var(--primary); }
  .stat-label { font-size: 0.75rem; color: var(--text-muted);
                text-transform: uppercase; letter-spacing: 0.05em; }
  table { width: 100%%; border-collapse: collapse; font-size: 0.85rem; margin-bottom: 1rem; }
  th, td { padding: 0.5rem 0.75rem; text-align: left; border-bottom: 1px solid var(--border); }
  th { background: var(--bg-card); font-weight: 600; color: var(--text-muted);
       text-transform: uppercase; font-size: 0.75rem; letter-spacing: 0.05em; }
  .feature-chip { display: inline-block; padding: 0.2rem 0.6rem;
                  border-radius: 12px; font-size: 0.8rem; margin: 0.15rem; }
  .feature-positive { background: rgba(0,191,255,0.15); border: 1px solid rgba(0,191,255,0.4);
                      color: var(--positive); }
  .feature-negative { background: rgba(255,48,48,0.15); border: 1px solid rgba(255,48,48,0.4);
                      color: var(--negative); }
  .chart-container { background: var(--bg-card); border: 1px solid var(--border);
                     border-radius: 8px; padding: 1rem; margin-bottom: 1.5rem; }
  .config-grid { display: grid; grid-template-columns: 1fr 1fr;
                 gap: 0.5rem 2rem; font-size: 0.85rem; }
  .config-item { display: flex; justify-content: space-between; }
  .config-key { color: var(--text-muted); }
  .config-val { font-weight: 500; }
  .footer { margin-top: 3rem; padding-top: 1rem; border-top: 1px solid var(--border);
            font-size: 0.75rem; color: var(--text-muted); text-align: center; }
  @media print {
    body { background: white; color: #333; padding: 1rem; }
    :root { --primary: #0088cc; --danger: #cc2020; --bg: #fff; --bg-card: #f9f9f9;
            --text: #333; --text-muted: #888; --border: #ddd; }
  }
</style>
</head>
<body>

<h1>Predomics Analysis Report</h1>
<div class="subtitle">
  Job: %(job_name)s &bull; ID: %(job_id_short)s &bull; Generated: %(now)s
</div>

<div class="stats-grid">
  <div class="stat-card"><div class="stat-value">%(auc)s</div><div class="stat-label">Best AUC</div></div>
  <div class="stat-card"><div class="stat-value">%(k)s</div><div class="stat-label">Features (k)</div></div>
  <div class="stat-card"><div class="stat-value">%(time)s</div><div class="stat-label">Time</div></div>
  <div class="stat-card"><div class="stat-value">%(generations)s</div><div class="stat-label">Generations</div></div>
  <div class="stat-card"><div class="stat-value">%(total_features)s</div><div class="stat-label">Total Features</div></div>
  <div class="stat-card"><div class="stat-value">%(samples)s</div><div class="stat-label">Samples</div></div>
  <div class="stat-card"><div class="stat-value">%(pop_size)s</div><div class="stat-label">Population</div></div>
  <div class="stat-card"><div class="stat-value">%(language)s</div><div class="stat-label">Language</div></div>
</div>

<h2>Best Model</h2>
<h3>Metrics</h3>
<table>
  <tr><th>Metric</th><th>Value</th></tr>
  <tr><td>AUC</td><td>%(auc2)s</td></tr>
  <tr><td>Fit</td><td>%(fit)s</td></tr>
  <tr><td>Accuracy</td><td>%(accuracy)s</td></tr>
  <tr><td>Sensitivity</td><td>%(sensitivity)s</td></tr>
  <tr><td>Specificity</td><td>%(specificity)s</td></tr>
  <tr><td>Threshold</td><td>%(threshold)s</td></tr>
  <tr><td>Language</td><td>%(best_language)s</td></tr>
  <tr><td>Data Type</td><td>%(best_data_type)s</td></tr>
  <tr><td>Epoch</td><td>%(best_epoch)s</td></tr>
</table>

<h3>Model Features</h3>
<div>%(chips_html)s</div>

<div class="chart-container"><div id="coeffChart"></div></div>

%(convergence_div)s
%(importance_html)s
%(pop_section)s
%(jury_html)s

<h2>Configuration</h2>
<div class="config-grid">
  <div class="config-item"><span class="config-key">Algorithm</span><span class="config-val">%(algo)s</span></div>
  <div class="config-item"><span class="config-key">Language</span><span class="config-val">%(cfg_language)s</span></div>
  <div class="config-item"><span class="config-key">Data Type</span><span class="config-val">%(cfg_data_type)s</span></div>
  <div class="config-item"><span class="config-key">Fit Function</span><span class="config-val">%(cfg_fit)s</span></div>
  <div class="config-item"><span class="config-key">Seed</span><span class="config-val">%(cfg_seed)s</span></div>
  <div class="config-item"><span class="config-key">Population Size</span><span class="config-val">%(cfg_pop_size)s</span></div>
  <div class="config-item"><span class="config-key">Max Epochs</span><span class="config-val">%(cfg_max_epochs)s</span></div>
  <div class="config-item"><span class="config-key">k Range</span><span class="config-val">%(cfg_k_min)s – %(cfg_k_max)s</span></div>
  <div class="config-item"><span class="config-key">Threads</span><span class="config-val">%(cfg_threads)s</span></div>
  <div class="config-item"><span class="config-key">k Penalty</span><span class="config-val">%(cfg_k_penalty)s</span></div>
</div>

<div class="footer">
  Generated by <strong>PredomicsApp</strong> &mdash; Predictive Models from Omics Data
</div>

<script>
%(coeff_chart_js)s
%(convergence_js)s
</script>

</body>
</html>"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _esc(s: str) -> str:
    """Escape HTML entities."""
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _fmt(val, decimals=4) -> str:
    """Format a numeric value."""
    if val is None:
        return "—"
    if isinstance(val, (int, float)):
        return f"{val:.{decimals}f}"
    return str(val)


def _build_jury_html(jury: dict) -> str:
    """Build HTML section for jury results."""
    preds = jury.get("sample_predictions", [])
    train = jury.get("train", {})
    test = jury.get("test", {})

    html = '<h2>Jury Voting</h2>\n'
    html += '<div class="stats-grid">\n'
    for label, data in [("Train", train), ("Test", test)]:
        if not data:
            continue
        for metric in ["auc", "accuracy", "sensitivity", "specificity"]:
            val = data.get(metric)
            if val is not None:
                html += f'  <div class="stat-card"><div class="stat-value">{_fmt(val, 4)}</div>'
                html += f'<div class="stat-label">{label} {metric.title()}</div></div>\n'
    html += '</div>\n'

    if preds:
        html += f'<h3>Sample Predictions ({len(preds)} samples)</h3>\n'
        html += '<table>\n<tr><th>Sample</th><th>Real</th><th>Predicted</th><th>Correct</th><th>Consistency %</th></tr>\n'
        for p in preds[:50]:
            correct = p.get("correct", "")
            row_style = ' style="color: #FF3030;"' if correct == False else ''
            html += f'<tr{row_style}><td>{_esc(str(p.get("name", "")))}</td>'
            html += f'<td>{p.get("real", "")}</td><td>{p.get("predicted", "")}</td>'
            html += f'<td>{"Yes" if correct else "No"}</td>'
            html += f'<td>{_fmt(p.get("consistency"), 1)}</td></tr>\n'
        html += '</table>\n'
        if len(preds) > 50:
            html += f'<p style="color: var(--text-muted); font-size: 0.8rem;">Showing first 50 of {len(preds)} predictions. Export CSV for full data.</p>\n'

    return html


# ---------------------------------------------------------------------------
# Notebook builders
# ---------------------------------------------------------------------------

def _nb_cell(cell_type: str, source: str, **kwargs) -> dict:
    """Build a single Jupyter notebook cell."""
    # Jupyter expects each line to end with \n except the last
    lines = source.split("\n")
    src = [line + "\n" for line in lines[:-1]] + [lines[-1]] if len(lines) > 1 else [source]
    cell = {
        "cell_type": cell_type,
        "metadata": {},
        "source": src,
    }
    if cell_type == "code":
        cell["execution_count"] = None
        cell["outputs"] = []
    return cell


def _build_python_notebook(job_name, job_id, config, best, best_features, results):
    """Build a Jupyter notebook (.ipynb) that reproduces the analysis with gpredomicspy."""
    gen = config.get("general", {})
    ga = config.get("ga", {})
    data = config.get("data", {})
    voting = config.get("voting", {})
    importance_cfg = config.get("importance", {})

    # Resolve config values (handle Pydantic enum .value)
    algo = gen.get("algo", "ga")
    if hasattr(algo, "value"):
        algo = algo.value
    language = gen.get("language", "bin,ter,ratio")
    data_type = gen.get("data_type", "raw,prev")
    fit_fn = gen.get("fit", "auc")
    if hasattr(fit_fn, "value"):
        fit_fn = fit_fn.value

    # Build feature info for the results recap
    feature_lines = []
    for f in best_features[:20]:
        sign = "+" if f["coef"] > 0 else ""
        feature_lines.append(f'  "{f["name"]}": {sign}{f["coef"]}')
    features_str = ",\\n".join(feature_lines)

    cells = []

    # Title
    cells.append(_nb_cell("markdown",
        f"# Predomics Analysis — {job_name}\n"
        f"\n"
        f"This notebook reproduces the analysis from job `{job_id[:12]}`.\n"
        f"It uses **gpredomicspy** (Python bindings for the Rust-based gpredomics engine).\n"
        f"\n"
        f"## Original Results Summary\n"
        f"- **AUC**: {_fmt(best.get('auc'), 4)}\n"
        f"- **Features (k)**: {best.get('k', '?')}\n"
        f"- **Language**: {best.get('language', '?')}\n"
        f"- **Data Type**: {best.get('data_type', '?')}\n"
    ))

    # Install
    cells.append(_nb_cell("markdown",
        "## 1. Install gpredomicspy\n"
        "\n"
        "If not already installed, uncomment and run the cell below."
    ))
    cells.append(_nb_cell("code",
        "# !pip install gpredomicspy"
    ))

    # Imports
    cells.append(_nb_cell("code",
        "import gpredomicspy\n"
        "import yaml\n"
        "import json\n"
        "import tempfile\n"
        "import os\n"
        "from pathlib import Path"
    ))

    # Data paths
    cells.append(_nb_cell("markdown",
        "## 2. Data Paths\n"
        "\n"
        "Update the paths below to point to your data files.\n"
        "- **X**: feature matrix (samples x features or features x samples)\n"
        "- **y**: class labels"
    ))
    cells.append(_nb_cell("code",
        '# Update these paths to your data files\n'
        'X_PATH = "your_data_X.tsv"\n'
        'Y_PATH = "your_data_y.tsv"\n'
        '\n'
        '# Optional: test data (leave empty to use holdout split)\n'
        'X_TEST_PATH = ""\n'
        'Y_TEST_PATH = ""'
    ))

    # Configuration
    k_min = ga.get("k_min", ga.get("kmin", 1))
    k_max = ga.get("k_max", ga.get("kmax", 200))
    pop_size = ga.get("population_size", 5000)
    max_epochs = ga.get("max_epochs", 200)
    seed = gen.get("seed", 42)
    threads = gen.get("thread_number", 4)
    k_penalty = gen.get("k_penalty", 0.0001)
    holdout = data.get("holdout_ratio", 0.20)
    features_in_rows = data.get("features_in_rows", True)
    cv_enabled = gen.get("cv", False)
    gpu_enabled = gen.get("gpu", False)
    vote_enabled = voting.get("vote", False)
    compute_imp = importance_cfg.get("compute_importance", False)

    cells.append(_nb_cell("markdown",
        "## 3. Configuration\n"
        "\n"
        "These parameters match the original analysis. Modify as needed."
    ))

    config_code = (
        f'config = {{\n'
        f'    "general": {{\n'
        f'        "algo": "{algo}",\n'
        f'        "language": "{language}",\n'
        f'        "data_type": "{data_type}",\n'
        f'        "fit": "{fit_fn}",\n'
        f'        "seed": {seed},\n'
        f'        "thread_number": {threads},\n'
        f'        "k_penalty": {k_penalty},\n'
        f'        "cv": {str(cv_enabled)},\n'
        f'        "gpu": {str(gpu_enabled)},\n'
        f'        "log_level": "info",\n'
        f'        "keep_trace": True,\n'
        f'        "display_colorful": True,\n'
        f'    }},\n'
        f'    "data": {{\n'
        f'        "X": X_PATH,\n'
        f'        "y": Y_PATH,\n'
        f'        "Xtest": X_TEST_PATH,\n'
        f'        "ytest": Y_TEST_PATH,\n'
        f'        "holdout_ratio": {holdout},\n'
        f'        "features_in_rows": {str(features_in_rows)},\n'
        f'    }},\n'
        f'    "ga": {{\n'
        f'        "population_size": {pop_size},\n'
        f'        "max_epochs": {max_epochs},\n'
        f'        "kmin": {k_min},\n'
        f'        "kmax": {k_max},\n'
        f'    }},\n'
        f'    "voting": {{\n'
        f'        "vote": {str(vote_enabled)},\n'
        f'    }},\n'
        f'    "importance": {{\n'
        f'        "compute_importance": {str(compute_imp)},\n'
        f'    }},\n'
        f'}}'
    )
    cells.append(_nb_cell("code", config_code))

    # Write YAML and run
    cells.append(_nb_cell("markdown",
        "## 4. Run Analysis\n"
        "\n"
        "Write the configuration to a YAML file and run gpredomics."
    ))
    cells.append(_nb_cell("code",
        '# Write config to YAML\n'
        'output_dir = tempfile.mkdtemp(prefix="predomics_")\n'
        'config["general"]["save_exp"] = os.path.join(output_dir, "experiment.bin")\n'
        '\n'
        'yaml_path = os.path.join(output_dir, "param.yaml")\n'
        'with open(yaml_path, "w") as f:\n'
        '    yaml.dump(config, f, default_flow_style=False, sort_keys=False)\n'
        '\n'
        'print(f"Config written to: {yaml_path}")\n'
        'print(f"Output directory: {output_dir}")'
    ))
    cells.append(_nb_cell("code",
        '# Run gpredomics\n'
        'gpredomicspy.init_logger("info")\n'
        '\n'
        'param = gpredomicspy.Param()\n'
        'param.load(yaml_path)\n'
        '\n'
        'experiment = gpredomicspy.fit(param)\n'
        'print("Fit complete!")'
    ))

    # Extract results
    cells.append(_nb_cell("markdown",
        "## 5. Extract Results"
    ))
    cells.append(_nb_cell("code",
        '# Get best population and best model\n'
        'best_pop = experiment.best_population()\n'
        'best = best_pop.best()\n'
        'metrics = dict(best.get_metrics())\n'
        '\n'
        'print(f"Best AUC:         {metrics.get(\'auc\', \'N/A\')}")\n'
        'print(f"Accuracy:         {metrics.get(\'accuracy\', \'N/A\')}")\n'
        'print(f"Sensitivity:      {metrics.get(\'sensitivity\', \'N/A\')}")\n'
        'print(f"Specificity:      {metrics.get(\'specificity\', \'N/A\')}")\n'
        'print(f"Features (k):     {metrics.get(\'k\', \'N/A\')}")\n'
        'print(f"Language:         {metrics.get(\'language\', \'N/A\')}")\n'
        'print(f"Data Type:        {metrics.get(\'data_type\', \'N/A\')}")'
    ))

    # Feature coefficients
    cells.append(_nb_cell("code",
        '# Get feature coefficients\n'
        'features = dict(best.get_features())\n'
        'feature_names = experiment.feature_names()\n'
        '\n'
        'print("\\nModel Features:")\n'
        'print("-" * 40)\n'
        'for idx_str, coef in sorted(features.items(), key=lambda x: int(x[0])):\n'
        '    idx = int(idx_str)\n'
        '    name = feature_names[idx] if idx < len(feature_names) else f"feature_{idx}"\n'
        '    sign = "+" if coef > 0 else ""\n'
        '    print(f"  {name}: {sign}{int(coef)}")'
    ))

    # Visualizations
    cells.append(_nb_cell("markdown",
        "## 6. Visualizations"
    ))
    cells.append(_nb_cell("code",
        'import matplotlib.pyplot as plt\n'
        'import numpy as np'
    ))

    # Coefficient bar chart
    cells.append(_nb_cell("code",
        '# Feature coefficient bar chart\n'
        'feat_names = []\n'
        'feat_coefs = []\n'
        'for idx_str, coef in sorted(features.items(), key=lambda x: int(x[0])):\n'
        '    idx = int(idx_str)\n'
        '    name = feature_names[idx] if idx < len(feature_names) else f"feature_{idx}"\n'
        '    feat_names.append(name)\n'
        '    feat_coefs.append(int(coef))\n'
        '\n'
        'colors = ["#00BFFF" if c > 0 else "#FF3030" for c in feat_coefs]\n'
        '\n'
        'fig, ax = plt.subplots(figsize=(10, max(3, len(feat_names) * 0.4)))\n'
        'ax.barh(feat_names, feat_coefs, color=colors, edgecolor="white", linewidth=0.5)\n'
        'ax.set_xlabel("Coefficient")\n'
        'ax.set_title("Best Model — Feature Coefficients")\n'
        'ax.axvline(0, color="gray", linewidth=0.8, linestyle="--")\n'
        'plt.tight_layout()\n'
        'plt.show()'
    ))

    # Generation tracking plot
    cells.append(_nb_cell("code",
        '# AUC evolution across generations\n'
        'tracking = experiment.generation_tracking()\n'
        '\n'
        'if tracking:\n'
        '    gens = [g["generation"] for g in tracking]\n'
        '    train_auc = [g["best_auc"] for g in tracking]\n'
        '    test_auc = [g.get("best_auc_test") for g in tracking]\n'
        '    has_test = any(v is not None for v in test_auc)\n'
        '\n'
        '    fig, ax = plt.subplots(figsize=(10, 4))\n'
        '    ax.plot(gens, train_auc, label="Train AUC", color="#00BFFF", linewidth=2)\n'
        '    if has_test:\n'
        '        ax.plot(gens, test_auc, label="Test AUC", color="#FF3030",\n'
        '                linewidth=2, linestyle="--")\n'
        '    ax.set_xlabel("Generation")\n'
        '    ax.set_ylabel("AUC")\n'
        '    ax.set_title("AUC Evolution")\n'
        '    ax.legend()\n'
        '    ax.grid(alpha=0.3)\n'
        '    plt.tight_layout()\n'
        '    plt.show()\n'
        'else:\n'
        '    print("No generation tracking data available.")'
    ))

    # Original results comparison
    cells.append(_nb_cell("markdown",
        "## 7. Comparison with Original Results\n"
        "\n"
        "The original analysis produced the following best model features:\n"
        "```\n"
        + "{\n" + features_str + "\n}\n"
        + "```"
    ))

    # Notebook structure
    notebook = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {
                "name": "python",
                "version": "3.11.0",
            },
        },
        "cells": cells,
    }
    return notebook


def _build_r_notebook(job_name, job_id, config, best, best_features, results):
    """Build an R Markdown (.Rmd) notebook that reproduces the analysis."""
    gen = config.get("general", {})
    ga = config.get("ga", {})
    data = config.get("data", {})

    algo = gen.get("algo", "ga")
    if hasattr(algo, "value"):
        algo = algo.value
    language = gen.get("language", "bin,ter,ratio")
    data_type = gen.get("data_type", "raw,prev")
    fit_fn = gen.get("fit", "auc")
    if hasattr(fit_fn, "value"):
        fit_fn = fit_fn.value

    k_min = ga.get("k_min", ga.get("kmin", 1))
    k_max = ga.get("k_max", ga.get("kmax", 200))
    pop_size = ga.get("population_size", 5000)
    max_epochs = ga.get("max_epochs", 200)
    seed = gen.get("seed", 42)
    threads = gen.get("thread_number", 4)
    holdout = data.get("holdout_ratio", 0.20)

    # Build feature summary for comparison
    feature_lines = []
    for f in best_features[:20]:
        sign = "+" if f["coef"] > 0 else ""
        feature_lines.append(f'  {f["name"]}: {sign}{f["coef"]}')
    features_str = "\n".join(feature_lines)

    rmd = f"""---
title: "Predomics Analysis — {job_name}"
author: "Generated by PredomicsApp"
date: "`r Sys.Date()`"
output:
  html_document:
    theme: darkly
    toc: true
    toc_float: true
---

# About

This R Markdown notebook reproduces the analysis from job `{job_id[:12]}`.
It uses **gpredomicsR**, the R interface to the gpredomics engine.

## Original Results Summary

- **AUC**: {_fmt(best.get('auc'), 4)}
- **Features (k)**: {best.get('k', '?')}
- **Language**: {best.get('language', '?')}

# 1. Setup

```{{r setup, message=FALSE}}
# Install gpredomicsR if needed:
# devtools::install_github("predomics/gpredomicsR")

library(gpredomicsR)
library(ggplot2)
library(yaml)
```

# 2. Data Paths

Update the paths below to point to your data files.

```{{r data_paths}}
X_PATH <- "your_data_X.tsv"
Y_PATH <- "your_data_y.tsv"

# Optional: test data (set to "" for holdout split)
X_TEST_PATH <- ""
Y_TEST_PATH <- ""
```

# 3. Configuration

These parameters match the original analysis.

```{{r config}}
config <- list(
  general = list(
    algo = "{algo}",
    language = "{language}",
    data_type = "{data_type}",
    fit = "{fit_fn}",
    seed = {seed}L,
    thread_number = {threads}L,
    k_penalty = {gen.get('k_penalty', 0.0001)},
    cv = {str(gen.get('cv', False)).upper()},
    gpu = {str(gen.get('gpu', False)).upper()},
    log_level = "info",
    keep_trace = TRUE,
    display_colorful = TRUE
  ),
  data = list(
    X = X_PATH,
    y = Y_PATH,
    Xtest = X_TEST_PATH,
    ytest = Y_TEST_PATH,
    holdout_ratio = {holdout},
    features_in_rows = {str(data.get('features_in_rows', True)).upper()}
  ),
  ga = list(
    population_size = {pop_size}L,
    max_epochs = {max_epochs}L,
    kmin = {k_min}L,
    kmax = {k_max}L
  )
)

# Write config to YAML
output_dir <- tempdir()
config$general$save_exp <- file.path(output_dir, "experiment.bin")
yaml_path <- file.path(output_dir, "param.yaml")
write_yaml(config, yaml_path)
cat("Config written to:", yaml_path, "\\n")
```

# 4. Run Analysis

```{{r run_analysis}}
param <- gpredomicsR::Param$new()
param$load(yaml_path)

experiment <- gpredomicsR::fit(param)
cat("Fit complete!\\n")
```

# 5. Extract Results

```{{r results}}
best_pop <- experiment$best_population()
best_model <- best_pop$best()
metrics <- best_model$get_metrics()

cat(sprintf("Best AUC:      %s\\n", metrics$auc))
cat(sprintf("Accuracy:      %s\\n", metrics$accuracy))
cat(sprintf("Sensitivity:   %s\\n", metrics$sensitivity))
cat(sprintf("Specificity:   %s\\n", metrics$specificity))
cat(sprintf("Features (k):  %s\\n", metrics$k))
cat(sprintf("Language:      %s\\n", metrics$language))
```

```{{r features}}
features <- best_model$get_features()
feature_names <- experiment$feature_names()

cat("\\nModel Features:\\n")
cat(strrep("-", 40), "\\n")
for (idx_str in names(features)) {{
  idx <- as.integer(idx_str) + 1  # R is 1-indexed
  name <- if (idx <= length(feature_names)) feature_names[idx] else paste0("feature_", idx)
  coef <- features[[idx_str]]
  sign <- if (coef > 0) "+" else ""
  cat(sprintf("  %s: %s%d\\n", name, sign, as.integer(coef)))
}}
```

# 6. Visualizations

```{{r coef_plot, fig.width=10, fig.height=6}}
# Feature coefficient bar chart
feat_df <- data.frame(
  name = character(0),
  coef = numeric(0),
  stringsAsFactors = FALSE
)

for (idx_str in names(features)) {{
  idx <- as.integer(idx_str) + 1
  name <- if (idx <= length(feature_names)) feature_names[idx] else paste0("feature_", idx)
  feat_df <- rbind(feat_df, data.frame(name = name, coef = as.numeric(features[[idx_str]])))
}}

feat_df$name <- factor(feat_df$name, levels = rev(feat_df$name))

ggplot(feat_df, aes(x = coef, y = name, fill = coef > 0)) +
  geom_col(show.legend = FALSE) +
  scale_fill_manual(values = c("TRUE" = "#00BFFF", "FALSE" = "#FF3030")) +
  labs(x = "Coefficient", y = "", title = "Best Model — Feature Coefficients") +
  theme_dark() +
  geom_vline(xintercept = 0, color = "gray", linetype = "dashed")
```

```{{r auc_evolution, fig.width=10, fig.height=5}}
# AUC evolution across generations
tracking <- experiment$generation_tracking()

if (length(tracking) > 0) {{
  gens <- sapply(tracking, function(g) g$generation)
  train_auc <- sapply(tracking, function(g) g$best_auc)

  plot_df <- data.frame(generation = gens, auc = train_auc, set = "Train")

  test_auc <- sapply(tracking, function(g) g$best_auc_test)
  if (!all(is.null(test_auc))) {{
    plot_df <- rbind(plot_df,
      data.frame(generation = gens, auc = test_auc, set = "Test"))
  }}

  ggplot(plot_df, aes(x = generation, y = auc, color = set)) +
    geom_line(linewidth = 1) +
    geom_point(size = 1.5) +
    scale_color_manual(values = c("Train" = "#00BFFF", "Test" = "#FF3030")) +
    labs(x = "Generation", y = "AUC", title = "AUC Evolution", color = "") +
    theme_dark() +
    theme(legend.position = "top")
}} else {{
  cat("No generation tracking data available.\\n")
}}
```

# 7. Comparison with Original Results

The original analysis produced the following best model:

```
{features_str}
```
"""
    return rmd


def _build_importance_html(importance: list) -> str:
    """Build HTML section for feature importance."""
    html = '<h2>Feature Importance (MDA)</h2>\n'
    html += '<table>\n<tr><th>Feature</th><th>Importance</th></tr>\n'
    sorted_imp = sorted(importance, key=lambda x: abs(x.get("importance", 0)), reverse=True)
    for item in sorted_imp[:30]:
        html += f'<tr><td>{_esc(item.get("feature", ""))}</td><td>{_fmt(item.get("importance"), 4)}</td></tr>\n'
    html += '</table>\n'
    return html
