"""Capa de texto del PDF (PyMuPDF): caracteres con posición, super/subíndices y enlaces.

Docling decide *qué* es cada región de la página; este módulo dice *exactamente qué dice* esa
región leyendo la capa de texto del PDF (grados, superíndices, griegas, acentos y enlaces).
Todos los bbox están en puntos, origen superior-izquierdo: (x0, y0, x1, y1).

Rarezas reales de los PDF científicos (Elsevier, MDPI, Wiley, RSC, Springer) que se tratan aquí:
- MuPDF expande las ligaduras (ﬁ → f + i) dejando la 'i' con ancho cero: no se puede ordenar
  por x0, hay que respetar el orden del flujo dentro de cada línea cruda (segmento).
- Un superíndice puede venir en su propia línea cruda: se fusiona con la línea visual vecina
  solo si está horizontalmente pegado (un numerador apilado sobre un denominador no se fusiona).
- Los acentos van como glifos sueltos (´ ` ¨ ¸ …) superpuestos a la base, antes o después en el
  flujo: se combinan con la letra con la que más se solapan en x.
- Los títulos con tracking amplio salen letra a letra ("A R T I C L E I N F O"): se colapsan
  usando los huecos reales para decidir dónde hay palabra.
"""
from __future__ import annotations

import bisect
import re
import statistics
import unicodedata
from dataclasses import dataclass, field, replace
from pathlib import Path

import pymupdf as fitz

from pdf2md.md_render import a_subindice, a_superindice, normalizar_glifos

# Sin TEXT_PRESERVE_LIGATURES: MuPDF expande ﬁ -> fi, ﬂ -> fl.
_FLAGS = fitz.TEXT_PRESERVE_WHITESPACE | fitz.TEXT_MEDIABOX_CLIP

# Acentos "espaciadores" que estos PDF dibujan como glifo aparte -> marca combinante Unicode.
_ACENTOS = {
    "´": "́", "`": "̀", "ˆ": "̂", "^": "̂", "¨": "̈",
    "˜": "̃", "~": "̃", "¸": "̧", "ˇ": "̌", "˚": "̊",
    "˘": "̆", "˙": "̇", "¯": "̄", "˝": "̋",
}


@dataclass
class Char:
    c: str
    x0: float
    y0: float
    x1: float
    y1: float
    linea: int
    superindice: bool
    subindice: bool
    url: str | None
    consumido: bool = False
    seq: int = 0      # orden en el flujo del PDF
    seg: int = 0      # línea cruda de MuPDF a la que pertenece
    tam: float = 0.0  # tamaño de fuente

    @property
    def centro(self) -> tuple[float, float]:
        return ((self.x0 + self.x1) / 2, (self.y0 + self.y1) / 2)


@dataclass
class PaginaTexto:
    numero: int
    ancho: float
    alto: float
    chars: list[Char]
    urls: list[str]
    enlaces: list[tuple[tuple[float, float, float, float], str]]
    # bbox de los rótulos verticales que pisan el cuerpo (marca de agua); su texto no está en chars
    marcas: list[tuple[float, float, float, float]] = field(default_factory=list)
    # página apaisada enderezada (`enderezar_apaisadas`): Docling desplaza sus cajas hasta 4 pt
    enderezada: bool = False


def _url_en(x: float, y: float, enlaces) -> str | None:
    """URL del enlace más pequeño que contiene el punto: un DOI dentro de una entrada
    bibliográfica enlazada entera debe ganar al enlace grande."""
    mejor, mejor_area = None, float("inf")
    for (x0, y0, x1, y1), uri in enlaces:
        if x0 <= x <= x1 and y0 <= y <= y1:
            area = (x1 - x0) * (y1 - y0)
            if area < mejor_area:
                mejor, mejor_area = uri, area
    return mejor


# Nature (npj) incrusta en el margen, en vertical, esta cadena para forzar el subconjunto de la fuente.
_ARTEFACTOS = {"1234567890():,;"}

# Algunas revistas de Elsevier (Poultry Science, Animal Nutrition…) dejan en la capa de texto las
# etiquetas de maquetación «TagedP», «TagedH1», «TagedEnd» (y en mayúsculas dentro de los títulos)
# como un span propio que no dibuja nada: sin esto salían pegadas a la palabra siguiente.
_RE_ETIQUETA_TAGED = re.compile(r"^(?:Taged[A-Z][A-Za-z0-9]{0,11}|TAGED[A-Z0-9]{1,12})$")


def _es_etiqueta_taged(span: dict) -> bool:
    return bool(_RE_ETIQUETA_TAGED.match("".join(c["c"] for c in span.get("chars", ())).strip()))


def _hueco_con_icono(y0, y1, xa, xb, enlaces) -> bool:
    """True si un enlace (icono ORCID sin texto) ocupa el hueco horizontal [xa, xb] de la línea."""
    return any(ex0 < xb and ex1 > xa and min(y1, ey1) - max(y0, ey0) > 0
               for (ex0, ey0, ex1, ey1), _ in enlaces)


def _marcas_de_agua(raw: dict) -> list[tuple[float, float, float, float]]:
    """Líneas no horizontales cuyo bbox pisa alguna línea horizontal: el rótulo «Accepted
    Article» de Wiley (80 pt, vertical, en el margen) tapa el arranque de cada línea del cuerpo
    y el ítem que Docling le da se tragaba esas letras. Un sello vertical que no toca el texto
    (arXiv) no es marca, ni el eje vertical de una figura aunque toque sus etiquetas."""
    lineas = [l for b in raw["blocks"] if b.get("type") == 0 for l in b["lines"]
              if "".join(c["c"] for s in l["spans"] for c in s.get("chars", ())).strip()]
    horizontales = [l["bbox"] for l in lineas if abs(l["dir"][0] - 1) < 0.01 and abs(l["dir"][1]) < 0.01]
    if not horizontales:
        return []
    cuerpo = statistics.median(s["size"] for l in lineas for s in l["spans"]
                               if abs(l["dir"][0] - 1) < 0.01 and abs(l["dir"][1]) < 0.01)
    marcas = []
    for l in lineas:
        if abs(l["dir"][0] - 1) < 0.01 and abs(l["dir"][1]) < 0.01:
            continue
        # el rótulo mide 30-80 pt; un eje vertical de figura o la tira «Downloaded from» (5-8 pt) no
        if max(s["size"] for s in l["spans"]) < 2 * cuerpo:
            continue
        x0, y0, x1, y1 = l["bbox"]
        if any(min(x1, h[2]) - max(x0, h[0]) > 1 and min(y1, h[3]) - max(y0, h[1]) > 1 for h in horizontales):
            marcas.append((x0, y0, x1, y1))
    return marcas


def textos_de_marcas(page: fitz.Page) -> list[str]:
    """Texto de los rótulos verticales que el flujo aparta (para que el verificador no los cuente)."""
    raw = page.get_text("rawdict", flags=_FLAGS)
    marcas = set(_marcas_de_agua(raw))
    return ["".join(c["c"] for s in l["spans"] for c in s.get("chars", ()))
            for b in raw["blocks"] if b.get("type") == 0 for l in b["lines"] if tuple(l["bbox"]) in marcas]


def etiquetas_invisibles(page: fitz.Page) -> set[str]:
    """Etiquetas «TagedP»/«TagedEnd» de la página que el flujo descarta. El verificador las quita del
    texto del PDF antes de contar palabras: en el modo «text» van pegadas a las vecinas
    («sequencingTagedEnd»)."""
    raw = page.get_text("rawdict", flags=_FLAGS)
    return {"".join(c["c"] for c in s["chars"]).strip()
            for b in raw["blocks"] if b.get("type") == 0 for l in b["lines"] for s in l["spans"]
            if _es_etiqueta_taged(s)}


