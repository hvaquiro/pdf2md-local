"""Docling -> bloques neutros. El texto de cada bloque se toma de la capa de texto del PDF.

Docling aporta la estructura (qué región es título, párrafo, tabla, figura, fórmula, encabezado o
pie); PyMuPDF aporta el texto exacto de cada región (pdf_texto.py); el orden de lectura del
cuerpo lo fija un corte XY sobre los bboxes (orden_lectura.py), que en la primera página de los
artículos de Elsevier acierta donde el modelo de Docling no.
"""
from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf as fitz
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import (
    AcceleratorDevice,
    AcceleratorOptions,
    PdfPipelineOptions,
    RapidOcrOptions,
    TableFormerMode,
)
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.doc import (
    ContentLayer,
    CoordOrigin,
    DocItemLabel,
    DoclingDocument,
    PictureItem,
    TableItem,
)

from pdf2md.md_modelo import Bloque, Celda, Pagina, Tabla
from pdf2md.md_render import (
    ajustar_niveles_encabezados,
    compactar_latex,
    elegir_titulo,
    es_numero_pagina,
    latex_es_fiable,
    marcador_de_lista,
    nivel_por_numeracion,
    normalizar_encabezado,
    parece_latex,
    respaldo_docling,
)
from pdf2md.orden_lectura import (
    VINETAS,
    agrupar_figuras,
    agrupar_lineas_en_bloques,
    celda_de_imagen,
    fusionar_residuales,
    ordenar_xy,
    repartir_por_pagina,
    vineta_huerfana,
)
from pdf2md.pdf_texto import (
    PaginaTexto,
    chars_en_bbox,
    chars_sin_consumir,
    componer_plano,
    componer_texto,
    diagnosticar_rejilla,
    enlaces_sin_texto_visible,
    es_indice_de_contenidos,
    extraer_pagina,
    fraccion_cubierta,
    imagenes_visibles,
    lineas_con_bbox,
    recortar_figura,
    region_en_blanco,
    rejilla_aprovechable,
    rejilla_por_posiciones,
    rejilla_rota,
    rescatar_cortes,
    tamano_medio,
)

_RE_NUM_EC = re.compile(r"\((\d{1,3}[a-z]?)\)\s*$")
_RE_SOLO_ENLACE = re.compile(r"^\[[^\]\n]+\]\([^)\s]+\)$")  # "[Check for updates](url)": botón, no texto perdido
_RE_SOLO_URL = re.compile(r"^\s*(https?://\S+|doi:\S+|www\.\S+)\s*$", re.I)
_TIPO_POR_LABEL = {
    DocItemLabel.TITLE: "titulo",
    DocItemLabel.SECTION_HEADER: "seccion",
    DocItemLabel.TEXT: "parrafo",
    DocItemLabel.PARAGRAPH: "parrafo",
    DocItemLabel.LIST_ITEM: "lista",
    DocItemLabel.CAPTION: "leyenda",
    DocItemLabel.FOOTNOTE: "nota",
    DocItemLabel.FORMULA: "formula",
    DocItemLabel.CODE: "codigo",
    DocItemLabel.PAGE_HEADER: "encabezado",
    DocItemLabel.PAGE_FOOTER: "pie",
    DocItemLabel.REFERENCE: "parrafo",
}
_TEXTO_INLINE = ("parrafo", "leyenda", "nota", "lista")
FIGURA_MINIMA_PT = 20.0  # iconos (ORCID, etc.) más pequeños que esto no se recortan como figura
MODELOS_POR_DEFECTO = Path.home() / ".cache" / "docling" / "models"


@dataclass
class OpcionesConversion:
    dpi: int = 200
    formulas: bool = True
    ocr: bool = False
    hilos: int = 16
    paginas: tuple[int, int] | None = None
    modelos: Path | None = None
    enderezadas: tuple[int, ...] = ()  # páginas apaisadas que `enderezar_apaisadas` redibujó


@dataclass
class ResultadoConversion:
    paginas: list[Pagina]
    stats: dict
    avisos: list[str] = field(default_factory=list)


