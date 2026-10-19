# Limitaciones conocidas y cómo abordarlas

Aunque el motor híbrido de `pdf2md-local` resuelve de forma determinista la gran mayoría de diseños editoriales científicos y técnicos, existen ciertos casos borde inherentes al formato PDF o a los modelos locales en CPU que conviene conocer.

---

## 1. Tablas extremas o que continúan en múltiples páginas

- **Tablas que abarcan varias páginas:** Como el PDF es un formato paginado, una tabla que continúa durante 3 o 4 páginas se emite como un bloque `<table>` independiente en cada página (separados por `<!-- PageBreak -->`), conservando la cabecera si el propio PDF la repite en cada página.
- **Tablas apaisadas muy densas (15+ columnas con celdas multilínea):** Aunque el adaptador endereza automáticamente las páginas giradas y realinea celdas omitidas por `TableFormer`, en tablas con más de 15 columnas muy estrechas y sin líneas divisorias visibles algunas celdas de texto multilínea pueden agruparse en la fila adyacente.
  - **Recomendación:** Revisar siempre en el Markdown las tablas de páginas muy densas cuando el registro `_conversion.log` indique `tablas_vacias` o el verificador muestre palabras ausentes concentradas en una página de tabla.

---

## 2. Tablas incrustadas como imagen (mapa de bits) en un PDF digital

Algunas publicaciones maquetan el texto del artículo en formato digital, pero pegan las tablas como imágenes `.png`/`.jpg` recortadas.
- En el modo digital por defecto, `TableFormer` detecta la caja de la tabla pero `PyMuPDF` no encuentra caracteres en esa zona, registrando un aviso `tablas_vacias=1` en `_conversion.log`.
- **Solución:** Reconvertir ese documento (o únicamente las páginas de las tablas con `--paginas M-N`) activando la bandera `--ocr --forzar` para que `RapidOCR` extraiga el texto de las celdas de la imagen.

---

## 3. PDFs con texto vectorizado («Print to PDF» sin capa de fuentes)

Algunos documentos generados mediante impresoras virtuales (como *Microsoft Print to PDF* desde ciertos visores) convierten cada letra en miles de trazos vectoriales (`drawings`) sin dejar ni un solo carácter en la capa de texto ni una imagen rasterizada a página completa.
- `pdf2md` detecta las páginas sin caracteres y activa automáticamente `RapidOCR` cuando al menos el `50 %` del documento carece de capa de texto.
- Si solo 1 o 2 páginas sueltas de un PDF grande están vectorizadas de este modo, el conversor registrará un aviso en `_conversion.log` y puedes forzar la lectura óptica pasando `--ocr --forzar`.

---

## 4. Velocidad del modelo de fórmulas (`CodeFormulaV2`) en CPU

El modelo neuronal `CodeFormulaV2` ofrece una transcripción LaTeX de alta calidad para ecuaciones en bloque, pero su inferencia autorregresiva en CPU toma entre **`5` y `30 segundos` por cada ecuación**.
- En una tesis o artículo de física/matemáticas con 80 ecuaciones en bloque, la conversión puede tardar entre 10 y 20 minutos.
- **Solución:** Si no necesitas reconstrucción LaTeX profunda de matrices o integrales complejas, utiliza `--sin-formulas`. La velocidad pasará a `~1.5–2.5 segundos por página` extrayendo el texto matemático directamente del PDF.

---

## 5. Idiomas soportados por el OCR local

El flujo de OCR local está configurado con el modelo unificado `PP-OCRv6` sobre PyTorch CPU (`PP-OCRv6_rec_small.pth` y respaldo latino `latin_PP-OCRv3_rec_mobile.pth`), que cubre con alta precisión:
- **Español, inglés, portugués, francés, italiano, alemán y demás lenguas de alfabeto latino**, además de dígitos y puntuación científica.
- En páginas puramente escaneadas con alfabetos no cubiertos por el diccionario del modelo, algunos caracteres especiales pueden requerir capa de texto digital (en PDFs digitales con capa de texto Unicode, cualquier alfabeto presente en el PDF sí se extrae directamente mediante `PyMuPDF`).

