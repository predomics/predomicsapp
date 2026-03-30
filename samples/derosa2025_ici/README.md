# Derosa et al. 2025 — ICI Response Prediction (NSAT Cohort)

Demo dataset for PredomicsApp, derived from the work of:

> **Derosa L, Iebba V, Silva CAC, et al.** *Custom scoring based on ecological topology of gut microbiota associated with cancer immunotherapy outcome.* Cell. 2024;187(13):3373-3389.e16. doi:[10.1016/j.cell.2024.05.029](https://doi.org/10.1016/j.cell.2024.05.029)

The NSAT cohort presented here is part of the broader research program led by Lisa Derosa and Laurence Zitvogel at Gustave Roussy Cancer Campus (Villejuif, France), investigating the role of the gut microbiome in predicting immune checkpoint inhibitor (ICI) efficacy across multiple cancer types.

## Context

Immune checkpoint inhibitors (ICIs) targeting PD-1/PD-L1 have transformed cancer treatment, but only a fraction of patients respond durably. Growing evidence links the gut microbiome composition at baseline to treatment outcome. In this study, shotgun metagenomics sequencing of pre-treatment stool samples was used to characterize the gut ecosystem of cancer patients receiving ICIs. The primary endpoint — overall survival at 12 months (OS12) — stratifies patients into responders (OS12+) and non-responders (OS12-), providing a clinically meaningful binary classification target.

This dataset serves as the second demo use case for PredomicsApp, illustrating how sparse microbial biomarker signatures can predict immunotherapy outcome from baseline metagenomics data.

## Dataset Description

- **Domain:** Gut metagenomics (whole-genome shotgun sequencing)
- **Cohort:** NSAT — multi-center cancer patients treated with immune checkpoint inhibitors
- **Features:** 2,834 Metagenomic Species Profiles (MSPs) — microbial species abundance
- **Endpoint:** Overall Survival at 12 months (OS12)
- **Task:** Binary classification
  - `0` = OS12- (non-responder / overall survival < 12 months)
  - `1` = OS12+ (responder / overall survival >= 12 months)

## Files

| File | Rows | Columns | Description |
|------|------|---------|-------------|
| `Xtrain.tsv` | 2,834 | 229 | Discovery cohort feature matrix (MSPs x samples) |
| `Xtest.tsv` | 2,834 | 188 | Validation cohort feature matrix |
| `Ytrain.tsv` | 229 | 1 | Discovery labels (111 OS12-, 118 OS12+) |
| `Ytest.tsv` | 188 | 1 | Validation labels (81 OS12-, 107 OS12+) |

## Data Format

- Tab-separated values (TSV)
- `X` matrices: features in rows, samples in columns (transposed from typical ML convention)
- `Y` vectors: sample ID (NCBI BioSample accession) + binary class label
- Sample IDs: NCBI BioSample accessions (SAMN376XXXXX)
- Feature IDs: MSP identifiers (msp_XXXX)

## Usage with gpredomics

```yaml
data:
  X: Xtrain.tsv
  y: Ytrain.tsv
  Xtest: Xtest.tsv
  ytest: Ytest.tsv
  features_in_rows: true
  classes:
    - "OS12-"
    - "OS12+"
    - "unknown"
```

## Related Work

- Derosa L, et al. Custom scoring based on ecological topology of gut microbiota associated with cancer immunotherapy outcome. *Cell*. 2024;187(13):3373-3389.e16. doi:[10.1016/j.cell.2024.05.029](https://doi.org/10.1016/j.cell.2024.05.029). PMID: [38906102](https://pubmed.ncbi.nlm.nih.gov/38906102/).
- Routy B, Le Chatelier E, Derosa L, et al. Gut microbiome influences efficacy of PD-1-based immunotherapy against epithelial tumors. *Science*. 2018;359(6371):91-97. doi:[10.1126/science.aan3706](https://doi.org/10.1126/science.aan3706). PMID: [29097494](https://pubmed.ncbi.nlm.nih.gov/29097494/).