@dataclass
class _Entrada:
    """Un ítem de Docling (o un bloque residual) ya convertido, con su bbox para ordenar."""
    bbox: tuple[float, float, float, float]
    bloques: list[Bloque]
    zona: str  # "encabezado" | "pie" | "cuerpo"
    orden: int
    figura_bbox: tuple[float, float, float, float] | None = None
    tam: float = 0.0
    fotos_celda: list = field(default_factory=list)  # [(bbox, Celda)]: imágenes dentro de una tabla


def ruta_modelos(op: OpcionesConversion) -> Path | None:
    for candidato in (op.modelos, os.environ.get("DOCLING_ARTIFACTS_PATH"), MODELOS_POR_DEFECTO):
        if candidato and Path(candidato).is_dir():
            return Path(candidato)
    return None


def construir_convertidor(op: OpcionesConversion) -> DocumentConverter:
    pipe = PdfPipelineOptions()
    modelos = ruta_modelos(op)
    if modelos is not None:
        pipe.artifacts_path = str(modelos)
    pipe.do_ocr = op.ocr
    if op.ocr:
        pipe.ocr_options = RapidOcrOptions(
            backend="torch",
            lang=["es"],  # PP-OCRv6 multilingüe unificado (español, inglés, portugués, latín)
        )
    pipe.do_table_structure = True
    pipe.table_structure_options.mode = TableFormerMode.ACCURATE
    pipe.table_structure_options.do_cell_matching = True
    pipe.do_formula_enrichment = op.formulas
    # CodeFormula genera hasta 4096 tokens por defecto: cuando alucina, tarda ~30 s por fórmula en CPU.
    pipe.code_formula_options.model_spec.max_new_tokens = 512
    pipe.generate_picture_images = False  # las figuras se recortan con PyMuPDF
    pipe.generate_page_images = False
    pipe.accelerator_options = AcceleratorOptions(num_threads=op.hilos, device=AcceleratorDevice.CPU)
    return DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipe)})


def _bbox_tl(item, doc: DoclingDocument, k: int = 0):
    prov = item.prov[k]
    bb = prov.bbox
    alto = doc.pages[prov.page_no].size.height
    if bb.coord_origin == CoordOrigin.BOTTOMLEFT:
        bb = bb.to_top_left_origin(alto)
    return (bb.l, bb.t, bb.r, bb.b)


def _area(bbox) -> float:
    return max(0.0, bbox[2] - bbox[0]) * max(0.0, bbox[3] - bbox[1])


def _union(a, b):
    return (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))


def _distancia(bbox, punto) -> float:
    x, y = punto
    dx = max(bbox[0] - x, 0, x - bbox[2])
    dy = max(bbox[1] - y, 0, y - bbox[3])
    return (dx * dx + dy * dy) ** 0.5


def _texto_item(item, pt: PaginaTexto, bbox) -> tuple[str, float]:
    chars = chars_en_bbox(pt, bbox)
    if chars:
        return componer_texto(chars), tamano_medio(chars)
    return respaldo_docling(getattr(item, "text", ""), bool(pt.chars)), 0.0


def _texto_ref(ref, doc: DoclingDocument, pt: PaginaTexto) -> tuple[str, tuple | None]:
    it = ref.resolve(doc)
    if it is None or not getattr(it, "prov", None):
        return "", None
    bb = _bbox_tl(it, doc)
    return _texto_item(it, pt, bb)[0], bb


def _texto_refs(refs, doc: DoclingDocument, pt: PaginaTexto) -> tuple[str, tuple | None]:
    textos, bbox = [], None
    for r in refs:
        t, bb = _texto_ref(r, doc, pt)
        if t:
            textos.append(t)
        if bb is not None:
            bbox = bb if bbox is None else _union(bbox, bb)
    return "\n".join(textos), bbox


def _es_marca_de_agua(bbox, marcas) -> bool:
    """True si más del 80 % del bbox del ítem cae dentro de un rótulo vertical de la página."""
    area = _area(bbox)
    for m in marcas:
        ancho = min(bbox[2], m[2]) - max(bbox[0], m[0])
        alto = min(bbox[3], m[3]) - max(bbox[1], m[1])
        if ancho > 0 and alto > 0 and area > 0 and ancho * alto / area > 0.8:
            return True
    return False


def _dentro(bbox, punto) -> bool:
    return bbox[0] <= punto[0] <= bbox[2] and bbox[1] <= punto[1] <= bbox[3]


