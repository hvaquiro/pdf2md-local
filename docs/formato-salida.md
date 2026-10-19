# Formato de salida Markdown

`pdf2md-local` genera archivos Markdown diseñados tanto para la lectura humana directa como para el procesamiento posterior en flujos de indexación semántica (RAG), revisión bibliográfica y análisis de datos científicos.

---

## 1. Estructura de directorios generada

Al convertir un lote hacia `--destino archivos-md`, se crea la siguiente estructura:

```text
archivos-md/
├── _conversion.log                 # Registro detallado de ejecución y tiempos
├── _verificacion/                  # (Generado al ejecutar pdf2md-verificar)
│   ├── reporte.md                  # Tabla consolidada de cobertura y alertas
│   ├── articulo-1.json             # Métricas detalladas por documento
│   └── articulo-2.json
├── articulo-1.md                   # Documento Markdown principal
├── articulo-2.md
└── figures/                        # Recortes de figuras por documento
    ├── articulo-1/
    │   ├── 2.1.jpg                 # Página 2, figura 1 (200 dpi)
    │   └── 5.1.jpg
    └── articulo-2/
        └── 3.1.jpg
```

---

## 2. Separadores de página (`<!-- PageBreak -->`)

Todas las páginas del PDF original se separan explícitamente mediante el comentario HTML estándar:

```markdown
Texto final de la página 1.

<!-- PageBreak -->

## 2. Materiales y métodos

Texto inicial de la página 2.
```

- Un PDF de $N$ páginas produce exactamente $N - 1$ marcadores `<!-- PageBreak -->`.
- Esto permite localizar de inmediato en qué página del PDF se encuentra cualquier párrafo, tabla o cita sin ensuciar la vista previa del Markdown con números de página ni encabezados repetidos.

---

## 3. Jerarquía de encabezados (`#`, `##`, `###`, `####`)

El motor combina la detección visual de bloques de `Docling` con el tamaño real en puntos (`pt`) y el estilo de fuente de `PyMuPDF`, aplicando reglas editoriales deterministas:

- **`#` (Nivel 1):** Reservado para el título principal del documento en la primera página.
- **`##` (Nivel 2):** Secciones principales (`Abstract`, `Resumen`, `1. Introduction`, `Materials and methods`, `References`, etc.).
- **`###` (Nivel 3):** Subsecciones de segundo nivel (`2.1. Experimental design`, `a) Sample preparation`).
- **`####` (Nivel 4):** Subsecciones de tercer nivel (`2.1.1. Statistical analysis`).

---

## 4. Estilos en línea, subíndices, superíndices y enlaces

El texto se construye directamente a partir de los *spans* del PDF (`pdf_texto.py`), conservando:

- **Negrita y cursiva:** `**negrita**`, `*cursiva*`, `***negrita cursiva***` (incluyendo nombres científicos en cursiva como `*Escherichia coli*`).
- **Subíndices y superíndices:**
  - Si todos los caracteres del tramo tienen equivalente Unicode (`0-9`, `+`, `-`, `=`, `(`, `)`, `n`, `i`, `a`, `b`...), se emiten como caracteres Unicode compactos: `CO₂`, `H₂O`, `m⁻²`, `10⁻⁴`, `R²`.
  - Si contienen letras o combinaciones sin equivalente Unicode completo, se emiten con etiquetas HTML estándar: `<sub>máx</sub>`, `<sup>a,b</sup>`.
- **Enlaces (`[texto](url)`):** Las anotaciones URI del PDF se asocian geométricamente a las palabras que cubren (DOIs, correos electrónicos, URLs externas), limpiando espacios no separables o saltos de línea invisibles al final de la URL.
- **Unión de palabras cortadas por guion al final de línea:** Si una línea termina en guion (`micro-` + `organisms`) y la siguiente comienza con minúscula, el motor reconstruye la palabra (`microorganisms`), conservando en cambio los compuestos reales (`well-known`, `pH-dependent` o prefijos seguidos de mayúscula como `anti-Stokes`).

---

## 5. Tablas en HTML (`<table>`)

Las tablas se emiten siempre como bloques HTML completos (`<table>`, `<thead>`, `<tbody>`, `<tr>`, `<th>`, `<td>`) en lugar de tablas Markdown con tuberías (`|`), ya que las tablas científicas requieren soporte nativo para:

- Celdas combinadas horizontal y verticalmente (`colspan="..."`, `rowspan="..."`).
- Cabeceras multinivel en `<thead>`.
- Celdas con múltiples líneas internas separadas mediante `<br>`.

Ejemplo de salida:

```html
<table>
  <thead>
    <tr>
      <th rowspan="2">Tratamiento</th>
      <th colspan="2">Rendimiento (kg ha⁻¹)</th>
    </tr>
    <tr>
      <th>Año 1</th>
      <th>Año 2</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>Control</td>
      <td>1250 ± 45<sup>a</sup></td>
      <td>1310 ± 52<sup>a</sup></td>
    </tr>
  </tbody>
</table>
```

La leyenda (`Table 1. ...`) y las notas al pie de tabla se emiten como párrafos independientes inmediatamente antes o después del bloque `<table>`.

---

## 6. Figuras y leyendas (`![](figures/...)`)

Cada figura relevante detectada en la página N se recorta a `200 dpi` en formato `.jpg` y se referencia con ruta relativa desde el archivo `.md`:

```markdown
![Figure 1. Evolución temporal de la biomasa.](figures/articulo-1/4.1.jpg)

Figure 1. Evolución temporal de la biomasa.
```

- **Recorte limpio sin pie de figura:** Si la caja visual de la figura incluye el texto del pie (`Figure 1...`), el motor ajusta el borde del recorte antes del texto para que la leyenda no aparezca duplicada dentro de la imagen y como párrafo.
- **Filtrado automático de ruido visual:** Se descartan automáticamente escudos o logos editoriales en las esquinas, tiras de encabezado, iconos de licencia Creative Commons/CrossMark y miniaturas decorativas.

---

## 7. Fórmulas matemáticas (`$$ ... $$`)

Las ecuaciones en bloque (*display equations*) se emiten encerradas entre dobles signos de dólar:

```markdown
$$Y_{ij} = \mu + \alpha_i + \beta_j + \epsilon_{ij} \quad (1)$$
```

- Con el modo por defecto, `CodeFormulaV2` transcribe la imagen de la ecuación a LaTeX y el posprocesador conserva el número de ecuación `(1)` si aparecía en el margen derecho de la misma línea en el PDF.
- Con `--sin-formulas`, la ecuación se construye a partir de los caracteres y símbolos Unicode de la capa de texto del PDF.

