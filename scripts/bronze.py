"""Fetch, load and inspect the real mobility Bronze sources (Ubuntu/WSL2)."""
from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import date, timedelta
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time
import tomllib
from urllib.request import Request, urlopen
import zipfile

ROOT = Path(__file__).resolve().parents[1]
TABLES = (
    'viajes_gau', 'viajes_municipios', 'viajes_distritos', 'distritos_descartados',
    'empleo_provincial', 'pib_provincial', 'renta_zonas', 'estaciones_aemet',
    'observaciones_aemet', 'relacion_ine_mitma', 'zonificacion_mitma',
    'poblacion_zonas', 'nombres_zonas', 'calendario_festivos',
)
TRIP_COLUMNS = ('fecha periodo origen destino distancia actividad_origen '
                'actividad_destino estudio_origen_posible estudio_destino_posible '
                'residencia renta edad sexo viajes viajes_km').split()
OBS_COLUMNS = ('fecha indicativo nombre provincia altitud tmed prec tmin horatmin '
               'tmax horatmax hrMedia hrMax horaHrMax hrMin horaHrMin pintMax dir '
               'velmedia racha horaracha presMax horaPresMax presMin horaPresMin '
               'horaPIntMax sol').split()
STATION_COLUMNS = 'latitud provincia altitud indicativo nombre indsinop longitud'.split()


def literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def ident(value):
    return '"' + str(value).replace('"', '""') + '"'


def resolve(value):
    path = Path(value).expanduser()
    return (ROOT / path).resolve() if not path.is_absolute() else path.resolve()


def days(start, end):
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    if last < first:
        raise ValueError('End date precedes start date')
    return [first + timedelta(days=i) for i in range((last - first).days + 1)]


def read_text(path):
    raw = Path(path).read_bytes()
    try:
        return raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        return raw.decode('cp1252')


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class Source:
    table: str
    path: Path
    kind: str
    url: str = ''
    level: str = ''
    day: str = ''


def select_path(local, downloaded):
    candidates = sorted(p for p in local if p.is_file())
    if len(candidates) > 1:
        raise ValueError(f'Ambiguous source: {candidates}')
    return candidates[0] if candidates else downloaded


def sources(config):
    root, downloads = resolve(config['source_dir']), resolve(config['download_dir'])
    result = []
    base = config['mitma']['base_url']
    for day in days(config['start'], config['end']):
        stamp = day.strftime('%Y%m%d')
        for level, directory in [('GAU', 'GAU'), ('municipios', 'MUNICIPIOS'), ('distritos', 'DISTITOS')]:
            name = f'{stamp}_Viajes_{level}.csv.gz'
            local = root / config['mitma']['local_dir'] / directory
            # Prefer one compressed original. Never recursively ingest extracted copies.
            path = select_path([local / name], downloads / 'mitma' / level / name)
            key = config['mitma']['trips_url'].format(level=level, month=day.strftime('%Y-%m'), day=stamp)
            result.append(Source('viajes_' + level.lower(), path, 'trips', base + key, level, stamp))
        name = f'{stamp}_distritos_descartados.csv'
        path = select_path([root / config['mitma']['local_dir'] / 'CALIDAD' / name], downloads / 'mitma/calidad' / name)
        key = config['mitma']['quality_url'].format(month=day.strftime('%Y-%m'), day=stamp)
        result.append(Source('distritos_descartados', path, 'quality', base + key, day=stamp))
    for key, table in [('empleo', 'empleo_provincial'), ('pib', 'pib_provincial'), ('renta', 'renta_zonas')]:
        name = {'empleo': '65349.csv', 'pib': '80109.csv', 'renta': '30824.xlsx'}[key]
        path = select_path(root.glob(config['ine'][key]), downloads / 'ine' / name)
        result.append(Source(table, path, 'xlsx' if key == 'renta' else 'ine', config['ine'][key + '_url']))
    for table, name, endpoint in [
        ('estaciones_aemet', 'inventario_estaciones.json', config['aemet']['stations_endpoint']),
        ('observaciones_aemet', f"observaciones_diarias_{config['start'].replace('-', '')}_{config['end'].replace('-', '')}.json",
         config['aemet']['observations_endpoint'].format(start=config['start'], end=config['end'])),
    ]:
        path = select_path([root / 'AEMET' / name], downloads / 'aemet' / name)
        result.append(Source(table, path, 'aemet', config['aemet']['base_url'] + endpoint))
    key = config['territory']['crosswalk']
    result.append(Source('relacion_ine_mitma', downloads / key, 'crosswalk', base + key))
    for level, suffix in zip(config['territory']['levels'], config['territory']['suffixes'], strict=True):
        folder = f'zonificacion/zonificacion_{level}/'
        for table, name, kind in [
            ('poblacion_zonas', f'poblacion_{suffix}.csv', 'population'),
            ('nombres_zonas', f'nombres_{suffix}.csv', 'names'),
            ('zonificacion_mitma', f'zonificacion_{suffix}.shp', 'shape'),
        ]:
            result.append(Source(table, downloads / folder / name, kind, base + folder + name, level))
        for ext in ('shx', 'dbf', 'prj', 'cpg'):
            name = f'zonificacion_{suffix}.{ext}'
            result.append(Source('zonificacion_mitma', downloads / folder / name, 'support', base + folder + name, level))
    result.append(Source('calendario_festivos', downloads / 'calendar/BOE-A-2022-16755.html',
                         'calendar', config['calendar']['source_url']))
    return result


