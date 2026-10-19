#!/usr/bin/env python3
"""Convierte archivos PDF a Markdown de alta fidelidad de forma local (CPU).

Uso:
    pdf2md [--origen RUTA] [--destino RUTA] [--solo FRAG] [--forzar] [--paginas A-B]
           [--sin-formulas] [--dpi 200] [--hilos N] [--ocr] [--modelos RUTA]
           [--parte N/M] [--lista ARCHIVO]

Salida: <destino>/<doc>.md y <destino>/figures/<doc>/<página>.<índice>.jpg.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

import pymupdf as fitz

from pdf2md.docling_adaptador import OpcionesConversion, construir_convertidor, convertir
from pdf2md.md_render import render_documento
from pdf2md.pdf_texto import (
    abrir_con_unicode,
    enderezar_apaisadas,
    paginas_escaneadas,
    tiene_capa_texto,
)

SRC_DIR = Path("archivos-pdf")
DST_DIR = Path("archivos-md")


def _parsear_paginas(valor: str | None) -> tuple[int, int] | None:
    if not valor:
        return None
    a, b = valor.split("-")
    return int(a), int(b)


def _seleccionar_pdfs(origen: Path, solo: str | None = None, lista: Path | None = None) -> list[Path]:
    """PDF de `origen` (carpeta o archivo único) filtrados por `solo`. Con `lista` (un nombre por
    línea, con o sin .pdf; `#` comenta) se toman solo los listados y en el orden de la lista; los
    que no están en la carpeta se avisan por stderr y se saltan."""
    if origen.is_file():
        if origen.suffix.lower() != ".pdf":
            return []
        if solo and solo.lower() not in origen.name.lower():
            return []
        return [origen]
    pdfs = sorted(p for p in origen.glob("*.pdf") if not solo or solo.lower() in p.name.lower())
    if lista is None:
        return pdfs
    por_nombre = {p.name.lower(): p for p in pdfs}
    elegidos: list[Path] = []
    for linea in lista.read_text(encoding="utf-8").splitlines():
        nombre = linea.strip()
        if not nombre or nombre.startswith("#"):
            continue
        clave = nombre.lower() if nombre.lower().endswith(".pdf") else f"{nombre.lower()}.pdf"
        if clave in por_nombre:
            if por_nombre[clave] not in elegidos:
                elegidos.append(por_nombre[clave])
        elif not solo or solo.lower() in clave:
            print(f"[aviso] {nombre}: está en la lista pero no en {origen}", file=sys.stderr)
    return elegidos


def _reintentar(accion, intentos: int = 6, espera: float = 0.5):
    """Carpetas sincronizadas o un antivirus pueden bloquear a ratos los archivos recién escritos
    (WinError 5 / 32): reintentar."""
    for i in range(intentos):
        try:
            return accion()
        except PermissionError:
            if i == intentos - 1:
                raise
            time.sleep(espera * (i + 1))


def _escribir_atomico(destino: Path, contenido: str) -> None:
    tmp = destino.with_suffix(destino.suffix + ".tmp")
    tmp.write_text(contenido, encoding="utf-8", newline="\n")
    _reintentar(lambda: os.replace(tmp, destino))


def _limpiar_directorio(directorio: Path) -> list[str]:
    """Borra los archivos de la carpeta de figuras uno a uno (con reintentos) y la carpeta si
    queda vacía. Devuelve los nombres que no se pudieron borrar; nunca aborta la conversión."""
    fallos: list[str] = []
    if not directorio.exists():
        return fallos
    for f in sorted(directorio.rglob("*")):
        if f.is_file():
            try:
                _reintentar(f.unlink)
            except PermissionError:
                fallos.append(f.name)
    try:
        _reintentar(lambda: shutil.rmtree(directorio))
    except (PermissionError, OSError):
        pass
    return fallos


def convertir_uno(pdf: Path, args, convertidor) -> dict:
    nombre = pdf.stem
    sufijo = f".p{args.paginas}" if args.paginas else ""
    dst_dir = args.destino
    destino = dst_dir / f"{nombre}{sufijo}.md"
    dir_fig = dst_dir / "figures" / nombre
    if (not args.forzar and not args.paginas and destino.exists()
            and destino.stat().st_mtime >= pdf.stat().st_mtime):
        return {"omitido": "al dia (usar --forzar para reconvertir)"}
    with fitz.open(str(pdf)) as fdoc:
        if fdoc.is_encrypted:
            raise RuntimeError("PDF cifrado; quitar la contraseña antes de convertir")
        ocr = args.ocr or not tiene_capa_texto(fdoc)
        imagen_sola = [] if ocr else paginas_escaneadas(fdoc)

    with tempfile.TemporaryDirectory(prefix="pdf2md-") as tmp_dir:
        tmp_root = Path(tmp_dir)
        # Glifos de fuentes de símbolos sin Unicode («−20 °C» salía «20 C»): se lee una copia con el
        # ToUnicode reparado; no cambia el dibujo de las páginas
        fuente = pdf
        con_unicode = tmp_root / f"{nombre}.unicode.pdf"
        doc_u, reparadas = abrir_con_unicode(pdf)
        with doc_u:
            if reparadas:
                doc_u.save(str(con_unicode), deflate=True)
                fuente = con_unicode
                print(f"  [aviso] ToUnicode reparado en {reparadas} fuente(s) de símbolos")
        # Tablas giradas 90°: Docling y PyMuPDF leen una copia con esas páginas en horizontal
        enderezado = tmp_root / f"{nombre}.enderezado.pdf"
        apaisadas = enderezar_apaisadas(fuente, enderezado)
        if apaisadas:
            print(f"  [aviso] páginas apaisadas enderezadas: {', '.join(map(str, apaisadas))}")
        op = OpcionesConversion(dpi=args.dpi, formulas=not args.sin_formulas, ocr=ocr, hilos=args.hilos,
                                paginas=_parsear_paginas(args.paginas), modelos=args.modelos,
                                enderezadas=tuple(apaisadas))
        if ocr and not args.ocr:
            print(f"  [aviso] {pdf.name}: sin capa de texto en la mayoría de las páginas -> OCR activado")
        elif imagen_sola:
            print(f"  [aviso] {pdf.name}: páginas de imagen sin texto (sin OCR): {', '.join(map(str, imagen_sola))}")
        if convertidor is None or ocr:
            convertidor = construir_convertidor(op)
        if not args.paginas:
            for f in _limpiar_directorio(dir_fig):
                print(f"  [aviso] no se pudo borrar la figura anterior {f}; se sobrescribirá")
        res = convertir(enderezado if apaisadas else fuente, nombre, dir_fig, op, convertidor)

    dst_dir.mkdir(parents=True, exist_ok=True)
    _escribir_atomico(destino, render_documento(res.paginas))
    for aviso in res.avisos:
        print(f"  [aviso] {aviso}")
    return res.stats


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--solo", help="procesar solo los PDF cuyo nombre contenga este fragmento")
    ap.add_argument("--forzar", action="store_true", help="reconvertir aunque el .md esté al día")
    ap.add_argument("--paginas", help="rango A-B solo para depuración; la salida lleva sufijo .pA-B")
    ap.add_argument("--sin-formulas", action="store_true", help="desactiva el modelo de fórmulas (más rápido)")
    ap.add_argument("--dpi", type=int, default=200, help="resolución de los recortes de figuras")
    ap.add_argument("--hilos", type=int, default=max(1, (os.cpu_count() or 4) - 4))
    ap.add_argument("--ocr", action="store_true", help="forzar OCR (por defecto solo si falta capa de texto)")
    ap.add_argument("--origen", type=Path, default=SRC_DIR,
                    help="carpeta con los PDF o ruta a un archivo .pdf (por defecto archivos-pdf)")
    ap.add_argument("--destino", type=Path, default=DST_DIR, help="carpeta de salida (por defecto archivos-md)")
    ap.add_argument("--parte", help="N/M: procesa solo la parte N de M de los PDF pendientes (para repartir el lote entre procesos)")
    ap.add_argument("--lista", type=Path, default=None,
                    help="archivo de texto con los PDF a procesar, uno por línea, en ese orden")
    ap.add_argument("--modelos", type=Path, default=None,
                    help="carpeta con los modelos de Docling (por defecto DOCLING_ARTIFACTS_PATH o ~/.cache/docling/models)")
    args = ap.parse_args()

    origen = args.origen
    if not origen.exists():
        print(f"No existe {origen}", file=sys.stderr)
        return 1
    pdfs = _seleccionar_pdfs(origen, args.solo, args.lista)
    if args.parte:
        n, m = (int(x) for x in args.parte.split("/"))
        if not args.forzar:
            pdfs = [p for p in pdfs if not (args.destino / f"{p.stem}.md").exists()
                    or (args.destino / f"{p.stem}.md").stat().st_mtime < p.stat().st_mtime]
        pdfs = pdfs[n - 1::m]
    if not pdfs:
        print("No hay PDF que procesar", file=sys.stderr)
        return 1
    convertidor = None
    ok = True
    t0 = time.time()
    for pdf in pdfs:
        print(f"[..] {pdf.name}", flush=True)
        try:
            if convertidor is None:
                convertidor = construir_convertidor(
                    OpcionesConversion(dpi=args.dpi, formulas=not args.sin_formulas, hilos=args.hilos,
                                       modelos=args.modelos))
            stats = convertir_uno(pdf, args, convertidor)
        except Exception as exc:  # noqa: BLE001
            ok = False
            msg = str(exc)
            if any(k in msg.lower() for k in ("huggingface", "connection", "http", "download")):
                msg += "\n  Sugerencia: ejecuta 'pdf2md-modelos' y reintenta"
            print(f"[ERROR] {pdf.name}: {msg}", file=sys.stderr, flush=True)
            continue
        print(f"[ok] {pdf.name} {stats}", flush=True)
    print(f"Total: {len(pdfs)} PDF en {time.time() - t0:.0f} s")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

