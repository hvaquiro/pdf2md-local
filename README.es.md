# pdf2md-local

> 🇬🇧 **[Read documentation in English (README.md)](README.md)**

**Conversor de alta fidelidad de PDF a Markdown para documentos científicos y técnicos, 100 % local y en CPU.**

`pdf2md-local` combina la extracción directa de texto, fuentes y coordenadas del PDF mediante **PyMuPDF (`fitz`)** con los modelos neuronales locales de diseño editorial, tablas, fórmulas y OCR de **Docling** y **RapidOCR**, ejecutándose íntegramente en CPU sin necesidad de GPU, servicios en la nube ni claves de API.

---

## Características principales

- **100 % local y privado:** Funciona completamente sin conexión tras descargar una única vez los modelos locales (`~1.33 GB`). Ningún documento sale de tu equipo.
- **Motor híbrido (texto nativo + estructura neuronal):**
  - **Texto nativo exacto (`PyMuPDF`):** Lee caracteres, negritas, cursivas, subíndices (`₂`), superíndices (`²`), enlaces y coordenadas directamente de la capa digital del PDF, evitando alucinaciones o cambios de palabras en el texto corrido.
  - **Diseño y estructura (`Docling`):** Detecta jerarquía de títulos (`#`, `##`, `###`), leyendas (`Figure N`, `Table N`), notas al pie y bloques en páginas de 1, 2 o más columnas.
  - **Tablas en HTML (`TableFormer` en modo `accurate`):** Reconstruye tablas complejas con `<thead>`, `<tbody>`, `rowspan` y `colspan`, combinadas con alineación determinista contra el PDF para no perder palabras en celdas multilínea.
  - **Fórmulas en LaTeX (`CodeFormulaV2`):** Transcribe ecuaciones en bloque a `$$ ... $$`, con modo rápido alternativo basado en la capa de texto (`--sin-formulas`).
  - **OCR local integrado (`RapidOCR` PP-OCRv6):** Detecta automáticamente documentos escaneados, páginas de imagen o glifos sin mapa `ToUnicode` válido y los transcribe en CPU con soporte para español, inglés, portugués y alfabeto latino.
- **Posprocesamiento determinista:**
  - Enderezado automático de páginas apaisadas o tablas giradas 90° (`/Rotate` o texto vertical mayoritario).
  - Reconstrucción geométrica del orden de lectura en múltiples columnas con bloques de ancho completo intercalados.
  - Recorte inteligente de figuras a `200 dpi` (`.jpg`) excluyendo el pie de figura y filtrando logos editoriales, marcas de agua y tiras de encabezado.
  - Limpieza de cabeceras y pies de página repetidos, numeración de líneas de revisión y etiquetas invisibles de maquetación.
- **Verificador de calidad incluido (`pdf2md-verificar`):**
  - Audita el porcentaje de cobertura de palabras respecto al PDF original, comprueba que todas las figuras referenciadas existan en disco y genera reportes en `<destino>/_verificacion/` (`reporte.json`, `resumen.csv`, `alertas.md`).

---

## Requisitos de espacio en disco y procesamiento

### Espacio en disco

| Componente | Tamaño aproximado | Ubicación / Notas |
|---|---|---|
| Entorno virtual (`.venv`) | **~1.20 GB** | ~255 paquetes (`PyMuPDF`, `Docling`, `PyTorch` solo CPU, `Transformers`, `RapidOCR`) |
| Caché de descarga de paquetes (`uv`) | **~3.30 GB** | Temporal durante la instalación; puede liberarse con `uv cache clean` |
| Modelos neuronales locales (`~/.cache/docling/models`) | **~1.33 GB** | `CodeFormulaV2` (~610 MB), `TableFormer` (~342 MB), `Layout Heron` (~327 MB), `RapidOCR PP-OCRv6` (~53 MB) |
| Salida generada | **~0.5 MB / PDF** | Archivo `.md` (`30–120 KB`) + carpeta `figures/<doc>/` con recortes `.jpg` a 200 dpi (`100 KB – 2 MB`) |
| **Espacio libre recomendado** | **6 GB (instalación) / 3 GB (uso continuo)** | Se recomienda unidad SSD |

### Procesador (CPU) y Memoria RAM

| Recurso | Mínimo | Recomendado |
|---|---|---|
| **Sistema operativo** | Windows 10/11 (64 bits), Linux (x86_64 / ARM64), macOS 13+ | Windows 11 / Linux x86_64 o Apple Silicon |
| **Python** | Python `3.12.x` (`>=3.12,<3.13`) | Python `3.12.10+` |
| **Memoria RAM** | **8 GB** (1 proceso, `--hilos 4`) | **16 GB o más** (~2 GB de RAM por proceso de conversión activo) |
| **Procesador (CPU)** | 4 núcleos / 8 hilos (con soporte AVX2) | 8+ núcleos / 16+ hilos |
| **Tarjeta gráfica (GPU)** | **No requiere** (100 % en CPU) | No requiere |

### Tiempos de procesamiento de referencia (solo CPU)