def _centro(bbox) -> tuple[float, float]:
    return ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)


def _celdas_con_caja(item: TableItem, pt: PaginaTexto) -> list[tuple]:
    """[(celda, caja)] (origen arriba-izquierda) de las celdas de la tabla que traen bbox, en orden."""
    out = []
    for c in item.data.table_cells:
        cb = getattr(c, "bbox", None)
        if cb is not None:
            if cb.coord_origin == CoordOrigin.BOTTOMLEFT:
                cb = cb.to_top_left_origin(pt.alto)
            out.append((c, (cb.l, cb.t, cb.r, cb.b)))
    return out


def _cajas_de_celdas(item: TableItem, pt: PaginaTexto) -> list[tuple]:
    """Cajas (origen arriba-izquierda) de las celdas de la tabla que traen bbox."""
    return [caja for _, caja in _celdas_con_caja(item, pt)]


def _rehacer_por_posiciones(item: TableItem, pt: PaginaTexto, bbox) -> bool:
    """True si la rejilla de TableFormer no casa con el PDF y la capa de texto da una mejor: las
    celdas cubren menos de la mitad del texto de la región, o las filas del PDF quedan repartidas
    entre filas de la rejilla o fuera de toda celda, con las salvaguardas de `rejilla_rota` y
    `rejilla_aprovechable`."""
    celdas = _celdas_con_caja(item, pt)
    if fraccion_cubierta(pt, bbox, [caja for _, caja in celdas]) < 0.5:
        return True
    d = diagnosticar_rejilla(pt, bbox, [(c.start_row_offset_idx, c.row_span == 1 and not c.column_header, caja)
                                        for c, caja in celdas])
    if not rejilla_rota(d):
        return False
    filas, _ = rejilla_por_posiciones(lineas_con_bbox(chars_en_bbox(pt, bbox, consumir=False)))
    return rejilla_aprovechable(filas)


def _tabla_desde(item: TableItem, doc: DoclingDocument, pt: PaginaTexto, bbox,
                 imagenes=(), por_posiciones: bool = False) -> tuple[Tabla, tuple, list]:
    """(tabla, bbox con leyenda y notas, [(bbox_imagen, Celda)]). Cada imagen de `imagenes` (fotos
    dentro de la tabla) se asigna a la celda de su fila y columna, que se crea si no existe.
    Con `por_posiciones` las celdas no salen de Docling sino de la capa de texto de la región
    (`rejilla_por_posiciones`), para cuando la rejilla de TableFormer no casa con el PDF."""
    celdas: list[Celda] = []
    simples: list[tuple[int, int, tuple]] = []  # celdas sin combinar con bbox: definen filas y columnas
    if por_posiciones:
        filas, cabecera = rejilla_por_posiciones(lineas_con_bbox(chars_en_bbox(pt, bbox)))
        n_filas, n_cols = len(filas), 1 + max((c for fila in filas for c, _ in fila), default=0)
        for f, fila in enumerate(filas):
            ocupadas = [c for c, _ in fila] + [n_cols]
            libres = set(range(n_cols)) - set(ocupadas)
            for k, (c, t) in enumerate(fila):
                # En la cabecera, una celda abarca hasta la siguiente celda ocupada de su fila
                span = ocupadas[k + 1] - c if f < cabecera else 1
                celdas.append(Celda(f, c, 1, span, t, f < cabecera))
                libres -= set(range(c, c + span))
            celdas += [Celda(f, c, texto="", encabezado=f < cabecera) for c in sorted(libres)]
        celdas.sort(key=lambda c: (c.fila, c.col))
    else:
        n_filas, n_cols = item.data.num_rows, item.data.num_cols
    # letras que el borde de una celda deja fuera de toda celda («s|weet»): van con
    # la celda que tiene la mayoría de su palabra en vez de perderse con los restos de la región
    extra = {} if por_posiciones else rescatar_cortes(pt, bbox, _cajas_de_celdas(item, pt))
    k_caja = -1
    for c in () if por_posiciones else item.data.table_cells:
        texto = None
        cb = getattr(c, "bbox", None)
        if cb is not None:
            k_caja += 1
            if cb.coord_origin == CoordOrigin.BOTTOMLEFT:
                cb = cb.to_top_left_origin(pt.alto)
            chars = chars_en_bbox(pt, (cb.l, cb.t, cb.r, cb.b), tol=0.5)
            for ch in extra.get(k_caja, ()):
                if not ch.consumido:
                    ch.consumido = True
                    chars.append(ch)
            if chars:
                texto = componer_texto(chars)
                if c.row_span == 1 and c.col_span == 1:
                    simples.append((c.start_row_offset_idx, c.start_col_offset_idx, (cb.l, cb.t, cb.r, cb.b)))
        if texto is None:
            texto = respaldo_docling(c.text, bool(pt.chars))
        celdas.append(Celda(c.start_row_offset_idx, c.start_col_offset_idx, c.row_span, c.col_span,
                            texto, bool(c.column_header)))  # <th> solo en cabeceras de columna
    chars_en_bbox(pt, bbox)  # consume restos dentro de la tabla (texto sin celda asignada)
    caption, bb_cap = _texto_refs(item.captions, doc, pt)
    notas, bb_notas = [], None
    for r in item.footnotes:
        t, bb = _texto_ref(r, doc, pt)
        if t:
            notas.append(t)
        if bb is not None:
            bb_notas = bb if bb_notas is None else _union(bb_notas, bb)
    total = bbox
    for bb in (bb_cap, bb_notas):
        if bb is not None:
            total = _union(total, bb)
    fotos = []
    for img in imagenes:
        pos = celda_de_imagen(simples, img)
        if pos is None:
            continue
        celda = next((c for c in celdas if (c.fila, c.col) == pos), None)
        if celda is None:
            celda = Celda(pos[0], pos[1])
            celdas.append(celda)
        fotos.append((img, celda))
    fotos.sort(key=lambda f: (f[1].fila, f[1].col, f[0][1]))  # numeración en el orden de las celdas
    return Tabla(n_filas, n_cols, celdas, caption, notas), total, fotos