def _lineas_visuales(raw: dict, enlaces=(), marcas=()) -> list[list]:
    """Fusiona en una línea visual las líneas crudas cuyo rango vertical se solapa > 50 % y que
    están horizontalmente pegadas (hueco entre -0.5 y 1 tamaños de fuente): superíndices sueltos.
    Si en el hueco hay un icono enlazado ("Autor [ORCID]¹, Coautor"), se toleran 2,5 tamaños.
    Devuelve [x0, y0, x1, y1, [(seg_id, spans)]]."""
    visuales: list[list] = []
    seg_id = 0
    for bloque in raw["blocks"]:
        if bloque.get("type") != 0:
            continue
        for linea in bloque["lines"]:
            spans = [s for s in linea["spans"] if s.get("chars") and not _es_etiqueta_taged(s)]
            if not spans or "".join(c["c"] for s in spans for c in s["chars"]).strip() in _ARTEFACTOS:
                continue
            x0, y0, x1, y1 = linea["bbox"]
            if (x0, y0, x1, y1) in marcas:
                continue
            destino = None
            for v in visuales:
                solape = min(y1, v[3]) - max(y0, v[1])
                alto = min(y1 - y0, v[3] - v[1])
                hueco = max(x0 - v[2], v[0] - x1)
                tam = max(s["size"] for _, ss in v[4] for s in ss)
                pegadas = hueco < tam or (hueco < 2.5 * tam and _hueco_con_icono(
                    y0, y1, min(x1, v[2]), max(x0, v[0]), enlaces))
                if alto > 0 and solape / alto > 0.5 and -0.5 * tam <= hueco and pegadas:
                    destino = v
                    break
            if destino is None:
                visuales.append([x0, y0, x1, y1, [(seg_id, spans)]])
            else:
                destino[0], destino[1] = min(destino[0], x0), min(destino[1], y0)
                destino[2], destino[3] = max(destino[2], x1), max(destino[3], y1)
                destino[4].append((seg_id, spans))
            seg_id += 1
    return visuales


def _falta_espacio(a: str, b: str, hueco: float, tam: float) -> bool:
    """En líneas justificadas muy comprimidas (npj, algunas de Elsevier) el hueco entre palabras
    (≈ 0,14 em) no llega al umbral con que MuPDF sintetiza el espacio: "Equation2isacontinuity".
    Entre letras de una palabra el hueco es ≈ 0; > 0,10 em entre dos alfanuméricos (o tras
    puntuación) de la misma fuente es un límite de palabra."""
    if hueco <= 0.10 * tam:
        return False
    return (a.isalnum() and (b.isalnum() or b == "(")) or (a in ".,;:)" and b.isalpha())


# Fuentes matemáticas que codifican = + ( ) en las posiciones de ¼ þ ð Þ (los códigos \x01-\x05 de
# las mismas fuentes cambian de un documento a otro y se resuelven por nombre de glifo en ToUnicode).
# Algunos PDF pegan el prefijo de subconjunto sin «+» («XrdnxnAdvP4C4E74»), por eso se compara el
# final del nombre.
_FUENTES_MATH = ("AdvP4C4E74", "AdvP4C4E3A", "AdvMacMthSyN", "TeX_CM_Bold_Maths_Symbol",
                 "TeX_CM_Maths_Symbols")
_MAPA_MATH = {"¼": "=", "þ": "+", "ð": "(", "Þ": ")"}


def _caracter_de_fuente(c: str, fuente: str) -> str:
    # MuPDF entrega a veces solo la mitad alta del par UTF-16 de una letra matemática (U+1D7xx de
    # MinionMath, «0 μm»): no se puede escribir en UTF-8 ni reconstruir -> U+FFFD
    if "\ud800" <= c <= "\udfff":
        return "\ufffd"
    return _MAPA_MATH.get(c, c) if fuente.split("+")[-1].endswith(_FUENTES_MATH) else c


def _control_sin_tinta(page: fitz.Page, c: str, chars: list[dict], i: int,
                       siguiente: dict | None = None) -> bool:
    """True si `c` (el carácter `i` del span) es un control que no dibuja nada: el tabulador de
    maquetación que Springer (MyriadPro), T&F (STIX) y Frontiers (MuseoSans) ponen como \\x07/\\x08
    ante los títulos. Los de las fuentes matemáticas (\\x01-\\x05 de AdvP4C4E74: ±, ≤…) sí dibujan y
    siguen como U+FFFD. El \\x07 de MyriadPro no avanza: la letra siguiente empieza en su misma x y su
    caja se ve «con tinta» por ella. En algunos capítulos de Elsevier (Palatino) y en J. Oleo Sci.
    esa letra abre el span siguiente (`siguiente`); ahí solo cuenta un control crudo, porque un
    U+FFFD sin avance ante otro span es el acento suelto de Elsevier (AdvP4C4E59), que sí dibuja.
    Recortar la caja por los dos vecinos no sirve porque cuando ± comparte caja con un espacio
    duplicado anterior se perdería."""
    if not (c == "\ufffd" or (c < " " and c not in "\n\t")):
        return False
    bbox = chars[i]["bbox"]
    sig = chars[i + 1] if i + 1 < len(chars) else (siguiente if c < " " else None)
    if sig and sig["c"].isalnum() and abs(sig["bbox"][0] - bbox[0]) < 0.05:
        return True
    return region_en_blanco(page, bbox, dpi=288, margen=0.15)


def _hueco_base(chars: list[dict]) -> float:
    """Hueco típico entre letras consecutivas de un span: ≈ 0 en texto normal y ≈ 1 pt en el texto
    con tracking («journal homepage» de Elsevier). Se descuenta antes de buscar espacios que
    faltan; con menos de 4 pares no hay estadística y vale 0. Cuentan también las letras separadas
    por un espacio que MuPDF sintetizó llenando justo el hueco: en «F I G U R E» (Wiley) casi todos
    los huecos lo llevan, y con solo los pares contiguos no había estadística."""
    huecos = [b["bbox"][0] - a["bbox"][2] for a, b in zip(chars, chars[1:])
              if a["c"].strip() and b["c"].strip()]
    huecos += [c["bbox"][0] - a["bbox"][2] for a, b, c in zip(chars, chars[1:], chars[2:])
               if a["c"].strip() and b["c"] == " " and c["c"].strip()
               and abs(b["bbox"][0] - a["bbox"][2]) < 0.05 and abs(c["bbox"][0] - b["bbox"][2]) < 0.05]
    return max(0.0, statistics.median(huecos)) if len(huecos) >= 4 else 0.0


def _hueco_palabra(chars: list[dict]) -> float | None:
    """Hueco típico entre palabras de una línea: distancia entre las letras que flanquean cada
    espacio que sí trae la capa de texto. En texto justificado todos miden lo mismo, así que un
    espacio que falta debe parecerse a ellos; None si la línea tiene menos de 2 espacios."""
    huecos = [c["bbox"][0] - a["bbox"][2] for a, b, c in zip(chars, chars[1:], chars[2:])
              if b["c"] == " " and a["c"].strip() and c["c"].strip()]
    return statistics.median(huecos) if len(huecos) >= 2 else None


