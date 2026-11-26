# Liver cirrhosis (Qin N. et al. 2014)

## Task

Liver cirrhosis vs healthy controls.

Discovery and validation stages are pooled as in Pasolli 2016; the original stage is kept in the `stage` column of `metadata.tsv` if you prefer the discovery/validation split used in Prifti et al. 2020.

## Files

| File | Content |
|------|---------|
| `Xtrain.tsv` / `Xtest.tsv` | 542 features × 185 / 47 samples (features in rows) |
| `Ytrain.tsv` / `Ytest.tsv` | sample, class (with header) — 0/1 |
| `metadata.tsv` | all samples: class, train/test assignment, available covariates |

## Class distribution

| Set | healthy (0) | cirrhosis (1) | Total |
|-----|:-:|:-:|:-:|
| Train | 91 | 94 | 185 |
| Test | 23 | 24 | 47 |

Split: stratified 80/20, seed=42.

## Provenance

Pasolli et al. 2016, *PLoS Comput Biol* 12(7):e1004977 — MetaPhlAn2 species-level profiles (raw tables in `predomics_testing/data/pasolli_2016/`), renormalised to relative abundance (columns sum to 1).

Part of the Predomics benchmark: built by `datasets/scripts/build_benchmark.R` in the predomics suite.
