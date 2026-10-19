"""Renderizado Markdown y correcciones deterministas (funciones puras, sin E/S).

Formato de salida estructurado por páginas (ver docs/formato-salida.md).
"""
from __future__ import annotations

import html
import re

from pdf2md.md_modelo import Bloque, Pagina, Tabla

# --- correcciones deterministas -------------------------------------------------------------

_LIGADURAS = {
    "\ufb00": "ff", "\ufb01": "fi", "\ufb02": "fl", "\ufb03": "ffi", "\ufb04": "ffl",
    "\ufb05": "st", "\ufb06": "st",
    # Fuentes AdvOT de RSC: ligaduras en el área de uso privado (MuPDF las expande en modo "text",
    # pero no en "rawdict"). Identificadas por contexto: "\ue103lms", "air\ue104ow", "so\ue09dware".
    "\ue103": "fi", "\ue104": "fl", "\ue09d": "ft", "\ue092": "fb",
}
# Glifos que algunos PDF (Elsevier/MDPI) usan como símbolo de grado: ◦ (viñeta blanca), º (ordinal), ˚ (ring).
_GRADO = {"\u25e6", "\u00ba", "\u02da"}
_SUPER = str.maketrans({
    "0": "\u2070", "1": "\u00b9", "2": "\u00b2", "3": "\u00b3", "4": "\u2074", "5": "\u2075",
    "6": "\u2076", "7": "\u2077", "8": "\u2078", "9": "\u2079", "+": "\u207a", "-": "\u207b",
    "\u2212": "\u207b", "=": "\u207c", "(": "\u207d", ")": "\u207e", "n": "\u207f", "i": "\u2071",
})
_SUB = str.maketrans({
    "0": "\u2080", "1": "\u2081", "2": "\u2082", "3": "\u2083", "4": "\u2084", "5": "\u2085",
    "6": "\u2086", "7": "\u2087", "8": "\u2088", "9": "\u2089", "+": "\u208a", "-": "\u208b",
    "\u2212": "\u208b", "=": "\u208c", "(": "\u208d", ")": "\u208e",
})
_RE_NUM_PAGINA = re.compile(r"^\d{1,4}(\s+of\s+\d{1,4})?$")
_RE_LATEX = re.compile(r"\\[a-zA-Z]+|[\^_]\{|[\^_][A-Za-z0-9]")
# "2.5.1. Texto", "2.1.Reagents" (RSC omite el espacio en la capa de texto), "2Materials"; no "2025 was"
_RE_NUMERACION = re.compile(r"^(\d{1,2})((?:\.\d{1,2})*)(\.?)(?:\s+\S|(?=[A-Z][a-z]))")


_GUIONES = "-‐‑"
# Lo que puede seguir a un guion blando de corte de línea: nada, o el cierre de un enlace «](url)»
_RE_FIN_DE_LINEA = re.compile(r" *(?:\]\([^\s]*\) *)?(?:\n|$)")


def normalizar_glifos(texto: str) -> str:
    salida = []
    for i, ch in enumerate(texto):
        if ch in _GRADO:
            salida.append("\u00b0")
        elif ch in _LIGADURAS:
            salida.append(_LIGADURAS[ch])
        elif "\ue000" <= ch <= "\uf8ff":
            continue  # área de uso privado sin mapeo: se elimina
        elif ch < " " and ch not in "\n\t":
            salida.append("\ufffd")  # glifo de control sin mapa: visible como símbolo ilegible
        elif ch == "\u00a0":
            salida.append(" ")
        elif ch == "\u00ad":
            # Guion blando: solo se dibuja en el corte de línea. Wiley lo pone además detrás de un
            # guion real y con ancho cero («Thin-\xadlayer» salía «Thin--layer»)
            if (not salida or salida[-1][-1:] not in _GUIONES) and _RE_FIN_DE_LINEA.match(texto, i + 1):
                salida.append("-")
        else:
            salida.append(ch)
    return "".join(salida)


