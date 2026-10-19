# Guía de contribución (Contributing)

¡Gracias por tu interés en contribuir a **pdf2md-local**!

## Principios del proyecto

1. **100 % local y determinista:** Todo el flujo de extracción y verificación debe ejecutarse en local en CPU, sin depender de servicios en la nube ni llaves de API externas.
2. **El texto del PDF manda sobre los modelos visuales:** Para PDFs con capa de texto digital, los caracteres, estilos y coordenadas se leen directamente del PDF (`PyMuPDF`); los modelos neuronales (`Docling`) aportan las cajas de estructura, tablas y fórmulas.
3. **Cero regresiones:** Cada regla de limpieza o posprocesamiento debe estar respaldada por una prueba unitaria reproducible con datos o PDFs sintéticos generados al vuelo con `fitz` (`PyMuPDF`).
4. **Respeto estricto a los derechos de autor y privacidad:** **Nunca subas al repositorio archivos PDF reales con copyright ni documentos que contengan datos personales.** Todas las pruebas del repositorio construyen sus propios PDFs sintéticos en memoria o en directorios temporales (`tmp_path`).

## Configuración del entorno de desarrollo

```bash
git clone https://github.com/<usuario>/pdf2md-local.git
cd pdf2md-local
uv sync --locked
```

## Ejecución de pruebas

La batería de pruebas está dividida mediante marcadores de `pytest`:

- **Pruebas unitarias rápidas (por defecto, sin necesidad de modelos descargados):**
  ```bash
  uv run pytest -v
  ```
- **Pruebas que requieren modelos locales de Docling y RapidOCR (`~1.33 GB`):**
  ```bash
  uv run pdf2md-modelos
  uv run pytest -m "modelos" -v
  ```
- **Pruebas de integración completa (extracción + verificación sobre PDF sintético):**
  ```bash
  uv run pytest -m "slow" -v
  ```

## Cómo añadir una regla o corrección

1. Identifica en qué etapa del flujo pertenece el cambio:
   - Extracción de spans, fuentes, sub/superíndices o enlaces del PDF: `pdf2md/pdf_texto.py`
   - Geometría de columnas y orden de lectura: `pdf2md/orden_lectura.py`
   - Fusión con layout, tablas (`TableFormer`), fórmulas (`CodeFormula`) u OCR (`RapidOCR`): `pdf2md/docling_adaptador.py`
   - Emisión de Markdown, tablas HTML y limpieza de texto: `pdf2md/md_render.py`
   - Verificación de cobertura y diagnóstico: `pdf2md/verificar.py`
2. Escribe primero una prueba en `tests/` que reproduzca el caso con un objeto `Documento` o un PDF sintético creado con `fitz.open()`.
3. Implementa la solución asegurándote de que todas las pruebas existentes (`uv run pytest`) sigan pasando.
4. Abre un Pull Request describiendo el problema y la solución.

