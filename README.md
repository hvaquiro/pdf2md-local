# pdf2md-local

> 🇪🇸 **[Leer documentación en español (README.es.md)](README.es.md)**

**High-fidelity, 100% local PDF-to-Markdown converter for scientific and technical documents.**

`pdf2md-local` combines direct text and font geometry extraction via **PyMuPDF (`fitz`)** with local neural layout, table, formula, and OCR models from **Docling** and **RapidOCR** running entirely on CPU—no GPU, no cloud services, and no API keys required.

---

## Key Features

- **100% Local & Private:** Runs completely offline on CPU after a one-time local model download (`~1.33 GB`).
- **Hybrid Extraction Engine:**
  - **Digital PDFs:** Reads characters, bold/italic styles, subscripts (`₂`), superscripts (`²`), links, and bounding boxes directly from the PDF text layer (`PyMuPDF`) so running text is never hallucinated or altered by vision models.
  - **Layout & Structure:** Uses **Docling** (`docling-layout-heron`) for section headers, captions, footnotes, and reading-order segmentation across multi-column pages.
  - **HTML Tables:** Uses **TableFormer** (`accurate` mode) to reconstruct complex tables with `<thead>`, `<tbody>`, `rowspan`, and `colspan`, paired with deterministic text-layer alignment that prevents dropped words in multi-line cells.
  - **LaTeX Block Formulas:** Uses **CodeFormulaV2** to transcribe display equations into `$$ ... $$` blocks, with fast text-layer fallback (`--sin-formulas`).
  - **Local OCR (`RapidOCR` PP-OCRv6):** Automatically detects scanned pages or untagged font glyphs (missing `ToUnicode` maps) and transcribes them locally on CPU covering English, Spanish, Portuguese, and Latin scripts.
- **Deterministic Post-Processing:**
  - Automatic straightening of rotated/landscape pages (`/Rotate` or vertical text tables).
  - Multi-column reading-order reconstruction with full-width spanning blocks.
  - Smart figure cropping at 200 dpi (`.jpg`) with automatic caption exclusion and filtering of publisher logos, header strips, and watermarks.
  - Removal of repeated running headers, footers, line numbers, and invisible publisher tags.
- **Built-in Quality Verifier (`pdf2md-verificar`):**
  - Audits word coverage against the source PDF, checks figure integrity, and generates structured reports (`reporte.json`, `resumen.csv`, `alertas.md`).

---

## Hardware & Storage Requirements

### Disk Space

| Component | Approximate Size | Location / Notes |
|---|---|---|
| Virtual environment (`.venv`) | **~1.20 GB** | ~255 packages (PyMuPDF, Docling, CPU-only PyTorch, Transformers, RapidOCR) |
| Package download cache (`uv`) | **~3.30 GB** | Temporary during installation; can be freed with `uv cache clean` |
| Local neural models (`~/.cache/docling/models`) | **~1.33 GB** | `CodeFormulaV2` (~610 MB), `TableFormer` (~342 MB), `Layout Heron` (~327 MB), `RapidOCR PP-OCRv6` (~53 MB) |
| Generated output | **~0.5 MB / PDF** | Markdown file (`30–120 KB`) + extracted 200 dpi `.jpg` figures (`100 KB – 2 MB`) |
| **Total Recommended Free Space** | **6 GB (install) / 3 GB (steady state)** | SSD strongly recommended |

### CPU & RAM Requirements

| Resource | Minimum | Recommended |
|---|---|---|
| **Operating System** | Windows 10/11 (64-bit), Linux (x86_64 / ARM64), macOS 13+ | Windows 11 / Linux x86_64 or Apple Silicon |
| **Python** | Python `3.12.x` (`>=3.12,<3.13`) | Python `3.12.10+` |
| **RAM** | **8 GB** (1 process, `--hilos 4`) | **16 GB+** (~2 GB RAM per active worker process) |
| **CPU** | 4 cores / 8 threads (AVX2 support) | 8+ cores / 16+ threads |
| **GPU** | **Not required** (runs 100% on CPU) | Not required |

### Measured Throughput (CPU-Only Reference)

