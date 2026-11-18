"""Local SQL workbench. Start with: python scripts/web.py"""
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
from pathlib import Path
import sys
import threading
import time
import tomllib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.bronze import connect, resolve


def json_value(value):
    if isinstance(value, dict):
        return {str(k): json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, bytes):
        return value.hex()
    return value


class Workbench:
    def __init__(self, config, timeout=60):
        if not (resolve(config['lake_dir']) / 'catalog.ducklake').is_file():
            raise ValueError('No existe el catálogo. Ejecuta primero scripts/bronze.py load.')
        self.con = connect(config, read_only=True)
        self.con.execute('USE lake.bronze')
        self.lock = threading.Lock()
        self.timeout = timeout

    def tables(self):
        with self.lock:
            rows = self.con.execute('''SELECT t.table_name,coalesce(i.n,0)
                FROM information_schema.tables t LEFT JOIN (
                    SELECT table_name,sum(row_count) n FROM lake.meta.ingestion GROUP BY 1
                ) i ON t.table_name=i.table_name
                WHERE t.table_catalog='lake' AND t.table_schema='bronze'
                ORDER BY t.table_name''').fetchall()
            columns = self.con.execute('''SELECT table_name,column_name,data_type
                FROM information_schema.columns
                WHERE table_catalog='lake' AND table_schema='bronze'
                ORDER BY table_name,ordinal_position''').fetchall()
        return {'tables': [{'name': name, 'rows': int(count),
                            'columns': [{'name': col, 'type': kind} for t, col, kind in columns if t == name]}
                           for name, count in rows]}

    def query(self, sql, limit):
        if not isinstance(sql, str) or not sql.strip() or len(sql) > 100_000:
            raise ValueError('Escribe una consulta SQL (máximo 100.000 caracteres).')
        if type(limit) is not int or not 1 <= limit <= 5000:
            raise ValueError('El límite de resultados debe estar entre 1 y 5.000.')
        if not self.lock.acquire(blocking=False):
            raise ValueError('Hay otra consulta en ejecución. Espera a que termine.')
        timer = None
        try:
            statements = self.con.extract_statements(sql)
            if len(statements) != 1 or str(statements[0].type).split('.')[-1] not in ('SELECT', 'EXPLAIN'):
                raise ValueError('Ejecuta una única consulta SELECT, WITH o EXPLAIN. El catálogo es de solo lectura.')
            started = time.monotonic()
            timer = threading.Timer(self.timeout, self.con.interrupt)
            timer.daemon = True
            timer.start()
            cursor = self.con.execute(sql)
            names = [column[0] for column in cursor.description]
            kinds = [str(column[1]) for column in cursor.description]
            rows = cursor.fetchmany(limit + 1)
            return {'columns': names, 'types': kinds,
                    'rows': [[json_value(v) for v in row] for row in rows[:limit]],
                    'truncated': len(rows) > limit, 'limit': limit,
                    'seconds': round(time.monotonic() - started, 3)}
        finally:
            if timer is not None:
                timer.cancel()
                timer.join()
            self.lock.release()

    def close(self):
        self.con.close()


class Handler(BaseHTTPRequestHandler):
    def reply(self, status, value, content_type='application/json; charset=utf-8'):
        payload = value.encode('utf-8') if isinstance(value, str) else json.dumps(
            value, ensure_ascii=False, default=str, allow_nan=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(payload)

    def allowed(self):
        port = self.server.server_address[1]
        hosts = {f'localhost:{port}', f'127.0.0.1:{port}'}
        if self.headers.get('Host') not in hosts:
            self.reply(403, {'error': 'Acceso local únicamente.'})
            return False
        origin = self.headers.get('Origin')
        if origin and origin not in {f'http://{host}' for host in hosts}:
            self.reply(403, {'error': 'Origen no permitido.'})
            return False
        return True

    def do_GET(self):
        if not self.allowed():
            return
        try:
            if self.path == '/':
                self.reply(200, (ROOT / 'web/index.html').read_text(encoding='utf-8'), 'text/html; charset=utf-8')
            elif self.path == '/api/tables':
                self.reply(200, self.server.workbench.tables())
            else:
                self.reply(404, {'error': 'Ruta no encontrada.'})
        except Exception as error:
            self.reply(500, {'error': str(error)})

    def do_POST(self):
        if not self.allowed():
            return
        if self.path != '/api/query':
            self.reply(404, {'error': 'Ruta no encontrada.'})
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 500_000:
                raise ValueError('Tamaño de petición inválido.')
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError('Petición inválida.')
            result = self.server.workbench.query(data.get('sql'), data.get('limit', 200))
            self.reply(200, result)
        except Exception as error:
            self.reply(400, {'error': str(error)})

    def log_message(self, format, *args):
        # SQL is never written to the request log.
        if len(args) < 2 or str(args[1]) not in ('200', '304'):
            super().log_message(format, *args)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--config', default=str(ROOT / 'config/bronze.toml'))
    parser.add_argument('--lake-dir')
    args = parser.parse_args()
    with resolve(args.config).open('rb') as stream:
        config = tomllib.load(stream)
    if args.lake_dir:
        config['lake_dir'] = args.lake_dir
    workbench = Workbench(config)
    try:
        with ThreadingHTTPServer(('127.0.0.1', args.port), Handler) as server:
            server.workbench = workbench
            print(f'Bronce SQL: http://localhost:{server.server_address[1]}', flush=True)
            print('Catálogo de solo lectura. Ctrl+C para cerrar.', flush=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
    finally:
        workbench.close()


if __name__ == '__main__':
    main()