def validate_download(path, source):
    if path.stat().st_size == 0:
        raise ValueError(f'Empty download: {source.path.name}')
    if source.kind in ('trips', 'quality'):
        opener = gzip.open if source.kind == 'trips' else open
        with opener(path, 'rt', encoding='utf-8-sig') as stream:
            header = stream.readline().strip().split('|')
            row = stream.readline().strip().split('|')
        expected = TRIP_COLUMNS if source.kind == 'trips' else ['fecha', 'zona']
        if header != expected or (row != [''] and row[0] != source.day):
            raise ValueError(f'Wrong header/date: {source.path.name}')
        if source.kind == 'trips' and row == ['']:
            raise ValueError('Empty trip file')
    elif source.kind == 'aemet':
        data = json.loads(read_text(path))
        if not isinstance(data, list) or not data or 'indicativo' not in data[0]:
            raise ValueError('Not an AEMET record array')
    elif source.kind == 'xlsx':
        with zipfile.ZipFile(path) as archive:
            if 'xl/workbook.xml' not in archive.namelist():
                raise ValueError('Not an XLSX workbook')
    elif source.kind == 'shape':
        with path.open('rb') as stream:
            if stream.read(4) != b'\x00\x00\x27\x0a':
                raise ValueError('Not a shapefile')
    elif source.kind == 'calendar':
        text = read_text(path)
        if 'BOE-A-2022-16755' not in text or '2023' not in text:
            raise ValueError('Wrong BOE evidence')
    elif source.kind != 'support':
        text = read_text(path)
        if text.lstrip().startswith('<') or (';' not in text[:1000] and '|' not in text[:1000]):
            raise ValueError('Not a delimited source file')


def download(source, opener=urlopen):
    """Own a unique partial file; never replace an existing source."""
    if source.path.exists():
        validate_download(source.path, source)
        return
    source.path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=source.path.name + '.', suffix='.part', dir=source.path.parent)
    partial = Path(name)
    url = source.url
    try:
        if source.kind == 'aemet':
            token = os.environ.get('AEMET_API_KEY')
            if not token:
                raise ValueError('AEMET_API_KEY is required only when the local AEMET JSON is missing')
            with opener(Request(url, headers={'api_key': token}), timeout=120) as response:
                metadata = json.loads(response.read())
            if metadata.get('estado') != 200 or not metadata.get('datos', '').startswith('https://'):
                raise ValueError('AEMET did not return a data URL')
            url = metadata['datos']
        with os.fdopen(fd, 'wb') as stream:
            fd = None
            with opener(Request(url, headers={'User-Agent': 'mobility-bronze/1.0'}), timeout=120) as response:
                expected = response.headers.get('Content-Length')
                received = 0
                while chunk := response.read(4 * 1024 * 1024):
                    stream.write(chunk)
                    received += len(chunk)
                if expected is not None and received != int(expected):
                    raise ValueError('Truncated download')
        validate_download(partial, source)
        # link() publishes atomically and fails if another process already published.
        try:
            os.link(partial, source.path)
        except FileExistsError:
            validate_download(source.path, source)
        provenance = {'url': source.url, 'sha256': sha256(source.path)}
        source.path.with_name(source.path.name + '.source.json').write_text(
            json.dumps(provenance, ensure_ascii=False) + '\n', encoding='utf-8')
    finally:
        if fd is not None:
            os.close(fd)
        partial.unlink(missing_ok=True)