def extraer_pagina(page: fitz.Page, numero: int) -> PaginaTexto:
    enlaces = [
        (tuple(fitz.Rect(l["from"])), l["uri"].strip())
        for l in page.get_links()
        if l.get("kind") == fitz.LINK_URI and l.get("uri")
    ]
    chars: list[Char] = []
    seq = 0
    raw = page.get_text("rawdict", flags=_FLAGS)
    marcas = _marcas_de_agua(raw)
    for linea_id, v in enumerate(_lineas_visuales(raw, enlaces, marcas)):
        spans_all = [s for _, ss in v[4] for s in ss]
        tam_base = max(s["size"] for s in spans_all)
        base_y = max(s["origin"][1] for s in spans_all if s["size"] == tam_base)
        # Documentos de Word justificados dejan huecos de ~0,11 em a mitad de palabra, lejos de los espacios reales
        ref_palabra = _hueco_palabra([ch for s in spans_all for ch in s["chars"]])
        for seg, spans in v[4]:
            previo = None  # (carácter, x1, fuente, tamaño) anterior de la misma línea cruda
            for k, s in enumerate(spans):
                siguiente = next((t["chars"][0] for t in spans[k + 1:] if t["chars"]), None)
                pequeno = s["size"] < 0.8 * tam_base
                superindice = bool(s["flags"] & 1) or (pequeno and s["origin"][1] < base_y - 0.15 * tam_base)
                subindice = pequeno and not superindice and s["origin"][1] > base_y + 0.1 * tam_base
                tracking = _hueco_base(s["chars"])
                for i, ch in enumerate(s["chars"]):
                    x0, y0, x1, y1 = ch["bbox"]
                    c = _caracter_de_fuente(ch["c"], s["font"])
                    if _control_sin_tinta(page, c, s["chars"], i, siguiente):
                        if previo and not previo[0].strip():
                            continue  # «2  \x07Materials»: ya hay un espacio delante
                        c = " "
                    hueco = x0 - previo[1] if previo else 0.0
                    if previo and previo[2:] == (s["font"], s["size"]) and _falta_espacio(
                            previo[0], ch["c"], hueco - tracking, s["size"]) and (
                            ref_palabra is None or hueco >= 0.5 * ref_palabra
                            or hueco - tracking >= 0.13 * s["size"]):
                        chars.append(Char(" ", previo[1], y0, x0, y1, linea_id, superindice, subindice,
                                          _url_en((previo[1] + x0) / 2, (y0 + y1) / 2, enlaces),
                                          seq=seq, seg=seg, tam=s["size"]))
                        seq += 1
                    previo = (c if c == " " else ch["c"], x1, s["font"], s["size"])
                    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
                    chars.append(Char(c, x0, y0, x1, y1, linea_id,
                                      superindice, subindice, _url_en(cx, cy, enlaces), seq=seq, seg=seg,
                                      tam=s["size"]))
                    seq += 1
    return PaginaTexto(numero, float(page.rect.width), float(page.rect.height), chars,
                       [u for _, u in enlaces], enlaces, marcas)


def chars_en_bbox(pt: PaginaTexto, bbox, tol: float = 1.0, consumir: bool = True) -> list[Char]:
    """Caracteres no consumidos cuyo centro cae dentro del bbox (ampliado en `tol` puntos). En una
    página enderezada se completan las palabras con la mayoría de sus letras dentro: Docling mide
    mal el texto girado y sus cajas quedan hasta 4 pt corridas («Biocha», «.5%» por «1.5%»)."""
    x0, y0, x1, y1 = bbox
    x0, y0, x1, y1 = x0 - tol, y0 - tol, x1 + tol, y1 + tol
    dentro = []
    for ch in pt.chars:
        if ch.consumido:
            continue
        cx, cy = ch.centro
        if x0 <= cx <= x1 and y0 <= cy <= y1:
            dentro.append(ch)
    if pt.enderezada and dentro:
        dentro = _completar_palabras(pt.chars, dentro)
    if consumir:
        for ch in dentro:
            ch.consumido = True
    return dentro


def fraccion_cubierta(pt: PaginaTexto, bbox, cajas) -> float:
    """Fracción de los caracteres visibles sin consumir de `bbox` que caen en alguna de las `cajas`
    (las celdas de una tabla). No consume nada. Sin caracteres en la región devuelve 1."""
    region = [c for c in chars_en_bbox(pt, bbox, consumir=False) if c.c.strip()]
    if not region:
        return 1.0
    ids = {id(c) for caja in cajas for c in chars_en_bbox(pt, caja, tol=0.5, consumir=False)}
    return sum(1 for c in region if id(c) in ids) / len(region)


def rejilla_por_posiciones(lineas: list[tuple[tuple, str]]) -> tuple[list[list[tuple[int, str]]], int]:
    """Rehace una tabla con las líneas de la capa de texto de su región (en estas tablas cada celda
    es una línea): filas por solape vertical, columnas ancladas en la fila con más celdas (por
    solape horizontal o, si no hay, por el centro más cercano). Devuelve las filas como
    [(columna, texto)] y el número de filas de cabecera (las anteriores a la primera fila con
    números en más de la mitad de sus celdas)."""
    filas: list[list[tuple[tuple, str]]] = []
    for bb, texto in sorted(lineas, key=lambda l: ((l[0][1] + l[0][3]) / 2, l[0][0])):
        cy = (bb[1] + bb[3]) / 2
        if filas and min(b[1] for b, _ in filas[-1]) <= cy <= max(b[3] for b, _ in filas[-1]):
            filas[-1].append((bb, texto))
        else:
            filas.append([(bb, texto)])
    if not filas:
        return [], 0
    anclas = sorted(b for b, _ in max(filas, key=len))

    def columna(bb) -> int:
        solapes = [min(bb[2], a[2]) - max(bb[0], a[0]) for a in anclas]
        if max(solapes) > 0:
            return solapes.index(max(solapes))
        centro = (bb[0] + bb[2]) / 2
        return min(range(len(anclas)), key=lambda i: abs((anclas[i][0] + anclas[i][2]) / 2 - centro))

    salida = []
    for fila in filas:
        celdas: dict[int, str] = {}
        for bb, texto in sorted(fila, key=lambda l: l[0][0]):
            c = columna(bb)
            celdas[c] = f"{celdas[c]} {texto}" if c in celdas else texto
        salida.append(sorted(celdas.items()))
    cabecera = next((i for i, f in enumerate(salida)
                     if sum(any(ch.isdigit() for ch in t) for _, t in f) > len(f) / 2), 0)
    return salida, cabecera


def rejilla_aprovechable(filas: list[list[tuple[int, str]]]) -> bool:
    """True si la rejilla por posiciones separa columnas: al menos la mitad de sus filas tienen dos
    celdas o más (evita casos donde dejaba cada fila en una sola celda)."""
    return bool(filas) and 2 * sum(len(f) >= 2 for f in filas) >= len(filas)


@dataclass
class DiagnosticoRejilla:
    """Señales de que la rejilla de TableFormer no casa con el PDF (ver `rejilla_rota`)."""
    cubierta: float        # fracción de caracteres de la región que acaban en una celda (con el rescate)
    filas_mezcladas: int   # filas físicas cuyo texto cae en dos filas de la rejilla o más
    filas_fisicas: int     # líneas horizontales de la región agrupadas por solape vertical
    horizontal: float      # fracción de caracteres en líneas horizontales
    multilinea: float      # fracción de celdas de cuerpo con texto en dos filas físicas o más


def _palabras(chars: list[Char]) -> list[list[Char]]:
    """Rachas sin espacios de la misma línea, en el orden de `chars`."""
    palabras: list[list[Char]] = [[]]
    for c in chars:
        if not c.c.strip():
            palabras.append([])
            continue
        if palabras[-1] and palabras[-1][-1].linea != c.linea:
            palabras.append([])
        palabras[-1].append(c)
    return [p for p in palabras if p]


