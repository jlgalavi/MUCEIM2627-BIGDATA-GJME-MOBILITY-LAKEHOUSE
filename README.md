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

## Tests

```bash
python -m unittest discover -s tests -v
```

## Team documentation

- [Installation, custom environments, and verification](docs/setup.md)
- [Data paths, downloads, and known coverage issues](docs/data.md)
- [Sprint 1 tasks, dependencies, and completion checklist](docs/sprint-1/plan.md)
- Templates: [table sheet](docs/templates/table-sheet.md),
  [design decision](docs/templates/design-decision.md),
  [source inventory](docs/templates/source-inventory.md)

Project documentation, comments, and authored outputs use English. Original source
identifiers retain their spelling. Data, environments, secrets, and run reports
stay outside version control. Airflow and cloud deployment belong to later sprints.
