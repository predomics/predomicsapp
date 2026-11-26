# Wetlab protocol (lysis effect) — demo dataset

Demo dataset for PredomicsApp. The same subjects were profiled twice, with two
laboratory (DNA extraction) protocols; the task is to recognise the protocol
from the gut microbiome profile. It illustrates how strongly a wet-lab protocol
can shape a metagenomic profile, and gives a paired, perfectly balanced
classification problem to try the application on.

> **To be completed by the data owner.** This file describes only what can be
> read from the files themselves. The items marked *to be completed* below
> (publication, which protocol is which, licence, consent) must be filled in by
> whoever contributed the dataset before it is redistributed further.

## Source

| | |
|---|---|
| Publication / citation | *to be completed* |
| Sequencing data | NCBI BioProjects [PRJNA319574](https://www.ncbi.nlm.nih.gov/bioproject/PRJNA319574) and [PRJNA942468](https://www.ncbi.nlm.nih.gov/bioproject/PRJNA942468); sample identifiers are BioSample accessions (`SAMN…`) |
| Cohort | 459 subjects, all labelled `control`, location `Netherlands` (metadata columns `status`, `geo_loc_name`) |
| Feature table provenance (catalogue, pipeline version, normalisation) | *to be completed* (the metadata column `version` reads `0.9.9.1`) |
| Licence of the derived tables | *to be completed* |
| Consent / ethics statement for the per-subject metadata (age, sex, BMI) | *to be completed* |

## Task

Binary classification, one sample per subject and per protocol
(459 subjects × 2 = 918 samples):

| Label | Samples | BioProject | Protocol |
|---|---|---|---|
| `1` | 459 | PRJNA319574 | *to be completed* (with or without mechanical lysis) |
| `0` | 459 | PRJNA942468 | *to be completed* |

The application describes the two protocols as "with / without mechanical
lysis".

## Files

| File | Content | Shape |
|---|---|---|
| `Xtrain.tsv` | Feature table, training set. Features in rows, samples in columns; first column is the feature name. Values are relative abundances. | 1,981 features × 734 samples |
| `Ytrain.tsv` | Training labels: `sample<TAB>label`, no header | 734 lines (367 per class) |
| `Xtest.tsv` | Feature table, test set (same features) | 1,981 features × 184 samples |
| `Ytest.tsv` | Test labels | 184 lines (92 per class) |
| `metadata.tsv` | One line per sample, 38 columns (below) | 918 lines |

Feature names are Metagenomic Species Pan-genome identifiers followed by their
taxonomy, separated by semicolons, for example
`msp_0001;Eukaryota;Heterokonta;Blastocystae;Blastocystida;Blastocystidae;Blastocystis;Blastocystis sp. subtype 3`.

How the 80/20 train/test split was drawn (in particular whether both samples
of a subject are always on the same side) is *to be completed*. If they are
not, test performance is optimistic for any question other than "which
protocol".

### Main columns of `metadata.tsv`

| Column | Meaning |
|---|---|
| `biosample_accession` | sample identifier (matches the column names of the feature tables) |
| `host_subject_id` | subject identifier; each appears twice, once per protocol |
| `projectid`, `project` | BioProject accession (= protocol, = label) |
| `sex`, `age`, `bmi` | subject characteristics (age 18–75; 12 samples without age) |
| `status` | `control` for every sample |
| `geo_loc_name`, `lat_lon`, `collection_date` | as submitted to NCBI (`Netherlands`; coordinates and, for one project, dates not provided) |
| `gene_count`, `species`, `shannon` | richness (genes, species) and Shannon diversity of the sample |
| `Gram+_abundance`, `Gram+_count`, `Gram-_abundance`, `Gram-_count` | abundance and number of Gram-positive / Gram-negative species |
| `total_read`, `filtered_read`, `unique_read`, `multiple_read`, `human_input_reads`, `human_aligned_reads`, `catalog_input_reads`, `catalog_aligned_reads`, `fastp_total_reads`, `fastp_passed_filtered` | read counts at the successive steps of the processing pipeline |
| `version`, `error_code`, `error`, `SUP` | pipeline version and status fields |
| `isolation_source`, `env_feature`, `env_biome`, `env_material`, `host` | NCBI BioSample attributes |
| `...1` | row index left by the export (no meaning) |

## Using it in PredomicsApp

On the Projects page, click **Load** next to *Wetlab Protocol (Lysis Effect)*.
The four data files are attached with their roles, and `metadata.tsv` is
available for the metadata-based views.
