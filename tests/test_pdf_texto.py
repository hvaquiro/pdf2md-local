from pathlib import Path

import pymupdf as fitz
import pytest

from pdf2md.pdf_texto import (
    chars_en_bbox,
    chars_sin_consumir,
    componer_plano,
    componer_texto,
    enlaces_sin_texto_visible,
    es_indice_de_contenidos,
    extraer_pagina,
    fraccion_cubierta,
    paginas_escaneadas,
    recortar_figura,
    rejilla_por_posiciones,
    reparar_tounicode,
    tiene_capa_texto,
)


@pytest.fixture
def pdf_sintetico() -> fitz.Document:
    doc = fitz.open()
    page = doc.new_page(width=300, height=200)
    page.insert_text((20, 40), "Hola mundo", fontsize=12)
    page.insert_text((20, 60), "Segunda linea", fontsize=12)
    page.insert_text((20, 100), "m", fontsize=12)
    page.insert_text((30, 95), "2", fontsize=7)      # superíndice simulado (más pequeño y elevado)
    page.insert_text((20, 140), "A", fontsize=12)
    page.insert_text((29, 143), "0", fontsize=7)     # subíndice simulado (más pequeño y bajado)
    page.insert_link({"kind": fitz.LINK_URI, "from": fitz.Rect(20, 30, 50, 42), "uri": "https://ej.org"})
    return doc


def test_extraer_pagina_lineas_y_urls(pdf_sintetico):
    pt = extraer_pagina(pdf_sintetico[0], 1)
    assert (pt.ancho, pt.alto) == (300, 200)
    assert "https://ej.org" in pt.urls
    texto = componer_texto(pt.chars)
    assert texto.splitlines()[0].startswith("[Hola](https://ej.org)")
    assert "Segunda linea" in texto


def test_url_con_espacio_o_retorno_al_final_se_limpia(pdf_sintetico):
    """Algunos documentos exportados desde Word dejan en la anotación una URL con espacio o
    retorno de carro al final (o nbsp) y el enlace salía roto antes del paréntesis de cierre."""
    pagina = pdf_sintetico[0]
    pagina.insert_link({"kind": fitz.LINK_URI, "from": fitz.Rect(20, 50, 80, 62),
                        "uri": "https://ej.org/doc.pdf \r"})
    pdf_sintetico.reload_page(pagina)
    assert "https://ej.org/doc.pdf" in extraer_pagina(pdf_sintetico[0], 1).urls


def test_chars_en_bbox_consume_una_sola_vez(pdf_sintetico):
    pt = extraer_pagina(pdf_sintetico[0], 1)
    primera = chars_en_bbox(pt, (0, 25, 300, 45))
    assert componer_plano(primera) == "Hola mundo"
    assert chars_en_bbox(pt, (0, 25, 300, 45)) == []          # ya consumidos
    restantes = componer_plano(chars_sin_consumir(pt))
    assert "Hola" not in restantes and "Segunda linea" in restantes


def test_super_y_subindices(pdf_sintetico):
    pt = extraer_pagina(pdf_sintetico[0], 1)
    assert "m²" in componer_texto(chars_en_bbox(pt, (0, 85, 300, 105)))
    assert "A₀" in componer_texto(chars_en_bbox(pt, (0, 128, 300, 150)))


def test_tiene_capa_texto(pdf_sintetico):
    assert tiene_capa_texto(pdf_sintetico)
    vacio = fitz.open()
    vacio.new_page()
    assert not tiene_capa_texto(vacio)


def test_enlace_cuyo_texto_cae_en_una_figura_cuenta_como_sin_texto(pdf_sintetico):
    """En algunos artículos de Elsevier bajo el icono CrossMark hay una «T» oculta; la figura la
    absorbe en su alt (texto plano) y el enlace se perdía si no se trataba como enlace sin texto."""
    pt = extraer_pagina(pdf_sintetico[0], 1)
    assert enlaces_sin_texto_visible(pt, []) == []
    sin_texto = enlaces_sin_texto_visible(pt, [(10, 25, 60, 45)])
    assert [url for _rect, url in sin_texto] == ["https://ej.org"]


def _imagen(ancho: int, alto: int, con_contenido: bool) -> fitz.Pixmap:
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, ancho, alto), False)
    pix.set_rect(pix.irect, (250, 245, 230))                   # fondo crema casi liso
    if con_contenido:                                          # «renglones» oscuros, como un escaneo
        for y in range(10, alto - 10, 12):
            pix.set_rect(fitz.IRect(10, y, ancho - 10, y + 5), (20, 20, 20))
    return pix


def test_paginas_decorativas_sin_texto_no_activan_ocr(pdf_sintetico):
    """Páginas sin texto que solo contienen una franja de dibujos vectoriales o una imagen de fondo
    casi lisa no muestran texto que leer y no deben pasar todo el documento a OCR."""
    franja = pdf_sintetico.new_page(width=300, height=200)
    for x in range(0, 300, 6):
        franja.draw_line((x, 0), (x + 20, 25), color=(0.7, 0.7, 0.3))
    fondo = pdf_sintetico.new_page(width=300, height=200)
    fondo.insert_image(fondo.rect, pixmap=_imagen(200, 130, False))
    assert tiene_capa_texto(pdf_sintetico)


def test_pagina_escaneada_activa_ocr(pdf_sintetico):
    escaneo = pdf_sintetico.new_page(width=300, height=200)
    escaneo.insert_image(escaneo.rect, pixmap=_imagen(200, 130, True))
    assert not tiene_capa_texto(pdf_sintetico)


def test_pagina_de_imagen_con_tamano_propio_no_activa_ocr(pdf_sintetico):
    """Manuscritos aceptados con páginas A4 de texto que terminan con el resumen gráfico en una
    página de dimensiones propias (p. ej. 700 × 280 pt): una hoja escaneada dentro de un documento
    digital tiene el tamaño de las demás; una página cortada a la medida de una imagen es figura."""
    grafico = pdf_sintetico.new_page(width=420, height=170)
    grafico.insert_image(grafico.rect, pixmap=_imagen(200, 80, True))
    assert tiene_capa_texto(pdf_sintetico)
    for _ in range(2):                                              # mismo tamaño, apaisada: sí cuenta
        girada = pdf_sintetico.new_page(width=200, height=300)
        girada.insert_image(girada.rect, pixmap=_imagen(130, 200, True))
    assert not tiene_capa_texto(pdf_sintetico)


def test_fotos_a_pagina_completa_en_un_libro_digital_no_activan_ocr(pdf_sintetico):
    """Libros digitales maquetados en InDesign con portada, separadores y fotos a página completa
    (1-15 % de las páginas): un escaneo lo es en la mayoría de sus páginas; pasar el libro entero
    a OCR degradaría las páginas digitales."""
    for _ in range(9):
        pdf_sintetico.new_page(width=300, height=200).insert_text((20, 40), "Texto de la pagina", fontsize=12)
    foto = pdf_sintetico.new_page(width=300, height=200)
    foto.insert_image(foto.rect, pixmap=_imagen(200, 130, True))
    assert tiene_capa_texto(pdf_sintetico)
    assert paginas_escaneadas(pdf_sintetico) == [11]