def _duenos_y_rescate(pt: PaginaTexto, bbox, cajas) -> tuple[list[Char], dict[int, int], dict[int, int]]:
    """(caracteres de la región, {id: caja que se lo queda}, {id: caja que lo rescata}). Cada carácter
    va a la primera caja que lo contiene, como al consumirlos celda a celda. Se rescata un carácter
    que no cae en ninguna caja si su palabra tiene la mayoría de sus letras en una sola."""
    todos = chars_en_bbox(pt, bbox, consumir=False)
    dueno: dict[int, int] = {}
    for i, caja in enumerate(cajas):
        for c in chars_en_bbox(pt, caja, tol=0.5, consumir=False):
            if c.c.strip():
                dueno.setdefault(id(c), i)
    rescate: dict[int, int] = {}
    for p in _palabras(todos):
        cuenta: dict[int, int] = {}
        for c in p:
            if id(c) in dueno:
                cuenta[dueno[id(c)]] = cuenta.get(dueno[id(c)], 0) + 1
        if cuenta:
            i, n = max(cuenta.items(), key=lambda kv: kv[1])
            if 2 * n > len(p):
                rescate.update((id(c), i) for c in p if id(c) not in dueno)
    return todos, dueno, rescate


def rescatar_cortes(pt: PaginaTexto, bbox, cajas) -> dict[int, list[Char]]:
    """{índice de caja: caracteres que se le añaden}: letras que el borde de la celda de TableFormer
    deja fuera de toda celda («s|weet») y que se perdían al consumir la región."""
    todos, _, rescate = _duenos_y_rescate(pt, bbox, cajas)
    extra: dict[int, list[Char]] = {}
    for c in todos:
        if id(c) in rescate:
            extra.setdefault(rescate[id(c)], []).append(c)
    return extra


def diagnosticar_rejilla(pt: PaginaTexto, bbox, celdas: list[tuple[int, bool, tuple]]) -> DiagnosticoRejilla:
    """Mide la rejilla de TableFormer contra la capa de texto de su región. `celdas`: (fila, es de
    cuerpo sin rowspan, caja). No consume nada."""
    todos, dueno, rescate = _duenos_y_rescate(pt, bbox, [caja for _, _, caja in celdas])
    region = [c for c in todos if c.c.strip()]
    if not region:
        return DiagnosticoRejilla(1.0, 0, 0, 1.0, 0.0)
    cubierta = sum(1 for c in region if id(c) in dueno or id(c) in rescate) / len(region)
    lineas: dict[int, list[Char]] = {}
    for c in region:
        lineas.setdefault(c.linea, []).append(c)
    cajas_linea = {k: (min(c.x0 for c in l), min(c.y0 for c in l), max(c.x1 for c in l), max(c.y1 for c in l))
                   for k, l in lineas.items()}
    # texto girado: la línea es más alta que ancha y que 1,5 cuerpos de letra
    horizontales = [k for k, (x0, y0, x1, y1) in cajas_linea.items()
                    if not (y1 - y0 > 1.5 * statistics.median(c.tam or c.y1 - c.y0 for c in lineas[k])
                            and y1 - y0 > x1 - x0)]
    fisica: dict[int, int] = {}
    tramos: list[list[float]] = []
    for k in sorted(horizontales, key=lambda k: (cajas_linea[k][1] + cajas_linea[k][3]) / 2):
        _, y0, _, y1 = cajas_linea[k]
        if tramos and tramos[-1][0] <= (y0 + y1) / 2 <= tramos[-1][1]:
            tramos[-1] = [min(tramos[-1][0], y0), max(tramos[-1][1], y1)]
        else:
            tramos.append([y0, y1])
        fisica[k] = len(tramos) - 1
    filas_de: dict[int, set[int]] = {}
    fisicas_de: dict[int, set[int]] = {}
    for c in region:
        i = dueno.get(id(c))
        if i is None or c.linea not in fisica or not celdas[i][1]:
            continue
        filas_de.setdefault(fisica[c.linea], set()).add(celdas[i][0])
        fisicas_de.setdefault(i, set()).add(fisica[c.linea])
    return DiagnosticoRejilla(
        cubierta=cubierta,
        filas_mezcladas=sum(1 for s in filas_de.values() if len(s) > 1),
        filas_fisicas=len(tramos),
        horizontal=sum(len(lineas[k]) for k in horizontales) / len(region),
        multilinea=sum(1 for s in fisicas_de.values() if len(s) > 1) / len(fisicas_de) if fisicas_de else 0.0)


def rejilla_rota(d: DiagnosticoRejilla) -> bool:
    """True si conviene rehacer la tabla por posiciones: texto horizontal (≥ 75 %), celdas de una
    línea (≤ 15 % de varias, que la rejilla por posiciones partiría en filas) y, además, texto que
    ninguna celda recoge (cubierta < 97 %, tras el rescate) o filas del PDF repartidas entre filas
    de la rejilla (≥ 3 y ≥ 20 % de las filas físicas)."""
    if d.horizontal < 0.75 or d.multilinea > 0.15:
        return False
    return d.cubierta < 0.97 or (d.filas_mezcladas >= 3 and d.filas_mezcladas >= 0.2 * d.filas_fisicas)


def _completar_palabras(todos: list[Char], dentro: list[Char]) -> list[Char]:
    """Añade a `dentro` las letras sin consumir de cada palabra (racha sin espacios de la misma
    línea, en el orden de `todos`) que tiene dentro más de la mitad de sus letras."""
    ids = {id(c) for c in dentro}
    palabras: list[list[Char]] = []
    for c in todos:
        if not c.c.strip():
            palabras.append([])
            continue
        if not palabras or not palabras[-1] or palabras[-1][-1].linea != c.linea:
            palabras.append([])
        palabras[-1].append(c)
    extra = set()
    for p in palabras:
        n = sum(id(c) in ids for c in p)
        if n and 2 * n > len(p):
            extra.update(id(c) for c in p if id(c) not in ids and not c.consumido)
    if not extra:
        return dentro
    return [c for c in todos if id(c) in ids or id(c) in extra]


def chars_sin_consumir(pt: PaginaTexto) -> list[Char]:
    return [ch for ch in pt.chars if not ch.consumido]


# --- ordenación dentro de una línea ------------------------------------------------------------

def _ordenar_linea(chars: list[Char]) -> list[Char]:
    """Segmento base (el más largo) en orden de flujo; los demás segmentos (superíndices sueltos)
    se insertan por posición x. Así las ligaduras expandidas no se desordenan."""
    por_seg: dict[int, list[Char]] = {}
    for ch in chars:
        por_seg.setdefault(ch.seg, []).append(ch)
    segmentos = sorted(por_seg.values(), key=lambda s: -len(s))
    base = sorted(segmentos[0], key=lambda c: c.seq)
    xs = [c.x0 for c in base]
    for seg in sorted(segmentos[1:], key=lambda s: min(c.x0 for c in s)):
        seg = sorted(seg, key=lambda c: c.seq)
        pos = bisect.bisect_left(xs, seg[0].x0 - 0.5)
        base[pos:pos] = seg
        xs[pos:pos] = [c.x0 for c in seg]
    if len(segmentos) == 1:
        return base
    # En líneas muy abiertas (RSC, títulos en cursiva de la bibliografía) MuPDF da cada palabra como
    # línea cruda aparte y no emite el espacio: se repone entre segmentos separados por un hueco
    # de palabra, salvo junto a un super/subíndice (que va pegado a su base).
    salida = [base[0]]
    for a, b in zip(base, base[1:]):
        if (a.seg != b.seg and a.c.strip() and b.c.strip() and b.x0 - a.x1 > 0.15 * max(a.tam, b.tam, 1.0)
                and not (a.superindice or a.subindice or b.superindice or b.subindice)):
            salida.append(replace(a, c=" ", x0=a.x1, x1=b.x0, url=a.url if a.url == b.url else None))
        salida.append(b)
    return salida


def _lineas_ordenadas(chars: list[Char]) -> list[list[Char]]:
    por_linea: dict[int, list[Char]] = {}
    for ch in chars:
        por_linea.setdefault(ch.linea, []).append(ch)
    lineas = [_ordenar_linea(l) for l in por_linea.values()]
    lineas.sort(key=lambda l: (round(sum(c.centro[1] for c in l) / len(l) / 2), l[0].x0))
    return lineas


