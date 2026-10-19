# Registro de cambios (Changelog)

Todos los cambios relevantes de este proyecto se documentan en este archivo.
El formato está basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y este proyecto sigue [Semantic Versioning](https://semver.org/lang/es/).

## [0.1.0] - 2026-10-19

### Añadido
- **Motor híbrido local de conversión PDF a Markdown (`pdf2md`):**
  - Extracción directa de texto, fuentes, negritas, cursivas, subíndices, superíndices y enlaces con `PyMuPDF` (`fitz`).
  - Detección de diseño editorial, tablas (`TableFormer`), fórmulas en bloque (`CodeFormulaV2`) y figuras con `Docling` en CPU.
  - Reconocimiento óptico de caracteres (OCR) 100 % local mediante `RapidOCR` (`PP-OCRv6` sobre PyTorch CPU) para documentos escaneados o páginas de imagen.
  - Ordenamiento geométrico determinista para páginas de 1, 2 o más columnas con bloques de ancho completo intercalados.
  - Enderezado automático en directorios temporales de páginas apaisadas (`/Rotate` o texto vertical mayoritario).
  - Rescate de glifos sin mapa Unicode válido mediante tabla de nombres PostScript/Adobe y OCR puntual del glifo o celda.
  - Recorte inteligente de figuras con exclusión de leyendas y filtrado de logos editoriales, marcas de agua y tiras de encabezado.
  - Emisión de tablas en HTML (`<table>`, `<thead>`, `<tbody>`, `rowspan`, `colspan`) con corrección de celdas multilínea y cabeceras corridas.
- **Verificador independiente de calidad (`pdf2md-verificar`):**
  - Cálculo de cobertura de palabras contra el PDF original descontando cabeceras, pies y números de página repetidos.
  - Generación de informes detallados en `<destino>/_verificacion/` (`reporte.json`, `resumen.csv` y `alertas.md`).
- **Descargador unificado de modelos locales (`pdf2md-modelos`):**
  - Descarga en un solo paso de los pesos de `Docling` (`layout`, `tableformer`, `code_formula`) y `RapidOCR` (`PP-OCRv6` + alfabeto latino), con resolución DNS-over-HTTPS (DoH) de respaldo.
- **Soporte de archivo único o directorio** en `--origen` tanto para `pdf2md` como para `pdf2md-verificar`.
- **Batería de 141 pruebas automatizadas** con `pytest` y generador de PDFs sintéticos para validación sin necesidad de documentos propietarios.

