# Verificación de calidad (`pdf2md-verificar`)

La herramienta `pdf2md-verificar` audita de forma automática e independiente los archivos Markdown generados comparándolos contra la capa de texto y las anotaciones de enlace de los PDFs originales.

---

## 1. Qué comprueba el verificador

Para cada par `<documento>.pdf` y `<documento>.md`, `pdf2md-verificar` evalúa cuatro dimensiones:

1. **Cobertura de palabras con multiplicidad (`cobertura_palabras`):**
   - Extrae todas las palabras significativas del PDF original normalizando acentos, ligaduras (`ﬁ`, `ﬂ`), superíndices Unicode y guiones de corte de línea.
   - Comprueba qué porcentaje de las ocurrencias de palabras del PDF está presente en el archivo `.md` generado (aceptando palabras que el PDF trae pegadas sin espacio o superíndices unidos a su base).
   - Emite una **alerta** (y devuelve código de salida `1`) si la cobertura es inferior al **`97.0 %`** (en páginas con texto en el PDF).
2. **Integridad de enlaces e hipervínculos (`urls_ausentes`):**
   - Extrae todas las URLs de las anotaciones `/Link` del PDF (DOIs, enlaces web, correos `mailto:`) y verifica que aparezcan en el Markdown generado.
   - Si algún enlace del PDF no se encuentra en el `.md`, lo registra en `urls_ausentes` y activa una alerta.
3. **Estructura de páginas (`paginas_pdf` vs `paginas_md`):**
   - Cuenta las secciones separadas por `<!-- PageBreak -->` y comprueba su correspondencia con el número de páginas del PDF.
4. **Recuento de elementos y marcadores de diagnóstico:**
   - Contabiliza el número de encabezados (`#`), tablas HTML (`<table>`), figuras (`![](figures/...)`), fórmulas en bloque (`$$...$$`) y caracteres de reemplazo (`U+FFFD`) o marcadores `[órmula ilegible]`.

---

## 2. Archivos de informe generados

Al ejecutar:

```bash
uv run pdf2md-verificar --origen archivos-pdf --destino archivos-md
```

Se crean en `<destino>/_verificacion/` (o en la ruta indicada con `--informe`) los siguientes archivos:

| Archivo | Formato | Contenido |
|---|---|---|
| `reporte.md` | Markdown | Tabla resumen de todos los documentos verificados (`Documento`, `Págs`, `Cobertura`, `Tablas`, `Figs`, `Ecs`, `URLs perdidas`, `Estado`) seguida del detalle de **Alertas** y las palabras más frecuentes ausentes en cada documento con alerta. |
| `<documento>.json` | JSON | Métricas detalladas de ese documento individual (`cobertura_palabras`, `palabras_pdf`, `palabras_md`, `palabras_faltantes_top`, `urls_pdf`, `urls_md`, `urls_ausentes`, `alertas`, `notas`). |

---

## 3. Cómo interpretar los resultados

### Caso 1: `Cobertura >= 98 %` y estado `OK`
El documento se ha extraído íntegramente. El pequeño porcentaje restante (`0.2 % – 2 %`) suele corresponder a cabeceras/pies de página repetidos (que `pdf2md` filtra intencionadamente para limpiar el Markdown) o a etiquetas de texto dentro de gráficos vectoriales que quedaron recortados como imagen `.jpg`.

### Caso 2: `Cobertura` entre `95 %` y `97 %` en artículos con muchas gráficas o ecuaciones
- **Texto dentro de figuras vectoriales:** En muchos PDFs científicos, los ejes y leyendas internas de los diagramas están guardados como texto en el PDF. Como `pdf2md` recorta la figura completa en `.jpg`, esas palabras están visualmente en la imagen pero no se repiten como texto suelto. Revisa `palabras_faltantes_top` en `reporte.md` para confirmar si corresponden a etiquetas de ejes o diagramas.
- **Ecuaciones transcritas a LaTeX:** El modelo `CodeFormulaV2` transforma símbolos o funciones en comandos LaTeX (`\mathrm{...}`, `\frac`, `\sum`).

### Caso 3: `Cobertura < 95 %`
Indica generalmente uno de estos escenarios:
1. **Tablas incrustadas como imagen de mapa de bits:** Algunas revistas maquetan las tablas como imágenes rasterizadas sin capa de texto. Reconvierte ese documento añadiendo `--ocr --forzar`.
2. **PDF generado con `Print to PDF` (texto vectorizado sin fuentes):** Si algunas páginas tienen el texto dibujado como curvas vectoriales sin caracteres en la capa de texto, reconvierte con `--ocr --forzar` para que `RapidOCR` las transcriba.