# --- correcciones a nivel de carácter ---------------------------------------------------------

def _combinar_acentos(linea: list[Char]) -> list[Char]:
    salida: list[Char] = []
    pendientes: list[Char] = []
    for ch in linea:
        if ch.c in _ACENTOS:
            pendientes.append(ch)
        else:
            salida.append(ch)
    if not pendientes:
        return linea
    for ac in pendientes:
        mejor, mejor_solape = None, 0.0
        for i, ch in enumerate(salida):
            if not ch.c.strip() or not ch.c.isalpha():
                continue
            solape = min(ac.x1, ch.x1) - max(ac.x0, ch.x0)
            if solape > mejor_solape:
                mejor, mejor_solape = i, solape
        ancho = max(0.1, ac.x1 - ac.x0)
        if mejor is not None and mejor_solape > 0.3 * ancho:
            base = salida[mejor]
            letra = {"ı": "i", "ȷ": "j"}.get(base.c, base.c)  # ı, ȷ sin punto no componen en NFC
            salida[mejor] = replace(base, c=unicodedata.normalize("NFC", letra + _ACENTOS[ac.c]))
        else:
            salida.append(ac)  # sin base: se conserva en su lugar aproximado
            salida.sort(key=lambda c: c.seq)
    return salida


_RE_MAYUS = re.compile(r"^[A-Z0-9ÁÉÍÓÚÑÜ]$")


def _colapsar_espaciado(linea: list[Char]) -> list[Char]:
    """'A R T I C L E I N F O' -> 'ARTICLE INFO' usando los huecos reales entre letras. Las versalitas
    de algunos artículos de Elsevier vienen en minúsculas ('a r t i c l e', 'i n f o' en otra línea):
    se aceptan desde 4 letras si el menor espacio (el tracking) mide 0,35-0,6 em (un espacio normal
    ronda 0,25 em, y las letras de significación sobre las barras de una figura, «a a b c», dejan
    ≥ 0,72 em). Los espacios de los extremos no cuentan y entre palabras puede haber dos
    («A R T I C L E  I N F O »): una racha de dos espacios es siempre límite de palabra."""
    nucleo = [i for i, c in enumerate(linea) if c.c != " "]
    if not nucleo:
        return linea
    ini, fin = nucleo[0], nucleo[-1] + 1
    letras = [linea[i] for i in nucleo]
    # entre cada par de letras consecutivas, una racha de 1 o 2 espacios en el flujo
    rachas = [linea[a + 1:b] for a, b in zip(nucleo, nucleo[1:])]
    if not rachas or any(not 1 <= len(r) <= 2 for r in rachas):
        return linea
    mayusculas = len(letras) >= 5 and all(_RE_MAYUS.match(c.c) for c in letras)
    versalitas = len(letras) >= 4 and all(c.c.isalpha() and c.c.islower() for c in letras) and (
        0.35 <= min((r[0].x1 - r[0].x0) / max(r[0].tam, 0.1) for r in rachas) <= 0.6)
    if not (mayusculas or versalitas):
        return linea
    huecos = [letras[i + 1].x0 - letras[i].x1 for i in range(len(letras) - 1)]
    mediana = statistics.median(huecos)
    salida = linea[:ini] + [letras[0]]
    for i, h in enumerate(huecos):
        espacio = rachas[i][0]
        # Hay palabra si el hueco es claramente mayor que el paso de letra, o si el espacio es un
        # glifo real que no llena el hueco (MuPDF sintetiza espacios que lo llenan exactamente).
        glifo_real = (espacio.x0 - letras[i].x1 > 1.0) or (letras[i + 1].x0 - espacio.x1 > 1.0)
        if len(rachas[i]) == 2 or h > 1.5 * max(mediana, 0.1) or glifo_real:
            salida.append(espacio)  # conserva el espacio real de palabra
        salida.append(letras[i + 1])
    return salida + linea[fin:]


_RE_LETRA_MAYUS = re.compile(r"^[A-ZÁÉÍÓÚÑÜ]$")


def _unir_tracking(linea: list[Char]) -> list[Char]:
    """«F I G U R E 1 Thin-layer» -> «FIGURE 1 Thin-layer». Rótulos de Wiley con tracking (≈ 0,14 em
    entre letras) seguidos de texto normal: MuPDF mete un espacio sintético en algunos huecos y
    `_colapsar_espaciado`, que exige la línea entera espaciada, no los ve. En una racha de ≥ 4
    mayúsculas separadas por 0-1 espacios cuyos huecos entre letras rondan un mismo valor de
    0,08-0,3 em, se quitan los espacios de los huecos que no superan 1,5 veces ese valor. Firma del
    tracking: algún hueco SIN espacio ya mide ≥ 0,08 em (F-I). En las mayúsculas normales las letras
    van pegadas (hueco ≈ 0), y las letras sueltas con espacios normales («A B C D») no tienen hueco
    sin espacio: no se tocan. Las cifras quedan fuera («1 2 3 4» de una tabla)."""
    quitar: set[int] = set()
    i = 0
    while i < len(linea):
        if not _RE_LETRA_MAYUS.match(linea[i].c):
            i += 1
            continue
        letras = [i]
        j = i + 1
        while j < len(linea):
            k = j + 1 if linea[j].c == " " else j
            if k < len(linea) and _RE_LETRA_MAYUS.match(linea[k].c):
                letras.append(k)
                j = k + 1
            else:
                break
        if len(letras) >= 4 and any(b - a == 2 for a, b in zip(letras, letras[1:])):
            huecos = [linea[b].x0 - linea[a].x1 for a, b in zip(letras, letras[1:])]
            m = statistics.median(huecos)
            tam = statistics.median(linea[a].tam for a in letras)
            sin_espacio = [h for (a, b), h in zip(zip(letras, letras[1:]), huecos) if b - a == 1]
            if 0.08 * tam <= m <= 0.3 * tam and any(h >= 0.08 * tam for h in sin_espacio):
                for (a, b), h in zip(zip(letras, letras[1:]), huecos):
                    if b - a == 2 and h <= 1.5 * m:
                        quitar.add(a + 1)
        i = letras[-1] + 1
    return [c for n, c in enumerate(linea) if n not in quitar] if quitar else linea