def fetch(config, table=None):
    for source in sources(config):
        if table and source.table != table:
            continue
        print(('LOCAL ' if source.path.exists() else 'FETCH ') + str(source.path), flush=True)
        download(source)


def csv_to_utf8(path, work):
    """Transcode only; preserve every character/value and keep originals untouched."""
    try:
        with path.open(encoding='utf-8-sig') as stream:
            for _ in stream:
                pass
        return path
    except UnicodeDecodeError:
        destination = work / 'utf8.csv'
        with path.open(encoding='cp1252', newline='') as source, destination.open('w', encoding='utf-8', newline='') as target:
            for line in source:
                target.write(line)
        return destination


def json_rows(path, table):
    data = json.loads(read_text(path))
    expected = STATION_COLUMNS if table == 'estaciones_aemet' else OBS_COLUMNS
    if not data or any(not isinstance(row, dict) for row in data):
        raise ValueError('Empty/invalid AEMET array')
    unknown = set().union(*(row.keys() for row in data)) - set(expected)
    if unknown:
        raise ValueError(f'Unexpected AEMET fields: {sorted(unknown)}')
    return expected, [tuple(None if row.get(c) is None else str(row[c]) for c in expected) for row in data]


def excel_rows(path):
    from openpyxl import load_workbook
    with path.open('rb') as stream:
        book = load_workbook(stream, read_only=True, data_only=True)
        try:
            sheet = book.worksheets[0]
            rows = sheet.iter_rows(values_only=True)
            for _ in range(6):
                next(rows)
            indicators, years = next(rows), next(rows)
            columns, indicator = ['Zona'], ''
            for name, year in zip(indicators[1:], years[1:], strict=True):
                if name is not None and str(name).strip():
                    indicator = str(name).strip()
                if not indicator or not re.fullmatch(r'20\d{2}', str(year)):
                    raise ValueError('Unrecognized INE rent header')
                columns.append(f'{indicator} [{year}]')
            if len(set(columns)) != len(columns):
                raise ValueError('Duplicate Excel column headings')
            output = []
            for row in rows:
                zone = str(row[0] or '')
                if re.match(r'^\d{5}(?:\d{2}(?:\d{3})?)?\s', zone):
                    output.append(tuple(None if v is None else str(v) for v in row[:len(columns)]))
                elif zone.strip() and not zone.startswith(('Notas:', 'Fuente:', 'Última modificación:')):
                    # Footnotes are outside the data table, but never silently drop a data-looking row.
                    if zone[0].isdigit():
                        raise ValueError(f'Unrecognized INE rent row: {zone}')
            if not output:
                raise ValueError('No INE rent records')
            return columns, output
        finally:
            book.close()


def calendar_rows(config, employment):
    first, last = config['calendar']['verified_start'], config['calendar']['verified_end']
    if config['start'] < first or config['end'] > last:
        raise ValueError(f'Calendar is verified only for {first} .. {last}')
    provinces = {}
    reader = csv.DictReader(io.StringIO(read_text(employment)), delimiter=';')
    for row in reader:
        match = re.fullmatch(r'(\d{2}) (.+)', row['Provincias'])
        if match:
            provinces[match[1]] = match[2]
    if set(provinces) != {f'{i:02}' for i in range(1, 53)}:
        raise ValueError('INE province codes do not cover 01..52')
    if config['calendar']['holidays']:
        raise ValueError('Holiday rules require a reviewed calendar implementation')
    columns = ('fecha_id codigo_provincia provincia anio mes nombre_mes dia dia_semana_num '
               'dia_semana_nombre es_fin_de_semana es_festivo_nacional tipo_dia').split()
    names = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
    rows = []
    for day in days(config['start'], config['end']):
        weekend = day.weekday() >= 5
        for code, province in sorted(provinces.items()):
            rows.append((day.strftime('%Y%m%d'), code, province, str(day.year), str(day.month),
                         'Marzo', str(day.day), str(day.isoweekday()), names[day.weekday()],
                         str(int(weekend)), '0', 'Fin de semana' if weekend else 'Laborable'))
    return columns, rows


