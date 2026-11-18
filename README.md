# Bronce de movilidad: guía paso a paso

Cómo preparar el entorno, obtener los datos, cargar las 14 tablas bronce, exportarlas y consultarlas desde la web. El periodo de movilidad es **9–15 de marzo de 2023**.

**En este equipo el entorno y las tablas ya están preparados.** Para el uso diario puedes ir directamente a «Volver a abrir la web», al final. Para preparar otro equipo, sigue todos los pasos.

Ejecuta los comandos en una **terminal de Ubuntu o Ubuntu/WSL2**, no dentro de Python. Espera a que termine cada comando antes de continuar.

## 1. Entrar en el proyecto

Entra en la carpeta donde hayas guardado el proyecto. Por ejemplo, si está en la raíz de Ubuntu:

```bash
cd /mobility-lakehouse
```

Todos los comandos siguientes se ejecutan desde esa carpeta.

## 2. Preparar y activar el entorno

La primera vez necesitas Internet y `curl` instalado en Ubuntu. Si falta:

```bash
sudo apt update
sudo apt install curl
```

Prepara el entorno:

```bash
bash scripts/setup.sh
```

El script instala las dependencias y crea `.venv` con Python 3.11.17, sin cambiar el Python del sistema.

Actívalo:

```bash
source .venv/bin/activate
```

A partir de aquí puedes usar `python`. Cada vez que abras otra terminal tendrás que volver a entrar en el proyecto y activar el entorno.

## 3. Obtener los datos originales

```bash
python scripts/bronze.py fetch
```

Se reutilizan los originales disponibles en `../DATA` y se descarga lo que falte en `data/raw`. No hace falta volver a descargar los ficheros que ya existen.

Las rutas y fuentes están en `config/bronze.toml`. Si tus originales están en otra carpeta, cambia `source_dir` antes de continuar.

Si faltan los JSON locales de AEMET, su descarga necesita una clave `AEMET_API_KEY` en el entorno. Con los JSON incluidos en `DATA/AEMET` no hace falta introducirla.

## 4. Cargar las tablas bronce

```bash
python scripts/bronze.py load
```

La primera carga puede tardar varios minutos. Las tablas quedan guardadas en:

- `data/lake/catalog.ducklake`: catálogo.
- `data/lake/files`: ficheros de datos Parquet.

**Conserva ambos juntos.** Si repites `load`, se omiten los ficheros ya cargados y no se duplican sus registros.

## 5. Comprobar la carga

```bash
python scripts/bronze.py inspect --verify --limit 0
```

Debe indicar `Bronze tables: 14/14` y terminar con `VERIFIED`.

Para ver una muestra desde la terminal:

```bash
python scripts/bronze.py inspect --table viajes_distritos --limit 5
```

## 6. Exportar datos a CSV o Parquet (opcional)

Para exportar una tabla completa, copia este bloque entero en la terminal. El ejemplo guarda el calendario en ambos formatos:

```bash
python - <<'PY'
import tomllib
from pathlib import Path
from scripts.bronze import connect

config = tomllib.loads(Path("config/bronze.toml").read_text())
Path("data/export").mkdir(parents=True, exist_ok=True)

with connect(config, read_only=True) as con:
    con.execute("""
        COPY lake.bronze.calendario_festivos
        TO 'data/export/calendario_festivos.csv'
        (FORMAT CSV, HEADER, DELIMITER ';')
    """)
    con.execute("""
        COPY lake.bronze.calendario_festivos
        TO 'data/export/calendario_festivos.parquet'
        (FORMAT PARQUET)
    """)

print("Exportaciones guardadas en data/export")
PY
```

Para exportar otra tabla, sustituye `calendario_festivos` y los nombres de los ficheros de salida. Esta exportación incluye **todas las filas**; para tablas grandes es preferible Parquet.

Puedes exportar solo una selección sustituyendo una de las instrucciones `COPY` del bloque anterior por esta:

```sql
COPY (
    SELECT * FROM lake.bronze.viajes_gau WHERE fecha = '20230309'
) TO 'data/export/viajes_gau_20230309.parquet' (FORMAT PARQUET);
```

Ese SQL se ejecuta dentro de `con.execute(...)`, no directamente en Bash ni en el editor de la web.

## 7. Arrancar la interfaz web

Con el entorno activado:

```bash
python scripts/web.py
```

Cuando aparezca `Bronce SQL: http://localhost:8765`, abre **http://localhost:8765** en tu navegador. En WSL2 puedes abrirlo desde Windows.

Deja la terminal abierta mientras utilizas la web. Si el puerto está ocupado:

```bash
python scripts/web.py --port 8766
```

En ese caso, abre **http://localhost:8766**.

## 8. Consultar y exportar desde la web

Selecciona una tabla en el panel izquierdo o escribe una consulta:

```sql
SELECT *
FROM viajes_distritos
LIMIT 10;
```

Pulsa **Ejecutar consulta** o **Ctrl+Enter**. Puedes desplegar las columnas de cada tabla y pulsar una para insertarla en el editor.

**Descargar CSV** guarda las filas del resultado mostrado. La web muestra hasta 5.000 filas por consulta; para exportar una tabla completa utiliza el paso 6. Las consultas tienen un máximo de 60 segundos y el catálogo se abre en modo de solo lectura.

Los campos de bronce son texto. Para sumar viajes:

```sql
SELECT fecha,
       SUM(TRY_CAST(viajes AS DOUBLE)) AS total_viajes
FROM viajes_gau
GROUP BY fecha
ORDER BY fecha;
```

`TRY_CAST` deja como `NULL` los valores que no se puedan convertir; esos valores no participan en la suma.

Para cerrar el servidor, vuelve a la terminal y pulsa **Ctrl+C**.