def test_fondo_compartido_con_paginas_de_texto_no_activa_ocr(pdf_sintetico):
    """Cuando una página sin texto muestra a página completa la misma imagen de fondo (mismo digest)
    que otras páginas que sí tienen texto, se trata de un fondo repetido decorativo y no de un escaneo."""
    fondo = _imagen(200, 130, True)
    pdf_sintetico[0].insert_image(pdf_sintetico[0].rect, pixmap=fondo, overlay=False)
    separadora = pdf_sintetico.new_page(width=300, height=200)
    separadora.insert_image(separadora.rect, pixmap=fondo)
    assert tiene_capa_texto(pdf_sintetico)


def _pdf_con_differences(base_font: str, differences: str, to_unicode: bytes | None = None) -> fitz.Document:
    doc = fitz.open()
    doc.new_page().insert_text((50, 50), "ABC", fontname="helv", fontsize=12)
    doc = fitz.open("pdf", doc.tobytes())
    xref = doc[0].get_fonts(full=True)[0][0]
    doc.xref_set_key(xref, "BaseFont", f"/{base_font}")
    doc.xref_set_key(xref, "Encoding", f"<< /Type /Encoding /Differences [ {differences} ] >>")
    if to_unicode is not None:
        tu = doc.get_new_xref()
        doc.update_object(tu, "<<>>")
        doc.update_stream(tu, to_unicode)
        doc.xref_set_key(xref, "ToUnicode", f"{tu} 0 R")
    return fitz.open("pdf", doc.tobytes())   # MuPDF guarda en caché la fuente ya cargada


def _reparado(doc: fitz.Document) -> fitz.Document:
    assert reparar_tounicode(doc) == 1
    return fitz.open("pdf", doc.tobytes())


def test_reparar_tounicode_nombres_de_glifo_de_fuentes_de_simbolos():
    """Elsevier (AdvP4C4E74) y otras editoriales (MathematicalPi) nombran sus glifos «C0», «H11034»…;
    MuPDF no conoce su Unicode y devuelve U+FFFD. El código cambia de un PDF a otro, pero el nombre
    del glifo en /Differences es constante."""
    doc = _pdf_con_differences("MNGBLD+AdvP4C4E74", "65 /C0 /C14 /C2")
    assert _reparado(doc)[0].get_text().strip() == "−°×"
    doc = _pdf_con_differences("MEMAAH+MathematicalPi-One", "65 /H11002 /H9262 /H11034")
    assert _reparado(doc)[0].get_text().strip() == "−μ°"
    doc = _pdf_con_differences("OKFAIG+AdvP4C4E74", "65 /C25 /C0 /C0")
    assert _reparado(doc)[0].get_text().strip() == "≈−−"
    doc = _pdf_con_differences("OKFAIE+AdvP4C4E5E", "65 /C18 /C19 /C19")
    assert _reparado(doc)[0].get_text().strip() == "`´´"
    doc = _pdf_con_differences("OKFAIB+AdvP4C4E59", "65 /C18 /C22 /C22")
    assert _reparado(doc)[0].get_text().strip() == "`¯¯"
    doc = _pdf_con_differences("ABCDEF+AdvP4C4E46", "65 /C16 /C17 /C17")
    assert _reparado(doc)[0].get_text().strip() == "())"


def test_reparar_tounicode_glifos_sueltos_por_nombre():
    """Glifos adicionales en fuentes técnicas: Δ en MathTime (RMTMI), α en AdvP4C4E51, ™ en AdvPSSym,
    y paréntesis grandes (C0/C1) y sumatoria (X -> ∑) en la fuente de extensiones AdvP4C4E46."""
    doc = _pdf_con_differences("OKDPJE+RMTMI", "65 /Delta1 /Delta1 /Delta1")
    assert _reparado(doc)[0].get_text().strip() == "ΔΔΔ"
    doc = _pdf_con_differences("KLEHAE+AdvP4C4E51", "65 /C11 /C11 /C11")
    assert _reparado(doc)[0].get_text().strip() == "ααα"
    doc = _pdf_con_differences("DBHCJN+AdvPSSym", "65 /C212 /C176 /C211")
    assert _reparado(doc)[0].get_text().strip() == "™°©"
    doc = _pdf_con_differences("BGJOGC+AdvP4C4E46", "65 /C0 /C1 /X")
    assert _reparado(doc)[0].get_text().strip() == "()∑"


def test_reparar_tounicode_conserva_lo_que_ya_mapeaba_y_no_toca_otras_fuentes():
    cmap = (b"/CIDInit /ProcSet findresource begin 12 dict begin begincmap\n"
            b"1 begincodespacerange <43> <43> endcodespacerange\n"
            b"1 beginbfchar\n<43> <00BC>\nendbfchar\nendcmap CMapName currentdict /CMap defineresource pop end end")
    doc = _pdf_con_differences("F11+AdvP4C4E74", "65 /C6 /C15 /onequarter", cmap)
    assert _reparado(doc)[0].get_text().strip() == "±•¼"
    otra = _pdf_con_differences("Helvetica", "65 /C0 /C14 /C2")
    assert reparar_tounicode(otra) == 0


def test_recortar_figura(pdf_sintetico, tmp_path: Path):
    destino = tmp_path / "1.1.jpg"
    recortar_figura(pdf_sintetico[0], (10, 20, 110, 70), dpi=144, destino=destino)
    pix = fitz.Pixmap(str(destino))
    assert destino.exists() and abs(pix.width - 200) <= 1 and abs(pix.height - 100) <= 1


# --- casos reales observados en PDF científicos ---------------------------------------------

def _char(c, x0, x1, y0=100.0, y1=112.0, linea=0, seg=0, seq=0, tam=10.0, sup=False, sub=False, url=None):
    from pdf2md.pdf_texto import Char
    return Char(c, x0, y0, x1, y1, linea, sup, sub, url, seq=seq, seg=seg, tam=tam)


def test_ligadura_expandida_conserva_orden_del_flujo():
    # MuPDF expande "ﬁ" en 'f' + 'i' con la 'i' de ancho cero y x0 igual al de la 's' siguiente
    chars = [_char("f", 239.6, 244.7, seq=0), _char("i", 244.7, 244.7, seq=1),
             _char("s", 244.69, 247.8, seq=2), _char("h", 247.8, 252.4, seq=3)]
    assert componer_texto(chars) == "fish"


