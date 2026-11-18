import json
from pathlib import Path
import tempfile
import threading
import tomllib
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from scripts import bronze, web


class WebTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        with (bronze.ROOT / 'config/bronze.toml').open('rb') as stream:
            self.config = tomllib.load(stream)
        self.config.update(lake_dir=str(Path(self.tmp.name) / 'lake'), memory_limit='512MB', threads=1)
        with bronze.connect(self.config) as con:
            bronze.initialize(con)
            con.execute('CREATE TABLE lake.bronze.viajes_gau (fecha VARCHAR,viajes VARCHAR)')
            con.execute("INSERT INTO lake.bronze.viajes_gau VALUES ('20230309','2.5'),('20230310','NA')")
            con.execute("INSERT INTO lake.meta.ingestion VALUES ('viajes_gau','test','test',2,current_timestamp)")
        self.workbench = web.Workbench(self.config)

    def tearDown(self):
        self.workbench.close()
        self.tmp.cleanup()

    def test_catalog_and_query_limits_and_types(self):
        tables = self.workbench.tables()['tables']
        self.assertEqual((tables[0]['name'], tables[0]['rows']), ('viajes_gau', 2))
        result = self.workbench.query('SELECT * FROM viajes_gau ORDER BY fecha', 1)
        self.assertEqual(result['columns'], ['fecha', 'viajes'])
        self.assertEqual(result['types'], ['VARCHAR', 'VARCHAR'])
        self.assertEqual(result['rows'], [['20230309', '2.5']])
        self.assertTrue(result['truncated'])
        result = self.workbench.query('WITH t AS (SELECT count(*) n FROM viajes_gau) SELECT * FROM t', 10)
        self.assertEqual(result['rows'], [[2]])

    def test_writes_multiple_statements_and_invalid_limits_are_rejected(self):
        for sql in ['DELETE FROM viajes_gau', 'DROP TABLE viajes_gau', 'SELECT 1; SELECT 2', '']:
            with self.assertRaises(ValueError):
                self.workbench.query(sql, 10)
        for limit in [0, 5001, True, '10']:
            with self.assertRaises(ValueError):
                self.workbench.query('SELECT 1', limit)
        # The storage itself is read-only, independently of the SQL type filter.
        with self.assertRaises(Exception):
            self.workbench.con.execute('DELETE FROM viajes_gau')
        self.assertEqual(self.workbench.query('SELECT count(*) FROM viajes_gau', 10)['rows'], [[2]])

    def test_error_and_timeout_release_connection_for_next_query(self):
        with self.assertRaises(Exception):
            self.workbench.query('SELECT campo_inexistente FROM viajes_gau', 10)
        self.workbench.timeout = 0.05
        with self.assertRaises(Exception):
            self.workbench.query('SELECT SUM(i) FROM range(1000000000000) t(i)', 10)
        self.workbench.timeout = 60
        self.assertEqual(self.workbench.query('SELECT 42', 10)['rows'], [[42]])

    def test_http_routes_origin_checks_and_structured_errors(self):
        with web.ThreadingHTTPServer(('127.0.0.1', 0), web.Handler) as server:
            server.workbench = self.workbench
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            base = f'http://127.0.0.1:{server.server_address[1]}'
            try:
                with urlopen(base) as response:
                    self.assertEqual(response.status, 200)
                    self.assertIn('Consulta SQL', response.read().decode())
                with urlopen(base + '/api/tables') as response:
                    self.assertEqual(len(json.load(response)['tables']), 1)
                request = Request(base + '/api/query', data=json.dumps({'sql': 'SELECT COUNT(*) FROM viajes_gau', 'limit': 10}).encode(), headers={'Content-Type': 'application/json'})
                with urlopen(request) as response:
                    self.assertEqual(json.load(response)['rows'], [[2]])
                request = Request(base + '/api/query', data=b'{"sql":"DELETE FROM viajes_gau"}', headers={'Content-Type': 'application/json'})
                with self.assertRaises(HTTPError) as error:
                    urlopen(request)
                self.assertEqual(error.exception.code, 400)
                self.assertIn('solo lectura', json.load(error.exception)['error'])
                request = Request(base + '/api/tables', headers={'Origin': 'https://example.invalid'})
                with self.assertRaises(HTTPError) as error:
                    urlopen(request)
                self.assertEqual(error.exception.code, 403)
            finally:
                server.shutdown()
                worker.join()


if __name__ == '__main__':
    unittest.main()
