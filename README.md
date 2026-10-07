# Charles Proxy File Analyzer (`charles_analizer`) v0.2.0

Herramienta interactiva y visual para parsear, analizar, filtrar e inspeccionar sesiones de **Charles Proxy** (`.chlz`, `.chls`) y archivos **HTTP Archive** (`.har`). Incluye una aplicación web interactiva (SPA) con vistas Structure y Sequence, motor de búsqueda con **expresiones regulares (Regex)**, badges de coincidencias en vivo, inspector JSON y *Live Request Replay*.

---

## ⚡ Inicio Rápido

La forma más rápida y recomendada de iniciar la aplicación web es mediante el script ejecutable:

```bash
# Prepara el entorno virtual (.venv), verifica dependencias y abre el navegador:
./run_web.sh
```

> **Tip**: También dispones del alias `./start.sh`.

---

## 🌐 Aplicación Web Interactiva (Web SPA)

### Opciones de Ejecución

```bash
# 1. Iniciar con puerto por defecto (8000) y abrir navegador automáticamente
./run_web.sh

# 2. Iniciar precargando directamente un archivo de sesión
./run_web.sh sesion.chlz
./run_web.sh sesion.har -p 8080

# 3. Especificar un puerto personalizado
./run_web.sh --port 8080
./run_web.sh -p 9000

# 4. Iniciar sin abrir automáticamente el navegador
./run_web.sh --no-browser

# 5. Forzar reinstalación de dependencias
./run_web.sh --reinstall

# 6. Ejecutar directamente con Python
python3 server.py --port 8000
python3 server.py sesion.chlz
```

### Funcionalidades de la Interfaz Web

Abre tu navegador en `http://localhost:8000`:

1. **Cargar sesión**: Arrastra o selecciona cualquier archivo de sesión (`.chlz`, `.chls`, `.har`). También puedes precargar un archivo indicándolo en el comando (`./run_web.sh archivo.chlz`).
2. **Explorar métricas y KPIs**:
   - Tarjetas de resumen: total de peticiones, ratio de éxito/fallo y volumen transferido.
   - Percentiles de latencia en milisegundos (**p50, p90, p95, p99**).
   - Gráficos interactivos de distribución de códigos de estado HTTP y principales dominios.
3. **Navegación Dual**:
   - **📂 Structure View**: Navega las peticiones agrupadas en carpetas jerárquicas por protocolo, dominio y rutas de endpoints.
   - **📋 Sequence View**: Tabla interactiva plana con ordenamiento multicriterio (ID, método, estado, host, duración y tamaño).
4. **Búsqueda Avanzada y Expresiones Regulares**:
   - Escribe en el buscador para filtrar en URLs, métodos, códigos de estado, cabeceras y cuerpos de petición/respuesta.
   - Haz clic en **`.* Regex`** para habilitar expresiones regulares (ej. `(api|v1)\/users\/\d+`, `^40[0-9]$`).
   - Badges contextuales visuales (`🎯 URL`, `🎯 Headers`, `🎯 Body`) con fragmentos de contexto y coincidencias resaltadas.
5. **Inspector Modal & Live Replay**:
   - Haz clic en cualquier petición para abrir el inspector modal.
   - Examina cabeceras formateadas y el árbol JSON colapsable con buscador en línea integrado.
   - Genera y copia con 1 clic el comando `curl` listo para terminal.
   - Modifica métodos, cabeceras, URL o cuerpo y presiona **Replay Request** para probar el endpoint en vivo.
6. **Descarga de Reportes**:
   - **📄 Download HTML Report**: Genera un reporte autónomo Glassmorphic de un solo archivo.
   - **Export JSON**: Volcado estructurado con todos los datos y payloads decodificados.
   - **Export CSV**: Formato tabular para análisis en hojas de cálculo.

---

## 📦 Instalación Manual

Si prefieres instalar las dependencias manualmente en tu entorno global o virtual:

### Requisitos
- **Python 3.8 o superior**

```bash
# 1. Instalar dependencias requeridas (descompresión Brotli)
pip install -r requirements.txt

# 2. (Opcional) Instalar en modo editable para habilitar comandos de consola globales
pip install -e .
```

Comandos de consola disponibles tras la instalación:
- `charles-web`: Servidor de la aplicación web interactiva (`charles-web --port 8000`).
- `charles-analizer`: Interfaz CLI por consola (`charles-analizer --help`).

---

## 📁 Estructura del Proyecto

```
charles_analizer/
├── run_web.sh            # Script de inicio rápido (prepara venv, instala dependencias y lanza web)
├── start.sh              # Enlace directo al script de lanzamiento
├── server.py             # Servidor Web SPA (Structure Tree, Sequence View, Inspector y Replay)
├── models.py             # Modelo CharlesRequest con helpers de estado, decodificación y tamaño
├── parser.py             # Parser multiformato (.chlz ZIP, .chls Java/JSON/XML, .har 1.2)
├── analyzer.py           # Agregación de métricas, percentiles, filtrado y motor de búsqueda Regex
├── exporter.py           # Exportadores a HTML interactivo, JSON y CSV
├── cli.py                # Interfaz de Línea de Comandos
├── analyze.py            # Script ejecutable de entrada CLI
├── pyproject.toml        # Metadatos del paquete y definición de comandos de consola
├── setup.py              # Configuración de instalación estándar setuptools
├── requirements.txt      # Dependencias del proyecto (brotli)
└── README.md             # Documentación del proyecto
```

---

## 📄 Licencia

Este proyecto está bajo la Licencia **MIT**.