def test_superindice_en_linea_aparte_se_inserta_por_posicion():
    # "H2O" con el "2" en su propio segmento (raw line) y un solo segmento base "HO"
    chars = [_char("H", 20, 28, seq=0, seg=0), _char("O", 33, 41, seq=1, seg=0),
             _char("2", 28.5, 32.5, y0=104, y1=112, seq=2, seg=1, tam=6, sub=True)]
    assert componer_texto(chars) == "H\u2082O"


def test_fraccion_cubierta_por_las_celdas_de_una_tabla(pdf_sintetico):
    """Cuando TableFormer devuelve una rejilla que no casa con las celdas del PDF y cubre menos de
    la mitad del texto de la región, `fraccion_cubierta` lo detecta sin consumir los caracteres."""
    pt = extraer_pagina(pdf_sintetico[0], 1)
    region = (0, 0, 300, 200)
    assert fraccion_cubierta(pt, region, [region]) == 1.0
    assert fraccion_cubierta(pt, region, [(10, 25, 120, 45)]) < 0.4     # solo «Hola mundo»
    assert fraccion_cubierta(pt, region, []) == 0.0
    assert len(pt.chars) == len(extraer_pagina(pdf_sintetico[0], 1).chars)  # no consume


def test_rejilla_por_posiciones_reconstruye_filas_columnas_y_cabecera():
    """Tabla que TableFormer no supo partir; se rehace con las líneas de la capa de texto
    (una por celda): filas por solape vertical, columnas ancladas en la fila más llena."""
    lineas = [
        ((40, 600, 70, 608), "Samples"), ((150, 600, 185, 608), "Melting"),
        ((110, 612, 150, 620), "Toff (°C)"), ((200, 612, 230, 620), "Tp (°C)"),
        ((40, 624, 55, 632), "CB"), ((110, 624, 160, 632), "27.74 ± 0.32c"), ((200, 624, 250, 632), "20.93 ± 0.44b"),
        ((40, 636, 95, 644), "10%CBE + 90%CB"), ((110, 636.5, 160, 644.5), "28.42 ± 0.51bc"),
        ((200, 636, 250, 644), "21.59 ± 0.71ab"),
    ]
    filas, cabecera = rejilla_por_posiciones(lineas)
    assert filas == [[(0, "Samples"), (1, "Melting")], [(1, "Toff (°C)"), (2, "Tp (°C)")],
                     [(0, "CB"), (1, "27.74 ± 0.32c"), (2, "20.93 ± 0.44b")],
                     [(0, "10%CBE + 90%CB"), (1, "28.42 ± 0.51bc"), (2, "21.59 ± 0.71ab")]]
    assert cabecera == 2


def _palabras_en(lineas):
    """PaginaTexto con una palabra por (texto, x0, y0, linea), letras de 5 pt de ancho y 8 de alto,
    en el orden del flujo; entre palabras de la misma línea, un espacio."""
    from pdf2md.pdf_texto import PaginaTexto
    chars, seq = [], 0
    for texto, x0, y0, linea in lineas:
        if chars and chars[-1].linea == linea:
            chars.append(_char(" ", x0 - 5, x0, y0, y0 + 8, linea=linea, seq=seq, tam=8.0))
            seq += 1
        for k, c in enumerate(texto):
            chars.append(_char(c, x0 + 5 * k, x0 + 5 * k + 5, y0, y0 + 8, linea=linea, seq=seq, tam=8.0))
            seq += 1
    return PaginaTexto(1, 600, 800, chars, [], [])


def _tabla_desplazada(desplazar: bool):
    """5 filas físicas (etiqueta en x 10-60, valor en x 100-130, 12 pt de paso). Con `desplazar`, la
    columna de valores de la rejilla va una fila por detrás."""
    lineas, celdas = [], []
    for k in range(5):
        y = 100 + 12 * k
        lineas += [(f"row{k}", 10, y, 2 * k), ("1.23", 100, y, 2 * k + 1)]
        celdas.append((k, True, (8, y - 1, 62, y + 9)))
        yv = y + 12 if desplazar else y
        celdas.append((k, True, (98, yv - 1, 132, yv + 9)))
    return _palabras_en(lineas), celdas


def test_rescate_de_letras_cortadas_por_el_borde_de_la_celda():
    """Cuando la caja de la celda de TableFormer empieza en la «w» de «sweet» y la «s» queda fuera de
    toda celda, `rescatar_cortes` la recupera. Una palabra entera fuera de las celdas no se asigna."""
    from pdf2md.pdf_texto import rescatar_cortes
    pt = _palabras_en([("sweet,", 100, 100, 0), ("almond", 135, 100, 0), ("bready", 100, 140, 1)])
    cajas = [(104, 99, 170, 109)]  # empieza en la «w»; «bready» queda fuera
    extra = rescatar_cortes(pt, (90, 90, 200, 160), cajas)
    assert "".join(c.c for c in extra[0]) == "s"
    assert set(extra) == {0}


def test_diagnostico_detecta_filas_mezcladas_y_texto_perdido():
    from pdf2md.pdf_texto import diagnosticar_rejilla, rejilla_rota
    region = (0, 90, 200, 170)
    pt, celdas = _tabla_desplazada(desplazar=False)
    sana = diagnosticar_rejilla(pt, region, celdas)
    assert (sana.cubierta, sana.filas_mezcladas, sana.filas_fisicas) == (1.0, 0, 5)
    assert not rejilla_rota(sana)
    pt, celdas = _tabla_desplazada(desplazar=True)
    rota = diagnosticar_rejilla(pt, region, celdas)
    assert rota.filas_mezcladas == 4 and rejilla_rota(rota)
    pt, celdas = _tabla_desplazada(desplazar=False)
    perdida = diagnosticar_rejilla(pt, region, celdas[:-2])  # la última fila sin celdas
    assert perdida.cubierta < 0.9 and rejilla_rota(perdida)


def test_diagnostico_no_rehace_tablas_de_texto_vertical_ni_de_celdas_de_varias_lineas():
    """No se rehacen por posiciones las tablas con texto vertical ni aquellas con celdas de varias
    líneas (que la rejilla por posiciones partiría en una fila por línea)."""
    from pdf2md.pdf_texto import PaginaTexto, diagnosticar_rejilla, rejilla_rota
    pt, celdas = _tabla_desplazada(desplazar=True)
    girada = PaginaTexto(1, 600, 800, [_char(c.c, c.y0, c.y1, c.x0, c.x1, linea=c.linea, seq=c.seq, tam=8.0)
                                       for c in pt.chars], [], [])
    d = diagnosticar_rejilla(girada, (0, 0, 200, 200), [(r, cu, (b[1], b[0], b[3], b[2])) for r, cu, b in celdas])
    assert d.horizontal < 0.5 and not rejilla_rota(d)
    # cada celda de valores abarca dos filas físicas (texto partido en dos líneas)
    lineas, celdas = [], []
    for k in range(4):
        y = 100 + 24 * k
        lineas += [(f"row{k}", 10, y, 3 * k), ("long", 100, y, 3 * k + 1), ("text", 100, y + 12, 3 * k + 2)]
        celdas += [(k, True, (8, y - 1, 62, y + 9)), (k, True, (98, y - 1, 132, y + 21))]
    d = diagnosticar_rejilla(_palabras_en(lineas), (0, 90, 200, 200), celdas[:-1])  # y falta texto
    assert d.cubierta < 0.97 and d.multilinea > 0.15 and not rejilla_rota(d)