def connect(config, read_only=False):
    import duckdb
    lake = resolve(config['lake_dir'])
    lake.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute('SET memory_limit=' + literal(config['memory_limit']))
    con.execute('SET threads=' + str(int(config['threads'])))
    con.execute('SET preserve_insertion_order=false')
    con.execute('SET temp_directory=' + literal(resolve(config.get('temp_dir', str(lake / 'tmp')))))
    con.execute('LOAD ducklake')
    con.execute('LOAD spatial')
    con.execute('ATTACH ' + literal('ducklake:' + str(lake / 'catalog.ducklake')) +
                ' AS lake (DATA_PATH ' + literal(lake / 'files') +
                (', READ_ONLY' if read_only else '') + ')')
    return con


def initialize(con):
    con.execute('CREATE SCHEMA IF NOT EXISTS lake.bronze')
    con.execute('CREATE SCHEMA IF NOT EXISTS lake.meta')
    con.execute('''CREATE TABLE IF NOT EXISTS lake.meta.ingestion (
        table_name VARCHAR, source_file VARCHAR, sha256 VARCHAR,
        row_count BIGINT, loaded_at TIMESTAMP)''')


def stage_rows(con, columns, rows, work):
    # Transfer auxiliary rows in one SQL scan, preserving NULL vs empty text.
    # Per-row INSERT calls are prohibitively slow for the national INE workbook.
    path = work / 'records.jsonl'
    with path.open('w', encoding='utf-8') as stream:
        for row in rows:
            stream.write(json.dumps(dict(zip(columns, row, strict=True)), ensure_ascii=False) + '\n')
    schema = '{' + ','.join(literal(c) + ":'VARCHAR'" for c in columns) + '}'
    con.execute('CREATE OR REPLACE TEMP VIEW incoming AS SELECT * FROM read_json(' +
                literal(path) + ", format='newline_delimited', columns=" + schema + ')')


def stage(con, source, config, work):
    path = source.path
    if source.kind in ('aemet', 'xlsx', 'calendar'):
        if source.kind == 'aemet':
            columns, rows = json_rows(path, source.table)
        elif source.kind == 'xlsx':
            columns, rows = excel_rows(path)
        else:
            employment = next(s.path for s in sources(config) if s.table == 'empleo_provincial')
            columns, rows = calendar_rows(config, employment)
        stage_rows(con, columns, rows, work)
    elif source.kind == 'shape':
        con.execute('CREATE OR REPLACE TEMP VIEW incoming AS SELECT ID::VARCHAR AS ID, '
                    'ST_AsText(geom)::VARCHAR AS geometria FROM ST_Read(' + literal(path) + ')')
    else:
        delimiter = ';' if source.kind == 'ine' else '|'
        # Compressed MITMA files are UTF-8. Auxiliary CSVs may be Windows-1252.
        selected = path if path.suffix == '.gz' else csv_to_utf8(path, work)
        opener = gzip.open if selected.suffix == '.gz' else open
        with opener(selected, 'rt', encoding='utf-8-sig', newline='') as stream:
            names = next(csv.reader(stream, delimiter=delimiter))
        nonnull = '[' + ','.join(literal(n) for n in names if n) + ']'
        options = f"delim={literal(delimiter)}, header=true, all_varchar=true, force_not_null={nonnull}, strict_mode=true"
        if source.kind == 'population':
            options = "delim='|', header=false, columns={'zona':'VARCHAR','poblacion':'VARCHAR'}, force_not_null=['zona','poblacion']"
        projection = '*'
        if source.kind == 'names':
            # The municipal file includes a provider row index, not a zone attribute.
            projection = 'ID, name'
        con.execute('CREATE OR REPLACE TEMP VIEW incoming AS SELECT ' + projection +
                    ' FROM read_csv(' + literal(selected) + ', ' + options + ')')
    if source.kind == 'trips':
        actual = [r[0] for r in con.execute('DESCRIBE incoming').fetchall()]
        if actual != TRIP_COLUMNS:
            raise ValueError(f'Wrong trip columns: {actual}')
    if source.level and source.kind in ('population', 'names', 'shape'):
        con.execute('CREATE OR REPLACE TEMP VIEW source_rows AS SELECT *, ' +
                    literal(source.level.lower()) + '::VARCHAR AS tipo_zona FROM incoming')
    else:
        con.execute('CREATE OR REPLACE TEMP VIEW source_rows AS SELECT * FROM incoming')


