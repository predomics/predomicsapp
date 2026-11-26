# Colorectal cancer (Zeller et al. 2014)

## Task

Colorectal cancer vs controls.

As in Pasolli 2016, the control class pools healthy subjects and small adenomas (see `disease` in `metadata.tsv`).

## Files

| File | Content |
|------|---------|
| `Xtrain.tsv` / `Xtest.tsv` | 503 features × 96 / 25 samples (features in rows) |
| `Ytrain.tsv` / `Ytest.tsv` | sample, class (with header) — 0/1 |
| `metadata.tsv` | all samples: class, train/test assignment, available covariates |

## Class distribution

| Set | control (0) | CRC (1) | Total |
|-----|:-:|:-:|:-:|
| Train | 58 | 38 | 96 |
| Test | 15 | 10 | 25 |

Split: stratified 80/20, seed=42.

## Provenance

Pasolli et al. 2016, *PLoS Comput Biol* 12(7):e1004977 — MetaPhlAn2 species-level profiles (raw tables in `predomics_testing/data/pasolli_2016/`), renormalised to relative abundance (columns sum to 1).

Part of the Predomics benchmark: built by `datasets/scripts/build_benchmark.R` in the predomics suite.