def test_rejilla_por_posiciones_aprovechable_si_separa_columnas():
    """Solo se usa la rejilla por posiciones si al menos la mitad de las filas tienen dos celdas o más."""
    from pdf2md.pdf_texto import rejilla_aprovechable
    assert rejilla_aprovechable([[(0, "a"), (1, "1")], [(0, "b"), (1, "2")], [(0, "Notas")]])
    assert not rejilla_aprovechable([[(0, "Rs (%) –99.3 99.8")], [(0, "C.V (%) –0.45")], [(0, "x"), (3, "y")]])


def _linea(spec, tam=8.0):
    """Chars de una línea a partir de [(carácter, x0, x1)]."""
    return [_char(c, x0, x1, seq=i, tam=tam) for i, (c, x0, x1) in enumerate(spec)]


def test_rotulo_con_tracking_seguido_de_texto_se_une():
    """En algunos PDF de Wiley «FIGURE» lleva ≈ 1,1 pt entre letras y MuPDF mete un espacio sintético
    en algunos huecos («F I G U R E 1 Thin-layer…»)."""
    chars = _linea([("F", 306.85, 311.38), ("I", 312.5, 314.87), (" ", 314.87, 316.14), ("G", 316.14, 321.95),
                    (" ", 321.95, 323.23), ("U", 323.23, 329.17), (" ", 329.17, 330.44), ("R", 330.44, 335.58),
                    (" ", 335.58, 336.82), ("E", 336.82, 341.42), (" ", 342.54, 344.49), ("1", 345.61, 350.25),
                    (" ", 351.37, 357.37), ("T", 357.37, 362.09), ("h", 362.25, 366.71), ("i", 366.81, 368.73),
                    ("n", 368.82, 373.29)])
    assert componer_texto(chars) == "FIGURE 1 Thin"


def test_hueco_base_cuenta_letras_separadas_por_un_espacio_sintetico():
    """En «F I G U R E» (Wiley) MuPDF ya puso espacio en casi todos los huecos: contando solo letras
    contiguas quedaba un par (F-I), no había estadística y el tracking valía 0."""
    from pdf2md.pdf_texto import _hueco_base
    span = [{"c": c, "bbox": (x0, 0, x1, 8)} for c, x0, x1 in [
        ("F", 306.85, 311.38), ("I", 312.5, 314.87), (" ", 314.87, 316.14), ("G", 316.14, 321.95),
        (" ", 321.95, 323.23), ("U", 323.23, 329.17), (" ", 329.17, 330.44), ("R", 330.44, 335.58),
        (" ", 335.58, 336.82), ("E", 336.82, 341.42)]]
    assert 1.1 < _hueco_base(span) < 1.3
    normal = [{"c": c, "bbox": (i * 5.0 + (0.3 if c == " " else 0), 0, i * 5.0 + 5, 8)}
              for i, c in enumerate("the soil and the water")]
    assert _hueco_base(normal) == 0.0


def test_palabras_en_mayusculas_sin_tracking_no_se_unen():
    # letras pegadas (hueco 0) y espacios de palabra sintéticos: «USA NATO WHO» se queda igual
    # ni letras o cifras sueltas separadas por espacios normales («A B C D», «1 2 3 4»)
    for texto in ("USA NATO WHO", "Grupos A B C D E", "Dosis 1 2 3 4 5"):
        spec, x = [], 0.0
        for c in texto:
            ancho = 2.0 if c == " " else 5.0
            spec.append((c, x, x + ancho))
            x += ancho
        assert componer_texto(_linea(spec)) == texto


def test_enlace_partido_en_una_anotacion_por_palabra_sale_entero():
    # Cuando una referencia lleva una anotación por palabra y el espacio no cae en ninguna,
    # se une en un solo enlace.
    u, v = "http://refhub.elsevier.com/S0960-3085(17)30154-2/sbref0110", "https://otra.org"
    texto = "Production of lipids. Other"
    chars, x = [], 0.0
    for i, c in enumerate(texto):
        url = None if c == " " else (u if i <= texto.index(".") else v)
        chars.append(_char(c, x, x + 5, seq=i, url=url))
        x += 5
    assert componer_texto(chars) == f"[Production of lipids.]({u}) [Other]({v})"


def test_acentos_separados_se_combinan_por_solape():
    # 'S´anchez' (acento antes de la base) y 'Polit`ecnica' (acento antes) y 'Ta¸sdemir', 'Go¨lge'
    chars = [_char("S", 198.7, 204.2, seq=0), _char("\u00b4", 204.2, 209.5, seq=1), _char("a", 204.1, 209.5, seq=2),
             _char("n", 209.5, 215.5, seq=3)]
    assert componer_texto(chars) == "Sán"
    chars = [_char("t", 0, 4, seq=0), _char("`", 4.1, 9, seq=1), _char("e", 4, 9, seq=2), _char("c", 9, 14, seq=3)]
    assert componer_texto(chars) == "tèc"
    chars = [_char("a", 0, 5, seq=0), _char("\u00b8", 5, 9, seq=1), _char("s", 5, 9, seq=2)]
    assert componer_texto(chars) == "aş"
    chars = [_char("o", 0, 5, seq=0), _char("\u00a8", 0.2, 5, seq=1), _char("l", 5, 8, seq=2)]
    assert componer_texto(chars) == "öl"


def test_acento_sin_solape_se_conserva():
    chars = [_char("a", 0, 5, seq=0), _char(" ", 5, 8, seq=1), _char("\u00b4", 20, 24, seq=2)]
    assert componer_texto(chars) == "a \u00b4"


def test_titulo_espaciado_letra_a_letra_se_colapsa_por_huecos():
    # "A R T I C L E I N F O": paso 7.9 pt entre letras, hueco mayor entre E e I
    letras = "ARTICLE INFO".replace(" ", "")
    xs = [37.6, 45.5, 53.2, 60.5, 66.9, 74.6, 82.4, 97.0, 101.5, 109.4, 117.0]
    chars, seq = [], 0
    for i, (c, x) in enumerate(zip(letras, xs)):
        chars.append(_char(c, x, x + 5.0, seq=seq)); seq += 1
        if i < len(xs) - 1:
            chars.append(_char(" ", x + 5.0, xs[i + 1], seq=seq)); seq += 1
    assert componer_texto(chars) == "ARTICLE INFO"


