# Inflammatory bowel disease (MetaHIT, Qin J. et al. 2010)

## Task

IBD (Crohn's disease + ulcerative colitis) vs controls.

Strongly imbalanced (25 IBD / 85 controls).

## Files

| File | Content |
|------|---------|
| `Xtrain.tsv` / `Xtest.tsv` | 443 features × 88 / 22 samples (features in rows) |
| `Ytrain.tsv` / `Ytest.tsv` | sample, class (with header) — 0/1 |
| `metadata.tsv` | all samples: class, train/test assignment, available covariates |

## Class distribution

| Set | control (0) | IBD (1) | Total |
|-----|:-:|:-:|:-:|
| Train | 68 | 20 | 88 |
| Test | 17 | 5 | 22 |

Split: stratified 80/20, seed=42.

## Provenance

Pasolli et al. 2016, *PLoS Comput Biol* 12(7):e1004977 — MetaPhlAn2 species-level profiles (raw tables in `predomics_testing/data/pasolli_2016/`), renormalised to relative abundance (columns sum to 1).

Part of the Predomics benchmark: built by `datasets/scripts/build_benchmark.R` in the predomics suite.