def _unir_letras_espaciadas(linea: list[Char]) -> list[Char]:
    """«K i c z o r o w s k a B., S a m o l i ń s k a W.» -> «Kiczorowska B., Samolińska W.».
    Algunas revistas (p. ej. Annals of Animal Science) justifican la bibliografía separando cada
    letra de los apellidos con un hueco fijo de 0,2 em (1,62 pt a 8,1 pt) que MuPDF rellena con un
    espacio sintético; entre palabras el hueco es ese paso más el espacio (3,6 pt). Un espacio normal
    mide ≈ 0,25 em (2,0 pt, 1,23 veces el paso) y queda fuera de la tolerancia: hasta 1,15 veces el
    paso, y hasta un 60 % menos si el par va kerneado («T i»). Se unen los grupos separados por ese
    hueco cuando hay ≥ 5 pares de letras sueltas para estimar el paso y la racha tiene a un lado un
    hueco de palabra (> 1,5 veces el paso): «A B C D E F G H» de una tabla, con todos los espacios
    iguales, no se toca, ni el texto normal con alguna «a» suelta."""
    grupos: list[list[int]] = []
    actual: list[int] = []
    for i, c in enumerate(linea):
        if c.c.strip():
            actual.append(i)
        elif actual:
            grupos.append(actual)
            actual = []
    if actual:
        grupos.append(actual)
    if len(grupos) < 8:
        return linea

    def suelta(g: list[int]) -> bool:
        c = linea[g[0]]
        return len(g) == 1 and not (c.superindice or c.subindice)

    def unidad(g: list[int]) -> bool:
        """Letras (y el guion en apellidos compuestos): «B.,» o «2016» no se unen con el apellido siguiente."""
        return all((linea[i].c.isalpha() or linea[i].c == "-") and not (linea[i].superindice or linea[i].subindice)
                   for i in g)

    huecos = [linea[b[0]].x0 - linea[a[-1]].x1 for a, b in zip(grupos, grupos[1:])]
    entre_letras = [h for h, a, b in zip(huecos, grupos, grupos[1:])
                    if suelta(a) and suelta(b) and linea[a[0]].c.isalpha() and linea[b[0]].c.isalpha()]
    if len(entre_letras) < 5:
        return linea
    paso = statistics.median(entre_letras)
    tam = statistics.median(c.tam for c in linea if c.tam) if any(c.tam for c in linea) else 0.0
    if tam and not 0.08 * tam <= paso <= 0.35 * tam:
        return linea

    def es_paso(h: float, a: list[int], b: list[int]) -> bool:
        return (suelta(a) or suelta(b)) and unidad(a) and unidad(b) and 0.4 * paso <= h <= 1.15 * paso

    marcas = [es_paso(h, a, b) for h, a, b in zip(huecos, grupos, grupos[1:])]
    quitar: set[int] = set()
    i = 0
    while i < len(marcas):
        if not marcas[i]:
            i += 1
            continue
        j = i
        while j < len(marcas) and marcas[j]:
            j += 1
        # racha de pasos entre los grupos i..j, con un hueco de palabra en alguno de sus lados
        lado = [huecos[k] for k in (i - 1, j) if 0 <= k < len(huecos)]
        if any(h > 1.5 * paso for h in lado):
            for k in range(i, j):
                quitar.update(range(grupos[k][-1] + 1, grupos[k + 1][0]))
        i = j
    return [c for n, c in enumerate(linea) if n not in quitar] if quitar else linea


def _render_run(texto: str, superindice: bool, subindice: bool) -> str:
    if superindice:
        return a_superindice(texto) or texto
    if subindice:
        return a_subindice(texto) or texto
    return texto


def _linea_a_texto(linea: list[Char], con_enlaces: bool) -> str:
    linea = _unir_letras_espaciadas(_unir_tracking(_colapsar_espaciado(_combinar_acentos(linea))))
    salida: list[str] = []
    i = 0
    while i < len(linea):
        url = linea[i].url if con_enlaces else None
        j = i
        while j < len(linea):
            if (linea[j].url if con_enlaces else None) == url:
                j += 1
                continue
            # Espacios entre dos trozos del mismo enlace (cuando el PDF pone una anotación por palabra
            # y el espacio no cae en ninguna): el enlace sigue
            k = j
            while url and k < len(linea) and not linea[k].c.strip() and linea[k].url != url:
                k += 1
            if k > j and k < len(linea) and linea[k].url == url:
                j = k
                continue
            break
        grupo = linea[i:j]
        partes: list[str] = []
        k = 0
        while k < len(grupo):
            clave = (grupo[k].superindice, grupo[k].subindice)
            m = k
            while m < len(grupo) and (grupo[m].superindice, grupo[m].subindice) == clave:
                m += 1
            partes.append(_render_run("".join(c.c for c in grupo[k:m]), *clave))
            k = m
        texto = "".join(partes)
        if url and texto.strip():
            # «Check for updates» de MDPI: glifos sin mapa Unicode (U+FFFD) -> la URL como texto
            visible = texto.strip() if texto.replace("\ufffd", "").strip() else url
            # El espacio que abre la anotación (Wiley, ORCID tras el icono) separa de la palabra previa
            if texto[0].isspace() and salida and not salida[-1][-1:].isspace():
                salida.append(" ")
            salida.append(f"[{visible}]({url})")
            if texto.endswith(" "):
                salida.append(" ")
        else:
            salida.append(texto)
        i = j
    return normalizar_glifos("".join(salida)).rstrip()


def componer_texto(chars: list[Char]) -> str:
    """Texto con saltos de línea del PDF, enlaces [..](url) y super/subíndices Unicode."""
    return "\n".join(_linea_a_texto(l, True) for l in _lineas_ordenadas(chars)).strip("\n")


def componer_plano(chars: list[Char]) -> str:
    """Una sola línea, sin enlaces: para el texto alternativo de las figuras."""
    return " ".join(_linea_a_texto(l, False) for l in _lineas_ordenadas(chars)).strip()


def lineas_con_bbox(chars: list[Char]) -> list[tuple[tuple[float, float, float, float], str]]:
    """[(bbox, texto)] por línea visual, para agrupar texto residual en bloques posicionados."""
    salida = []
    for l in _lineas_ordenadas(chars):
        visibles = [c for c in l if c.c.strip()] or l  # los espacios de relleno de MuPDF no cuentan
        bb = (min(c.x0 for c in visibles), min(c.y0 for c in visibles),
              max(c.x1 for c in visibles), max(c.y1 for c in visibles))
        texto = _linea_a_texto(l, True)
        if texto.strip():
            salida.append((bb, texto))
    return salida


def tamano_medio(chars: list[Char]) -> float:
    letras = [c.tam for c in chars if c.c.strip()]
    return sum(letras) / len(letras) if letras else 0.0


def enlaces_sin_texto_visible(pt: PaginaTexto, figuras) -> list[tuple[tuple[float, float, float, float], str]]:
    """Enlaces de la página (uno por URL) que no dejan texto enlazado en el cuerpo: sin caracteres
    debajo (iconos ORCID, CrossMark) o con todos ellos dentro de alguna de las `figuras`, cuyo
    `alt` es texto plano (el CrossMark de algunos artículos de Elsevier esconde una «T» bajo el icono)."""
    def en_figura(c: Char) -> bool:
        x, y = c.centro
        return any(f[0] <= x <= f[2] and f[1] <= y <= f[3] for f in figuras)

    con_texto = {c.url for c in pt.chars if c.url and c.c.strip() and not en_figura(c)}
    vistos: set[str] = set()
    salida = []
    for rect, url in pt.enlaces:
        if url not in con_texto and url not in vistos:
            vistos.add(url)
            salida.append((rect, url))
    return salida


def giro_para_enderezar(page: fitz.Page, minimo: int = 200) -> int:
    """Giro (grados, para `show_pdf_page`) que deja horizontal el texto de una página apaisada, o
    0 si la mayoría de sus caracteres (≥ `minimo`) ya va en líneas horizontales. Se mide en
    coordenadas sin girar, así que vale igual con /Rotate 90 que con el contenido girado sobre una
    página vertical: texto hacia arriba (0,-1) → −90; hacia abajo → 90."""
    cuenta = {"h": 0, "arriba": 0, "abajo": 0}
    for b in page.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            n = sum(len(s["text"]) for s in l["spans"])
            dx, dy = l["dir"]
            clave = "h" if abs(dx) > 0.99 else "arriba" if dy < -0.99 else "abajo" if dy > 0.99 else None
            if clave:
                cuenta[clave] += n
    total = sum(cuenta.values())
    if total < minimo or cuenta["h"] >= 0.5 * total:
        return 0
    return -90 if cuenta["arriba"] >= cuenta["abajo"] else 90


