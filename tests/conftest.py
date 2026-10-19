"""Configuración y fixtures compartidas para las pruebas de pdf2md."""
from __future__ import annotations

from pathlib import Path

import pymupdf as fitz
import pytest


@pytest.fixture
def pdf_articulo_sintetico(tmp_path: Path) -> Path:
    """Genera un PDF sintético de 3 páginas con título, secciones numeradas, párrafos,
    enlace URI, una figura embebida y encabezados/pies de página."""
    doc = fitz.open()

    # Página 1: título, autores con enlace, sección 1 y figura
    p1 = doc.new_page(width=595, height=842)
    p1.insert_text((50, 35), "Journal of Synthetic Testing 2026", fontsize=8)
    p1.insert_text(
        (50, 85),
        "A comprehensive synthetic study on local document extraction and layout analysis",
        fontsize=15,
    )
    p1.insert_text((50, 115), "Jane Doe, John Smith", fontsize=10)
    p1.insert_link({
        "kind": fitz.LINK_URI,
        "from": fitz.Rect(50, 105, 100, 120),
        "uri": "https://orcid.org/0000-0000-0000-0001",
    })
    p1.insert_text((50, 155), "1. Introduction", fontsize=12)
    p1.insert_text(
        (50, 180),
        "Scientific articles require accurate extraction of headings, paragraphs, links,\n"
        "tables, and figures while preserving special characters such as 25 °C and m².",
        fontsize=10,
    )
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 120, 80), False)
    pix.set_rect(pix.irect, (235, 240, 250))
    for y in range(15, 70, 15):
        pix.set_rect(fitz.IRect(15, y, 105, y + 6), (40, 80, 160))
    p1.insert_image(fitz.Rect(50, 230, 250, 350), pixmap=pix)
    p1.insert_text((50, 370), "Figure 1. Synthetic experimental profile.", fontsize=9)
    p1.insert_text((290, 810), "1", fontsize=9)

    # Página 2: sección 2 y subsección 2.1
    p2 = doc.new_page(width=595, height=842)
    p2.insert_text((50, 35), "Journal of Synthetic Testing 2026", fontsize=8)
    p2.insert_text((50, 80), "2. Materials and methods", fontsize=12)
    p2.insert_text(
        (50, 105),
        "Samples were conditioned at 20 °C prior to analysis. More details are available at\n"
        "https://example.org/protocol for reproducibility.",
        fontsize=10,
    )
    p2.insert_link({
        "kind": fitz.LINK_URI,
        "from": fitz.Rect(50, 112, 195, 128),
        "uri": "https://example.org/protocol",
    })
    p2.insert_text((50, 155), "2.1. Data acquisition", fontsize=11)
    p2.insert_text(
        (50, 180),
        "Measurements were recorded in triplicate across all experimental treatments.",
        fontsize=10,
    )
    p2.insert_text((290, 810), "2", fontsize=9)

    # Página 3: sección 3 y referencias
    p3 = doc.new_page(width=595, height=842)
    p3.insert_text((50, 35), "Journal of Synthetic Testing 2026", fontsize=8)
    p3.insert_text((50, 80), "3. Conclusions", fontsize=12)
    p3.insert_text(
        (50, 105),
        "The local pipeline reproduces the document structure without external cloud services.",
        fontsize=10,
    )
    p3.insert_text((50, 150), "References", fontsize=12)
    p3.insert_text((50, 175), "[1] Doe J. Local extraction methods. J Synth Test 2025;10:1-9.", fontsize=9)
    p3.insert_text((290, 810), "3", fontsize=9)

    ruta = tmp_path / "articulo_sintetico.pdf"
    doc.save(str(ruta))
    doc.close()
    return ruta

