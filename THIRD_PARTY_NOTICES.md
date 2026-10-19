# Avisos de software y modelos de terceros (Third-Party Notices)

**pdf2md-local** se distribuye bajo la licencia **GNU Affero General Public License v3.0 or later (`AGPL-3.0-or-later`)** debido a su dependencia directa de **PyMuPDF**.

A continuación se relacionan las principales bibliotecas y modelos preentrenados utilizados por este proyecto y sus respectivas licencias:

## Bibliotecas principales de Python

| Componente | Licencia | Proyecto / Autor |
|---|---|---|
| [PyMuPDF (`fitz`)](https://github.com/pymupdf/PyMuPDF) | GNU AGPL-3.0-or-later (o licencia comercial de Artifex) | Artifex Software, Inc. |
| [Docling](https://github.com/docling-project/docling) | MIT License | IBM Research (`docling-project`) |
| [Docling Core / IBM Models](https://github.com/docling-project/docling-ibm-models) | MIT License | IBM Research |
| [PyTorch (`torch`, `torchvision`)](https://github.com/pytorch/pytorch) | BSD-3-Clause License | Meta Platforms, Inc. y colaboradores |
| [Hugging Face Transformers](https://github.com/huggingface/transformers) | Apache License 2.0 | Hugging Face, Inc. |
| [RapidOCR](https://github.com/RapidAI/RapidOCR) | Apache License 2.0 | RapidAI |
| [Pillow (`PIL`)](https://github.com/python-pillow/Pillow) | MIT-CMU License | Jeffrey A. Clark y colaboradores |
| [BeautifulSoup4 (`bs4`)](https://www.crummy.com/software/BeautifulSoup/) | MIT License | Leonard Richardson |
| [pytest](https://github.com/pytest-dev/pytest) | MIT License | Holger Krekel y equipo de pytest |

## Modelos preentrenados (descargados localmente por `pdf2md-modelos`)

Los pesos neuronales no se almacenan dentro de este repositorio Git; se descargan bajo demanda en la caché local del usuario (`~/.cache/docling/models/`):

| Modelo | Uso en `pdf2md-local` | Licencia de los pesos | Origen |
|---|---|---|---|
| `docling-layout-heron` / `docling-layout-heron-onnx` | Detección de bloques de diseño editorial (títulos, texto, figuras, tablas, fórmulas) | Apache License 2.0 | Hugging Face (`docling-project`) |
| `docling-models` (`TableFormer`) | Reconocimiento de estructura de filas, columnas y celdas de tablas | Apache License 2.0 | Hugging Face (`docling-project`) |
| `CodeFormulaV2` | Transcripción de ecuaciones y fórmulas matemáticas en bloque a LaTeX | Apache License 2.0 | Hugging Face (`docling-project`) |
| `PP-OCRv6` / `PP-OCRv4` (`PP-OCRv6_det_small.pth`, `PP-OCRv6_rec_small.pth`, `ch_ptocr_mobile_v2.0_cls_mobile.pth`, `latin_PP-OCRv3_rec_mobile.pth`) | Detección y reconocimiento óptico de caracteres (OCR) en páginas escaneadas o glifos sin Unicode | Apache License 2.0 | PaddleOCR / ModelScope (`RapidAI`) |

