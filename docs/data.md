# Data configuration and source coverage

## Local configuration

Course datasets are not included in Git. The default `config/datasets.toml` points
to a sibling folder named `MITMA 9-03-15-03`, matching the supplied course layout.
For a standalone clone, create your own ignored local configuration:

```bash
cp config/datasets.local.example.toml config/datasets.local.toml
```

Edit `data_root` to the folder containing the configured level subdirectories.
`data/raw` is the example destination, not a dataset supplied with the repository.
Relative paths resolve from the repository root; absolute Linux paths work too.
Local values override the shared configuration, including individual entries of
`directories`. The source folder spelling `DISTITOS` is deliberately preserved.

| Setting | Meaning |
|---|---|
| `data_root` | Parent of the level directories used for local reads |
| `download_dir` | Parent directory for new downloads |
| `level` | `distritos`, `municipios`, `gau`, or `calidad` |
| `start`, `end` | Inclusive dates in YYYY-MM-DD format |
| `directories` | Mapping of level identifiers to actual subdirectory names |
| `url_template` | Verified HTTPS direct-download CSV URL, empty until configured |

Inspect or select data from the repository root:

```bash
python scripts/datasets.py --inventory
python scripts/datasets.py --level gau --start 2022-03-09 --end 2022-03-15
python scripts/datasets.py --data-root /path/to/mitma --level municipios --start 2022-09-09 --end 2022-09-15
```

Selection rejects missing or ambiguous dates. Original source codes are initially
read as text, preserving leading zeros. The notebook reads configuration by default;
its parameter cell can override level, dates, and root for interactive exploration.
Full verification executes the notebook as saved, so keep notebook overrides aligned
with the configuration when preparing shared verification evidence.

## Known sample inventory

Observed on 25 October 2026; re-inventory your own copy before analysis:

| Level | Actual period | Files | Issue |
|---|---|---:|---|
| Districts | 12–15 March 2022 | 4 | 9–11 March absent from supplied files and ZIP |
| GAU | 9–15 March 2022 | 7 | Complete prototype week; not the final reference year |
| Municipalities | 9–15 September 2022 | 7 | Different month from GAU/districts |
| District quality | 9–15 March 2023 | 7 | Different year from district mobility |

The initial selection is the complete GAU week. Do not combine these datasets as
one synchronized week. The final reference year remains 2023. INE data, geometries,
and territorial correspondence tables still need to be sourced and understood.
Resolve or document these issues through the [Sprint 1 plan](sprint-1/plan.md).

## Downloads

Downloads are opt-in. Configure a verified direct CSV URL with `url_template` or
`--url-template`; the repository does not currently provide a verified provider URL.
Supported placeholders are `{date}` (YYYYMMDD), `{year}`, `{month}`, `{day}`, `{level}`.
First review the plan without network access:

```bash
python scripts/datasets.py --download --dry-run --level gau --start 2023-03-09 --end 2023-03-15
```

Once the URL is configured, remove `--dry-run` to download. Existing files are
skipped; downloads are sequential and use `.part` files. Header validation is only
a basic format check and does not establish complete-file or analytical quality.
The default destination is `data/raw/<level-directory>`; override it with
`--download-dir`. Use `--data-root data/raw` to read that destination.

## Version control boundaries

Commit code, configuration examples, methodological decisions, schemas, and selected
small evidence intended for review. Keep raw datasets, downloaded archives, local
configuration, credentials, virtual environments, temporary databases, full profiling
outputs, and generated environment reports outside Git. Curated Sprint 1 results
can be added deliberately after review; they must not expose private local settings.
