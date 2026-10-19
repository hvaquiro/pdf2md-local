# Requisitos de sistema, espacio en disco y procesamiento

`pdf2md-local` ejecuta modelos de visión artificial y aprendizaje profundo (detección de diseño editorial, reconstrucción de tablas con `TableFormer`, transcripción de ecuaciones con `CodeFormulaV2` y reconocimiento óptico de caracteres con `RapidOCR PP-OCRv6`) **100 % en local sobre la CPU**.

A continuación se detallan los requisitos reales medidos para dimensionar adecuadamente el equipo donde se ejecutará.

---

## 1. Espacio en disco

El almacenamiento se divide en tres partes: el entorno de Python, la caché local de modelos neuronales y los archivos generados.

| Componente | Espacio en disco | Ubicación por defecto | Observaciones |
|---|---|---|---|
| **Entorno virtual (`.venv`)** | **~1.20 GB** | `<repo>/.venv` | ~255 paquetes instalados, incluyendo `PyMuPDF`, `Docling`, `PyTorch` (compilación solo CPU), `Transformers` y `RapidOCR`. |
| **Caché de paquetes de `uv`** | **~3.30 GB** | `~/.cache/uv` (Linux/macOS) o `%LOCALAPPDATA%\uv\cache` (Windows) | Solo necesaria durante la instalación o actualización. Se puede liberar íntegramente tras instalar ejecutando `uv cache clean`. |
| **Modelos neuronales locales** | **~1.33 GB** | `~/.cache/docling/models` | Se descargan una sola vez con `uv run pdf2md-modelos`. |
| **Salida por PDF convertido** | **~0.5 MB / PDF** | `<destino>/` y `<destino>/figures/` | Un artículo típico de 10–15 páginas genera `30–120 KB` de texto `.md` y entre `100 KB` y `2 MB` de figuras `.jpg` a 200 dpi. |
| **Archivos temporales en ejecución** | **~10–50 MB** | Directorio temporal del sistema (`%TEMP%` / `/tmp`) | Copias efímeras para páginas apaisadas o glifos sin Unicode; se eliminan automáticamente al terminar cada PDF. |

### Desglose de los modelos neuronales (`~1.33 GB`)

| Carpeta en `~/.cache/docling/models/` | Tamaño | Función dentro del flujo |
|---|---|---|
| `docling-project--CodeFormulaV2` | **~610 MB** | Transcripción de fórmulas matemáticas en bloque a código LaTeX (`$$ ... $$`). |
| `docling-project--docling-models` | **~342 MB** | Pesos de `TableFormer` (`accurate`) para detectar filas, columnas y celdas fusionadas en tablas. |
| `docling-project--docling-layout-heron` | **~164 MB** | Modelo de segmentación de diseño de página (títulos, párrafos, figuras, tablas, pies). |
| `docling-project--docling-layout-heron-onnx` | **~163 MB** | Pesos ONNX complementarios del detector de diseño. |
| `RapidOcr` (`PP-OCRv6` + script latino) | **~53 MB** | Detección, orientación y reconocimiento de texto sobre PyTorch CPU (`PP-OCRv6_det_small.pth`, `PP-OCRv6_rec_small.pth`, `ch_ptocr_mobile_v2.0_cls_mobile.pth`, `latin_PP-OCRv3_rec_mobile.pth`). |

> **Resumen de almacenamiento:**
> - **Durante la instalación inicial:** Disponer de al menos **6 GB libres**.
> - **En operación normal (tras `uv cache clean`):** El proyecto y sus modelos ocupan **~2.6 a 3.0 GB** fijos.
> - **Tipo de disco:** Se recomienda encarecidamente unidad **SSD NVMe o SATA** para la carga inicial de los pesos de PyTorch y el recorte de imágenes.

---

## 2. Memoria RAM y Procesador (CPU)

| Recurso | Configuración mínima | Configuración recomendada | Configuración para lotes masivos |
|---|---|---|---|
| **Memoria RAM del sistema** | **8 GB** | **16 GB** | **32 GB o más** |
| **Procesador (CPU)** | 4 núcleos / 8 hilos (x86_64 con AVX2 o ARM64) | 8 núcleos / 16 hilos | 10+ núcleos / 20+ hilos |
| **Procesos simultáneos (`--parte`)** | 1 proceso | 2 procesos (`1/2` y `2/2`) | 2 a 3 procesos |
| **Hilos por proceso (`--hilos`)** | `--hilos 4` | `--hilos 8` | `--hilos 8` |
| **GPU dedicada** | No necesaria | No necesaria | No necesaria |

### Consumo de RAM por proceso

- Cada instancia de `pdf2md` carga en memoria los modelos de `Docling` y `RapidOCR`, consumiendo alrededor de **1.8 a 2.5 GB de RAM** en estado estacionario, con picos de hasta **3.5 GB** en páginas con tablas muy densas o imágenes a página completa.
- En equipos con **8 GB de RAM**, ejecuta **un único proceso** a la vez (`--hilos 4`).
- En equipos con **16 GB de RAM o más**, puedes lanzar **2 procesos en paralelo** (`--parte 1/2` y `--parte 2/2`), manteniendo siempre un margen de seguridad para el sistema operativo.

---

## 3. Rendimiento y tiempos de procesamiento

Los tiempos de conversión en CPU dependen principalmente de tres factores: el número de páginas, la cantidad de tablas y, sobre todo, el **número de fórmulas matemáticas en bloque**.

### Tiempos medidos de referencia (CPU de 10 núcleos / 20 hilos)

| Tipo de documento | Configuración | Tiempo medio | Velocidad por página |
|---|---|---|---|
| Artículo científico estándar (10–15 págs., 3–5 tablas, pocas fórmulas) | Por defecto | **25 – 60 s / PDF** | `~3 – 4 s / pág.` |
| Artículo con abundantes ecuaciones (20+ fórmulas en bloque) | Por defecto (`CodeFormulaV2` activo) | **3 – 5 min / PDF** | `~10 – 25 s / pág.` (`5–30 s` por fórmula) |
| Cualquier artículo científico o técnico | Modo rápido (`--sin-formulas`) | **15 – 35 s / PDF** | **`~1.5 – 2.5 s / pág.`** (`~10×` más rápido en textos matemáticos) |
| Documento escaneado (OCR completo con `RapidOCR`) | `--ocr` (o detección automática) | **45 – 90 s / PDF** | `~4 – 7 s / pág.` |
| Anuario o libro extenso (300+ páginas con decenas de tablas) | Por defecto | **30 – 60 min** | `~6 – 12 s / pág.` |
| Lote de 40 artículos variados (2 procesos en paralelo) | `--parte 1/2` y `2/2 --hilos 8` | **~11 – 15 min total** | **`~3.5 PDFs / minuto`** |

### ¿Cuándo usar `--sin-formulas`?

El modelo neuronal `CodeFormulaV2` transcribe imágenes de ecuaciones a LaTeX completo, pero en CPU invierte entre `5` y `30 segundos` por cada ecuación en bloque.
- Si necesitas la máxima fidelidad en ecuaciones complejas (integrales, matrices, fracciones anidadas), usa el modo por defecto.
- Si priorizas la velocidad o trabajas con documentos donde las fórmulas son sencillas y ya están en la capa de texto del PDF, añade `--sin-formulas`: el conversor extraerá los símbolos matemáticos directamente de la capa de texto del PDF en milisegundos.