def source_key(source, config):
    for label, root in [('DATA', resolve(config['source_dir'])), ('RAW', resolve(config['download_dir']))]:
        if source.path.is_relative_to(root):
            return label + '/' + source.path.relative_to(root).as_posix()
    return source.path.as_posix()


def source_digest(source, config):
    digest = sha256(source.path)
    if source.kind == 'shape':
        digest = hashlib.sha256(''.join(sha256(source.path.with_suffix('.' + ext))
                                      for ext in ('shp', 'shx', 'dbf', 'prj', 'cpg')).encode()).hexdigest()
    if source.kind == 'calendar':
        employment = next(s.path for s in sources(config) if s.table == 'empleo_provincial')
        digest = hashlib.sha256((digest + sha256(employment) + json.dumps(config['calendar'], sort_keys=True)
                                 + config['start'] + config['end']).encode()).hexdigest()
    return digest


def load_one(con, source, config):
    validate_download(source.path, source)
    digest = source_digest(source, config)
    key = source_key(source, config)
    previous = con.execute('SELECT sha256,row_count FROM lake.meta.ingestion WHERE table_name=? AND source_file=?',
                           [source.table, key]).fetchall()
    if previous and previous != [(digest, previous[0][1])]:
        raise ValueError(f'Changed source already loaded: {key}. Use a new --lake-dir for a new snapshot.')
    if previous:
        print(f'SKIP {source.table}: {key} ({previous[0][1]:,} rows)', flush=True)
        return
    target = 'lake.bronze.' + ident(source.table)
    started = time.monotonic()
    con.execute('BEGIN')
    try:
        temporary = resolve(config.get('temp_dir', str(resolve(config['lake_dir']) / 'tmp')))
        temporary.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temporary) as tmp:
            stage(con, source, config, Path(tmp))
            con.execute(f'CREATE TABLE IF NOT EXISTS {target} AS SELECT *, '
                        f'{literal(key)}::VARCHAR AS _source_file FROM source_rows LIMIT 0')
            date_column = 'fecha_id' if source.kind == 'calendar' else 'fecha'
            if source.kind in ('trips', 'quality', 'aemet', 'calendar') and source.table != 'estaciones_aemet':
                con.execute(f'ALTER TABLE {target} SET PARTITIONED BY ({ident(date_column)})')
            con.execute(f'INSERT INTO {target} BY NAME SELECT *, {literal(key)}::VARCHAR AS _source_file FROM source_rows')
            count = con.execute(f'SELECT count(*) FROM {target} WHERE _source_file=?', [key]).fetchone()[0]
            expected = con.execute('SELECT count(*) FROM source_rows').fetchone()[0]
            if count != expected:
                raise ValueError(f'Count mismatch: source={expected}, loaded={count}')
            if source.kind in ('trips', 'quality'):
                bad = con.execute(f'SELECT count(*) FROM {target} WHERE _source_file=? AND '
                                  '(fecha IS NULL OR fecha != ?)', [key, source.day]).fetchone()[0]
                if bad or (source.kind == 'trips' and count == 0):
                    raise ValueError(f'Wrong or empty dates in {key}')
            if source.table == 'observaciones_aemet':
                present = {r[0] for r in con.execute(f'SELECT DISTINCT fecha FROM {target} WHERE _source_file=?', [key]).fetchall()}
                if present != {str(d) for d in days(config['start'], config['end'])}:
                    raise ValueError(f'AEMET date coverage mismatch: {present}')
            con.execute('INSERT INTO lake.meta.ingestion VALUES (?, ?, ?, ?, current_timestamp)',
                        [source.table, key, digest, count])
            con.execute('COMMIT')
    except Exception:
        con.execute('ROLLBACK')
        raise
    print(f'LOAD {source.table}: {count:,} rows ({time.monotonic()-started:.1f}s) {key}', flush=True)