def _mapear(texto: str, tabla: dict) -> str | None:
    if not texto.strip():
        return None
    resultado = []
    for ch in texto:
        if ch == " ":
            resultado.append(" ")
            continue
        mapeado = tabla.get(ord(ch))
        if mapeado is None:
            return None
        resultado.append(mapeado)
    return "".join(resultado)


def a_superindice(texto: str) -> str | None:
    """Texto en superíndice -> Unicode, o None si algún carácter no tiene equivalente."""
    return _mapear(texto, _SUPER)


def a_subindice(texto: str) -> str | None:
    return _mapear(texto, _SUB)


def respaldo_docling(texto: str | None, hay_capa_texto: bool) -> str:
    """Texto de Docling para una región donde PyMuPDF no ve caracteres. Si la página tiene capa
    de texto, esa región solo contiene texto oculto (recortado por un clip: restos de la
    maquetación, "x FOR PEER REVIEW" repetido) que el parser de Docling no filtra: se descarta.
    Sin capa de texto (OCR) el de Docling es el único texto que hay."""
    return "" if hay_capa_texto else normalizar_glifos(texto or "")


def es_numero_pagina(texto: str) -> bool:
    return bool(_RE_NUM_PAGINA.match(texto.strip()))


def parece_latex(texto: str) -> bool:
    return bool(texto) and bool(_RE_LATEX.search(texto))


def nivel_por_numeracion(texto: str) -> int | None:
    """'2.5.1. X' -> 3; '1. Intro' -> 1; sin numeración -> None."""
    m = _RE_NUMERACION.match(texto.strip())
    if not m:
        return None
    return 1 + (m.group(2).count(".") if m.group(2) else 0)


def normalizar_encabezado(texto: str) -> str:
    """Inserta el espacio que la capa de texto omite tras la numeración ('2.1.Reagents' ->
    '2.1. Reagents'); el PDF lo muestra, MuPDF no lo emite por ser un hueco pequeño."""
    m = _RE_NUMERACION.match(texto.strip())
    if not m:
        return texto
    return re.sub(r"^(\s*\d{1,2}(?:\.\d{1,2})*\.?)(?=[A-Z])", r"\1 ", texto, count=1)


# --- render -----------------------------------------------------------------------------------

_DOBLE_BLANCO = ("titulo", "seccion", "tabla", "figura")


def _una_linea(texto: str) -> str:
    return re.sub(r"\s*\n\s*", " ", texto.strip())


def _celda_html(texto: str, figuras: list[str] | None = None) -> str:
    partes = [html.escape(texto.strip(), quote=False).replace("\n", "<br>")] if texto.strip() else []
    partes += [f"![]({ruta})" for ruta in figuras or []]
    return "<br>".join(partes)


def render_tabla_html(tabla: Tabla) -> str:
    lineas = ["<table>"]
    if tabla.caption.strip():
        lineas.append(f"<caption>{_celda_html(_una_linea(tabla.caption))}</caption>")
    vistas: set[tuple[int, int]] = set()
    por_fila: dict[int, list] = {}
    for c in sorted(tabla.celdas, key=lambda c: (c.fila, c.col)):
        if (c.fila, c.col) in vistas:
            continue
        vistas.add((c.fila, c.col))
        por_fila.setdefault(c.fila, []).append(c)
    for fila in range(tabla.filas):
        celdas = por_fila.get(fila)
        if not celdas or not any(c.texto.strip() or c.figuras for c in celdas):
            continue  # fila sin contenido (p. ej. solo tenía texto oculto del PDF, ya descartado)
        lineas.append("<tr>")
        for c in celdas:
            etiqueta = "th" if c.encabezado else "td"
            atributos = ""
            if c.col_span > 1:
                atributos += f' colspan="{c.col_span}"'
            if c.fila_span > 1:
                atributos += f' rowspan="{c.fila_span}"'
            lineas.append(f"<{etiqueta}{atributos}>{_celda_html(c.texto, c.figuras)}</{etiqueta}>")
        lineas.append("</tr>")
    lineas.append("</table>")
    return "\n".join(lineas)


