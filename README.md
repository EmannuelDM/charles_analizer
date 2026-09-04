# Charles Proxy File Analyzer (`charles_analizer`) v0.2.0

`charles_analizer` es una herramienta en Python de grado profesional para parsear, analizar, inspeccionar y exportar archivos de sesión de Charles Proxy (`.chlz`, `.chls`) y HTTP Archive (`.har`).

---

## 🌟 Características Principales (v0.2.0)

- **Soporte Multiformato Nativo (`.chlz`, `.chls`, `.har`)**:
  - **Archivos ZIP `.chlz`**: Descompresión e inspección automática (`-meta.json`, `-req.*`, `-res.*`) tanto en la raíz como en subcarpetas.
  - **Sesiones Binarias Java `.chls`**: Decodificación directa de flujos serializados de Java (`0xACED 0005`), extraendo transacciones, encabezados y payloads.
  - **Sesiones JSON / XML `.chls`**: Auto-detección y parseo de exportaciones estructuradas en JSON o XML.
  - **Archivos HTTP Archive `.har`**: Decodificación estándar v1.2 de logs HAR con extracción de peticiones, respuestas y timing de red.
- **Descompresión Transparente**: Soporta cuerpos codificados con **GZIP**, **Deflate** y **Brotli** (`brotli`).
- **Métricas Avanzadas y Percentiles de Latencia**: Métricas completas de peticiones totales, éxitos (2xx/3xx), fallos (4xx/5xx), transferencia de datos (subida/bajada), tiempos de respuesta (promedio, latencia, min, max, **Percentiles p50, p90, p95 y p99**) y desglose por categorías de estado HTTP (`2xx`, `3xx`, `4xx`, `5xx`, `ERR`).
- **Filtros Avanzados y Ordenamiento**: Filtrado por host/dominio, código de estado HTTP (p. ej. `200`, `4xx`, `503`), método (`GET`, `POST`), ruta de endpoint (`path`), parámetros de consulta (`query_param`) o solo errores. Soporta ordenamiento por duración, tamaño, estado o ID.
- **Búsqueda Global en Tiempo Real**: Búsqueda por texto o regex en URLs, encabezados (*headers*) y cuerpos de petición/respuesta (*request/response JSON/text*).
- **Inspección Detallada por ID**: Inspección profunda de encabezados y cuerpo codificado/JSON de cualquier petición por su número de ID con búsqueda insensible a mayúsculas/minúsculas en encabezados (`get_header()`).
- **Exportación Flexible**:
  - **JSON / CSV**: Exportación de datos estructurados y tablas con soporte para tamaño formateado (`formatted_size`) y categoría de estado.
  - **Manifiesto de Payloads (`manifest.json`)**: Volcado de cargas útiles con generación de archivo de índice `manifest.json` en el directorio de salida.
  - **HTML Interactivo (Glassmorphic Report)**: Reporte visual autónomo e interactivo con estética moderna, tarjetas de percentiles, tabla buscable, generador cURL e inspector JSON.
  - **Aplicación Web Interactiva (SPA)**: Servidor Web con soporte **CORS**, visualización en árbol de estructura por dominios y endpoints, inspector con pestañas completas y editor de parámetros para **Replay de peticiones en vivo**.

---

## 🌐 Aplicación Web (Servidor Web)

Puedes iniciar la aplicación web ejecutando cualquiera de los siguientes comandos:

```bash
# Iniciar servidor web e interactuar desde el navegador web (puerto 8000)
python3 charles_analizer/server.py

# O bien mediante la bandera --web
python3 charles_analizer/analyze.py --web
```

Abre tu navegador en `http://localhost:8000`:
1. Arrastra o selecciona tu archivo de sesión (`.chlz`, `.chls`, `.har`).
2. Explora las tarjetas de métricas KPI, percentiles de latencia, distribución de estados y dominios.
3. Utiliza la vista en árbol (*Tree View*) o el buscador para seleccionar peticiones.
4. Inspecciona encabezados, edita parámetros y ejecuta peticiones en vivo (**Live Replay**).
5. Haz clic en **📄 Generate HTML Report** para descargar un informe HTML interactivo e independiente.

