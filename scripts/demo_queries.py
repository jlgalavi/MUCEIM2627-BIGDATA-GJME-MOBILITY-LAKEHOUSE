"""Run individual read-only source exploration queries from the terminal."""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.datasets import get_files, load_config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('number', type=int, nargs='?')
    parser.add_argument('--list', action='store_true')
    parser.add_argument('--day', help='YYYY-MM-DD; defaults to the configured start day')
    parser.add_argument('--level', choices=['gau', 'municipios'], default='gau')
    args = parser.parse_args()
    text = (ROOT / 'docs/sprint-1/demo-queries.sql').read_text(encoding='utf-8')
    sections = re.findall(r'^-- QUERY (\d+): ([^\n]+)\n(.*?)(?=^-- QUERY |\Z)',
                          text, flags=re.M | re.S)
    queries = {int(n): (title, sql.strip()) for n, title, sql in sections}
    if args.list:
        for number, (title, _) in queries.items():
            print(f'{number:2}. {title}')
        return
    if args.number not in queries:
        parser.error('Choose a query from 1 to 20, or use --list.')
    config = load_config()
    day = args.day or config['start']
    source = get_files(args.level, day, day)[0]
    title, sql = queries[args.number]
    print(f'QUERY {args.number}: {title}\nLevel: {args.level}\nSource: {source}\n', flush=True)
    print(sql, flush=True)
    import duckdb
    with duckdb.connect() as con:
        con.execute("SET memory_limit='1GB'")
        con.execute('SET threads=2')
        # Escape the filename as an SQL literal; the view only reads source files.
        literal = "'" + str(source).replace("'", "''") + "'"
        con.execute(f"""CREATE TEMP VIEW raw_trips AS SELECT * FROM read_csv(
            {literal}, delim='|', header=true, all_varchar=true, filename=true,
            nullstr='')""")
        con.execute("""CREATE TEMP VIEW typed_trips AS SELECT *,
            TRY_STRPTIME(fecha, '%Y%m%d')::DATE AS trip_date,
            TRY_CAST(periodo AS INTEGER) AS hour_slot,
            TRY_CAST(viajes AS DOUBLE) AS trip_count,
            TRY_CAST(viajes_km AS DOUBLE) AS trip_km
            FROM raw_trips""")
        result = con.execute(sql).fetchdf()
        print('\n' + result.to_string(index=False))
    print('\nSource exploration only: no persistent Bronze/Silver/Gold tables created.')


if __name__ == '__main__':
    main()
