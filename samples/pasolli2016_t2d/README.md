# Type 2 diabetes (Qin J. et al. 2012)

## Task

T2D vs non-diabetic controls, Chinese cohort (stages I + II).

## Files

| File | Content |
|------|---------|
| `Xtrain.tsv` / `Xtest.tsv` | 572 features × 275 / 69 samples (features in rows) |
| `Ytrain.tsv` / `Ytest.tsv` | sample, class (with header) — 0/1 |
| `metadata.tsv` | all samples: class, train/test assignment, available covariates |

## Class distribution

| Set | control (0) | T2D (1) | Total |
|-----|:-:|:-:|:-:|
| Train | 139 | 136 | 275 |
| Test | 35 | 34 | 69 |

Split: stratified 80/20, seed=42.

## Provenance

Pasolli et al. 2016, *PLoS Comput Biol* 12(7):e1004977 — MetaPhlAn2 species-level profiles (raw tables in `predomics_testing/data/pasolli_2016/`), renormalised to relative abundance (columns sum to 1).

Part of the Predomics benchmark: built by `datasets/scripts/build_benchmark.R` in the predomics suite.
