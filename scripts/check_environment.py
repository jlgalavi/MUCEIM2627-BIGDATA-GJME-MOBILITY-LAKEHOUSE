"""Check a Linux Python 3.11 environment; real data and notebooks are opt-in.

This command never installs dependencies or extensions. Source datasets and
notebooks are read-only. Use --with-data --with-notebook for full verification.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import gzip
import hashlib
import importlib
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.datasets import dates, get_files, load_config, resolve_path

PACKAGES = {
    "duckdb": "duckdb", "pandas": "pandas", "numpy": "numpy",
    "matplotlib": "matplotlib", "scikit-learn": "sklearn", "pyarrow": "pyarrow",
    "jupyterlab": "jupyterlab", "pendulum": "pendulum", "ipykernel": "ipykernel",
    "nbclient": "nbclient",
}
KERNEL = "mobility-lakehouse-py311"


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def command(args, *, cwd=ROOT, timeout=120):
    result = subprocess.run(args, cwd=cwd, text=True, capture_output=True,
                            timeout=timeout, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    require(result.returncode == 0, f"Command failed ({result.returncode}): {args}\n"
            f"{result.stdout}\n{result.stderr}")
    return (result.stdout + result.stderr).strip()


def sql_literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def interpreter_check():
    require(platform.system() == "Linux", "Run this check on Linux or inside WSL2.")
    require(sys.version_info[:2] == (3, 11), "Python 3.11 is required for this baseline.")
    require(sys.prefix != sys.base_prefix, "Activate a Python 3.11 virtual environment first.")
    return {"executable": sys.executable, "python": platform.python_version(),
            "system": platform.platform(), "prefix": sys.prefix}


def dependency_check():
    versions = {}
    for distribution, module in PACKAGES.items():
        importlib.import_module(module)
        versions[distribution] = metadata.version(distribution)
    for line in (ROOT / "requirements.txt").read_text().splitlines():
        if "==" in line and not line.lstrip().startswith("#"):
            distribution, expected = line.strip().split("==", 1)
            require(metadata.version(distribution) == expected,
                    f"Pinned version mismatch: {distribution} must be {expected}")
    uv = shutil.which("uv") or str(Path.home() / ".local/bin/uv")
    consistency = command([uv, "pip", "check", "--python", sys.executable])
    return {"versions": versions, "consistency": consistency,
            "uv": command([uv, "--version"])}


def selector_tests():
    return command([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"])


def source_selection_check():
    config = load_config()
    source_root = resolve_path(config["data_root"])
    files = get_files()
    require(len(files) == len(dates(config["start"], config["end"])),
            "The configured date range is incomplete.")
    args = [sys.executable, str(ROOT / "scripts/datasets.py"), "--data-root", str(source_root),
            "--level", config["level"], "--start", config["start"], "--end", config["end"]]
    require(command(args) == command(args, cwd=Path.home()),
            "File selection depends on the working directory.")
    return {"files": [str(path) for path in files], "level": config["level"],
            "start": config["start"], "end": config["end"],
            "missing_day_rejection": "Verified by synthetic unit tests, independent of source coverage."}


def analytical_check(work):
    import duckdb
    import pandas as pd
    import pyarrow.parquet as pq
    source = work / "fixture.csv.gz"
    with gzip.open(source, "wt", encoding="utf-8", newline="") as stream:
        stream.write("fecha|periodo|origen|destino|viajes|viajes_km\n"
                     "20220309|08|01001|01002|2.5|25\n"
                     "20220309|09|01001|01003|3.5|70\n"
                     "20220310|10|01001|01004|NA|NA\n")
    database = work / "fixture.duckdb"
    parquet = work / "fixture.parquet"
    with duckdb.connect(str(database)) as con:
        con.execute("SET memory_limit='512MB'")
        con.execute("SET temp_directory=" + sql_literal(work / "spill"))
        con.execute("CREATE TABLE bronze AS SELECT * FROM read_csv(?, delim='|', all_varchar=true)",
                    [str(source)])
        con.execute("""CREATE TABLE silver AS SELECT
            strptime(fecha, '%Y%m%d')::DATE AS fecha, periodo::SMALLINT AS hora,
            origen, destino, TRY_CAST(viajes AS DOUBLE) AS viajes,
            TRY_CAST(viajes_km AS DOUBLE) AS viajes_km FROM bronze""")
        require(con.execute("SELECT fecha,hora,origen FROM silver ORDER BY hora LIMIT 1").fetchone()
                == (date(2022, 3, 9), 8, "01001"), "Date/type/identifier conversion failed.")
        require(con.execute("SELECT COUNT(*) FROM silver WHERE viajes IS NULL").fetchone()[0] == 1,
                "Null handling failed.")
        con.execute("CREATE TABLE gold AS SELECT fecha,SUM(viajes) AS trips FROM silver GROUP BY fecha")
        require(con.execute("SELECT trips FROM gold WHERE fecha=DATE '2022-03-09'").fetchone()[0] == 6.0,
                "Unexpected aggregate result.")
        con.execute("COPY silver TO " + sql_literal(parquet) + " (FORMAT PARQUET)")
        require(con.execute("SELECT SUM(viajes_km) FROM read_parquet(?)", [str(parquet)]).fetchone()[0]
                == 95.0, "DuckDB Parquet round trip failed.")
        require(pq.read_table(parquet).num_rows == 3, "PyArrow Parquet read failed.")
        require(pd.read_parquet(parquet).iloc[0]["origen"] == "01001", "Pandas identifier changed.")
    with duckdb.connect(str(database), read_only=True) as con:
        require(con.execute("SELECT COUNT(*) FROM silver").fetchone()[0] == 3,
                "Persistent database reopen failed.")
    return {"fixture_rows": 3, "trip_total": 6.0,
            "trip_km_total": 95.0}


def real_sample_check(work):
    import duckdb
    files = get_files()
    sample = work / "real-sample.csv"
    opener = gzip.open if files[0].suffix == ".gz" else open
    # Bound decompression before SQL; never scan an entire source day here.
    with opener(files[0], "rt", encoding="utf-8-sig") as src, sample.open("w", encoding="utf-8") as dest:
        for _ in range(11):
            line = src.readline()
            if not line:
                break
            dest.write(line)
    with duckdb.connect() as con:
        frame = con.execute("SELECT * FROM read_csv(?, delim='|', all_varchar=true) LIMIT 10",
                            [str(sample)]).fetchdf()
    expected = {"fecha", "zona"} if load_config()["level"] == "calidad" else {
        "fecha", "origen", "destino", "viajes"}
    require(0 < len(frame) <= 10 and expected <= set(frame.columns),
            "The real sample is empty or has unexpected columns.")
    return {"source": str(files[0]), "rows": len(frame), "columns": list(frame.columns)}


def plot_and_cluster_check(work):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from sklearn.cluster import KMeans
    figure, axis = plt.subplots()
    axis.plot([8, 9], [2.5, 3.5])
    target = work / "plot.png"
    figure.savefig(target)
    plt.close(figure)
    require(target.stat().st_size > 0, "Plot file is empty.")
    labels = KMeans(n_clusters=2, random_state=0, n_init=10).fit_predict(
        [[0., 0.], [0., 1.], [9., 9.], [9., 10.]])
    require(labels[0] == labels[1] and labels[2] == labels[3] and labels[0] != labels[2],
            "Clustering did not recover the separated fixture groups.")
    return {"plot_bytes": target.stat().st_size, "clusters": 2}


def extension_check():
    import duckdb
    with duckdb.connect() as con:
        for name in ("ducklake", "spatial", "httpfs"):
            con.execute(f"LOAD {name}")
        columns = [item[0] for item in con.execute("DESCRIBE SELECT * FROM duckdb_extensions()").fetchall()]
        rows = con.execute("SELECT * FROM duckdb_extensions() WHERE extension_name IN "
                           "('ducklake','spatial','httpfs')").fetchall()
        return [dict(zip(columns, row)) for row in rows]


def ducklake_check(work):
    import duckdb
    catalog = work / "catalog.ducklake"
    data_path = work / "lake-data"
    data_path.mkdir()
    attach = "ATTACH " + sql_literal("ducklake:" + str(catalog)) + " AS lake"
    with duckdb.connect() as con:
        con.execute("LOAD ducklake")
        con.execute(attach + " (DATA_PATH " + sql_literal(str(data_path)) + ")")
        con.execute("CREATE SCHEMA lake.bronze")
        con.execute("CREATE SCHEMA lake.silver")
        con.execute("CREATE SCHEMA lake.gold")
        con.execute("BEGIN")
        con.execute("CREATE TABLE lake.bronze.fixture AS SELECT '01001' AS zone, 2.5 AS trips "
                    "UNION ALL SELECT '01001',3.5")
        con.execute("CREATE TABLE lake.silver.fixture AS SELECT zone,trips::DOUBLE AS trips "
                    "FROM lake.bronze.fixture")
        con.execute("CREATE TABLE lake.gold.fixture AS SELECT zone,SUM(trips) AS trips "
                    "FROM lake.silver.fixture GROUP BY zone")
        con.execute("COMMIT")
    with duckdb.connect() as con:
        con.execute("LOAD ducklake")
        con.execute(attach)
        require(con.execute("SELECT zone,trips FROM lake.gold.fixture").fetchall() == [("01001", 6.0)],
                "DuckLake committed aggregate did not survive reopening.")
    return {"catalog_reopened": True, "layers": ["bronze", "silver", "gold"], "trips": 6.0}


def spatial_check():
    import duckdb
    with duckdb.connect() as con:
        con.execute("LOAD spatial")
        distance = con.execute("SELECT ST_Distance(ST_Point(0,0),ST_Point(3,4))").fetchone()[0]
        require(distance == 5.0, "Unexpected planar point distance.")
    return {"planar_distance": distance}


def notebook_check(work, kernel_name=KERNEL):
    import nbformat
    from nbclient import NotebookClient
    from jupyter_client.kernelspec import KernelSpecManager
    source = ROOT / "notebooks/01_data_selection.ipynb"
    original = source.read_bytes()
    kernel = KernelSpecManager().get_kernel_spec(kernel_name)
    require(Path(kernel.argv[0]).absolute() == Path(sys.executable).absolute(),
            f"Kernel interpreter differs from check interpreter: {kernel.argv[0]}")
    notebook = nbformat.reads(original.decode("utf-8"), as_version=4)
    nbformat.validate(notebook)
    # Keep any notebook runtime/cache files in the Linux working directory.
    runtime_dir = work / "notebook-runtime"
    runtime_dir.mkdir()
    os.environ["JUPYTER_RUNTIME_DIR"] = str(runtime_dir)
    client = NotebookClient(notebook, timeout=180, kernel_name=kernel_name,
                            resources={"metadata": {"path": str(source.parent)}})
    try:
        client.execute()
    finally:
        require(source.read_bytes() == original, "The source notebook changed during execution.")
    executed = work / "executed-data-selection.ipynb"
    nbformat.write(notebook, executed)
    outputs = "\n".join(output.get("text", "") for cell in notebook.cells
                        for output in cell.get("outputs", []) if output.get("output_type") == "stream")
    require(sys.executable in outputs, "Notebook did not report the intended Linux interpreter.")
    return {"kernel": kernel_name, "interpreter": kernel.argv[0],
            "source_sha256": hashlib.sha256(original).hexdigest(),
            "source_unchanged": True, "executed_copy": str(executed)}


def parse_arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path,
                        default=Path.home() / ".local/share/mobility-lakehouse")
    parser.add_argument("--with-data", action="store_true", help="Verify configured source files")
    parser.add_argument("--with-notebook", action="store_true", help="Execute notebook; implies --with-data")
    parser.add_argument("--kernel", default=KERNEL, help="Registered notebook kernel name")
    args = parser.parse_args(argv)
    args.with_data = args.with_data or args.with_notebook
    return args


def build_checks(work, args):
    return [
        ("linux_interpreter", interpreter_check),
        ("dependencies", dependency_check),
        ("selector_unit_tests", selector_tests),
        ("analytical_round_trip", lambda: analytical_check(work)),
        ("plot_and_clustering", lambda: plot_and_cluster_check(work)),
        ("extensions", extension_check),
        ("ducklake_persistence", lambda: ducklake_check(work)),
        ("spatial_operation", spatial_check),
        ("source_selection", source_selection_check if args.with_data else None),
        ("real_sample", (lambda: real_sample_check(work)) if args.with_data else None),
        ("notebook_execution", (lambda: notebook_check(work, args.kernel)) if args.with_notebook else None),
    ]


def main(argv=None):
    args = parse_arguments(argv)
    base = args.work_dir.expanduser().resolve()
    base.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="readiness-", dir=base))
    os.environ.setdefault("MPLCONFIGDIR", str(work / "matplotlib"))
    os.environ["TMPDIR"] = str(work)
    checks = build_checks(work, args)
    report = {"started_at": datetime.now(timezone.utc).isoformat(), "work_dir": str(work),
              "scope": "notebook" if args.with_notebook else "data" if args.with_data else "core",
              "checks": [], "limitations": [
                  "Source coverage is inconsistent across levels and years.",
                  "INE data, geometries, and territorial mappings are not yet integrated.",
                  "Remote dataset downloads, Airflow, and AWS are not verified by this check.",
                  "Real source reads are bounded samples, not full-file quality validation."]}
    for name, check in checks:
        if check is None:
            report["checks"].append({"name": name, "status": "skipped", "reason": "Not requested"})
            print(f"[SKIPPED] {name}: not requested", flush=True)
            continue
        start = time.monotonic()
        try:
            detail = check()
            item = {"name": name, "status": "passed", "detail": detail}
        except Exception as error:
            item = {"name": name, "status": "failed", "error": f"{type(error).__name__}: {error}"}
        item["seconds"] = round(time.monotonic() - start, 3)
        report["checks"].append(item)
        print(f"[{item['status'].upper()}] {name}", flush=True)
        if "error" in item:
            print(f"  {item['error']}", flush=True)
    report["ready"] = all(item["status"] != "failed" for item in report["checks"])
    report["full_verification"] = all(item["status"] == "passed" for item in report["checks"])
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    serialized = json.dumps(report, indent=2, default=str) + "\n"
    (work / "report.json").write_text(serialized, encoding="utf-8")
    latest = base / "environment-report.json"
    latest.write_text(serialized, encoding="utf-8")
    print(f"Report: {latest}\nEnvironment ready ({report['scope']}): {report['ready']}\n"
          f"Full data and notebook verification: {report['full_verification']}", flush=True)
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