Medidos en un procesador de 10 núcleos / 20 hilos (AMD Ryzen AI 9 365, 32 GB RAM):
- **Artículo estándar de 10–15 páginas (con tablas y figuras, pocas fórmulas):** `~25–60 s` por PDF (`~3–4 s / página`).
- **Modo rápido (`--sin-formulas`):** `~1.5–2.5 s / página` (hasta `10×` más rápido en documentos con muchas ecuaciones).
- **Artículo con abundantes fórmulas en bloque (`CodeFormulaV2` activo):** `~3–5 min` por PDF (`5–30 s` por fórmula en CPU).
- **Conversión en paralelo (2 procesos con `--parte 1/2` y `--parte 2/2 --hilos 8`):** `~3.5 PDFs / minuto`.

Consulta el desglose completo en [`docs/requisitos.md`](docs/requisitos.md).

---

## Inicio rápido

### 1. Clonar el repositorio e instalar dependencias

Con [`uv`](https://docs.astral.sh/uv/) (recomendado):

```bash
git clone https://github.com/hvaquiro/pdf2md-local.git
cd pdf2md-local
uv sync --locked
```

> **Alternativa con `pip`:** Crea un entorno virtual con Python 3.12 y ejecuta `pip install -r requirements.txt && pip install -e .` (ver [`docs/instalacion.md`](docs/instalacion.md)).

### 2. Descargar los modelos locales (una sola vez, ~1.33 GB)

```bash
uv run pdf2md-modelos
```

Este comando descarga en `~/.cache/docling/models/` los pesos de **Docling** (`layout`, `tableformer`, `code_formula`) y de **RapidOCR** (`PP-OCRv6` con alfabeto latino y respaldo DNS-over-HTTPS). Una vez completado, el proyecto funciona sin conexión a internet.

### 3. Convertir un archivo PDF o una carpeta completa

```bash
# Convertir un único archivo PDF
uv run pdf2md --origen ruta/al/articulo.pdf --destino archivos-md

# Convertir todos los PDFs de una carpeta (por defecto: archivos-pdf -> archivos-md)
uv run pdf2md --origen archivos-pdf --destino archivos-md

# Modo rápido sin modelo neuronal de fórmulas LaTeX
uv run pdf2md --origen archivos-pdf --destino archivos-md --sin-formulas

# Convertir solo un rango de páginas (1-indexado, inclusivo)
uv run pdf2md --origen ruta/al/articulo.pdf --destino archivos-md --paginas 1-5
```

### 4. Verificar la calidad de la extracción

```bash
uv run pdf2md-verificar --origen archivos-pdf --destino archivos-md
```

Genera en `<destino>/_verificacion/` el informe consolidado `reporte.md` y un archivo `<doc>.json` por documento, señalando cualquier documento con cobertura de palabras `< 97 %` o enlaces ausentes.

---

## Procesamiento en paralelo para lotes grandes

En equipos con 8 o más núcleos y `16 GB+` de RAM, la forma más rápida de procesar decenas de PDFs es repartir el lote en 2 procesos independientes:

```bash
# Terminal 1 (primera mitad)
uv run pdf2md --origen archivos-pdf --destino archivos-md --parte 1/2 --hilos 8

# Terminal 2 (segunda mitad)
uv run pdf2md --origen archivos-pdf --destino archivos-md --parte 2/2 --hilos 8
```

El flujo es **reanudable**: si detienes la ejecución y vuelves a lanzar el comando, omitirá automáticamente los archivos `.md` que ya existan en `--destino` (usa `--forzar` si deseas regenerarlos).

---

## Documentación detallada

- [`docs/requisitos.md`](docs/requisitos.md) — Requisitos detallados de disco, memoria RAM, CPU y tiempos de ejecución.
- [`docs/instalacion.md`](docs/instalacion.md) — Instalación paso a paso con `uv` o `pip`, descarga de modelos y rutas largas en Windows.
- [`docs/uso.md`](docs/uso.md) — Referencia completa de la línea de comandos (`pdf2md`, `pdf2md-verificar`, `pdf2md-modelos`) y ejemplos prácticos.
- [`docs/formato-salida.md`](docs/formato-salida.md) — Estructura del Markdown generado (`<!-- PageBreak -->`, tablas HTML, figuras, sub/superíndices y fórmulas).
- [`docs/arquitectura.md`](docs/arquitectura.md) — Arquitectura interna del motor híbrido y catálogo de reglas deterministas.
- [`docs/verificacion.md`](docs/verificacion.md) — Funcionamiento del verificador de cobertura e interpretación de alertas.
- [`docs/limitaciones.md`](docs/limitaciones.md) — Casos borde conocidos (texto vectorizado sin capa de caracteres, tablas multipágina complejas) y cómo abordarlos.
- [`docs/solucion-de-problemas.md`](docs/solucion-de-problemas.md) — Solución de problemas frecuentes (bloqueos DNS al bajar modelos, consumo de RAM, tablas apaisadas).

---

## Pruebas automatizadas

```bash
# Batería rápida de pruebas unitarias (~140 pruebas en ~15 s, no requiere modelos)
uv run pytest -q

# Pruebas de adaptador Docling y RapidOCR (requiere `uv run pdf2md-modelos`)
uv run pytest -m "modelos" -v

# Prueba de integración de extremo a extremo sobre PDF sintético
uv run pytest -m "slow" -v
```

---

## Licencia

Copyright (C) 2026 **hvaquiro**.

Distribuido bajo la licencia **GNU Affero General Public License v3.0 or later (`AGPL-3.0-or-later`)** — consulta [`LICENSE`](LICENSE) y [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) para más información.