def _alt_figura(alt: str) -> str:
    return re.sub(r"\s+", " ", alt.replace("]", " ").replace("[", " ")).strip()


def render_bloque(b: Bloque) -> str:
    if b.tipo == "titulo":
        return "# " + _una_linea(b.texto)
    if b.tipo == "seccion":
        return "#" * (max(1, b.nivel) + 1) + " " + _una_linea(b.texto)
    if b.tipo in ("parrafo", "leyenda", "nota", "encabezado", "pie", "numero_pagina"):
        return b.texto.strip()
    if b.tipo == "lista":
        return f"{b.marcador_lista} " + _una_linea(b.texto)
    if b.tipo == "codigo":
        return "```\n" + b.texto.strip("\n") + "\n```"
    if b.tipo == "formula":
        if b.latex:
            salida = f"$${b.latex.strip()}$$"
            if b.numero_ecuacion:
                salida += f"\n{b.numero_ecuacion}"
            return salida
        return "<!-- FormulaSinLatex -->\n" + b.texto.strip()
    if b.tipo == "tabla":
        assert b.tabla is not None
        salida = render_tabla_html(b.tabla)
        for nota in b.tabla.notas:
            salida += "\n\n" + nota.strip()
        return salida
    if b.tipo == "figura":
        return f"![{_alt_figura(b.alt)}]({b.figura_ruta})"
    if b.tipo == "sin_clasificar":
        return "<!-- SinClasificar -->\n" + b.texto.strip()
    raise ValueError(f"tipo de bloque desconocido: {b.tipo}")


def render_comentario(b: Bloque) -> str:
    """Encabezados, pies y números de página se emiten en comentarios HTML."""
    if b.tipo == "numero_pagina":
        return f"<!-- PageNumber: {_una_linea(b.texto)} -->"
    etiqueta = "PageFooter" if b.tipo == "pie" else "PageHeader"
    contenido = render_bloque(b) if b.tipo == "figura" else _una_linea(b.texto)
    return f"<!-- {etiqueta}: {contenido} -->"


def render_pagina(p: Pagina) -> str:
    partes: list[str] = []
    if p.encabezados:
        partes.append("\n".join(render_comentario(b) for b in p.encabezados))
    cuerpo = ""
    for i, b in enumerate(p.cuerpo):
        separador = "" if i == 0 else ("\n\n\n" if b.tipo in _DOBLE_BLANCO else "\n\n")
        cuerpo += separador + render_bloque(b)
    if cuerpo:
        partes.append(cuerpo)
    if p.pies:
        partes.append("\n".join(render_comentario(b) for b in p.pies))
    return "\n\n".join(partes) + "\n"


def render_documento(paginas: list[Pagina]) -> str:
    return "<!-- PageBreak -->\n\n".join(render_pagina(p) for p in paginas)


# --- fórmulas ---------------------------------------------------------------------------------

_RE_LETRAS_SUELTAS = re.compile(r"(?<![\\A-Za-z0-9])([A-Za-z0-9])((?: [A-Za-z0-9])+)(?![A-Za-z0-9])")
_RE_TEXT_CMD = re.compile(r"\\(?:text|mathrm|mathit|operatorname)\s*\{([^{}]*)\}")
_RE_COMANDO = re.compile(r"\\[a-zA-Z]+")


def compactar_latex(latex: str) -> str:
    r"""'P r o d u c t \, m a s s' -> 'Product \, mass'. En modo matemático los espacios entre
    letras no cambian el renderizado; el modelo de fórmulas los emite letra a letra."""
    return _RE_LETRAS_SUELTAS.sub(lambda m: m.group(1) + m.group(2).replace(" ", ""), latex)