def load(config, table=None):
    selected = [s for s in sources(config) if s.kind != 'support' and (not table or s.table == table)]
    missing = [str(s.path) for s in sources(config) if (not table or s.table == table) and not s.path.is_file()]
    if missing:
        raise ValueError('Missing sources; run fetch first:\n' + '\n'.join(missing))
    if not table or table == 'calendario_festivos':
        employment = next(s.path for s in sources(config) if s.table == 'empleo_provincial')
        calendar_rows(config, employment)  # Reject unverified intervals before writing.
    with connect(config) as con:
        initialize(con)
        (resolve(config['lake_dir']) / 'tmp').mkdir(parents=True, exist_ok=True)
        for source in selected:
            load_one(con, source, config)


def verify(con, config, table=None):
    """Validate the persisted snapshot, not a fixture or a bounded sample."""
    errors = []
    selected = [s for s in sources(config) if s.kind != 'support' and (not table or s.table == table)]
    expected_keys = {(s.table, source_key(s, config)) for s in selected}
    audit = con.execute('SELECT table_name,source_file,sha256,row_count FROM lake.meta.ingestion').fetchall()
    audit = [r for r in audit if not table or r[0] == table]
    if {(r[0], r[1]) for r in audit} != expected_keys or len(audit) != len(expected_keys):
        errors.append('Source inventory differs from the committed ingestion records')
    for name in ([table] if table else TABLES):
        target = 'lake.bronze.' + ident(name)
        columns = con.execute(f'DESCRIBE {target}').fetchall()
        if any(c[1] != 'VARCHAR' for c in columns):
            errors.append(f'{name}: non-text business columns')
        counts = dict(con.execute(f'SELECT _source_file,count(*) FROM {target} GROUP BY 1').fetchall())
        expected = {r[1]: r[3] for r in audit if r[0] == name}
        # Empty quality files legitimately have an audit entry and zero physical rows.
        if any(counts.get(k, 0) != n for k, n in expected.items()) or set(counts) - set(expected):
            errors.append(f'{name}: persisted counts differ from the complete source counts')
        if name.startswith('viajes_') or name == 'observaciones_aemet':
            dates = {r[0] for r in con.execute(f'SELECT DISTINCT fecha FROM {target}').fetchall()}
            wanted = {d.strftime('%Y%m%d') if name.startswith('viajes_') else str(d)
                      for d in days(config['start'], config['end'])}
            if dates != wanted:
                errors.append(f'{name}: date coverage differs: {sorted(str(d) for d in dates)}')
    for source in selected:
        entry = [r for r in audit if r[:2] == (source.table, source_key(source, config))]
        if entry and entry[0][2] != source_digest(source, config):
            errors.append(f'{source.table}: original source changed: {source_key(source, config)}')
    if not table:
        for name, code in [('zonificacion_mitma', 'ID'), ('poblacion_zonas', 'zona'), ('nombres_zonas', 'ID')]:
            duplicates = con.execute(f'SELECT count(*) FROM (SELECT tipo_zona,{ident(code)},count(*) n '
                                     f'FROM lake.bronze.{name} GROUP BY 1,2 HAVING count(*)>1)').fetchone()[0]
            if duplicates:
                errors.append(f'{name}: {duplicates} duplicate territorial keys')
            for level, cross_col in [('distritos', 'distrito_mitma'), ('municipios', 'municipio_mitma'), ('gau', 'gau_mitma')]:
                missing = con.execute(f'SELECT count(DISTINCT r.{cross_col}) FROM lake.bronze.relacion_ine_mitma r '
                                      f'ANTI JOIN lake.bronze.{name} z ON r.{cross_col}=z.{ident(code)} AND z.tipo_zona=?',
                                      [level]).fetchone()[0]
                if missing:
                    errors.append(f'{name}/{level}: {missing} crosswalk zones missing')
        employment = next(s.path for s in selected if s.table == 'empleo_provincial')
        cols, rows = calendar_rows(config, employment)
        actual = con.execute('SELECT ' + ','.join(ident(c) for c in cols) + ' FROM lake.bronze.calendario_festivos').fetchall()
        if sorted(actual) != sorted(rows):
            errors.append('Calendar differs from the verified day/province mapping')
        print('Territorial coverage and calendar checked')
    if errors:
        raise ValueError('\n'.join(errors))
    print(f'VERIFIED: {len(audit)} complete sources; counts, hashes, text types and dates match')


