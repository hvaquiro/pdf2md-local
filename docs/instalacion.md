# Guía de instalación

Esta guía explica cómo preparar el entorno en **Windows**, **Linux** o **macOS**, instalar las dependencias y descargar los modelos locales para trabajar sin conexión.

---

## 1. Requisitos previos

1. **Python 3.12 (`>=3.12,<3.13`):**
   - El proyecto está fijado a Python `3.12.x` para garantizar compatibilidad binaria exacta con `PyMuPDF`, `Docling`, `PyTorch` (CPU) y `RapidOCR`.
2. **Git:** Para clonar el repositorio.
3. **Rutas largas habilitadas en Windows (recomendado):**
   - Si vas a convertir PDFs con nombres de archivo muy largos, los recortes en `<destino>/figures/<nombre-del-pdf>/1.1.jpg` pueden superar el límite clásico de 260 caracteres (`MAX_PATH`) de Windows.
   - Para habilitar rutas largas en Windows 10/11 (PowerShell como Administrador):
     ```powershell
     New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" `
       -Name "LongPathsEnabled" -Value 1 -PropertyType DWORD -Force
     ```

---

## 2. Instalación recomendada con `uv`

[`uv`](https://docs.astral.sh/uv/) gestiona automáticamente la versión de Python 3.12 y resuelve el entorno virtual en segundos usando el archivo `uv.lock`.

### Paso 1: Instalar `uv` (si no lo tienes)

- **Windows (PowerShell):**
  ```powershell
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  ```
- **Linux / macOS:**
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```

### Paso 2: Clonar el repositorio y sincronizar el entorno

```bash
git clone https://github.com/<usuario>/pdf2md-local.git
cd pdf2md-local
uv python install 3.12
uv sync --locked
```

> **Nota sobre PyTorch en Linux:** El archivo `pyproject.toml` está configurado para descargar la variante **CPU-only** de `torch` y `torchvision` en Linux desde `https://download.pytorch.org/whl/cpu`, ahorrando más de `2 GB` de librerías CUDA innecesarias.

### Paso 3 (opcional): Liberar la caché de descarga de `uv`

Una vez creado `.venv`, puedes recuperar `~3.3 GB` de espacio en disco limpiando la caché de paquetes descargados:

```bash
uv cache clean
```

---

## 3. Instalación alternativa con `pip` y `venv`

Si prefieres no utilizar `uv`, puedes instalar el proyecto con las herramientas estándar de Python 3.12:

### En Windows (PowerShell)

```powershell
python3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -e .
```

### En Linux / macOS

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
# En Linux, instalar primero PyTorch CPU para evitar bajar paquetes CUDA:
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
pip install -e .
```

---

## 4. Descarga de los modelos neuronales locales (`~1.33 GB`)

Antes de convertir el primer PDF, ejecuta el descargador unificado de modelos:

```bash
uv run pdf2md-modelos
```

*(O `pdf2md-modelos` directamente si activaste `.venv`).*

### ¿Qué hace `pdf2md-modelos`?

1. **Modelos de Docling (`~1.28 GB`):** Descarga desde Hugging Face los modelos `layout` (`Heron`), `tableformer` (`accurate`) y `code_formula` (`CodeFormulaV2`) dentro de `~/.cache/docling/models/`.
2. **Modelos de RapidOCR (`~53 MB`):** Descarga los modelos PyTorch de `PP-OCRv6` y script latino (`PP-OCRv6_det_small.pth`, `PP-OCRv6_rec_small.pth`, `ch_ptocr_mobile_v2.0_cls_mobile.pth`, `ppocrv6_dict.txt`, `latin_PP-OCRv3_rec_mobile.pth`) en `~/.cache/docling/models/RapidOcr/`.
   - Incluye resolución **DNS-over-HTTPS (DoH)** automática (Google / Cloudflare) por si el proveedor de internet local bloquea las consultas DNS al servidor de distribución de modelos (`modelscope.cn`).

### Opciones avanzadas de `pdf2md-modelos`

```bash
# Descargar en un directorio personalizado
uv run pdf2md-modelos --destino /ruta/a/mis/modelos

# Descargar únicamente los modelos de RapidOCR (~53 MB)
uv run pdf2md-modelos --solo-ocr

# Descargar únicamente los modelos de Docling (~1.28 GB), omitiendo RapidOCR
uv run pdf2md-modelos --sin-ocr

# Forzar la redescarga aunque los archivos ya existan
uv run pdf2md-modelos --forzar
```

---

## 5. Comprobar que todo funciona

Ejecuta la batería de pruebas rápidas y verifica los comandos de consola:

```bash
uv run pytest -q
uv run pdf2md --help
uv run pdf2md-verificar --help
```

