from pathlib import Path

from pdf2md.cli import (
    _escribir_atomico,
    _limpiar_directorio,
    _parsear_paginas,
    _seleccionar_pdfs,
)


def test_seleccionar_pdfs_respeta_orden_de_la_lista_y_archivo_unico(tmp_path: Path, capsys):
    for n in ("a-art.pdf", "b-inst.pdf", "c-art.pdf"):
        (tmp_path / n).write_bytes(b"%PDF")
    assert [p.name for p in _seleccionar_pdfs(tmp_path)] == ["a-art.pdf", "b-inst.pdf", "c-art.pdf"]
    assert [p.name for p in _seleccionar_pdfs(tmp_path, solo="ART")] == ["a-art.pdf", "c-art.pdf"]
    assert [p.name for p in _seleccionar_pdfs(tmp_path / "b-inst.pdf")] == ["b-inst.pdf"]
    assert _seleccionar_pdfs(tmp_path / "b-inst.pdf", solo="art") == []
    lista = tmp_path / "orden.txt"
    lista.write_text("# artículos primero\nc-art\n\na-art.pdf\nfalta.pdf\nb-inst.pdf\n", encoding="utf-8")
    assert [p.name for p in _seleccionar_pdfs(tmp_path, lista=lista)] == ["c-art.pdf", "a-art.pdf", "b-inst.pdf"]
    assert "falta.pdf" in capsys.readouterr().err
    assert [p.name for p in _seleccionar_pdfs(tmp_path, solo="inst", lista=lista)] == ["b-inst.pdf"]


def test_limpiar_directorio_borra_archivos_y_carpeta(tmp_path: Path):
    d = tmp_path / "figs"
    d.mkdir()
    (d / "1.1.jpg").write_bytes(b"x")
    (d / "2.1.jpg").write_bytes(b"y")
    assert _limpiar_directorio(d) == []
    assert not d.exists()
    assert _limpiar_directorio(tmp_path / "no-existe") == []


def test_escribir_atomico_y_paginas(tmp_path: Path):
    destino = tmp_path / "a.md"
    _escribir_atomico(destino, "hola\n")
    _escribir_atomico(destino, "adiós\n")
    assert destino.read_text(encoding="utf-8") == "adiós\n" and not destino.with_suffix(".md.tmp").exists()
    assert _parsear_paginas("2-5") == (2, 5) and _parsear_paginas(None) is None

