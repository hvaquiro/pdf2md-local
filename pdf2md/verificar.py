#!/usr/bin/env python3
"""Verifica la fidelidad de los archivos Markdown generados contra su PDF de origen.

Uso:
    pdf2md-verificar [--origen RUTA] [--destino RUTA] [--informe RUTA] [--solo FRAG]

Salida: <informe>/<doc>.json y <informe>/reporte.md (por defecto <destino>/_verificacion/).
Código de salida 1 si hay alertas (cobertura < 97 % o enlaces ausentes); los marcadores de
diagnóstico son notas informativas.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

import pymupdf as fitz

from pdf2md.md_render import _LIGADURAS, normalizar_glifos
from pdf2md.pdf_texto import abrir_con_unicode, etiquetas_invisibles, textos_de_marcas

DIR_MD = Path("archivos-md")
DIR_PDF = Path("archivos-pdf")
UMBRALES = {"cobertura_min": 97.0}

_RE_MARCADOR = re.compile(r"<!--.*?-->", re.S)
_RE_MARCADOR_TEXTO = re.compile(r"<!-- Page(?:Header|Footer|Number): (.*?) -->", re.S)
# Destino con paréntesis equilibrados: p. ej. URLs de refhub con «S0960-3085(17)30154-2»
_DESTINO = r"(?:[^()\s]|\([^()\s]*\))*"
_RE_IMG = re.compile(r"!\[([^\]]*)\]\(" + _DESTINO + r"\)")
_RE_LINK = re.compile(r"\[([^\]]*)\]\((" + _DESTINO + r")\)")
_RE_TAG = re.compile(r"</?[a-zA-Z][^<>]{0,80}>")  # solo etiquetas reales: "p < 0.05 … >" no es una etiqueta
_RE_URL = re.compile(r"\]\((https?://" + _DESTINO + r")\)")


def normalizar_md(md: str) -> str:
    t = _RE_MARCADOR_TEXTO.sub(r" \1 ", md)  # el texto de encabezados y pies cuenta como contenido
    t = _RE_MARCADOR.sub(" ", t)
    t = _RE_IMG.sub(r" \1 ", t)
    t = _RE_LINK.sub(r"\1", t)
    t = _RE_TAG.sub(" ", t)
    t = re.sub(r"^#{1,6}\s+", "", t, flags=re.M)
    return re.sub(r"\s+", " ", t).strip()


def tokens(texto: str) -> list[str]:
    # NFKC pliega superíndices y subíndices Unicode (Ca²⁺ -> Ca2+) para comparar con el texto del PDF
    texto = normalizar_glifos(texto)
    # Acento que el PDF dibuja como glifo aparte («Gonz´alez», antes o después de su letra) y que el
    # MD compone («González»): se compara sin diacríticos en los dos lados
    texto = re.sub(r"(?<=\w)[´`ˆ¨˜¸ˇ˚˘˙¯˝]|[´`ˆ¨˜¸ˇ˚˘˙¯˝](?=\w)", "", texto)
    texto = "".join(c for c in unicodedata.normalize("NFD", texto) if not unicodedata.combining(c))
    texto = unicodedata.normalize("NFKC", texto).lower().replace("‐", " ").replace("-", " ")
    return [w for w in re.findall(r"[^\W_]+", texto) if len(w) >= 2 or w.isdigit()]


def _partir(palabra: str, vocabulario, media_minima: float = 2.5) -> list[str] | None:
    """Trozos de `palabra` si se parte en ≥ 2 palabras del vocabulario con una longitud media
    razonable (mínimo de trozos por programación dinámica; la media evita aceptar cualquier cosa
    a base de abreviaturas de dos letras); None si no."""
    n = len(palabra)
    trozos = [0] + [n + 1] * n  # trozos[i] = mínimo de palabras que cubren palabra[:i]
    corte = [0] * (n + 1)
    for i in range(1, n + 1):
        for j in range(max(0, i - 25), i):
            if trozos[j] < trozos[i] - 1 and palabra[j:i] in vocabulario:
                trozos[i], corte[i] = trozos[j] + 1, j
    if not (2 <= trozos[n] <= n and n / trozos[n] >= media_minima):
        return None
    piezas, i = [], n
    while i > 0:
        piezas.append(palabra[corte[i]:i])
        i = corte[i]
    return piezas[::-1]


def cobertura(tokens_pdf: list[str], tokens_md: list[str]) -> tuple[float, list[tuple[str, int]]]:
    """% de tokens del PDF (con multiplicidad) presentes en el MD, y los 20 más ausentes."""
    cp, cm = Counter(tokens_pdf), Counter(tokens_md)
    if not cp:
        return 100.0, []
    # Palabras que la capa de texto trae pegadas ("awisthewater") y el MD separa: no son pérdidas.
    vocabulario = set(cm) | {"a"}  # tokens() descarta las palabras de una letra
    for w in [w for w in cp if w not in cm and len(w) >= 5 and _partir(w, vocabulario)]:
        cm[w] = cp[w]
    # Y al revés: el PDF da el exponente como token aparte ("hp" "2") y el MD lo une (hp² -> "hp2").
    for w in [w for w in cm if w not in cp and len(w) <= 8]:
        for pieza in _partir(w, cp, media_minima=1.5) or []:
            cm[pieza] += cm[w]
    encontrados = sum(min(n, cm.get(w, 0)) for w, n in cp.items())
    faltantes = sorted(((w, n - cm.get(w, 0)) for w, n in cp.items() if n > cm.get(w, 0)),
                       key=lambda x: (-x[1], x[0]))[:20]
    return round(100.0 * encontrados / sum(cp.values()), 2), faltantes


def urls_md(md: str) -> set[str]:
    return {u.rstrip(".,;") for u in _RE_URL.findall(md)}


def urls_ausentes(urls_pdf: set[str], md: str) -> list[str]:
    """Una URL del PDF está presente si aparece literalmente como destino "](url)" en el MD
    (las URL con paréntesis, p. ej. DOIs antiguos, no se pueden capturar con una expresión regular)."""
    return sorted(u for u in urls_pdf if f"]({u})" not in md and f"]({u}." not in md)


def verificar_documento(nombre: str, dir_md: Path, dir_pdf: Path) -> dict:
    md = (dir_md / f"{nombre}.md").read_text(encoding="utf-8")
    pdf_path = dir_pdf if dir_pdf.is_file() else (dir_pdf / f"{nombre}.pdf")
    # Mismo Unicode que ve el conversor para los glifos de las fuentes de símbolos
    with abrir_con_unicode(pdf_path)[0] as doc:
        texto_pdf = "\n".join(
            p.get_text("text", flags=fitz.TEXT_PRESERVE_WHITESPACE | fitz.TEXT_MEDIABOX_CLIP) for p in doc
        )
        # Caracteres de uso privado que el flujo elimina por no saber qué son: si son muchos, mirar el
        # contexto y añadirlos a _LIGADURAS de md_render si corresponden a ligaduras.
        privados = sum(1 for p in doc for b in p.get_text("rawdict")["blocks"] for l in b.get("lines", [])
                       for sp in l["spans"] for ch in sp["chars"]
                       if "\ue000" <= ch["c"] <= "\uf8ff" and ch["c"] not in _LIGADURAS)
        marcas = [t for p in doc for t in textos_de_marcas(p)]
        # Etiquetas «TagedP» de Elsevier: invisibles, el flujo las descarta; van pegadas a las vecinas
        etiquetas = sorted({e for p in doc for e in etiquetas_invisibles(p)}, key=len, reverse=True)
        for e in etiquetas:
            texto_pdf = texto_pdf.replace(e, " ")
        urls_pdf = {
            l["uri"].strip().rstrip(".,;") for p in doc for l in p.get_links()
            if l.get("kind") == fitz.LINK_URI and l.get("uri")
        }
    tokens_md = tokens(normalizar_md(md))
    # Los rótulos verticales de marca de agua («Accepted Article») se apartan a propósito.
    tokens_pdf = tokens(texto_pdf)
    for t in tokens(" ".join(marcas)):
        if t in tokens_pdf:
            tokens_pdf.remove(t)
    pct, faltantes = cobertura(tokens_pdf, tokens_md)
    r = {
        "documento": nombre, "cobertura_pct": pct, "palabras_faltantes": faltantes,
        "marcas_de_agua": len(marcas),
        "enlaces_pdf": len(urls_pdf), "enlaces_faltantes": urls_ausentes(urls_pdf, md),
        "figuras": len(list((dir_md / "figures" / nombre).glob("*.jpg"))),
        "tablas": md.count("<table>"), "formulas_bloque": len(re.findall(r"^\$\$", md, re.M)),
        "sin_clasificar": md.count("<!-- SinClasificar -->"),
        "formulas_sin_latex": md.count("<!-- FormulaSinLatex -->"),
        "privados_sin_mapa": privados,
    }
    r["alertas"], r["notas"] = alertas_y_notas(r)
    return r


def alertas_y_notas(r: dict) -> tuple[list[str], list[str]]:
    """(alertas, notas). Alertan (código de salida 1) la cobertura y los enlaces. Los marcadores de
    diagnóstico son informativos."""
    alertas, notas = [], []
    if r["cobertura_pct"] < UMBRALES["cobertura_min"]:
        alertas.append(f"cobertura {r['cobertura_pct']}% < {UMBRALES['cobertura_min']}%")
    if r["enlaces_faltantes"]:
        alertas.append(f"{len(r['enlaces_faltantes'])} enlaces del PDF ausentes")
    if r["sin_clasificar"] or r["formulas_sin_latex"]:
        notas.append(f"SinClasificar={r['sin_clasificar']} FormulaSinLatex={r['formulas_sin_latex']}")
    if r.get("marcas_de_agua"):
        notas.append(f"{r['marcas_de_agua']} rótulos de marca de agua apartados")
    if r.get("privados_sin_mapa"):
        notas.append(f"{r['privados_sin_mapa']} caracteres de uso privado sin mapa (eliminados)")
    return alertas, notas


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--solo", help="verificar solo los .md cuyo nombre contenga este fragmento")
    ap.add_argument("--origen", type=Path, default=DIR_PDF,
                    help="carpeta con los PDF o ruta a un archivo .pdf (por defecto archivos-pdf)")
    ap.add_argument("--destino", type=Path, default=DIR_MD, help="carpeta con los .md (por defecto archivos-md)")
    ap.add_argument("--informe", type=Path, default=None,
                    help="carpeta del informe (por defecto <destino>/_verificacion)")
    args = ap.parse_args()
    dir_md, dir_pdf = args.destino, args.origen
    dir_out = args.informe or (dir_md / "_verificacion")
    dir_out.mkdir(parents=True, exist_ok=True)
    if dir_pdf.is_file():
        nombres = [dir_pdf.stem] if (dir_md / f"{dir_pdf.stem}.md").exists() else []
    else:
        nombres = sorted(
            p.stem for p in dir_md.glob("*.md")
            if (not args.solo or args.solo.lower() in p.name.lower()) and (dir_pdf / f"{p.stem}.pdf").exists()
        )
    if not nombres:
        print("No hay .md con PDF de origen que verificar", file=sys.stderr)
        return 1
    filas, hay_alertas = [], False
    for n in nombres:
        r = verificar_documento(n, dir_md, dir_pdf)
        (dir_out / f"{n}.json").write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
        hay_alertas |= bool(r["alertas"])
        filas.append(
            f"| {n} | {r['cobertura_pct']} | {r['figuras']} | {r['tablas']} | {r['formulas_bloque']} | "
            f"{len(r['enlaces_faltantes'])}/{r['enlaces_pdf']} | {r['sin_clasificar']} | "
            f"{r['formulas_sin_latex']} | {'; '.join(r['alertas']) or 'ok'} | {'; '.join(r['notas']) or '-'} |"
        )
    reporte = (
        "| Documento | Cobertura % | Figuras | Tablas | $$ | "
        "Enlaces faltantes/total | SinClasif. | FórmSinLatex | Alertas | Notas (informativas) |\n"
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n" + "\n".join(filas) + "\n"
    )
    (dir_out / "reporte.md").write_text(reporte, encoding="utf-8")
    print(reporte)
    return 1 if hay_alertas else 0


if __name__ == "__main__":
    raise SystemExit(main())