def inspect(config, table=None, limit=5, check=False):
    catalog = resolve(config['lake_dir']) / 'catalog.ducklake'
    if not catalog.is_file():
        raise ValueError('Lakehouse does not exist; run load first')
    with connect(config) as con:
        found = [r[0] for r in con.execute("SELECT table_name FROM information_schema.tables WHERE table_catalog='lake' AND table_schema='bronze' ORDER BY table_name").fetchall()]
        if check and not table and set(found) != set(TABLES):
            raise ValueError(f'Expected 14 Bronze tables, found {found}')
        for name in found:
            if table and name != table:
                continue
            target = 'lake.bronze.' + ident(name)
            count = con.execute(f'SELECT count(*) FROM {target}').fetchone()[0]
            columns = con.execute(f'DESCRIBE {target}').fetchall()
            print(f'\nbronze.{name}: {count:,} rows')
            print('Columns:', ', '.join(f'{c[0]} {c[1]}' for c in columns))
            date_col = next((c[0] for c in columns if c[0] in ('fecha', 'fecha_id')), None)
            if date_col:
                print('Dates:', con.execute(f'SELECT {ident(date_col)},count(*) FROM {target} GROUP BY 1 ORDER BY 1').fetchall())
            sample = con.execute(f'SELECT * FROM {target} LIMIT {int(limit)}').fetchall()
            print('Sample:', [tuple(v[:160] + '…' if isinstance(v, str) and len(v) > 160 else v for v in row) for row in sample])
        if table and table not in found:
            raise ValueError(f'Table not loaded: {table}')
        print(f'\nBronze tables: {len(found)}/{len(TABLES)}')
        if check:
            verify(con, config, table)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['fetch', 'load', 'inspect'])
    parser.add_argument('--config', default=str(ROOT / 'config/bronze.toml'))
    parser.add_argument('--source-dir')
    parser.add_argument('--download-dir')
    parser.add_argument('--lake-dir')
    parser.add_argument('--temp-dir')
    parser.add_argument('--start')
    parser.add_argument('--end')
    parser.add_argument('--table', choices=TABLES)
    parser.add_argument('--memory-limit')
    parser.add_argument('--threads', type=int)
    parser.add_argument('--limit', type=int, default=5)
    parser.add_argument('--verify', action='store_true', help='inspect: validate the complete persisted snapshot')
    args = parser.parse_args(argv)
    with resolve(args.config).open('rb') as stream:
        config = tomllib.load(stream)
    for key in ('source_dir', 'download_dir', 'lake_dir', 'temp_dir', 'start', 'end', 'memory_limit', 'threads'):
        if getattr(args, key) is not None:
            config[key] = getattr(args, key)
    days(config['start'], config['end'])
    if args.limit < 0 or config['threads'] < 1:
        parser.error('limit must be nonnegative and threads must be positive')
    try:
        if args.command == 'fetch':
            fetch(config, args.table)
        elif args.command == 'load':
            load(config, args.table)
        else:
            inspect(config, args.table, args.limit, args.verify)
    except Exception as error:
        # Do not print request objects or AEMET credentials.
        parser.exit(1, f'ERROR: {type(error).__name__}: {error}\n')


if __name__ == '__main__':
    main()
