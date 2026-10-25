# Installation and verification

## Supported workflow

Use the same Bash procedure on Linux and WSL2. It has been verified in Ubuntu
26.04.1 on WSL2, x86_64. Native Linux on another machine has not been independently
tested; package and extension availability on other architectures must be checked.

Validation on 25 October 2026 passed all 10 unit tests and all 11 full environment
checks. Setup was repeated without recreating the existing environment. An isolated
copy without source data or personal configuration also passed all 8 core checks
with repository and environment paths containing spaces. Explicit data checks on
that copy correctly failed; incompatible setup destinations were rejected without
changing their existing contents. Validation reports remain outside Git under the
Linux working directory, including `repository-preparation-validation.json`.

The repository can live anywhere, including a path containing spaces. Setup locates
itself rather than assuming your terminal's working directory. Keep one authoritative
checkout. Do not activate a Windows virtual environment inside Linux.

## Setup

Bash and curl must already be available. Setup installs user-local uv when needed,
provisions Python 3.11.17, synchronizes the pinned Linux dependencies, registers a
Jupyter kernel, and installs/loads DuckLake, spatial, and httpfs for DuckDB 2.0.0.
No sudo or change to system Python is required by the setup script.

```bash
bash scripts/setup.sh
source ~/.venvs/mobility-lakehouse-py311/bin/activate
python scripts/check_environment.py
```

For another environment or kernel:

```bash
bash scripts/setup.sh --venv "$HOME/.venvs/team mobility" --kernel team-mobility
source "$HOME/.venvs/team mobility/bin/activate"
python scripts/check_environment.py --with-data --with-notebook --kernel team-mobility
```

Relative `--venv` paths resolve from the caller's current directory. Repeating setup
synchronizes an existing Linux Python 3.11.17 virtual environment without recreating
it. Synchronization removes packages absent from the lock file: use a dedicated
project environment. An incompatible or non-environment destination is rejected
before synchronization; choose another path instead of deleting your environment.
Registering an existing kernel name updates that user's kernel specification.

The dependency files have distinct roles:

- `requirements.txt`: original application dependency pins.
- `requirements-dev.txt`: application dependencies plus notebook execution tools.
- `requirements-linux.lock.txt`: the complete resolved Linux package versions used
  by setup. The versions were preserved when the former WSL lock file was renamed.

When dependencies deliberately change, regenerate the lock file in the agreed
Linux environment and rerun verification before committing it. Setup does not
silently select different application versions on a resolution failure.

## WSL2 paths

Open Ubuntu from Windows and run the commands above there. Windows drives are
available under `/mnt/<drive>/`; for example `C:\data` is `/mnt/c/data`. The data
selector also converts absolute Windows drive paths when running on Linux.
A Linux-native checkout uses normal Linux paths and needs no WSL configuration.
Working databases and reports default to `~/.local/share/mobility-lakehouse/`.

## Verification scopes

```bash
python scripts/check_environment.py
python scripts/check_environment.py --with-data
python scripts/check_environment.py --with-data --with-notebook
```

- **Core (default):** Linux Python 3.11 virtual environment, dependency imports and
  pins, consistency, unit tests, synthetic CSV.gz/SQL/Parquet round trips, persistence,
  plotting, clustering, extensions, DuckLake committed writes/reopening, and spatial SQL.
- **Data:** core plus configured date coverage, working-directory-independent file
  selection, and a bounded real CSV sample. Missing dates are errors.
- **Notebook:** data plus execution through the specified registered kernel.
  `--with-notebook` implies `--with-data`; use `--kernel NAME` for a custom kernel.

The report contains `scope`, each check's `status`, `ready` for the requested scope,
and `full_verification`, which is true only when all checks including data and the
notebook passed. Optional checks appear as `skipped` when not requested. A core pass
alone does not establish full data/notebook readiness or completion of Sprint 1.
Each failed required check is printed and causes exit code 1; a successful requested
scope returns 0. Argument errors return a nonzero code as well.

Reports are written outside Git:

```text
~/.local/share/mobility-lakehouse/environment-report.json
~/.local/share/mobility-lakehouse/readiness-<run>/report.json
```

Use `--work-dir /absolute/linux/path` to choose another report/fixture directory.
The executed notebook copy stays in that run directory; the source notebook is
checksum-checked and preserved. The checker loads extensions but does not install
packages or extensions. Remote dataset downloads, full-file data quality, Airflow,
and AWS are not validated by these checks.

## Jupyter

Start from the activated Linux environment and repository root:

```bash
python -m jupyterlab --no-browser --ip=127.0.0.1
```

Open the printed localhost URL in your browser. The default kernel is named
`mobility-lakehouse-py311`, displayed as **Mobility Lakehouse — Python 3.11 (Linux)**.
If setup used `--kernel`, select that registered kernel and pass the same name to
notebook verification. Linux Jupyter discovers Linux kernels; a Windows Jupyter
server has a separate kernel list. Stop the server with Ctrl+C.

## Troubleshooting

- Wrong Python: activate the environment and inspect `python -c "import sys; print(sys.executable)"`.
- Missing extension: rerun setup from Linux; initial installation needs network access.
- Missing datasets: follow [Data configuration](data.md); core checks work without them.
- Kernel mismatch: rerun setup for the intended environment/name and use `--kernel`.
- WSL cannot start: resolve Windows virtualization/WSL startup before running Linux setup.

Installer and extension references: [uv installation](https://docs.astral.sh/uv/getting-started/installation/)
and [DuckLake connections](https://ducklake.select/docs/stable/duckdb/usage/connecting).