# Glifos de fuentes de símbolos que el PDF nombra con nombres propios del fabricante («C0», «H11034»)
# y sin Unicode: MuPDF da U+FFFD. El código de cada glifo cambia de un PDF a otro, pero el nombre no.
_GRIEGAS = "αβγδεζηθικλμνξοπρσςτυφχψω"
_GLIFOS_POR_FUENTE = {
    "AdvP4C4E74": {"C0": "−", "C1": "·", "C2": "×", "C3": "∗", "C4": "÷", "C6": "±", "C14": "°",
                   "C15": "•", "C20": "≤", "C21": "≥", "C24": "∼", "C25": "≈", "C138": "]"},
    "AdvMacMthSyN": {"C0": "−", "C1": "·"},
    # acentos sueltos; C22 es la barra de Q̄
    "AdvP4C4E59": {"C18": "`", "C19": "´", "C20": "ˇ", "C21": "˘", "C22": "¯", "C23": "˚"},
    "AdvP4C4E5E": {"C18": "`", "C19": "´"},  # los mismos acentos en cursiva
    # extensiones de fórmula (como CMEX10): paréntesis grandes de dos tamaños y la sumatoria grande,
    # que el ToUnicode de algunos PDF de Elsevier da como la letra «X»
    "AdvP4C4E46": {"C0": "(", "C1": ")", "C16": "(", "C17": ")", "X": "∑"},
    "AdvP4C4E51": {"C11": "α"},  # alfa en cursiva (p. ej. F₂α)
    # códigos de la fuente Symbol; C212 es ™
    "AdvPSSym": {"C176": "°", "C210": "®", "C211": "©", "C212": "™", "C226": "®"},
    "AdvPSMP": {"C160": "†"},
    "RMTMI": {"Delta1": "Δ"},  # MathTime Italic de pdfTeX (p. ej. ΔΔCt)
    "MathematicalPi": {"H11002": "−", "H11003": "×", "H11015": "≈", "H11034": "°", "H9002": "Β",
                       **{f"H{9251 + i}": g for i, g in enumerate(_GRIEGAS)}},
}


def _differences(doc: fitz.Document, xref: int) -> dict[int, str]:
    """Código → nombre de glifo del /Differences de la codificación de una fuente simple."""
    tipo, valor = doc.xref_get_key(xref, "Encoding")
    if tipo == "xref":
        valor = doc.xref_object(int(valor.split()[0]))
    elif tipo != "dict":
        return {}
    m = re.search(r"/Differences\s*\[(.*?)\]", valor, re.S)
    res, codigo = {}, 0
    for tok in re.findall(r"\d+|/[^\s/\[\]<>()]+", m.group(1) if m else ""):
        if tok[0] == "/":
            res[codigo] = tok[1:]
            codigo += 1
        else:
            codigo = int(tok)
    return res


def _leer_tounicode(cmap: str) -> dict[int, str]:
    """Entradas bfchar/bfrange de un ToUnicode de un byte (el de las fuentes simples)."""
    def texto(hexa: str) -> str:
        return bytes.fromhex(hexa).decode("utf-16-be", errors="replace")
    res = {}
    for bloque in re.findall(r"beginbfchar(.*?)endbfchar", cmap, re.S):
        for cod, dst in re.findall(r"<([0-9a-fA-F]+)>\s*<([0-9a-fA-F]*)>", bloque):
            res[int(cod, 16)] = texto(dst)
    for bloque in re.findall(r"beginbfrange(.*?)endbfrange", cmap, re.S):
        for a, b, dst in re.findall(r"<([0-9a-fA-F]+)>\s*<([0-9a-fA-F]+)>\s*(<[0-9a-fA-F]*>|\[[^\]]*\])", bloque):
            a, b = int(a, 16), int(b, 16)
            if dst.startswith("["):
                for i, d in enumerate(re.findall(r"<([0-9a-fA-F]*)>", dst)):
                    res[a + i] = texto(d)
            else:
                ini = texto(dst[1:-1])
                for i in range(b - a + 1):
                    res[a + i] = ini[:-1] + chr(ord(ini[-1]) + i) if ini else ""
    return res


def reparar_tounicode(doc: fitz.Document) -> int:
    """Da Unicode a los glifos de `_GLIFOS_POR_FUENTE` reescribiendo (en memoria) el ToUnicode de
    sus fuentes; conserva lo que el ToUnicode original ya mapeaba. Solo cambia la extracción de
    texto, no el dibujo. Devuelve el número de fuentes reparadas."""
    reparadas = 0
    for xref in range(1, doc.xref_length()):
        try:
            tipo, base = doc.xref_get_key(xref, "BaseFont")
        except Exception:  # entrada libre o rota de la tabla xref
            continue
        if tipo != "name":
            continue
        tabla = next((t for fam, t in _GLIFOS_POR_FUENTE.items() if fam in base), None)
        if tabla is None:
            continue
        nuevos = {c: tabla[n] for c, n in _differences(doc, xref).items() if n in tabla and c < 256}
        if not nuevos:
            continue
        tipo_tu, valor_tu = doc.xref_get_key(xref, "ToUnicode")
        mapa = {}
        if tipo_tu == "xref":
            mapa = _leer_tounicode(doc.xref_stream(int(valor_tu.split()[0])).decode("latin-1"))
        mapa.update(nuevos)
        lineas = [f"<{c:02x}> <{u.encode('utf-16-be').hex()}>" for c, u in sorted(mapa.items()) if u]
        cmap = ("/CIDInit /ProcSet findresource begin 12 dict begin begincmap\n"
                "/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def\n"
                "/CMapName /Adobe-Identity-UCS def /CMapType 2 def\n"
                "1 begincodespacerange <00> <ff> endcodespacerange\n"
                f"{len(lineas)} beginbfchar\n" + "\n".join(lineas) + "\nendbfchar\n"
                "endcmap CMapName currentdict /CMap defineresource pop end end")
        nuevo = doc.get_new_xref()
        doc.update_object(nuevo, "<<>>")
        doc.update_stream(nuevo, cmap.encode("ascii"))
        doc.xref_set_key(xref, "ToUnicode", f"{nuevo} 0 R")
        reparadas += 1
    return reparadas


def abrir_con_unicode(pdf: Path) -> tuple[fitz.Document, int]:
    """Abre `pdf` con `reparar_tounicode` aplicado; devuelve el documento y las fuentes reparadas.
    Si hubo cambios se reabre desde memoria: MuPDF guarda en caché las fuentes ya cargadas."""
    doc = fitz.open(str(pdf))
    reparadas = reparar_tounicode(doc)
    if reparadas:
        datos = doc.tobytes()
        doc.close()
        doc = fitz.open("pdf", datos)
    return doc, reparadas


def enderezar_apaisadas(pdf: Path, destino: Path) -> list[int]:
    """Escribe en `destino` una copia de `pdf` con las páginas apaisadas redibujadas en horizontal
    y devuelve sus números (1-based); si no hay ninguna, no escribe nada y devuelve []. Docling y
    PyMuPDF leen luego la copia: el flujo arma líneas y celdas suponiendo texto horizontal.
    El resto de páginas no cambia; los enlaces se trasladan con el mismo giro (`show_pdf_page`
    no los copia)."""
    fuente = fitz.open(str(pdf))
    giros, enlaces = {}, {}
    for page in fuente:
        rotacion = page.rotation
        # get_links() da los rectángulos ya girados con /Rotate y no se actualiza tras set_rotation
        uris = [(fitz.Rect(l["from"]) * page.derotation_matrix, l["uri"]) for l in page.get_links()
                if l.get("kind") == fitz.LINK_URI and l.get("uri")]
        page.set_rotation(0)  # show_pdf_page recorta con el rectángulo girado: se trabaja sin /Rotate
        giro = giro_para_enderezar(page)
        if giro:
            giros[page.number], enlaces[page.number] = giro, uris
        else:
            page.set_rotation(rotacion)
    if not giros:
        return []
    salida = fitz.open(str(pdf))
    for n in sorted(giros, reverse=True):
        cb = fuente[n].cropbox
        nueva = salida.new_page(pno=n, width=cb.height, height=cb.width)
        nueva.show_pdf_page(nueva.rect, fuente, n, rotate=giros[n])
        for r, uri in enlaces[n]:
            if giros[n] == -90:   # (x, y) → (y1 − y, x − x0): el texto que subía pasa a ir a la derecha
                nr = fitz.Rect(cb.y1 - r.y1, r.x0 - cb.x0, cb.y1 - r.y0, r.x1 - cb.x0)
            else:                 # (x, y) → (y − y0, x1 − x)
                nr = fitz.Rect(r.y0 - cb.y0, cb.x1 - r.x1, r.y1 - cb.y0, cb.x1 - r.x0)
            nueva.insert_link({"kind": fitz.LINK_URI, "uri": uri, "from": nr})
        salida.delete_page(n + 1)
    destino.parent.mkdir(parents=True, exist_ok=True)
    salida.save(str(destino), garbage=3, deflate=True)
    return [n + 1 for n in sorted(giros)]


