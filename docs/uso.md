# Guía de uso y referencia de línea de comandos (CLI)

El paquete instala tres herramientas de línea de comandos:

1. **`pdf2md`** (o `python -m pdf2md`): Convierte un archivo PDF o un directorio de PDFs a Markdown.
2. **`pdf2md-verificar`**: Audita la cobertura de palabras y la integridad de las figuras de los archivos Markdown generados.
3. **`pdf2md-modelos`**: Descarga y verifica los modelos locales de `Docling` y `RapidOCR`.

---

## 1. Conversión de PDFs (`pdf2md`)

### Uso básico

```bash
# 1. Convertir todos los PDFs de la carpeta por defecto (archivos-pdf -> archivos-md)
uv run pdf2md

# 2. Convertir un único archivo PDF
uv run pdf2md --origen ruta/al/documento.pdf --destino archivos-md

# 3. Convertir todos los PDFs de una carpeta específica
uv run pdf2md --origen mis-pdfs/ --destino salida-md/
```

Por cada archivo `<nombre>.pdf`, el conversor genera:
- `<destino>/<nombre>.md`: El documento en formato Markdown con tablas en HTML y fórmulas en LaTeX.
- `<destino>/figures/<nombre>/<pagina>.<indice>.jpg`: Los recortes de las figuras e ilustraciones a `200 dpi` (p. ej. `1.1.jpg`).
- `<destino>/_conversion.log`: Registro detallado con tiempos por documento, avisos de páginas apaisadas, tablas vacías o páginas escaneadas.

### Todas las opciones de `pdf2md`

| Opción | Valor por defecto | Descripción |
|---|---|---|
| `--origen <RUTA>` | `archivos-pdf` | Ruta a un **archivo `.pdf` individual** o a un **directorio** con archivos `.pdf`. |
| `--destino <DIR>` | `archivos-md` | Directorio donde se escribirán los `.md`, la subcarpeta `figures/` y `_conversion.log`. |
| `--solo <FRAGMENTO>` | *(Todos)* | Filtra los PDFs de un directorio procesando solo aquellos cuyo nombre contenga este fragmento. |
| `--lista <ARCHIVO.txt>` | *(Ninguno)* | Ruta a un archivo de texto con un nombre de PDF por línea (con o sin `.pdf`) para procesar un subconjunto exacto. |
| `--parte <N/M>` | *(Todo el lote)* | Divide la lista ordenada de PDFs pendientes en `M` partes y procesa únicamente la parte `N` (p. ej. `--parte 1/2`, `--parte 2/2`). |
| `--paginas <A-B>` | *(Todas)* | Rango de páginas 1-indexado e inclusivo para depuración (p. ej. `--paginas 1-5`); la salida lleva sufijo `.pA-B.md`. |
| `--dpi <DPI>` | `200` | Resolución en puntos por pulgada de los recortes de figuras `.jpg`. |
| `--hilos <N>` | `8` | Número de hilos de CPU internos asignados a PyTorch/OMP por proceso. |
| `--sin-formulas` | `False` | Desactiva el modelo neuronal `CodeFormulaV2` y extrae las fórmulas directamente de la capa de texto del PDF (~10× más rápido en artículos con muchas ecuaciones). |
| `--ocr` | Automático | Fuerza el uso de `RapidOCR` incluso en documentos que ya tienen capa de texto digital. Por defecto, el OCR se activa automáticamente solo en documentos escaneados (≥ 50 % de páginas sin texto). |
| `--modelos <RUTA>` | `~/.cache/docling/models` | Carpeta raíz con los modelos locales (o variable de entorno `DOCLING_ARTIFACTS_PATH`). |
| `--forzar` | `False` | Reconvierte y sobrescribe los archivos `.md` aunque ya estén al día en `--destino`. |

---

## 2. Ejemplos prácticos de conversión

### Reanudar un lote interrumpido
Si cancelas la ejecución con `Ctrl+C` o se apaga el equipo, basta con volver a ejecutar el mismo comando. `pdf2md` detecta qué archivos `.md` ya están al día en `--destino` y continúa únicamente con los pendientes:

```bash
uv run pdf2md --origen archivos-pdf --destino archivos-md
```

### Procesar un lote grande en paralelo (2 procesos)
Para aprovechar al máximo procesadores de 8 o más núcleos (con `16 GB+` de RAM), abre dos terminales y ejecuta una mitad en cada una:

```bash
# Terminal 1
uv run pdf2md --origen archivos-pdf --destino archivos-md --parte 1/2 --hilos 8

# Terminal 2
uv run pdf2md --origen archivos-pdf --destino archivos-md --parte 2/2 --hilos 8
```

### Procesar una lista específica de archivos
Si quieres convertir o reconvertir (`--forzar`) únicamente ciertos documentos seleccionados, crea un archivo `pendientes.txt` con un nombre por línea:

```text
articulo-1.pdf
articulo-2.pdf
informe-tecnico.pdf
```

Y ejecuta:

```bash
uv run pdf2md --origen archivos-pdf --destino archivos-md --lista pendientes.txt --forzar
```

### Probar una página compleja en pocos segundos
Si quieres inspeccionar cómo queda una tabla en la página 7 de un PDF de 30 páginas sin convertir el documento entero:

```bash
uv run pdf2md --origen archivos-pdf/estudio.pdf --destino pruebas-md --paginas 7-7 --forzar
```

---

## 3. Verificación de calidad (`pdf2md-verificar`)

Una vez terminada la conversión, ejecuta el verificador para comprobar que no se haya perdido texto ni enlaces del PDF:

```bash
# Verificar una carpeta completa
uv run pdf2md-verificar --origen archivos-pdf --destino archivos-md

# Verificar un único PDF frente a su carpeta de salida
uv run pdf2md-verificar --origen archivos-pdf/estudio.pdf --destino archivos-md

# Filtrar por fragmento de nombre de archivo
uv run pdf2md-verificar --origen archivos-pdf --destino archivos-md --solo estudio
```

### Opciones de `pdf2md-verificar`

| Opción | Valor por defecto | Descripción |
|---|---|---|
| `--origen <RUTA>` | `archivos-pdf` | Archivo `.pdf` individual o directorio con los PDFs originales. |
| `--destino <DIR>` | `archivos-md` | Directorio con los archivos `.md` convertidos. |
| `--informe <DIR>` | `<destino>/_verificacion` | Carpeta donde se guardarán `reporte.md` y los archivos `<doc>.json`. |
| `--solo <FRAGMENTO>` | *(Todos)* | Verifica únicamente los archivos `.md` cuyo nombre contenga el fragmento indicado. |

El comando devuelve código de salida `1` si al menos un documento presenta alertas (cobertura `< 97 %` o enlaces ausentes). Consulta [`docs/verificacion.md`](verificacion.md) para aprender a interpretar el informe.