Measured on a 10-core / 20-thread CPU (AMD Ryzen AI 9 365, 32 GB RAM):
- **Standard 10–15 page article (tables + figures, few formulas):** `~25–60 s` per PDF (`~3–4 s / page`).
- **Fast mode (`--sin-formulas`):** `~1.5–2.5 s / page` (`~10×` faster on equation-heavy papers).
- **Formula-heavy article (with `CodeFormulaV2` enabled):** `~3–5 min` per PDF (`5–30 s` per display formula on CPU).
- **Parallel batch (`--parte 1/2` and `--parte 2/2` with `--hilos 8`):** `~3.5 PDFs / minute`.

---

## Quick Start

### 1. Install `uv` and Clone the Repository

```bash
git clone https://github.com/hvaquiro/pdf2md-local.git
cd pdf2md-local
uv sync --locked
```

> **Alternative (`pip`):** Create a Python 3.12 virtual environment and run `pip install -r requirements.txt && pip install -e .`.

### 2. Download Local Models (One-Time Setup, ~1.33 GB)

```bash
uv run pdf2md-modelos
```

This downloads all required **Docling** (`layout`, `tableformer`, `code_formula`) and **RapidOCR** (`PP-OCRv6` Latin) weights into `~/.cache/docling/models/`. After this step, `pdf2md` works completely offline.

### 3. Convert a Single PDF or a Folder of PDFs

```bash
# Convert a single PDF file
uv run pdf2md --origen path/to/article.pdf --destino archivos-md

# Convert all PDFs inside a directory (default: archivos-pdf -> archivos-md)
uv run pdf2md --origen archivos-pdf --destino archivos-md

# Fast mode (skip neural LaTeX formula model, use PDF text layer)
uv run pdf2md --origen archivos-pdf --destino archivos-md --sin-formulas
```

### 4. Verify Extraction Quality

```bash
uv run pdf2md-verificar --origen archivos-pdf --destino archivos-md
```

Generates `<destino>/_verificacion/reporte.md` and per-document `<doc>.json` reports, flagging any document with `< 97%` word coverage or missing links.

---

## Parallel Batch Processing

For large batches on multi-core machines with `16 GB+` RAM, split the workload across 2 independent processes:

```bash
# Terminal 1 (first half)
uv run pdf2md --origen archivos-pdf --destino archivos-md --parte 1/2 --hilos 8

# Terminal 2 (second half)
uv run pdf2md --origen archivos-pdf --destino archivos-md --parte 2/2 --hilos 8
```

Already converted PDFs are automatically skipped on resume unless `--forzar` is passed.

---

## Documentation Index (in Spanish)

Detailed guides are available in [`README.es.md`](README.es.md) and the [`docs/`](docs/) directory:

- [`docs/requisitos.md`](docs/requisitos.md) — Detailed disk, RAM, CPU, and OS requirements & benchmarks.
- [`docs/instalacion.md`](docs/instalacion.md) — Step-by-step installation with `uv` or `pip`/`venv`, offline model caching, and long-path setup on Windows.
- [`docs/uso.md`](docs/uso.md) — Full CLI reference (`pdf2md`, `pdf2md-verificar`, `pdf2md-modelos`), single-file vs. batch conversion, and parallel execution.
- [`docs/formato-salida.md`](docs/formato-salida.md) — Output Markdown conventions (`<!-- PageBreak -->`, HTML tables, figure paths, sub/superscripts, LaTeX blocks).
- [`docs/arquitectura.md`](docs/arquitectura.md) — Hybrid pipeline architecture and catalog of deterministic corrections.
- [`docs/verificacion.md`](docs/verificacion.md) — How coverage metrics work and how to interpret `_verificacion/reporte.md`.
- [`docs/limitaciones.md`](docs/limitaciones.md) — Known edge cases (vectorized text without character layer, complex multi-page tables) and workarounds.
- [`docs/solucion-de-problemas.md`](docs/solucion-de-problemas.md) — Troubleshooting guide (DNS model downloads, memory limits, rotated tables).

---

## Running Tests

```bash
# Fast unit test suite (~140 tests, runs in ~15s without model weights)
uv run pytest -q

# Model & OCR tests (requires `uv run pdf2md-modelos`)
uv run pytest -m "modelos" -v

# Full end-to-end integration test on synthetic multi-page PDF
uv run pytest -m "slow" -v
```

---

## License

Copyright (C) 2026 **hvaquiro**.

Distributed under the **GNU Affero General Public License v3.0 or later (`AGPL-3.0-or-later`)** — see [`LICENSE`](LICENSE) and [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) for details.

