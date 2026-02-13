# Qin et al. 2014 — Liver Cirrhosis Metagenomics Dataset

Demo dataset for PredomicsApp, derived from the study:

> **Qin N, Yang F, Li A, et al.** *Alterations of the human gut microbiome in liver cirrhosis.* Nature. 2014;513(7516):59-64. doi:10.1038/nature13568

## Dataset Description

- **Domain:** Gut metagenomics (shotgun sequencing)
- **Features:** 1,980 Metagenomic Species Profiles (MSPs) — microbial species abundance
- **Classes:** Binary classification
  - `0` = Healthy (HD)
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
# param.yaml excerpt
data:
  x_train: Xtrain.tsv
  y_train: Ytrain.tsv
  x_test: Xtest.tsv
  y_test: Ytest.tsv
  class_healthy: healthy
  class_sick: cirrhosis
```

## Reference

Qin N, Yang F, Li A, Prifti E, Chen Y, Shao L, Guo J, Le Chatelier E, Yao J, Wu L, Zhou J, Ni S, Liu L, Pons N, Batto JM, Kennedy SP, Leonard P, Yuan C, Ding W, Chen Y, Hu X, Zheng B, Qian G, Xu W, Ehrlich SD, Zheng S, Li L. *Alterations of the human gut microbiome in liver cirrhosis.* Nature. 2014 Sep 4;513(7516):59-64.
