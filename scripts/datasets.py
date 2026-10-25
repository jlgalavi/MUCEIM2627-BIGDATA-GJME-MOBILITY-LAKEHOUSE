"""Select local MITMA files or download an explicitly configured date range.

Uses only Python 3.11's standard library. Running without --download never
accesses the network. get_files() can also be used from notebooks and scripts.
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta
import gzip
import os
from pathlib import Path, PureWindowsPath
import re
import sys
import tomllib
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
LEVELS = ("distritos", "municipios", "gau", "calidad")


def resolve_path(value: str) -> Path:
    """Accept repo-relative paths and Windows drive paths when running in WSL."""
    value = os.path.expandvars(os.path.expanduser(value))
    win = PureWindowsPath(value)
    if os.name != "nt" and win.drive:
        if len(win.drive) != 2 or win.drive[1] != ":":
            raise ValueError("Use a Linux path for network shares in WSL.")
        return Path("/mnt") / win.drive[0].lower() / Path(*win.parts[1:])
    path = Path(value)
    return path.resolve() if path.is_absolute() else (ROOT / path).resolve()


def load_config() -> dict:
    with (ROOT / "config/datasets.toml").open("rb") as stream:
        config = tomllib.load(stream)
    local = ROOT / "config/datasets.local.toml"
    if local.exists():
        with local.open("rb") as stream:
            overrides = tomllib.load(stream)
        config["directories"].update(overrides.pop("directories", {}))
        config.update(overrides)
    return config


def dates(start: str, end: str) -> list[date]:
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    if last < first:
        raise ValueError("The end date must be on or after the start date.")
    return [first + timedelta(days=n) for n in range((last - first).days + 1)]


def file_date(path: Path) -> date | None:
    match = re.match(r"^(\d{4})(\d{2})(\d{2})_", path.name)
    return date(*map(int, match.groups())) if match else None


def get_files(level: str | None = None, start: str | None = None,
              end: str | None = None, data_root: str | None = None) -> list[Path]:
    """Return one source file per requested day; fail if coverage is incomplete."""
    config = load_config()
    level = level or config["level"]
    if level not in LEVELS:
        raise ValueError(f"Unknown level: {level}")
    days = dates(start or config["start"], end or config["end"])
    directory = resolve_path(data_root or config["data_root"]) / config["directories"][level]
    found: dict[date, list[Path]] = {}
    for path in sorted(directory.glob("*.csv*")):
        if path.is_file() and (day := file_date(path)) in days:
            found.setdefault(day, []).append(path)
    missing = [str(day) for day in days if day not in found]
    duplicates = [str(day) for day, paths in found.items() if len(paths) > 1]
    if missing or duplicates:
        raise ValueError(f"Incomplete or ambiguous selection in {directory}. "
                         f"Missing: {missing}; multiple files: {duplicates}")
    return [found[day][0] for day in days]


def inventory(config: dict, data_root: str | None) -> None:
    root = resolve_path(data_root or config["data_root"])
    print(f"Data root: {root}")
    for level in LEVELS:
        directory = root / config["directories"][level]
        files = sorted(p for p in directory.glob("*.csv*") if p.is_file())
        days = sorted({d for p in files if (d := file_date(p)) is not None})
        span = f"{days[0]} .. {days[-1]}" if days else "no dated files"
        print(f"{level}: {len(files)} files; {span}; "
              f"{sum(p.stat().st_size for p in files) / 1e6:.1f} MB")


def download(config: dict, args: argparse.Namespace) -> None:
    template = args.url_template or config["url_template"]
    if not template:
        raise ValueError("Set url_template or --url-template to a verified direct-download URL.")
    level = args.level or config["level"]
    output = resolve_path(args.download_dir or config["download_dir"]) / config["directories"][level]
    for day in dates(args.start or config["start"], args.end or config["end"]):
        url = template.format(date=day.strftime("%Y%m%d"), year=day.strftime("%Y"),
                              month=day.strftime("%m"), day=day.strftime("%d"), level=level)
        parsed = urlparse(url)
        name = parsed.path.rsplit("/", 1)[-1]
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("Download URLs must use HTTPS.")
        if not re.fullmatch(r"\d{8}_[A-Za-z0-9_.-]+\.csv(?:\.gz)?", name):
            raise ValueError("The direct URL must end with a dated MITMA CSV filename.")
        if file_date(Path(name)) != day:
            raise ValueError(f"URL filename does not match requested date: {url}")
        target = output / name
        print(f"{url} -> {target}")
        if args.dry_run:
            continue
        output.mkdir(parents=True, exist_ok=True)
        if target.exists():
            print("  Already exists; skipped")
            continue
        partial = target.with_name(target.name + ".part")
        try:
            # Exclusive creation prevents overwriting another running download.
            with partial.open("xb") as stream:
                with urlopen(Request(url, headers={"User-Agent": "mobility-lakehouse/0.1"}), timeout=120) as response:
                    while chunk := response.read(1024 * 1024):
                        stream.write(chunk)
            opener = gzip.open if name.endswith(".gz") else open
            with opener(partial, "rt", encoding="utf-8-sig") as stream:
                header = stream.readline()
            if "fecha" not in header.split("|") or "|" not in header:
                raise ValueError("Downloaded content does not have a MITMA CSV header.")
            partial.rename(target)
        except FileExistsError:
            raise ValueError(f"A download already exists or is in progress: {partial}") from None
        except Exception:
            partial.unlink(missing_ok=True)
            raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", action="store_true")
    parser.add_argument("--level", choices=LEVELS)
    parser.add_argument("--start", help="YYYY-MM-DD")
    parser.add_argument("--end", help="YYYY-MM-DD")
    parser.add_argument("--data-root", help="Local source folder")
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--url-template")
    parser.add_argument("--download-dir")
    parser.add_argument("--dry-run", action="store_true", help="Show download plan without network access")
    args = parser.parse_args()
    try:
        config = load_config()
        if args.inventory:
            inventory(config, args.data_root)
        elif args.download:
            download(config, args)
        else:
            if args.dry_run:
                raise ValueError("Use --dry-run together with --download.")
            for path in get_files(args.level, args.start, args.end, args.data_root):
                print(path)
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f"ERROR: {error}\n")


if __name__ == "__main__":
    main()