def _zonas(items_pagina, doc) -> tuple[float, float]:
    """(límite inferior de la zona de encabezado, límite superior de la zona de pie) según los
    ítems 'furniture' de Docling (items_pagina: [(item, k)], ver repartir_por_pagina); sin ellos, franjas fijas del 6 % arriba y abajo."""
    alto = doc.pages[items_pagina[0][0].prov[items_pagina[0][1]].page_no].size.height if items_pagina else 842.0
    cab = [_bbox_tl(it, doc, k)[3] for it, k in items_pagina if it.label == DocItemLabel.PAGE_HEADER]
    pie = [_bbox_tl(it, doc, k)[1] for it, k in items_pagina if it.label == DocItemLabel.PAGE_FOOTER]
    return (max(cab) + 2 if cab else alto * 0.06), (min(pie) - 2 if pie else alto * 0.94)


def convertir(pdf: Path, nombre_doc: str, dir_figuras: Path, op: OpcionesConversion,
              convertidor: DocumentConverter | None = None) -> ResultadoConversion:
    t0 = time.time()
    conv = convertidor or construir_convertidor(op)
    kwargs = {"page_range": op.paginas} if op.paginas else {}
    res = conv.convert(str(pdf), **kwargs)
    doc: DoclingDocument = res.document
    estado = getattr(res.status, "name", str(res.status))
    avisos = [] if estado == "SUCCESS" else [f"estado docling: {estado}"]

    fdoc = fitz.open(str(pdf))
    total = len(fdoc)
    numeros = sorted(doc.pages.keys())
    textos = {n: extraer_pagina(fdoc[n - 1], n) for n in numeros}
    for n in op.enderezadas:
        if n in textos:
            textos[n].enderezada = True
    for n in numeros:
        w, h = doc.pages[n].size.width, doc.pages[n].size.height
        if abs(w - textos[n].ancho) > 1 or abs(h - textos[n].alto) > 1:
            avisos.append(f"pagina {n}: tamaño docling {w:.0f}x{h:.0f} != pymupdf "
                          f"{textos[n].ancho:.0f}x{textos[n].alto:.0f}")

    stats = {"paginas": len(numeros), "bloques": 0, "tablas": 0, "figuras": 0, "figuras_omitidas": 0,
             "formulas": 0, "formulas_sin_latex": 0, "enlaces": sum(len(t.urls) for t in textos.values()),
             "sin_clasificar": 0}

    # 1) Ítems de ambas capas (cuerpo y 'furniture' = encabezados/pies); leyendas y notas de
    #    tablas/figuras se renderizan con su padre.
    items = []
    omitidos: set[str] = set()
    capas = {ContentLayer.BODY, ContentLayer.FURNITURE}
    for item, _nivel in doc.iterate_items(with_groups=False, included_content_layers=capas):
        if not getattr(item, "prov", None):
            continue
        if isinstance(item, (TableItem, PictureItem)):
            omitidos.update(r.cref for r in item.captions)
            omitidos.update(r.cref for r in item.footnotes)
        items.append(item)
    items = [it for it in items if it.self_ref not in omitidos]
    # Un ítem con varias procedencias (párrafo que sigue en otra columna o página) da un
    # fragmento (item, k) por cada una, en su página.
    por_pagina = repartir_por_pagina(items, numeros)

    paginas: list[Pagina] = []
    for n in numeros:
        pt = textos[n]
        its = por_pagina[n]
        zona_cab, zona_pie = _zonas(its, doc)
        entradas: list[_Entrada] = []
        # Encabezados y pies se reconstruyen por líneas visuales del PDF, no por ítems de Docling:
        # Docling parte líneas como "Available online…" en varios ítems y omite a veces el encabezado izquierdo.
        chars_zona: dict[str, list] = {"encabezado": [], "pie": []}
        # Figuras: los paneles cercanos (a, b, c… de una misma figura) se recortan como una sola.
        # Fotos dentro de una tabla: Docling no las da (o da alguna suelta); se toman las imágenes
        # visibles del PDF que caen en la tabla y se emiten dentro de su celda.
        pagina_pdf = fdoc[n - 1]
        tablas_bb = {it.self_ref: _bbox_tl(it, doc) for it, k in its if k == 0 and isinstance(it, TableItem)
                     and any((c.text or "").strip() for c in it.data.table_cells)}
        visibles = imagenes_visibles(pagina_pdf, FIGURA_MINIMA_PT) if tablas_bb else []
        fotos_de = {ref: [img for img in visibles if _dentro(bb, _centro(img))] for ref, bb in tablas_bb.items()}
        con_fotos = [tablas_bb[ref] for ref, imgs in fotos_de.items() if imgs]
        fig_items = [it for it, k in its if k == 0 and isinstance(it, PictureItem)]
        fig_bboxes = [_bbox_tl(it, doc) for it in fig_items]
        grandes = [i for i, bb in enumerate(fig_bboxes)
                   if bb[2] - bb[0] >= FIGURA_MINIMA_PT and bb[3] - bb[1] >= FIGURA_MINIMA_PT
                   and not any(_dentro(tb, _centro(bb)) for tb in con_fotos)  # ya va en su celda
                   and not region_en_blanco(pagina_pdf, bb)]  # Docling "ve" imágenes recortadas por un clip
        stats["figuras_omitidas"] += len(fig_items) - len(grandes)
        figura_de: dict[str, tuple | None] = {}  # self_ref -> (bbox_union, miembros) o None si es panel secundario
        for g in agrupar_figuras([fig_bboxes[i] for i in grandes], margen=24):  # paneles a ~15-18 pt
            miembros = [fig_items[grandes[k]] for k in g]
            union = fig_bboxes[grandes[g[0]]]
            for k in g[1:]:
                union = _union(union, fig_bboxes[grandes[k]])
            for m in miembros:
                figura_de[m.self_ref] = None
            figura_de[miembros[0].self_ref] = (union, miembros)
        # 2) Asignar caracteres del PDF: primero los bboxes más pequeños (leyendas antes que figuras).
        for orden, (it, k) in sorted(enumerate(its), key=lambda p: _area(_bbox_tl(p[1][0], doc, p[1][1]))):
            bbox = _bbox_tl(it, doc, k)
            if _es_marca_de_agua(bbox, pt.marcas):
                continue  # rótulo vertical sobre el cuerpo: su bbox se tragaría el arranque de las líneas
            if k > 0 and isinstance(it, (TableItem, PictureItem)):
                continue  # tabla o figura con varias procedencias: su texto queda como residual
            if isinstance(it, TableItem):
                if not any((c.text or "").strip() for c in it.data.table_cells):
                    stats["tablas_vacias"] = stats.get("tablas_vacias", 0) + 1
                    continue  # tabla fantasma de Docling: no consume texto, que pasa a otros bloques
                # Un índice con puntos guía no es una tabla: Docling lo toma por una de 2-3 columnas y su
                # rejilla corta las palabras (índices de tesis). Sale como párrafo, con los saltos del PDF.
                if pt.chars:
                    texto_region = componer_texto(chars_en_bbox(pt, bbox, consumir=False))
                    if es_indice_de_contenidos(texto_region):
                        texto_region = componer_texto(chars_en_bbox(pt, bbox))
                        entradas.append(_Entrada(bbox, [Bloque("parrafo", texto=texto_region)], "cuerpo", orden))
                        stats["indices_como_texto"] = stats.get("indices_como_texto", 0) + 1
                        continue
                # TableFormer puede dar una rejilla que no casa con las celdas del PDF (celdas omitidas
                # o filas desplazadas): la tabla perdía texto o mezclaba filas. Se rehace con la capa de texto.
                por_posiciones = _rehacer_por_posiciones(it, pt, bbox)
                if por_posiciones:
                    stats["tablas_por_posiciones"] = stats.get("tablas_por_posiciones", 0) + 1
                tabla, bb_total, fotos = _tabla_desde(it, doc, pt, bbox, fotos_de.get(it.self_ref, ()),
                                                      por_posiciones=por_posiciones)
                entradas.append(_Entrada(bb_total, [Bloque("tabla", tabla=tabla)], "cuerpo", orden,
                                         fotos_celda=fotos))
                stats["tablas"] += 1
                stats["figuras"] += len(fotos)
            elif isinstance(it, PictureItem):
                info = figura_de.get(it.self_ref, "omitida")
                if info == "omitida":
                    # icono, foto de una celda o imagen invisible: no se recorta, pero la leyenda que
                    # Docling le colgó (la de la figura visible de al lado) no se puede perder
                    leyenda, bb_cap = _texto_refs(it.captions, doc, pt)
                    if leyenda and bb_cap:
                        entradas.append(_Entrada(bb_cap, [Bloque("leyenda", texto=leyenda)], "cuerpo", orden))
                    continue
                if info is None:
                    continue  # panel secundario ya incluido en su figura
                bbox, miembros = info
                alt = componer_plano(chars_en_bbox(pt, bbox))  # texto interno completo de la figura
                refs = [r for m in miembros for r in m.captions]
                leyenda, bb_cap = _texto_refs(refs, doc, pt)
                bloques = [Bloque("leyenda", texto=leyenda)] if leyenda else []
                bloques.append(Bloque("figura", alt=alt))
                bb_total = _union(bbox, bb_cap) if bb_cap else bbox
                entradas.append(_Entrada(bb_total, bloques, "cuerpo", orden, figura_bbox=bbox))
                stats["figuras"] += 1
            else:
                tipo = _TIPO_POR_LABEL.get(it.label, "parrafo")
                if k > 0 and tipo not in ("nota", "leyenda", "encabezado", "pie"):
                    tipo = "parrafo"  # continuación: sin viñeta, título ni LaTeX (van con prov[0])
                chars = chars_en_bbox(pt, bbox)
                # el texto de Docling es el del ítem entero: solo sirve de respaldo para prov[0]
                respaldo = respaldo_docling(getattr(it, "text", ""), bool(pt.chars)) if k == 0 else ""
                texto = componer_texto(chars) if chars else respaldo
                tam = tamano_medio(chars)
                if tipo == "formula" and not texto.strip() and pt.chars:
                    continue  # región sin texto visible (ya consumido por otro ítem, u oculto)
                if tipo == "formula":
                    crudo = it.text or ""
                    latex = compactar_latex(crudo) if (parece_latex(crudo) and latex_es_fiable(crudo, texto)) else None
                    m = _RE_NUM_EC.search(texto.replace("\n", " "))
                    numero = f"({m.group(1)})" if (m and latex) else None
                    stats["formulas"] += 1
                    stats["formulas_sin_latex"] += latex is None
                    entradas.append(_Entrada(bbox, [Bloque("formula", texto=texto, latex=latex,
                                                          numero_ecuacion=numero)], "cuerpo", orden))
                    continue
                if not texto.strip():
                    continue
                corto = len(texto) <= 160 and texto.count("\n") <= 1
                if tipo in ("seccion", "titulo") and _RE_SOLO_URL.match(texto):
                    tipo = "parrafo"
                if tipo in ("parrafo", "seccion", "lista", "nota") and corto and bbox[1] >= zona_pie - 12:
                    tipo = "pie"
                if tipo in ("encabezado", "pie") and chars:
                    chars_zona[tipo].extend(chars)
                    continue
                if tipo in ("encabezado", "pie") and es_numero_pagina(texto):
                    zona = "encabezado" if bbox[3] <= pt.alto / 2 else "pie"
                    entradas.append(_Entrada(bbox, [Bloque("numero_pagina", texto=texto)], zona, orden))
                elif tipo in ("encabezado", "pie"):
                    entradas.append(_Entrada(bbox, [Bloque(tipo, texto=texto)], tipo, orden))
                elif tipo == "seccion":
                    texto = normalizar_encabezado(texto)
                    nivel = nivel_por_numeracion(texto) or getattr(it, "level", 1) or 1
                    entradas.append(_Entrada(bbox, [Bloque("seccion", texto=texto, nivel=nivel)], "cuerpo",
                                             orden, tam=tam))
                elif tipo == "lista":
                    marcador = marcador_de_lista(texto, getattr(it, "marker", "") or "", bool(getattr(it, "enumerated", False)))
                    if marcador:
                        entradas.append(_Entrada(bbox, [Bloque("lista", texto=texto, marcador_lista=marcador)],
                                                 "cuerpo", orden, tam=tam))
                    else:
                        entradas.append(_Entrada(bbox, [Bloque("parrafo", texto=texto)], "cuerpo", orden, tam=tam))
                else:
                    entradas.append(_Entrada(bbox, [Bloque(tipo, texto=texto)], "cuerpo", orden, tam=tam))

        # 3) Texto que ningún ítem cubrió: por zona (encabezado/pie) o, en el cuerpo, agrupado en
        #    bloques por posición para que el corte XY lo coloque donde estaba.
        #    Una viñeta suelta con un ítem de texto a su derecha es su marcador: el ítem pasa a lista.
        residual_cuerpo = []
        items_texto = [e for e in entradas if e.zona == "cuerpo" and len(e.bloques) == 1
                       and e.bloques[0].tipo in ("lista", "parrafo")]
        for c in chars_sin_consumir(pt):
            if c.y1 <= zona_cab:
                chars_zona["encabezado"].append(c)
            elif c.y0 >= zona_pie:
                chars_zona["pie"].append(c)
            elif c.c in VINETAS and (i := vineta_huerfana((c.x0, c.y0, c.x1, c.y1),
                                                          [e.bbox for e in items_texto])) is not None:
                items_texto[i].bloques[0].tipo = "lista"
                stats["vinetas_absorbidas"] = stats.get("vinetas_absorbidas", 0) + 1
            else:
                residual_cuerpo.append(c)
        for bb, lineas in agrupar_lineas_en_bloques(lineas_con_bbox(residual_cuerpo)):
            texto = "\n".join(lineas).strip()
            if texto and _RE_SOLO_ENLACE.match(texto):
                entradas.append(_Entrada(bb, [Bloque("parrafo", texto=texto)], "cuerpo", 10_000))
            elif texto:
                entradas.append(_Entrada(bb, [Bloque("sin_clasificar", texto=texto)], "cuerpo", 10_000))
                stats["sin_clasificar"] += len(lineas)
        for zona, chars in chars_zona.items():
            for bb, lineas in agrupar_lineas_en_bloques(lineas_con_bbox(chars), solo_continuacion=True):
                texto = "\n".join(lineas).strip()
                if texto:
                    tipo = "numero_pagina" if es_numero_pagina(texto) else zona
                    entradas.append(_Entrada(bb, [Bloque(tipo, texto=texto)], zona, 10_000))

        # 4) Título del artículo: en la primera página, el encabezado de sección de mayor tamaño.
        if n == numeros[0]:
            # Docling etiqueta el título como section_header o como text; el nombre de la revista es
            # corto y a veces más grande. Se elige por tamaño de fuente entre los textos largos.
            cuerpo_txt = [e for e in entradas if e.zona == "cuerpo" and e.tam > 0
                          and e.bloques[0].tipo in ("seccion", "parrafo")]
            tams = sorted(e.tam for e in cuerpo_txt)
            mediana = tams[len(tams) // 2] if tams else 0.0
            idx = elegir_titulo([(e.bloques[0].texto, e.tam, e.bloques[0].tipo) for e in cuerpo_txt], mediana)
            if idx is not None:
                cuerpo_txt[idx].bloques[0].tipo = "titulo"

        # 5) Enlaces sin texto debajo (iconos ORCID, CrossMark): al bloque de cuerpo más cercano.
        #    También los que solo tienen texto dentro de una figura (su alt no lleva enlaces).
        cuerpo = [e for e in entradas if e.zona == "cuerpo"]
        figuras = [e.figura_bbox for e in entradas if e.figura_bbox is not None]
        for rect, url in enlaces_sin_texto_visible(pt, figuras):
            enlace = f"[{url}]({url})"
            if not cuerpo:
                entradas.append(_Entrada(rect, [Bloque("parrafo", texto=enlace)], "cuerpo", 20_000))
                continue
            centro = ((rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2)
            cercana = min(cuerpo, key=lambda e: _distancia(e.bbox, centro))
            ultimo = cercana.bloques[-1]
            if ultimo.tipo in _TEXTO_INLINE:
                ultimo.texto = ultimo.texto.rstrip() + f" {enlace}"
            else:
                cercana.bloques.append(Bloque("parrafo", texto=enlace))

        # 6) Orden: encabezados y pies por posición; cuerpo por corte XY.
        pagina = Pagina(n, total)
        for e in sorted((e for e in entradas if e.zona == "encabezado"), key=lambda e: (e.bbox[1], e.bbox[0])):
            pagina.encabezados.extend(e.bloques)
        for e in sorted((e for e in entradas if e.zona == "pie"), key=lambda e: (e.bbox[1], e.bbox[0])):
            pagina.pies.extend(e.bloques)
        ordenadas = [e for _bb, e in ordenar_xy([(e.bbox, e) for e in cuerpo])]

        # 7) Un bloque residual justo debajo de un párrafo es su continuación (Docling recortó el bbox).
        def _unir(prev: _Entrada, res: _Entrada) -> _Entrada:
            prev.bloques[-1].texto = prev.bloques[-1].texto.rstrip() + "\n" + res.bloques[0].texto.lstrip()
            prev.bbox = _union(prev.bbox, res.bbox)
            stats["sin_clasificar"] -= res.bloques[0].texto.count("\n") + 1
            stats["sin_clasificar_fusionadas"] = stats.get("sin_clasificar_fusionadas", 0) + 1
            return prev
        ordenadas = [e for _bb, _tipo, e in fusionar_residuales(
            [(e.bbox, e.bloques[-1].tipo, e) for e in ordenadas], unir=_unir)]
        contador = 0
        for e in ordenadas:
            for img, celda in e.fotos_celda:
                contador += 1
                nombre = f"{n}.{contador}.jpg"
                recortar_figura(fdoc[n - 1], img, op.dpi, dir_figuras / nombre)
                celda.figuras.append(f"figures/{nombre_doc}/{nombre}")
            if e.figura_bbox is not None:
                contador += 1
                nombre = f"{n}.{contador}.jpg"
                recortar_figura(fdoc[n - 1], e.figura_bbox, op.dpi, dir_figuras / nombre)
                for b in e.bloques:
                    if b.tipo == "figura":
                        b.figura_ruta = f"figures/{nombre_doc}/{nombre}"
            pagina.cuerpo.extend(e.bloques)
        stats["bloques"] += len(pagina.encabezados) + len(pagina.cuerpo) + len(pagina.pies)
        paginas.append(pagina)

    ajustar_niveles_encabezados(paginas)
    stats["segundos"] = round(time.time() - t0, 1)
    fdoc.close()
    return ResultadoConversion(paginas, stats, avisos)