def _espaciado(texto, x, paso_letra, ancho_espacio, tam):
    chars, seq = [], 0
    for i, c in enumerate(texto):
        ancho = paso_letra if c != " " else ancho_espacio
        chars.append(_char(c, x, x + ancho, seq=seq, tam=tam)); seq += 1
        x += ancho
    return chars


def test_versalitas_en_minusculas_con_tracking_se_colapsan():
    # En algunos artículos de Elsevier las versalitas de la portada vienen en minúsculas en la capa
    # de texto, con espacios de 3,98 pt a 8,97 pt (0,44 em); «info» va en otra línea y tiene 4 letras
    assert componer_texto(_espaciado("a r t i c l e", 42.5, 4.85, 3.98, 8.97)) == "article"
    assert componer_texto(_espaciado("i n f o", 107.3, 4.2, 3.98, 8.97)) == "info"
    assert componer_texto(_espaciado("a b s t r a c t", 206.9, 4.8, 3.98, 8.97)) == "abstract"


def test_titulo_espaciado_con_doble_espacio_y_espacios_en_los_extremos():
    # «A R T I C L E  I N F O » y « A B S T R A C T »: el doble espacio entre palabras y los
    # espacios de los extremos rompían la alternancia letra-espacio
    assert componer_texto(_espaciado("A R T I C L E  I N F O ", 56.6, 6.0, 2.2, 8.0)) == "ARTICLE INFO"
    assert componer_texto(_espaciado(" A B S T R A C T ", 207.1, 6.0, 2.2, 8.0)).strip() == "ABSTRACT"


def test_letras_sueltas_en_minusculas_con_espacio_normal_no_se_colapsan():
    # espacio de 0,25 em (Times): texto normal, no tracking
    assert componer_texto(_espaciado("x y z w v", 20.0, 5.0, 2.5, 10.0)) == "x y z w v"
    # letras de significación sobre las barras de una figura: 0,74 em
    assert componer_texto(_espaciado("a a b c", 322.9, 3.89, 5.2, 7.0)) == "a a b c"


def test_texto_normal_con_palabras_cortas_no_se_colapsa():
    chars, seq = [], 0
    for i, c in enumerate("a b c"):
        chars.append(_char(c, i * 6.0, i * 6.0 + 5.0, seq=seq)); seq += 1
    assert componer_texto(chars) == "a b c"


def test_fraccion_apilada_no_se_fusiona_en_una_linea(pdf_sintetico):
    page = pdf_sintetico[0]
    page.insert_text((150, 160), "Numerador", fontsize=7)
    page.insert_text((150, 168), "Denominador", fontsize=7)
    pt = extraer_pagina(page, 1)
    assert componer_texto(chars_en_bbox(pt, (100, 150, 300, 175))) == "Numerador\nDenominador"


def test_guion_blando_se_muestra_como_guion():
    from pdf2md.md_render import normalizar_glifos
    assert normalizar_glifos("his\u00ad") == "his-"


def test_titulo_espaciado_con_espacio_real_estrecho():
    # caso real: el espacio de palabra es un glifo que no llena el hueco (87.6-89.7 dentro de 84.5-90.0)
    datos = [("A", 37.6, 42.3), (" ", 42.3, 45.5), ("R", 45.5, 50.0), (" ", 50.0, 53.2), ("T", 53.2, 57.3),
             (" ", 57.3, 60.5), ("I", 60.5, 62.8), (" ", 62.8, 66.0), ("C", 66.0, 70.4), (" ", 70.4, 73.5),
             ("L", 73.5, 77.2), (" ", 77.2, 80.4), ("E", 80.4, 84.5), (" ", 87.6, 89.7), ("I", 90.0, 92.3),
             (" ", 92.3, 95.4), ("N", 95.4, 100.5), (" ", 100.5, 103.6), ("F", 103.6, 107.4),
             (" ", 107.4, 110.6), ("O", 110.6, 115.7)]
    chars = [_char(c, x0, x1, seq=i) for i, (c, x0, x1) in enumerate(datos)]
    assert componer_texto(chars) == "ARTICLE INFO"


def test_lineas_con_bbox_ignora_espacios_de_relleno():
    from pdf2md.pdf_texto import lineas_con_bbox
    chars = [_char("A", 37.6, 42.0, seq=0), _char(".", 42.0, 44.0, seq=1), _char(" ", 44.0, 461.0, seq=2)]
    (bb, texto), = lineas_con_bbox(chars)
    assert texto == "A." and bb[2] <= 44.0


def test_enlace_mas_pequeno_gana_cuando_se_solapan(pdf_sintetico):
    # un enlace grande (entrada bibliográfica completa) y uno pequeño (DOI) sobre la misma línea
    page = pdf_sintetico[0]
    page.insert_link({"kind": fitz.LINK_URI, "from": fitz.Rect(10, 50, 200, 66), "uri": "https://grande.org"})
    page.insert_link({"kind": fitz.LINK_URI, "from": fitz.Rect(20, 50, 60, 66), "uri": "https://doi.org/x"})
    page = pdf_sintetico.reload_page(page)  # PyMuPDF no ve enlaces insertados sin recargar la página
    pt = extraer_pagina(page, 1)
    texto = componer_texto(chars_en_bbox(pt, (0, 48, 300, 68)))
    assert "](https://doi.org/x)" in texto and "](https://grande.org)" in texto


