# Solución de problemas frecuentes (Troubleshooting)

Esta guía reúne las soluciones a los problemas más habituales durante la instalación, descarga de modelos y conversión de lotes de PDFs.

---

## 1. Falla la descarga de modelos de RapidOCR por bloqueo DNS (`RCODE_REFUSED` o `ConnectionError`)

**Síntoma:** Al intentar usar OCR por primera vez, la descarga automática desde `modelscope.cn` falla por rechazo del servidor DNS de tu proveedor de internet.

**Solución:** Ejecuta siempre el comando incluido en este proyecto:

```bash
uv run pdf2md-modelos
```

`pdf2md-modelos` incorpora un cliente **DNS-over-HTTPS (DoH)** que consulta directamente a los servidores públicos de Google (`dns.google`) y Cloudflare (`cloudflare-dns.com`) cuando el DNS del sistema falla, descargando los pesos `.pth` y diccionarios en `~/.cache/docling/models/RapidOcr/`.

---

## 2. El proceso se detiene repentinamente o consume demasiada memoria RAM

**Síntoma:** Al procesar un lote grande o un libro de varios cientos de páginas en un equipo con `8 GB` de RAM, el sistema operativo cierra el proceso o el equipo se vuelve lento.

**Soluciones:**
1. **Ejecuta un único proceso a la vez** y reduce el número de hilos de CPU:
   ```bash
   uv run pdf2md --origen archivos-pdf --destino archivos-md --hilos 4
   ```
2. **Simplemente vuelve a lanzar el comando:** Como `pdf2md` guarda cada archivo `.md` inmediatamente al terminar su conversión y libera memoria (`gc.collect()`), al relanzar el comando omitirá todos los documentos ya convertidos y continuará desde donde se quedó.
3. **Para libros o anuarios muy extensos (200+ páginas):** Si un único PDF gigante agota la memoria, puedes convertirlo por tramos de páginas usando `--paginas`:
   ```bash
   uv run pdf2md --origen libro.pdf --destino salida-tramo-1 --paginas 1-100
   uv run pdf2md --origen libro.pdf --destino salida-tramo-2 --paginas 101-200
   ```

---

## 3. Error `FileNotFoundError` en Windows al guardar figuras

**Síntoma:** En Windows, al convertir un PDF cuyo nombre de archivo tiene más de 150 caracteres, falla la escritura de `archivos-md/figures/<nombre-largo>/1.1.jpg`.

**Causa:** El límite clásico de `260 caracteres` (`MAX_PATH`) de la API de archivos de Windows cuando la ruta del directorio de trabajo ya es larga.

**Soluciones:**
1. Acorta el nombre del archivo `.pdf` antes de convertirlo, o ubica la carpeta de `--destino` en una ruta más corta.
2. Habilita el soporte de rutas largas en Windows ejecutando en PowerShell como Administrador:
   ```powershell
   New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" `
     -Name "LongPathsEnabled" -Value 1 -PropertyType DWORD -Force
   ```

---

## 4. El PDF es rechazado o `PyMuPDF` indica archivo dañado en descargas web

**Síntoma:** Un archivo `.pdf` descargado desde un navegador o gestor automatizado falla al abrirse o parece corrupto.

**Causa frecuente:** Algunos servidores devuelven el archivo envuelto en cabeceras HTTP *multipart* (`--boundary...%PDF-1.7...%%EOF...--boundary--`) antes del encabezado `%PDF-`.

**Solución:** Comprueba los primeros bytes del archivo. Si existen líneas de texto antes de `%PDF-`, recorta el archivo desde la primera aparición de `%PDF-` hasta el último `%%EOF`.

---

## 5. Una página o tabla sale sin texto en un documento antiguo

**Síntoma:** El archivo `.md` tiene una página casi vacía o falta una tabla específica, y `_conversion.log` muestra `paginas_imagen_sin_ocr` o `tablas_vacias`.

**Causa:** El documento es mayoritariamente digital (por lo que no activó el OCR global), pero contiene una página escaneada suelta o una tabla pegada como imagen de mapa de bits.

**Solución:** Reconvierte ese documento forzando el motor de OCR local:

```bash
uv run pdf2md --origen archivos-pdf/documento.pdf --destino archivos-md --ocr --forzar
```

---

## 6. La conversión tarda varios minutos en un solo artículo

**Causa:** El artículo contiene numerosas fórmulas matemáticas en bloque y el modelo `CodeFormulaV2` está transcribiéndolas una por una en la CPU (`5–30 s` por ecuación).

**Solución:** Si no necesitas transcripción neuronal a LaTeX de esas ecuaciones, cancela con `Ctrl+C` y relanza con `--sin-formulas --forzar`:

```bash
uv run pdf2md --origen archivos-pdf/documento.pdf --destino archivos-md --sin-formulas --forzar
```