def _imagenes_grandes(page: fitz.Page, area_min: float) -> list[dict]:
    """Imágenes (con su `digest`) que cubren al menos `area_min` de la página."""
    grandes = []
    for info in page.get_image_info(hashes=True):
        r = fitz.Rect(info["bbox"]) & page.rect
        if not r.is_empty and abs(r) >= area_min * abs(page.rect):
            grandes.append(info)
    return grandes


def pagina_escaneada(page: fitz.Page, minimo: int = 20, area_min: float = 0.3,
                     fondos: frozenset = frozenset()) -> bool:
    """True si la página no trae capa de texto pero muestra una imagen grande con contenido (un
    escaneo). Las páginas sin texto que solo llevan dibujos vectoriales (franjas decorativas), una
    imagen de fondo casi lisa o uno de los `fondos` del documento (imágenes que también cubren
    páginas con texto) no tienen nada que leer y no cuentan."""
    if len(page.get_text("text").strip()) >= minimo:
        return False
    for info in _imagenes_grandes(page, area_min):
        if info["digest"] in fondos:
            continue
        if not region_en_blanco(page, fitz.Rect(info["bbox"]) & page.rect):
            return True
    return False


def _medidas(page: fitz.Page) -> tuple[float, float]:
    """Lados de la página de menor a mayor (una hoja apaisada mide lo mismo que la vertical)."""
    return tuple(sorted((page.rect.width, page.rect.height)))


def _mismo_tamano(a: tuple[float, float], b: tuple[float, float], tolerancia: float = 0.1) -> bool:
    return all(abs(x - y) <= tolerancia * max(x, y) for x, y in zip(a, b))


def paginas_escaneadas(doc: fitz.Document, minimo: int = 20, area_min: float = 0.3) -> list[int]:
    """Números de página (desde 1) que son un escaneo: sin texto, con una imagen propia a página
    completa (no una que también cubre páginas con texto como imagen de fondo) y del tamaño de las
    páginas con texto (no un resumen gráfico en una hoja a su medida)."""
    con_texto = [len(p.get_text("text").strip()) >= minimo for p in doc]
    fondos = frozenset(info["digest"] for p, t in zip(doc, con_texto) if t
                       for info in _imagenes_grandes(p, area_min))
    tamanos = {_medidas(p) for p, t in zip(doc, con_texto) if t}
    return [n for n, (p, t) in enumerate(zip(doc, con_texto), 1)
            if not t and any(_mismo_tamano(_medidas(p), m) for m in tamanos)
            and pagina_escaneada(p, minimo, area_min, fondos)]


def tiene_capa_texto(doc: fitz.Document, minimo: int = 20, area_min: float = 0.3,
                     fraccion_escaneo: float = 0.5) -> bool:
    """False si hay que activar el OCR: el documento no trae texto en ninguna página o es un
    escaneo, es decir, al menos `fraccion_escaneo` de sus páginas lo son (`paginas_escaneadas`).
    Un libro digital con portada, separadores y fotos a página completa tiene entre 1 y 15 % de
    páginas de imagen, cada una con su propia imagen, y no es un escaneo: pasarlo a OCR degradaría
    todo su texto digital. Sus páginas de imagen se quedan sin texto (ver `paginas_escaneadas`)."""
    if not any(len(p.get_text("text").strip()) >= minimo for p in doc):
        return False
    return len(paginas_escaneadas(doc, minimo, area_min)) < fraccion_escaneo * len(doc)


_RE_PUNTOS_GUIA = re.compile(r"(?:\.\s?){5,}")


def es_indice_de_contenidos(texto: str, minimo_con_puntos: int = 3, fraccion: float = 0.15) -> bool:
    """True si el texto de una región es un índice (de contenidos, de tablas, de figuras): al menos
    `minimo_con_puntos` líneas, y `fraccion` del total, llevan puntos guía hasta el número de página
    (en algunos índices de tablas solo ~19 % de las líneas llevan puntos porque los títulos ocupan
    2-4 líneas y los puntos van en la última). Docling lo toma por una tabla y su rejilla corta las
    palabras en el borde de cada celda; una tabla de datos no lleva cinco puntos seguidos."""
    lineas = [l for l in texto.splitlines() if l.strip()]
    con_puntos = sum(1 for l in lineas if _RE_PUNTOS_GUIA.search(l))
    return con_puntos >= minimo_con_puntos and con_puntos >= fraccion * len(lineas)


def region_en_blanco(page: fitz.Page, bbox, dpi: int = 36, margen: float = 0.1,
                     umbral: float = 0.995) -> bool:
    """True si la región se dibuja (casi) de un solo color: ahí no se ve ninguna figura. Se mira el
    interior (sin un `margen` relativo por lado) para que el filete de una tabla o un borde que
    roce la caja no cuente como contenido."""
    r = fitz.Rect(*bbox)
    clip = fitz.Rect(r.x0 + margen * r.width, r.y0 + margen * r.height,
                     r.x1 - margen * r.width, r.y1 - margen * r.height) & page.rect
    if clip.is_empty:
        return True
    # fracción del color dominante: un gráfico de líneas sobre blanco ronda el 0,9; una foto, < 0,5
    return page.get_pixmap(dpi=dpi, clip=clip, alpha=False).color_topusage()[0] > umbral


def imagenes_visibles(page: fitz.Page, minimo: float = 20.0) -> list[tuple[float, float, float, float]]:
    """Cajas de las imágenes incrustadas que de verdad se ven, en orden de lectura. Los PDF
    generados desde Word (MDPI) arrastran copias recortadas por un clip de la misma imagen, que
    ni get_image_info ni get_bboxlog distinguen: se descartan las que se dibujan en blanco, las
    casi coincidentes con otra ya aceptada y las menores que `minimo` puntos (iconos)."""
    aceptadas: list[fitz.Rect] = []
    for info in page.get_image_info():
        r = fitz.Rect(info["bbox"]) & page.rect
        if r.is_empty or r.width < minimo or r.height < minimo:
            continue
        if any((r & a).get_area() > 0.7 * min(r.get_area(), a.get_area()) for a in aceptadas):
            continue
        # margen y umbral holgados: un filete de tabla puede cruzar el hueco de una imagen recortada
        if not region_en_blanco(page, r, margen=0.2, umbral=0.9):
            aceptadas.append(r)
    return [tuple(r) for r in sorted(aceptadas, key=lambda r: (round(r.y0), r.x0))]


def recortar_figura(page: fitz.Page, bbox, dpi: int, destino: Path) -> None:
    escala = dpi / 72
    clip = fitz.Rect(*bbox) & page.rect
    pix = page.get_pixmap(matrix=fitz.Matrix(escala, escala), clip=clip, alpha=False)
    destino.parent.mkdir(parents=True, exist_ok=True)
    pix.save(str(destino), jpg_quality=90)