---

## 📁 Estructura del Módulo

```
charles_analizer/
├── example_1.chlz        # Archivo de ejemplo de sesión Charles Proxy
├── __init__.py           # Exportaciones principales del paquete (v0.2.0)
├── models.py             # Modelo de datos CharlesRequest con helpers de categoría y tamaño
├── parser.py             # Lógica de descompresión y lectura de .chlz (CharlesSessionParser)
├── analyzer.py           # Métricas, percentiles, búsquedas, filtros y ordenamiento (CharlesAnalyzer)
├── exporter.py           # Exportadores a JSON, CSV, Reporte HTML y Payloads con manifiesto (CharlesExporter)
├── cli.py                # Interfaz de Línea de Comandos (CLI) con colores ANSI y percentiles
├── analyze.py            # Script ejecutable principal
├── server.py             # Servidor Web SPA con CORS, Replay y vistas interactivas
├── test_analyzer.py      # Suite de pruebas unitarias e integración
└── README.md             # Documentación del proyecto
```

---

## 🚀 Uso en Línea de Comandos (CLI)

### 1. Ver Resumen Estadístico en Terminal (con Percentiles y Colores ANSI)

```bash
python3 charles_analizer/analyze.py --summary
```

### 2. Obtener Resumen Estadístico en Formato JSON

```bash
python3 charles_analizer/analyze.py --json-summary
```

### 3. Filtrar por Dominio, Ruta y Ordenar por Duración Descendente

```bash
python3 charles_analizer/analyze.py --host clarovideo.net --sort-by duration --reverse
```

### 4. Filtrar por Parámetro de Consulta

```bash
python3 charles_analizer/analyze.py --query-param "profile=1"
```

### 5. Ver Solo Errores (4xx / 5xx)

```bash
python3 charles_analizer/analyze.py --errors-only
```

### 6. Buscar Términos en Peticiones y Cuerpos

```bash
python3 charles_analizer/analyze.py --search "already_with_susc"
```

### 7. Inspeccionar Detalladamente una Petición por ID

```bash
python3 charles_analizer/analyze.py --inspect-id 32
```

### 8. Exportar Resultados Completo (JSON, CSV, Reporte HTML y Payloads con Manifiesto)

```bash
python3 charles_analizer/analyze.py \
  --export-json output/session.json \
  --export-csv output/session.csv \
  --export-html output/report.html \
  --export-payloads output/payloads
```

---

## 🐍 Uso desde Código Python

```python
from charles_analizer import CharlesAnalyzer, CharlesExporter

# 1. Cargar archivo .chlz
analyzer = CharlesAnalyzer.from_file("charles_analizer/example_1.chlz")

# 2. Obtener métricas principales y percentiles
summary = analyzer.summary()
print(f"Total peticiones: {summary['total_requests']}")
print(f"Peticiones con error: {summary['failed_requests']}")
print(f"Percentiles latencia: p50={summary['percentiles_ms']['p50']}ms, p95={summary['percentiles_ms']['p95']}ms")

# 3. Filtrar y ordenar peticiones
peticiones_lentas = analyzer.filter(sort_by="duration", reverse=True)
for req in peticiones_lentas[:5]:
    print(f"Petición #{req.id} [{req.status_category}] ({req.formatted_size}): {req.duration_ms}ms -> {req.url}")

# 4. Obtener encabezados de manera insensible a mayúsculas
first_req = analyzer.requests[0]
content_type = first_req.get_header("Content-Type", response=True)
print(f"Content-Type de respuesta: {content_type}")

# 5. Exportar reporte HTML interactivo
CharlesExporter.to_html_report(summary, analyzer.requests, "reporte.html")
```

---

## 🧪 Pruebas Unitarias

Ejecuta el suite de pruebas para verificar el correcto funcionamiento de todas las características:

```bash
pytest
# O mediante unittest:
python3 -m unittest charles_analizer/test_analyzer.py
```