def latex_es_fiable(latex: str, texto_pdf: str, umbral: float = 0.8, minimo_letras: int = 4) -> bool:
    """El modelo de fórmulas a veces alucina texto vecino a la fórmula. Las palabras que contenga
    el LaTeX (≥ minimo_letras) deben aparecer en el texto del PDF de esa región; si menos del
    `umbral` aparece, el LaTeX se descarta. Una fórmula sin palabras es fiable por definición."""
    if not latex.strip():
        return False
    pdf = re.sub(r"[^a-z]", "", texto_pdf.lower())
    palabras: list[str] = []
    for contenido in _RE_TEXT_CMD.findall(latex):
        palabras += re.findall(r"[A-Za-z]+", contenido)
    resto = _RE_TEXT_CMD.sub(" ", latex)
    resto = _RE_COMANDO.sub(" ", resto)
    palabras += re.findall(r"[A-Za-z]+", compactar_latex(resto))
    palabras = [p.lower() for p in palabras if len(p) >= minimo_letras]
    if not palabras:
        return True
    encontradas = sum(1 for p in palabras if p in pdf)
    return encontradas / len(palabras) >= umbral


# --- jerarquía de encabezados -----------------------------------------------------------------

def ajustar_niveles_encabezados(paginas: list[Pagina]) -> None:
    """Un encabezado sin numeración que está entre dos numerados de una misma sección (p. ej.
    'Determination of antioxidant activity.' entre 2.5.3 y 2.5.4) es un subtítulo: nivel del
    último numerado + 1. Si le sigue un numerado de nivel 1, o ninguno ('References'), es nivel 1."""
    secciones = [b for p in paginas for b in p.cuerpo if b.tipo == "seccion"]
    niveles_num = [nivel_por_numeracion(b.texto) for b in secciones]
    for i, b in enumerate(secciones):
        if niveles_num[i] is not None:
            b.nivel = niveles_num[i]
            continue
        anterior = next((n for n in reversed(niveles_num[:i]) if n is not None), None)
        siguiente = next((n for n in niveles_num[i + 1:] if n is not None), None)
        if anterior is not None and siguiente is not None and siguiente >= 2:
            b.nivel = min(anterior + 1, 5)
        else:
            b.nivel = 1


# --- portada y listas -------------------------------------------------------------------------

def elegir_titulo(candidatos, tam_mediana: float, min_len: int = 40, max_len: int = 300,
                  factor: float = 1.25) -> int | None:
    """Índice del bloque de la primera página que es el título del artículo: el de mayor tamaño de
    fuente entre los textos de 40-300 caracteres, siempre que sea claramente mayor (× factor) que
    el texto normal de la página. Docling etiqueta el título como section_header o como text."""
    mejor, mejor_tam = None, 0.0
    for i, (texto, tam, tipo) in enumerate(candidatos):
        if tipo not in ("seccion", "parrafo") or not (min_len <= len(texto.strip()) <= max_len):
            continue
        if tam > mejor_tam:
            mejor, mejor_tam = i, tam
    if mejor is None or mejor_tam < factor * max(tam_mediana, 1.0):
        return None
    return mejor


# «[14]» también cuando le sigue pegado el enlace de la referencia («[14][Official methods…](url)»)
_RE_MARCADOR_PDF = re.compile(r"^\s*(?:([•◦▪●○■□▸►–\-*]|\(?[0-9a-zA-Z]{1,3}[.)]|\[[0-9]{1,4}\])\s|\[[0-9]{1,4}\]\[)")
# "a Grupo ASPA, …": letra de afiliación en superíndice que Docling toma por viñeta
_RE_AFILIACION = re.compile(r"^\s*[a-z0-9]\s+[A-Z]")


def marcador_de_lista(texto: str, marcador_docling: str, enumerado: bool) -> str:
    """Marcador a anteponer al ítem de lista. Vacío si el texto del PDF ya trae su viñeta o número,
    o si Docling propone como marcador una palabra (letra de afiliación 'a', 'b'…): entonces se
    emite como párrafo."""
    if _RE_MARCADOR_PDF.match(texto) or _RE_AFILIACION.match(texto):
        return ""
    marcador = (marcador_docling or "").strip()
    if enumerado:
        return marcador or "1."
    if marcador and marcador.isalnum():
        return ""
    return "-"
