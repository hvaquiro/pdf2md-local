from pathlib import Path

import pytest

from pdf2md.docling_adaptador import OpcionesConversion, convertir
from pdf2md.md_render import render_documento


@pytest.mark.slow
@pytest.mark.modelos
def test_convertir_tres_paginas(pdf_articulo_sintetico: Path, tmp_path: Path):
    op = OpcionesConversion(dpi=150, formulas=False, paginas=(1, 3))
    res = convertir(pdf_articulo_sintetico, "sintetico", tmp_path / "figures" / "sintetico", op)
    assert [p.numero for p in res.paginas] == [1, 2, 3]
    md = render_documento(res.paginas)
    assert md.count("<!-- PageBreak -->") == 2
    assert "## " in md                      # al menos una sección
    assert "](https://" in md               # enlaces inyectados
    figuras = list((tmp_path / "figures" / "sintetico").glob("*.jpg"))
    assert all(f"figures/sintetico/{f.name}" in md for f in figuras)
    assert res.stats["paginas"] == 3 and res.stats["sin_clasificar"] <= 10

