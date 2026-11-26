# Obesity (Le Chatelier et al. 2013)

## Task

Obese vs lean individuals.

Known to be a hard task (weak signal at species level).

## Files

| File | Content |
|------|---------|
| `Xtrain.tsv` / `Xtest.tsv` | 465 features × 202 / 51 samples (features in rows) |
| `Ytrain.tsv` / `Ytest.tsv` | sample, class (with header) — 0/1 |
| `metadata.tsv` | all samples: class, train/test assignment, available covariates |

## Class distribution

| Set | lean (0) | obese (1) | Total |
|-----|:-:|:-:|:-:|
| Train | 71 | 131 | 202 |
| Test | 18 | 33 | 51 |

Split: stratified 80/20, seed=42.

## Provenance

Pasolli et al. 2016, *PLoS Comput Biol* 12(7):e1004977 — MetaPhlAn2 species-level profiles (raw tables in `predomics_testing/data/pasolli_2016/`), renormalised to relative abundance (columns sum to 1).

Part of the Predomics benchmark: built by `datasets/scripts/build_benchmark.R` in the predomics suite.
