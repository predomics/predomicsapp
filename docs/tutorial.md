# Tutorial — from a data table to an interpretable signature

This walk-through uses the demo dataset shipped with PredomicsApp: gut
metagenomes of patients with liver cirrhosis and healthy controls
([Qin et al., *Nature* 2014](https://doi.org/10.1038/nature13568)). It takes
about fifteen minutes and needs no data of your own. At the end you will know
what each screen is for and how to read the results.

The statistical background is on the project website
([Methods](https://predomics.github.io/docs/Methods)); this page only says what
you need at each step and points there for the details.

---

## What PredomicsApp looks for

Most machine-learning methods combine hundreds of variables with real-valued
weights. Predomics searches instead for **very small models with very simple
weights**: a handful of features (species, genes, clinical variables), each
with a coefficient taken from a tiny set such as −1, 0, +1. A model is a score
and a threshold:

```
score = (sum of the features with +1) − (sum of the features with −1)
class 1 if score ≥ threshold, otherwise class 0
```

Such a model can be read, checked against biology, and measured in a
laboratory. The price is a hard search problem — there are astronomically many
candidate models — which is what the engine (gpredomics) solves with heuristic
search algorithms.

Four **languages** define what a model may look like:

| Language | Coefficients | Score | Reads as |
|---|---|---|---|
| Binary (`bin`) | 0, 1 | sum of the selected features | the more of these, the higher the score |
| Ternary (`ter`) | −1, 0, +1 | sum of one group minus sum of the other | some features rise, others fall |
| Ratio (`ratio`) | −1, 0, +1 | one group divided by the other | the balance between two groups |
| Pow2 (`pow2`) | ±1, ±2, ±4, … ±64 | ternary with weights | some features count more than others |

Each language can be applied to the data in several forms (**data types**):
`raw` values, `prev` (presence/absence: is the feature above a small threshold
ε?), `log` (logarithm, for the skewed distributions typical of abundance data)
and `zscore` (standardised values).

---

## 1. Sign in and load the demo dataset

Open the application, create an account (or sign in), and on the **Projects**
page choose **Qin2014 Liver Cirrhosis** among the demo datasets. This creates a
project and opens it.

The dataset holds 1,980 microbial species (metagenomic species, "MSP") measured
in 180 training samples (83 healthy, 97 cirrhosis) and 30 test samples (15 and
15). Class `0` is healthy, class `1` is cirrhosis.

With your own data you would instead create a project and fill four slots:

| Slot | Content |
|---|---|
| X train | the table of measurements: one row per feature, one column per sample (tab- or comma-separated, first column = feature names, first row = sample names) |
| y train | one row per sample: sample name and class (`0` or `1`) |
| X test, y test | optional, same layout, samples kept aside to check the model |

If your table has samples in rows instead, untick **Features in rows**. If you
have no separate test set, **Holdout ratio** sets aside a fraction of the
training samples.

## 2. Look at the data first (Data tab)

The left panel summarises the dataset (features, samples, classes). **Class
labels** lets you name the classes ("Healthy", "Cirrhosis"); the names are then
used in the charts.

**Feature filtering** decides which features are offered to the search:

- *Selection method* — a statistical test per feature between the two classes
  (Wilcoxon by default; t-test and Bayesian Fisher are alternatives; "None"
  keeps everything).
- *Min prevalence %* — discard features present in fewer than this percentage
  of samples. Rare features produce fragile models.
- *Max adj. p-value* — keep features whose test, corrected for multiple
  testing, is below this value.
- *Min feature value* — values below it are treated as absent.

Filtering is not cosmetic: it defines the search space. Loosen it and the
search is slower and noisier; tighten it and you may exclude a useful feature.
The defaults are a reasonable start.

The charts on the right describe the features that pass the filter:

| Chart | What it shows |
|---|---|
| Prevalence | in what share of each class a feature is detected |
| Abundance | the distribution of its values per class |
| Barcode | presence/absence across samples, grouped by class |
| Class heatmap | the selected features against samples |
| Volcano | size of the difference against its statistical significance |
| PCoA | the samples in two dimensions, by overall similarity — do the classes separate at all? |

In this dataset you should see species of oral origin (for instance
*Veillonella* and *Streptococcus*) more prevalent in cirrhosis, and several
butyrate producers more prevalent in healthy subjects.

## 3. Choose how to search (Parameters & Run tab)

Three presets set how hard the search works without changing the question
asked:

| Preset | Use it for |
|---|---|
| **Quick** | a first look in a fraction of the time; scores are indicative |
| **Standard** | the documented defaults |
| **Thorough** | a larger search with cross-validation, feature importance and the voting ensemble — for results you intend to report |

For this tutorial choose **Quick**, keep the algorithm on **Genetic
algorithm**, and launch. The main settings, when you want to go further:

- **Algorithm.** The genetic algorithm (GA) evolves a population of models
  over generations and is the general-purpose choice. Beam search grows models
  one feature at a time; MCMC samples models and gives a probabilistic view.
  Others (simulated annealing, iterated local search, ant colony, LASSO-based)
  and standard machine-learning comparators (random forest, gradient boosting,
  SVM, …) are available to put the result in perspective.
- **Language** and **Data type.** Several can be given at once (for example
  `bin,ter,ratio` and `raw,prev`); the search then explores each combination
  and you compare them in the results. Ternary is the most commonly used.
- **Fit.** What the search optimises: AUC by default. Sensitivity- or
  specificity-oriented fits exist for screening or confirmation settings.
- **Model size (k).** `k min` and `k max` bound the number of features in a
  model. A small penalty on k favours the smaller of two models that perform
  alike.
- **Population size** and **epochs** (GA). Larger values explore more and take
  longer. Very small populations (around 100 or less) can fail: stay at the
  preset values or above.
- **Cross-validation.** Repeats the search on several splits of the training
  data to estimate how well the *procedure* generalises. Slower, but the honest
  way to report performance when you have no separate test set.
- **Seed.** Fixes the random choices: the same data, parameters and seed give
  the same result.
- **ε (epsilon).** The value under which a feature counts as absent for the
  `prev` and `log` data types and that stabilises ratios.

Every parameter has a help bubble. **Launch** queues the job; the console at
the bottom shows its progress live (generation, current best model, estimated
time left) and stays available if you leave the page. A running job can be
cancelled. If the server restarts while a job runs, the job is marked as
failed with an explanation: launch it again.

## 4. Read the results (Results tab)

Select the finished job. The tabs go from the overview to the detail.

### Summary

The headline numbers of the best model: its size **k**, and on the training
set (and the test set when there is one) the **AUC**, accuracy, sensitivity
and specificity; and how the search converged over the generations.

- **AUC** — the probability that a randomly chosen positive sample scores
  higher than a randomly chosen negative one. 0.5 is chance, 1 is perfect. It
  does not depend on the threshold.
- **Sensitivity** — the share of true positives detected; **specificity** —
  the share of true negatives recognised. Both depend on the threshold, which
  is chosen on the training data.
- **Accuracy** — the share of correct predictions; misleading when one class is
  much larger than the other.

Compare training and test: a model at 0.99 in training and 0.75 in test has
learned noise. On this dataset expect a test AUC around 0.9 with five to ten
features.

### Best Model

The model itself: its features, the sign of each coefficient, the threshold,
and the score of every sample. This is the object to take to a biologist: "the
sum of these species minus the sum of those, above this value, indicates
cirrhosis". A feature with a positive coefficient is enriched in class 1, a
negative one in class 0. From here you can check the model on other samples
(**Validate**) and export it.

### Population

The search does not return one model but many of similar quality. The
**Family of Best Models (FBM)** is the set of models whose performance cannot
be told apart from the best one statistically. Looking at the family rather
than the single winner is central to the method:

- A feature present in most models of the family (high **prevalence in the
  FBM**, say above 80 %) is a robust signal.
- Features that appear in some models only are often interchangeable
  alternatives.
- The heatmap (models × features, coloured by coefficient) shows these
  patterns at a glance.

### Jury

When voting is enabled, the models of the family vote on each sample. The
ensemble is usually a little more accurate and more stable than any single
model; the tab shows the vote of each model and where they disagree — samples
on which the models disagree are worth a second look.

### Comparative

Side-by-side comparison of jobs or of the languages and data types explored in
one job: does `ratio` do better than `ter` here? Does working on
presence/absence lose anything compared with raw abundances?

### Co-presence

Which features appear together in the models of the family more often than
chance (they may form a functional group), and which avoid each other (they
may carry the same information and replace one another).

### Stability

Do the models of a given size select the same features? High stability at
size k means the signature at that size is reproducible; low stability means
several different feature sets do equally well. The curve of stability against
k helps choose the model size to report: prefer a size where both performance
and stability are high.

### Enrichment

Tests whether the features of the signature belong to particular taxonomic or
functional groups (a phylum, a family, butyrate producers, …) more than the
features offered to the search do. Requires species annotations, which the
application fetches for MSP identifiers (see "Network access" in the README).

### Ecosystem

A network of the species that vary together across samples (co-abundance),
with the species used by the models highlighted. It places the signature in its
ecological context: are the selected species neighbours in one community, or
representatives of several?

### Insights

An automatically written digest of the points above for this job — a starting
point for your own reading, not a substitute for it.

### Basket and exports

Models from different jobs can be put in the **basket** to compare them. The
**Export** menu produces a report (HTML or PDF), the raw results (JSON, CSV)
and a notebook (Python or R) that reloads them. A model can be published to the
**Signature Zoo**, the instance's shared collection of signatures.

## 5. What to report, and what to be careful about

- Report the **test** (or cross-validated) performance, never the training
  performance alone.
- State the language, data type, model size, seed and the application and
  engine versions (shown by `/health` on your instance) — they are needed to
  reproduce the result.
- Prefer features that are frequent in the family of best models to features
  of the single best model.
- A small test set gives an imprecise estimate: with 30 samples, an AUC of
  0.90 is compatible with a true value quite far from it.
- A signature found in one cohort is a hypothesis. Its value is established by
  validating it on independent samples (the **Validate** function, or the
  meta-analysis page for several cohorts).

## Where to go next

- Algorithms, languages, stability indices and the ecosystem network in
  detail: [predomics.github.io](https://predomics.github.io/docs/Methods).
- Running analyses from scripts: [API guide](api-guide.md).
- Installing and operating an instance: [DEPLOYMENT.md](../DEPLOYMENT.md).
- The method: Prifti E, et al. *Interpretable and accurate prediction models
  for metagenomics data.* GigaScience 2020.
  [doi:10.1093/gigascience/giaa010](https://doi.org/10.1093/gigascience/giaa010)
