# Qin et al. 2014 — Liver Cirrhosis Metagenomics Dataset

Demo dataset for PredomicsApp, derived from the study:

> **Qin N, Yang F, Li A, Prifti E, Chen Y, Shao L, et al.** *Alterations of the human gut microbiome in liver cirrhosis.* Nature. 2014;513(7516):59-64. doi:[10.1038/nature13568](https://doi.org/10.1038/nature13568)

## Context

Liver cirrhosis is a major cause of morbidity and mortality worldwide. This landmark study demonstrated that the gut microbiome of patients with liver cirrhosis is significantly altered compared to healthy individuals, with invasion of oral-origin bacteria into the gut and depletion of beneficial species. Whole-genome shotgun sequencing of stool samples from a Chinese cohort enabled the construction of metagenomic species profiles (MSPs) capturing species-level microbial abundances.

This dataset serves as the primary demo use case for PredomicsApp, illustrating how sparse interpretable models can discriminate cirrhosis patients from healthy controls using a small subset of microbial features.

## Dataset Description

- **Domain:** Gut metagenomics (whole-genome shotgun sequencing)
- **Cohort:** Chinese population (Zhejiang University, Hangzhou)
- **Features:** 1,980 Metagenomic Species Profiles (MSPs) — microbial species gene-count abundance
- **Task:** Binary classification
  - `0` = Healthy donor (HD)
  - `1` = Liver cirrhosis (LD)

## Files

| File | Rows | Columns | Description |
|------|------|---------|-------------|
| `Xtrain.tsv` | 1,980 | 180 | Training feature matrix (MSPs x samples) |
| `Xtest.tsv` | 1,980 | 30 | Test feature matrix |
| `Ytrain.tsv` | 180 | 1 | Training labels (83 healthy, 97 cirrhosis) |
| `Ytest.tsv` | 30 | 1 | Test labels (15 healthy, 15 cirrhosis) |
| `param.yaml` | — | — | gpredomics parameter configuration |

## Data Format

- Tab-separated values (TSV)
- `X` matrices: features in rows, samples in columns (transposed from typical ML convention)
- `Y` vectors: sample ID + binary class label
- Sample IDs: `HD-*` = healthy donor, `LD-*` = liver disease (cirrhosis)

## Usage with gpredomics

```yaml
data:
  X: Xtrain.tsv
  y: Ytrain.tsv
  Xtest: Xtest.tsv
  ytest: Ytest.tsv
  features_in_rows: true
  classes:
    - "healthy"
    - "cirrhosis"
    - "unknown"
```

## Expected Results

With the genetic algorithm (GA), ternary language, and default parameters, gpredomics typically achieves:
- **AUC 0.92-0.94** on the test set with k=5-10 features
- Key discriminating species include oral-origin bacteria (*Veillonella*, *Streptococcus*) enriched in cirrhosis and butyrate-producing species depleted in cirrhosis

## Reference

Qin N, Yang F, Li A, Prifti E, Chen Y, Shao L, Guo J, Le Chatelier E, Yao J, Wu L, Zhou J, Ni S, Liu L, Pons N, Batto JM, Kennedy SP, Leonard P, Yuan C, Ding W, Chen Y, Hu X, Zheng B, Qian G, Xu W, Ehrlich SD, Zheng S, Li L. Alterations of the human gut microbiome in liver cirrhosis. *Nature*. 2014 Sep 4;513(7516):59-64. doi:[10.1038/nature13568](https://doi.org/10.1038/nature13568). PMID: [25079328](https://pubmed.ncbi.nlm.nih.gov/25079328/).