def test_imagenes_visibles_descarta_invisibles_duplicadas_e_iconos():
    from pdf2md.pdf_texto import imagenes_visibles

    def imagen(ancho, alto, blanca=False):
        pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, ancho, alto), False)
        pix.clear_with(255)
        if not blanca:
            for x in range(0, ancho // 2):        # mitad oscura: no es de un solo color
                for y in range(alto):
                    pix.set_pixel(x, y, (120, 30, 30))
        return pix

    doc = fitz.open()
    page = doc.new_page(width=300, height=300)
    page.insert_image(fitz.Rect(20, 20, 80, 100), pixmap=imagen(60, 80))
    page.insert_image(fitz.Rect(21, 21, 81, 101), pixmap=imagen(60, 80))       # copia casi encima
    page.insert_image(fitz.Rect(120, 20, 180, 100), pixmap=imagen(60, 80, blanca=True))  # no se ve nada
    page.draw_line((110, 22), (190, 22))  # filete de tabla que roza la imagen invisible: no la hace visible
    page.insert_image(fitz.Rect(200, 20, 210, 30), pixmap=imagen(10, 10))      # icono < 20 pt
    page.insert_image(fitz.Rect(20, 280, 80, 360), pixmap=imagen(60, 80))      # se sale de la página
    visibles = imagenes_visibles(page)
    assert [tuple(round(v) for v in bb) for bb in visibles] == [(20, 20, 80, 100), (20, 280, 80, 300)]


def test_superindice_tras_icono_enlazado_sigue_en_la_linea():
    # "Beatriz Llavata [icono ORCID] 1, Ronaldo…": el icono (enlazado, sin texto) abre un hueco
    # mayor que un tamaño de fuente entre el nombre y su superíndice, que venía en otra línea cruda
    doc = fitz.open()
    page = doc.new_page(width=400, height=200)
    page.insert_text((20, 50), "Beatriz Llavata", fontsize=9)
    fin = page.get_text("words")[-1][2]
    page.insert_link({"kind": fitz.LINK_URI, "from": fitz.Rect(fin + 1, 41, fin + 11, 51), "uri": "http://orcid.org/0000"})
    page.insert_text((fin + 12, 47), "1", fontsize=5.5)
    page.insert_text((fin + 15, 50), ", Ronaldo E. Mello", fontsize=9)
    doc.reload_page(page)
    pt = extraer_pagina(doc[0], 1)
    assert componer_plano(pt.chars) == "Beatriz Llavata¹, Ronaldo E. Mello"


def test_artefacto_de_fuentes_de_nature_se_descarta():
    doc = fitz.open()
    page = doc.new_page(width=300, height=400)
    page.insert_text((20, 40), "Texto normal", fontsize=10)
    page.insert_text((8, 330), "1234567890():,;", fontsize=5, rotate=90)  # margen izquierdo, en vertical
    pt = extraer_pagina(doc[0], 1)
    assert componer_plano(pt.chars) == "Texto normal"


def test_caracter_de_control_sin_tinta_es_espacio_y_con_tinta_queda_ilegible():
    # Springer (MyriadPro) pone un \x07 de tabulación entre el número y el título de sección
    # («2  \x07Materials»): no dibuja nada. Los \x01-\x05 de AdvP4C4E74 sí dibujan un símbolo (±, ≤)
    # cuyo mapa cambia por documento: siguen como U+FFFD.
    doc = fitz.open()
    page = doc.new_page(width=300, height=100)
    page.insert_text((20, 50), "2 \x07Materials and P \x01 0.05 a\x07b", fontsize=10)
    x0 = next(c["bbox"] for b in page.get_text("rawdict")["blocks"] for l in b["lines"]
              for s in l["spans"] for c in s["chars"] if c["c"] == "\x01")
    page.draw_line((x0[0] + 1, 42), (x0[2] - 1, 48), width=1)  # la «tinta» del símbolo
    pt = extraer_pagina(doc[0], 1)
    assert componer_plano(pt.chars) == "2 Materials and P \ufffd 0.05 a b"


def test_control_sin_avance_ante_otro_span():
    # En algunos capítulos de libro de Elsevier (Palatino) cada referencia es «\t 1.\t \x07» en un
    # span y el autor en el siguiente, que empieza en la misma x que el \x07; la caja del control se
    # ve «con tinta» por la primera letra. Pero el acento suelto de Elsevier (AdvP4C4E59) llega como
    # U+FFFD sin avance ante la vocal del span siguiente y sí dibuja: no puede pasar a espacio.
    from pdf2md.pdf_texto import _control_sin_tinta
    doc = fitz.open()
    page = doc.new_page(width=100, height=100)
    page.insert_text((40, 50), "G", fontsize=10)  # la tinta de la letra siguiente
    caja = {"c": "\x07", "bbox": (40, 40, 42, 52)}
    letra = {"c": "G", "bbox": (40, 40, 47, 52)}
    assert _control_sin_tinta(page, "\x07", [caja], 0, letra)
    assert not _control_sin_tinta(page, "\ufffd", [dict(caja, c="\ufffd")], 0, letra)


def test_espacio_sintetico_en_lineas_justificadas_muy_apretadas():
    # en las líneas muy comprimidas el hueco entre palabras (≈0,14 em) no llega al umbral de
    # MuPDF y la capa de texto dice "Equation2isacontinuity"; el hueco entre letras es ≈0
    doc = fitz.open()
    page = doc.new_page(width=400, height=100)
    x = 20.0
    for palabra in ("Equation", "2", "is", "a", "continuity"):
        page.insert_text((x, 50), palabra, fontsize=9)
        x += fitz.get_text_length(palabra, fontsize=9) + 1.25   # 0,14 em entre palabras
    pt = extraer_pagina(doc[0], 1)
    assert componer_plano(pt.chars) == "Equation 2 is a continuity"


def test_texto_con_tracking_no_recibe_espacios_entre_letras():
    # En encabezados de Elsevier "journal homepage" lleva ≈1 pt entre todas las letras (0,14 em a
    # 7 pt); sin descontar el tracking se partía en "j o u r n a l h o m e p a g e"
    doc = fitz.open()
    page = doc.new_page(width=400, height=100)
    x = 20.0
    for palabra in ("journal", "homepage:"):
        for letra in palabra:
            page.insert_text((x, 50), letra, fontsize=7)
            x += fitz.get_text_length(letra, fontsize=7) + 1.0
        x += fitz.get_text_length(" ", fontsize=7) + 1.0
    pt = extraer_pagina(doc[0], 1)
    assert componer_plano(pt.chars) == "journal homepage:"


def test_hueco_a_mitad_de_palabra_en_linea_con_espacios_reales():
    # Documentos de Word justificados dejan huecos de ≈1,2 pt (0,11 em) a mitad de palabra,
    # mucho menores que los espacios reales de la misma línea
    doc = fitz.open()
    page = doc.new_page(width=500, height=100)
    x = 20.0
    for trozo in ("la sociedad del conocimie", "nto y la innovación en el p", "aís"):
        page.insert_text((x, 50), trozo, fontsize=11.2)
        x += fitz.get_text_length(trozo, fontsize=11.2) + 1.25
    pt = extraer_pagina(doc[0], 1)
    assert componer_plano(pt.chars) == "la sociedad del conocimiento y la innovación en el país"


def test_palabras_en_lineas_crudas_separadas_conservan_el_espacio():
    # RSC, títulos en cursiva de la bibliografía: en las líneas muy abiertas MuPDF da cada palabra
    # como una línea cruda aparte (hueco ≈ 8 pt) y no emite el espacio: "cellulosenanocrystal"
    doc = fitz.open()
    page = doc.new_page(width=400, height=100)
    x = 20.0
    for palabra in ("cellulose", "nanocrystal", "biocomposites:", "Tuning"):
        page.insert_text((x, 50), palabra, fontsize=9)
        x += fitz.get_text_length(palabra, fontsize=9) + 8.0
    pt = extraer_pagina(doc[0], 1)
    assert len({c.seg for c in pt.chars}) == 4          # el caso real: cuatro líneas crudas
    assert componer_plano(pt.chars) == "cellulose nanocrystal biocomposites: Tuning"


def test_acento_sobre_i_sin_punto_da_la_letra_precompuesta():
    # RSC escribe "Dom´ınguez" con ı (i sin punto): ı + acento combinante no se compone en NFC
    chars = [_char("m", 0, 6, seq=0), _char("\u00b4", 6.1, 9, seq=1), _char("\u0131", 6, 9, seq=2), _char("n", 9, 14, seq=3)]
    assert componer_texto(chars) == "mín"


def test_marca_de_agua_vertical_sobre_el_texto_se_aparta():
    # Wiley «Accepted Article»: rótulo vertical de 80 pt en el margen cuyo bbox pisa el arranque
    # de cada línea del cuerpo.
    doc = fitz.open()
    page = doc.new_page(width=400, height=400)
    page.insert_text((60, 100), "diversified groups of microbes", fontsize=11)
    page.insert_text((60, 120), "decomposition of the soil", fontsize=11)
    page.insert_text((80, 380), "Accepted Article", fontsize=48, rotate=90)
    pt = extraer_pagina(page, 1)
    assert len(pt.marcas) == 1
    assert pt.marcas[0][0] < 80 < pt.marcas[0][2]
    texto = componer_plano(chars_en_bbox(pt, (0, 0, 400, 400)))
    assert "Accepted" not in texto
    assert "diversified groups" in texto and "decomposition" in texto


def test_texto_vertical_que_no_pisa_el_cuerpo_se_conserva():
    doc = fitz.open()
    page = doc.new_page(width=400, height=400)
    page.insert_text((100, 100), "cuerpo del articulo", fontsize=11)
    page.insert_text((30, 380), "arXiv:1234.5678", fontsize=12, rotate=90)
    page.insert_text((105, 130), "Flux (mg)", fontsize=8, rotate=90)  # eje de figura que toca el cuerpo
    pt = extraer_pagina(page, 1)
    assert pt.marcas == []
    assert any(ch.c == "X" for ch in pt.chars) and any(ch.c == "F" for ch in pt.chars)


def test_enlace_con_texto_ilegible_usa_la_url():
    # MDPI: el botón «Check for updates» esconde glifos sin mapa Unicode (U+FFFD) bajo el enlace
    url = "http://www.mdpi.com/x?type=check_update&version=1"
    chars = [_char("\ufffd", 10 + 5 * i, 14 + 5 * i, seq=i, url=url) for i in range(4)]
    assert componer_texto(chars) == f"[{url}]({url})"


def test_fuentes_matematicas_sin_mapa_unicode():
    # Elsevier (AdvP4C4E74), npj (AdvMacMthSyN), Heliyon (TeX_CM_Bold_Maths_Symbol): la capa de
    # texto da "Stress ðsÞ ¼ F" por "Stress (s) = F" y "IA þ IB" por "IA + IB"
    from pdf2md.pdf_texto import _caracter_de_fuente
    assert [_caracter_de_fuente(c, "ABCDEF+AdvP4C4E74") for c in "ð¼þÞ"] == ["(", "=", "+", ")"]
    assert _caracter_de_fuente("¼", "AdvMacMthSyN") == "="
    assert _caracter_de_fuente("\ud835", "MinionMath-Regular-Graph") == "\ufffd"   # sustituto suelto
    assert _caracter_de_fuente("þ", "TeX_CM_Bold_Maths_Symbol") == "+"
    assert _caracter_de_fuente("¼", "STIX-Regular") == "¼"          # ¼ de pulgada real
    assert _caracter_de_fuente("x", "AdvP4C4E74") == "x"
    # AdvP4C4E3A y TeX_CM_Maths_Symbols; prefijo de subconjunto sin «+»
    assert _caracter_de_fuente("þ", "AdvP4C4E3A") == "+"
    assert _caracter_de_fuente("¼", "TeX_CM_Maths_Symbols") == "="
    assert _caracter_de_fuente("ð", "XrdnxnAdvP4C4E74") == "("


def test_caracteres_de_control_se_ven_como_reemplazo():
    from pdf2md.md_render import normalizar_glifos
    assert normalizar_glifos("a\x07b\x08c\nd\te") == "a\ufffdb\ufffdc\nd\te"


def _pdf_apaisado(ruta: Path, rotacion_pagina: int) -> None:
    """Página 1 normal; página 2 con una tabla girada 90° (texto hacia arriba) y un enlace sobre
    «SampleRef». Con `rotacion_pagina` = 90 la página lleva además /Rotate 90."""
    doc = fitz.open()
    p1 = doc.new_page(width=300, height=400)
    p1.insert_text((20, 40), "Texto normal horizontal de la primera pagina", fontsize=9)
    p2 = doc.new_page(width=300, height=400)
    for i, fila in enumerate(["Rose and teak wood Open field SampleRef et al. (2022)",
                              "Peanut hull Pots Quinoa AuthorB et al. (2022)",
                              "Wheat straw Open field Maize AuthorC et al. (2022)"] * 3):
        p2.insert_text((40 + 14 * i, 380), fila, fontsize=9, rotate=90)
    ancho = fitz.get_text_length("Rose and teak wood Open field ", fontsize=9)
    largo = fitz.get_text_length("SampleRef", fontsize=9)
    p2.insert_link({"kind": fitz.LINK_URI, "uri": "https://doi.org/10.1/ref",
                    "from": fitz.Rect(32, 380 - ancho - largo, 42, 380 - ancho)})
    if rotacion_pagina:
        p2.set_rotation(rotacion_pagina)
    doc.save(ruta)


@pytest.mark.parametrize("rotacion_pagina", [0, 90])
def test_paginas_apaisadas_se_enderezan_con_sus_enlaces(tmp_path: Path, rotacion_pagina):
    # Tanto con /Rotate 90 como con el contenido girado en página vertical, el flujo endereza la página
    from pdf2md.pdf_texto import enderezar_apaisadas
    origen, destino = tmp_path / "a.pdf", tmp_path / "enderezado.pdf"
    _pdf_apaisado(origen, rotacion_pagina)
    assert enderezar_apaisadas(origen, destino) == [2]
    doc = fitz.open(destino)
    assert doc.page_count == 2
    assert "Texto normal horizontal" in doc[0].get_text()
    p2 = doc[1]
    assert p2.rotation == 0 and p2.rect.width > p2.rect.height
    lineas = [l for b in p2.get_text("dict")["blocks"] for l in b.get("lines", [])]
    assert lineas and all(abs(l["dir"][0] - 1) < 0.01 for l in lineas)
    pt = extraer_pagina(p2, 2)
    assert "Rose and teak wood Open field [SampleRef](https://doi.org/10.1/ref) et al." in componer_texto(pt.chars)


def test_pdf_sin_paginas_apaisadas_no_se_copia(tmp_path: Path):
    from pdf2md.pdf_texto import enderezar_apaisadas
    origen, destino = tmp_path / "a.pdf", tmp_path / "enderezado.pdf"
    doc = fitz.open()
    doc.new_page().insert_text((20, 40), "Solo texto horizontal " * 20, fontsize=9)
    doc.save(origen)
    assert enderezar_apaisadas(origen, destino) == []
    assert not destino.exists()


def test_texto_girado_hacia_abajo_se_endereza_en_sentido_contrario(tmp_path: Path):
    from pdf2md.pdf_texto import enderezar_apaisadas, giro_para_enderezar
    origen, destino = tmp_path / "a.pdf", tmp_path / "enderezado.pdf"
    doc = fitz.open()
    page = doc.new_page(width=300, height=400)
    for i in range(9):
        page.insert_text((260 - 14 * i, 20), "Wheat straw Open field Maize Sample et al. (2022)",
                         fontsize=9, rotate=270)
    assert giro_para_enderezar(page) == 90
    doc.save(origen)
    assert enderezar_apaisadas(origen, destino) == [1]
    p = fitz.open(destino)[0]
    lineas = [l for b in p.get_text("dict")["blocks"] for l in b.get("lines", [])]
    assert lineas and all(abs(l["dir"][0] - 1) < 0.01 for l in lineas)
    assert p.get_text().splitlines()[0] == "Wheat straw Open field Maize Sample et al. (2022)"


def _pagina_celdas(enderezada: bool):
    from pdf2md.pdf_texto import PaginaTexto
    chars, x, seq = [], 70.9, 0
    for c in "Biochar  16":   # dos columnas: «Biochar» y «16» (la siguiente celda)
        chars.append(_char(c, x, x + 4.0, seq=seq, tam=9.0)); x += 4.0; seq += 1
    return PaginaTexto(7, 842, 595, chars, [], [], enderezada=enderezada)


def test_en_pagina_enderezada_la_celda_toma_la_palabra_entera():
    # Docling sitúa las celdas del texto girado hasta 4 pt a la izquierda de donde PyMuPDF ve las letras
    pt = _pagina_celdas(enderezada=True)
    assert componer_plano(chars_en_bbox(pt, (67.0, 100, 95.5, 112), tol=0.5)) == "Biochar"
    assert componer_plano(chars_sin_consumir(pt)) == "16"   # la columna vecina no se toca


def test_en_pagina_normal_la_celda_no_se_amplia():
    pt = _pagina_celdas(enderezada=False)
    assert componer_plano(chars_en_bbox(pt, (67.0, 100, 95.5, 112), tol=0.5)) == "Biocha"


def test_espacio_al_inicio_del_enlace_no_se_pierde():
    # Wiley (sección ORCID): apellido + icono + « https://orcid…», con el espacio dentro de la anotación
    u = "https://orcid.org/0000-0003-4385-7656"
    chars, x = [], 0.0
    for i, c in enumerate("Guillemot"):
        chars.append(_char(c, x, x + 5, seq=i))
        x += 5
    x += 10  # hueco del icono
    for i, c in enumerate(" orcid"):
        chars.append(_char(c, x, x + 5, seq=20 + i, url=u))
        x += 5
    assert componer_texto(chars) == f"Guillemot [orcid]({u})"


def test_indice_con_puntos_guia_no_es_una_tabla():
    """El índice de contenidos o de tablas, con sus puntos guía, se maqueta con tabuladores y Docling
    lo toma por una tabla de 2-3 columnas; la rejilla cortaba las palabras."""
    indice = "\n".join([
        "6.2.1. Amostras ............................ 93",
        "6.2.2. Extração e determinação do conteúdo de fenólicos e",
        "flavonoides totais por espectrofotometria UV-vis ..... 94",
        "6.2.3. Análise do perfil fenólico .......................... 94",
        "6.3. RESULTADOS E DISCUSSÃO ........................ 96",
    ])
    assert es_indice_de_contenidos(indice)
    datos = "Tratamiento Dosis Rendimiento\nT1 10 2.5\nT2 20 3.1\nT3 30 3.4"
    assert not es_indice_de_contenidos(datos)
    assert not es_indice_de_contenidos("Tabla 1 ... nota")           # una línea suelta no basta


def _linea_con_letras_espaciadas(palabras, paso=1.62, ancho=4.0, espacio=2.0):
    """Chars de una línea de bibliografía donde cada letra va separada por un hueco fijo que MuPDF
    rellena con un espacio sintético; entre palabras, el hueco más el espacio real."""
    spec, x = [], 0.0
    for k, palabra in enumerate(palabras):
        for i, c in enumerate(palabra):
            spec.append((c, x, x + ancho))
            x += ancho
            if i < len(palabra) - 1 and not any(p in ".," for p in palabra):
                spec.append((" ", x, x + paso))  # «B.,» y «A.R.M.» van sin espacios
                x += paso
        x += paso if not any(p in ".," for p in palabra) else 0.0
        if k < len(palabras) - 1:
            spec.append((" ", x, x + espacio))
            x += espacio
    return _linea(spec)


def test_letras_espaciadas_de_la_bibliografia_se_unen():
    """«K i c z o r o w s k a B., S a m o l i ń s k a W.» (paso de 1,62 pt a 8,1 pt, 3,6 pt entre palabras)."""
    chars = _linea_con_letras_espaciadas(["Kiczorowska", "B.,", "Samolińska", "W.,", "Al-Yasiry", "A.R.M."])
    assert componer_texto(chars) == "Kiczorowska B., Samolińska W., Al-Yasiry A.R.M."


def test_texto_normal_con_letras_sueltas_no_se_une():
    # «a» y «I» sueltas con espacios normales (hueco 2,0 pt), y una fila de letras con huecos iguales
    for texto in ("Effect of a new feed for the hens in a farm and I", "Dosis A B C D E F G H"):
        spec, x = [], 0.0
        for c in texto:
            ancho = 2.0 if c == " " else 4.0
            spec.append((c, x, x + ancho))
            x += ancho
        assert componer_texto(_linea(spec)) == texto


def test_etiquetas_taged_de_elsevier_no_salen():
    # «TagedP»/«TagedH1»/«TagedEnd» están en la capa de texto de algunas revistas, sin dibujar nada
    from pdf2md.pdf_texto import _es_etiqueta_taged
    for t in ("TagedP", "TagedH1", "TagedH2", "TagedEnd", "TAGEDP", "TAGEDH1", "TAGEDEND"):
        assert _es_etiqueta_taged({"chars": [{"c": c} for c in t]})
    for t in ("Tagedness", "package", "Taged text", "TagedP Author"):
        assert not _es_etiqueta_taged({"chars": [{"c": c} for c in t]})


def test_letras_espaciadas_de_dos_palabras_y_apellidos_cortos():
    # «A b d E l - H a c k» son dos palabras (Abd El-Hack) y «A d e l», «T i w a r i» llevan kerning
    chars = _linea_con_letras_espaciadas(["Abd", "El-Hack", "M.E.,", "Adel", "M.,", "Tiwari", "R.,", "Farag", "M."])
    assert componer_texto(chars) == "Abd El-Hack M.E., Adel M., Tiwari R., Farag M."

