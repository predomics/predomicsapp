# Type 2 diabetes in European women (Karlsson et al. 2013)

## Task

T2D vs normal glucose tolerance (IGT subjects excluded, as in Pasolli 2016).

The three-class version of this cohort (with IGT) is `mc_t2d_karlsson2013`.

## Files

| File | Content |
|------|---------|
| `Xtrain.tsv` / `Xtest.tsv` | 381 features × 76 / 20 samples (features in rows) |
| `Ytrain.tsv` / `Ytest.tsv` | sample, class (with header) — 0/1 |
| `metadata.tsv` | all samples: class, train/test assignment, available covariates |

## Class distribution

| Set | NGT (0) | T2D (1) | Total |
|-----|:-:|:-:|:-:|
| Train | 34 | 42 | 76 |
| Test | 9 | 11 | 20 |

Split: stratified 80/20, seed=42.

## Provenance

Pasolli et al. 2016, *PLoS Comput Biol* 12(7):e1004977 — MetaPhlAn2 species-level profiles (raw tables in `predomics_testing/data/pasolli_2016/`), renormalised to relative abundance (columns sum to 1).

Part of the Predomics benchmark: built by `datasets/scripts/build_benchmark.R` in the predomics suite.
