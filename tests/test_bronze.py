from contextlib import redirect_stdout
import csv
import gzip
import io
import json
from pathlib import Path
import tempfile
import tomllib
import unittest
from unittest.mock import patch

from scripts import bronze


class Response(io.BytesIO):
    def __init__(self, body, length=None):
        super().__init__(body)
        self.headers = {'Content-Length': str(len(body) if length is None else length)}


class BrokenResponse(Response):
    def read(self, *args):
        raise ConnectionError('interrupted')


class BronzeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        with (bronze.ROOT / 'config/bronze.toml').open('rb') as stream:
            self.config = tomllib.load(stream)
        self.config.update(source_dir=str(self.root / 'DATA'),
                           download_dir=str(self.root / 'raw'),
                           lake_dir=str(self.root / 'lake'), memory_limit='512MB')
        (self.root / 'lake/tmp').mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def trip(self, name='20230309_Viajes_GAU.csv.gz', wrong_last=False):
        path = self.root / name
        first = ['20230309', '00', '01001', '01002', '2-10', 'casa', 'frecuente',
                 'no', 'no', '01', '<10', 'NA', 'NA', 'NA', '']
        second = first.copy()
        second[0] = '20220309' if wrong_last else '20230309'
        second[-2:] = ['2.500', '03.50']
        with gzip.open(path, 'wt', encoding='utf-8', newline='') as stream:
            writer = csv.writer(stream, delimiter='|', lineterminator='\n')
            writer.writerow(bronze.TRIP_COLUMNS)
            writer.writerows([first, second])
        return bronze.Source('viajes_gau', path, 'trips', day='20230309')

    def test_real_loader_preserves_text_and_repetition_does_not_duplicate(self):
        source = self.trip()
        with bronze.connect(self.config) as con, redirect_stdout(io.StringIO()):
            bronze.initialize(con)
            bronze.load_one(con, source, self.config)
            bronze.load_one(con, source, self.config)
            self.assertEqual(con.execute('SELECT count(*) FROM lake.bronze.viajes_gau').fetchone()[0], 2)
            self.assertEqual(con.execute('SELECT count(*) FROM lake.meta.ingestion').fetchone()[0], 1)
            self.assertIn(('01001', '00', 'NA', ''), con.execute(
                'SELECT origen,periodo,viajes,viajes_km FROM lake.bronze.viajes_gau').fetchall())
            self.assertEqual({r[1] for r in con.execute('DESCRIBE lake.bronze.viajes_gau').fetchall()}, {'VARCHAR'})
        # Persistence uses a separate DuckDB connection and reattaches the catalog.
        with bronze.connect(self.config) as con:
            self.assertEqual(con.execute('SELECT count(*) FROM lake.bronze.viajes_gau').fetchone()[0], 2)
            bad = self.trip('20230309_bad.csv.gz', wrong_last=True)
            with self.assertRaisesRegex(ValueError, 'Wrong or empty dates'):
                bronze.load_one(con, bad, self.config)
            self.assertEqual(con.execute('SELECT count(*) FROM lake.bronze.viajes_gau').fetchone()[0], 2)
            self.assertEqual(con.execute('SELECT count(*) FROM lake.meta.ingestion').fetchone()[0], 1)
        with gzip.open(source.path, 'at', encoding='utf-8') as stream:
            stream.write('changed\n')
        with bronze.connect(self.config) as con:
            with self.assertRaisesRegex(ValueError, 'Changed source'):
                bronze.load_one(con, source, self.config)

    def test_wrong_later_date_rolls_back_rows_and_completion_record(self):
        source = self.trip(wrong_last=True)
        with bronze.connect(self.config) as con:
            bronze.initialize(con)
            with self.assertRaisesRegex(ValueError, 'Wrong or empty dates'):
                bronze.load_one(con, source, self.config)
            self.assertEqual(con.execute('SELECT count(*) FROM lake.meta.ingestion').fetchone()[0], 0)
            self.assertEqual(con.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema='bronze'").fetchone()[0], 0)
        # A corrected source can be retried in the same lake.
        source = self.trip()
        with bronze.connect(self.config) as con, redirect_stdout(io.StringIO()):
            bronze.load_one(con, source, self.config)
            self.assertEqual(con.execute('SELECT count(*) FROM lake.bronze.viajes_gau').fetchone()[0], 2)

    def test_download_failures_remove_only_the_owned_partial_file(self):
        source = bronze.Source('distritos_descartados', self.root / 'quality.csv', 'quality',
                               'https://example.invalid/quality.csv', day='20230309')
        unrelated = self.root / 'other.part'
        unrelated.write_bytes(b'keep')
        for response in [Response(b'<html>error</html>'),
                         Response(b'fecha|zona\n20230309|01001\n', length=999),
                         BrokenResponse(b'interrupted')]:
            with self.assertRaises((ValueError, ConnectionError)):
                bronze.download(source, opener=lambda *a, **kw: response)
            self.assertFalse(source.path.exists())
            self.assertEqual(list(self.root.glob('*.part')), [unrelated])
        bronze.download(source, opener=lambda *a, **kw: Response(b'fecha|zona\n20230309|01001\n'))
        original = source.path.read_bytes()
        def forbidden(*args, **kwargs):
            self.fail('Existing source must not access the network')
        bronze.download(source, opener=forbidden)
        self.assertEqual(source.path.read_bytes(), original)

    def test_aemet_optional_fields_encoding_and_original_identifier(self):
        path = self.root / 'aemet.json'
        path.write_bytes(json.dumps([{'fecha': '2023-03-09', 'indicativo': '001X',
                                      'nombre': 'ÁLAVA', 'horaPIntMax': 'Varias', 'tmed': '19,4'}],
                                   ensure_ascii=False).encode('cp1252'))
        columns, rows = bronze.json_rows(path, 'observaciones_aemet')
        record = dict(zip(columns, rows[0]))
        self.assertEqual(record['horaPIntMax'], 'Varias')
        self.assertEqual(record['nombre'], 'ÁLAVA')
        self.assertEqual(record['tmed'], '19,4')
        self.assertIsNone(record['prec'])
        self.assertEqual(record['indicativo'], '001X')

    def test_aemet_two_step_download_keeps_credential_out_of_provenance(self):
        source = bronze.Source('estaciones_aemet', self.root / 'stations.json', 'aemet',
                               'https://opendata.aemet.es/opendata/api/inventory')
        requests = []
        def opener(request, **kwargs):
            requests.append(request)
            if len(requests) == 1:
                return Response(json.dumps({'estado': 200, 'datos': 'https://opendata.aemet.es/opendata/sh/data'}).encode())
            return Response(b'[{"indicativo":"001X"}]')
        with patch.dict('os.environ', {'AEMET_API_KEY': 'test-only-token'}):
            bronze.download(source, opener=opener)
        self.assertEqual(requests[0].get_header('Api_key'), 'test-only-token')
        self.assertEqual(len(requests), 2)
        self.assertNotIn('test-only-token', source.path.with_name('stations.json.source.json').read_text())

    def test_verifier_rejects_a_persisted_count_mismatch(self):
        source = self.trip()
        self.config['start'] = self.config['end'] = '2023-03-09'
        with bronze.connect(self.config) as con, redirect_stdout(io.StringIO()):
            bronze.initialize(con)
            bronze.load_one(con, source, self.config)
            with patch.object(bronze, 'sources', return_value=[source]):
                bronze.verify(con, self.config, 'viajes_gau')
                con.execute("DELETE FROM lake.bronze.viajes_gau WHERE viajes='NA'")
                with self.assertRaisesRegex(ValueError, 'persisted counts'):
                    bronze.verify(con, self.config, 'viajes_gau')

    def test_excel_keeps_indicator_year_columns_and_missing_values(self):
        from openpyxl import Workbook
        path = self.root / 'rent.xlsx'
        book = Workbook()
        sheet = book.active
        sheet.cell(7, 1, ' ')
        sheet.cell(7, 2, 'Renta neta media por persona')
        sheet.cell(8, 2, '2024')
        sheet.cell(8, 3, '2023')
        sheet.append(['01001 Alegría-Dulantzi', 17698, ' '])
        sheet.append(['0100101 Alegría-Dulantzi distrito 01', None, '.'])
        sheet.append(['Notas:', 'metadata'])
        book.save(path)
        book.close()
        columns, rows = bronze.excel_rows(path)
        self.assertEqual(columns, ['Zona', 'Renta neta media por persona [2024]', 'Renta neta media por persona [2023]'])
        self.assertEqual(rows[0], ('01001 Alegría-Dulantzi', '17698', ' '))
        self.assertEqual(rows[1][-2:], (None, '.'))
        self.assertEqual(len(rows), 2)

    def test_calendar_exact_coverage_and_excludes_melilla_local_holiday(self):
        path = self.root / 'employment.csv'
        with path.open('w', encoding='utf-8', newline='') as stream:
            writer = csv.writer(stream, delimiter=';')
            writer.writerow(['Provincias'])
            writer.writerows([[f'{i:02} Provincia {i}'] for i in range(1, 53)])
        columns, rows = bronze.calendar_rows(self.config, path)
        records = [dict(zip(columns, row)) for row in rows]
        self.assertEqual(len(records), 364)
        self.assertEqual(sum(r['es_fin_de_semana'] == '1' for r in records), 104)
        self.assertEqual(next(r for r in records if r['fecha_id'] == '20230313' and r['codigo_provincia'] == '52')['tipo_dia'], 'Laborable')
        self.config['end'] = '2023-03-16'
        with self.assertRaisesRegex(ValueError, 'verified only'):
            bronze.calendar_rows(self.config, path)

    def test_selection_never_uses_2022_districts_or_extracted_duplicates(self):
        directory = self.root / 'DATA' / self.config['mitma']['local_dir']
        (directory / 'DISTITOS').mkdir(parents=True)
        (directory / 'DISTITOS/20220309_Viajes_distritos.csv.gz').touch()
        (directory / 'GAU/20230309_Viajes_GAU.csv').mkdir(parents=True)
        (directory / 'GAU/20230309_Viajes_GAU.csv/20230309_Viajes_GAU.csv').touch()
        selected = bronze.sources(self.config)
        districts = [s for s in selected if s.table == 'viajes_distritos']
        self.assertEqual(len(districts), 7)
        self.assertTrue(all(s.day.startswith('2023') for s in districts))
        self.assertTrue(all('raw' in s.path.parts for s in districts))
        self.assertEqual(len([s for s in selected if s.table == 'viajes_gau']), 7)


if __name__ == '__main__':
    unittest.main()
