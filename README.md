# Mobility Lakehouse

A shared Big Data Engineering and Technologies project for a Bronze/Silver/Gold
mobility lakehouse. The final reference year is 2023. Sprint 1 covers schema design
and a reproducible SQL proof of concept; its analytical model is not implemented yet.

## Requirements

Linux or WSL2, Bash, curl, an internet connection for initial setup, and a writable
home directory. Setup provisions Python 3.11.17 without replacing system Python.

## Quick start

From the repository root in a **Linux or Ubuntu/WSL2 terminal**:

```bash
bash scripts/setup.sh
source ~/.venvs/mobility-lakehouse-py311/bin/activate
python scripts/check_environment.py
```

The default check uses synthetic fixtures and requires no course datasets.
To run from another directory, use the absolute path to each script.

## Working with data and notebooks

Configure your local data path as described in [Data configuration](docs/data.md).
Then run the complete environment verification:

```bash
python scripts/check_environment.py --with-data --with-notebook
python -m jupyterlab --no-browser --ip=127.0.0.1
```

Open the localhost URL printed by Jupyter. Select
**Mobility Lakehouse — Python 3.11 (Linux)** for `notebooks/01_data_selection.ipynb`.
The original notebook and source datasets are not modified by verification.

## Terminal source demonstration

With the project environment activated, list or run the read-only exploration queries:

```bash
python scripts/demo_queries.py --list
python scripts/demo_queries.py 1
python scripts/demo_queries.py 17 --day 2023-03-10 --level municipios
```

Choose a number from 1 to 20. Each invocation prints its SQL and result and reads
one complete source day, except queries that only inspect a limited sample or
schema. The default is GAU on the configured start date. Queries do not create
persistent analytical tables. The [SQL source](docs/sprint-1/demo-queries.sql)
uses temporary `raw_trips` and `typed_trips` views created by the runner.
The typed view demonstrates conversions; it is not the integrated Silver layer.
An empty result in query 11 means no unparseable trip values were found in that
file, not that every source is clean. Multiple segment rows in query 15 do not
establish duplication. Numeric sums exclude unparseable values; inspect quality
checks before interpreting totals. Query 20 reports floating-point reconciliation
differences; a small rounding residual can occur and no acceptance tolerance is
assumed. These are source exploration examples, not annual mobility conclusions.

## Tests

```bash
python -m unittest discover -s tests -v
```

## Team documentation

- [Installation, custom environments, and verification](docs/setup.md)
- [Data paths, downloads, and known coverage issues](docs/data.md)
- [Sprint 1 tasks, dependencies, and completion checklist](docs/sprint-1/plan.md)
- [Mobility lakehouse architecture, table contracts and SVG diagrams](docs/sprint-1/review-architecture.md)
- Templates: [table sheet](docs/templates/table-sheet.md),
  [design decision](docs/templates/design-decision.md),
  [source inventory](docs/templates/source-inventory.md)

Project documentation, comments, and authored outputs use English. Original source
identifiers retain their spelling. Data, environments, secrets, and run reports
stay outside version control. Airflow and cloud deployment belong to later sprints.
