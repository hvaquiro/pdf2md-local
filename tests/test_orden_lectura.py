from pdf2md.orden_lectura import agrupar_lineas_en_bloques, ordenar_xy, vineta_huerfana


def _ids(resultado):
    return [obj for _bbox, obj in resultado]


def test_dos_columnas_simples():
    # bbox = (x0, y0, x1, y1); página de 600 pt de ancho
    elementos = [
        ((310, 100, 560, 300), "der1"), ((40, 100, 290, 300), "izq1"),
        ((40, 310, 290, 500), "izq2"), ((310, 310, 560, 500), "der2"),
    ]
    assert _ids(ordenar_xy(elementos)) == ["izq1", "izq2", "der1", "der2"]


def test_primera_pagina_elsevier():
    # título ancho, banda info/resumen (columna estrecha + bloque ancho), luego dos columnas
    elementos = [
        ((40, 470, 290, 640), "intro_izq"), ((300, 470, 560, 640), "intro_der"),
        ((200, 296, 560, 437), "resumen"), ((200, 277, 260, 283), "cab_resumen"),
        ((40, 296, 90, 360), "keywords"), ((40, 277, 116, 283), "cab_info"),
        ((40, 168, 470, 198), "titulo"), ((40, 210, 480, 235), "autores"),
    ]
    assert _ids(ordenar_xy(elementos)) == [
        "titulo", "autores", "cab_info", "keywords", "cab_resumen", "resumen", "intro_izq", "intro_der",
    ]


def test_figura_ancha_al_pie_no_rompe_columnas():
    elementos = [
        ((40, 60, 290, 400), "izq"), ((300, 60, 560, 400), "der"),
        ((40, 430, 560, 700), "figura"), ((40, 705, 560, 720), "leyenda"),
    ]
    assert _ids(ordenar_xy(elementos)) == ["izq", "der", "figura", "leyenda"]


def test_huecos_de_parrafo_alineados_no_cortan_columnas():
    # ambas columnas tienen un hueco de párrafo a la misma altura (3 pt): no debe partir en bandas
    elementos = [
        ((40, 60, 290, 200), "izq1"), ((40, 203, 290, 400), "izq2"),
        ((300, 60, 560, 200), "der1"), ((300, 203, 560, 400), "der2"),
    ]
    assert _ids(ordenar_xy(elementos)) == ["izq1", "izq2", "der1", "der2"]


def test_agrupar_lineas_en_bloques():
    # (bbox, texto): tres líneas seguidas en una columna y una línea lejana
    lineas = [
        ((40, 100, 280, 110), "a"), ((40, 112, 285, 122), "b"), ((40, 124, 200, 134), "c"),
        ((300, 500, 400, 510), "z"),
    ]
    bloques = agrupar_lineas_en_bloques(lineas)
    assert [(b[0], b[1]) for b in bloques] == [((40, 100, 285, 134), ["a", "b", "c"]), ((300, 500, 400, 510), ["z"])]


def test_agrupar_lineas_que_se_solapan_verticalmente():
    # MuPDF da cajas de línea más altas que el paso de línea: líneas consecutivas se solapan ~2 pt
    lineas = [
        ((306, 51.3, 560, 64.3), "a"), ((306, 61.8, 560, 74.8), "b"), ((306, 72.2, 560, 85.3), "c"),
    ]
    bloques = agrupar_lineas_en_bloques(lineas)
    assert len(bloques) == 1 and bloques[0][1] == ["a", "b", "c"]


def test_agrupar_solo_continuacion_en_zonas_de_pie():
    # pie de página de Elsevier: DOI, "Received…", "Available online…" son líneas sueltas; la licencia
    # ocupa dos líneas (la primera llega al margen derecho) y debe quedar como un solo bloque
    lineas = [
        ((38, 699, 179, 706), "doi"), ((38, 709, 339, 716), "received"), ((38, 715, 131, 726), "available"),
        ((38, 723, 560, 733), "licencia"), ((38, 734, 90, 744), "nc-nd"),
    ]
    bloques = agrupar_lineas_en_bloques(lineas, solo_continuacion=True)
    assert [b[1] for b in bloques] == [["doi"], ["received"], ["available"], ["licencia", "nc-nd"]]


def test_agrupar_lineas_intercaladas_de_dos_columnas():
    # líneas residuales de la columna izquierda y derecha alternan al ordenar por y
    lineas = [
        ((38, 51, 288, 64), "L1"), ((307, 51, 558, 65), "R1"),
        ((38, 62, 288, 75), "L2"), ((307, 62, 558, 75), "R2"),
        ((38, 72, 288, 85), "L3"),
    ]
    bloques = agrupar_lineas_en_bloques(lineas)
    assert sorted(b[1] for b in bloques) == [["L1", "L2", "L3"], ["R1", "R2"]]


def test_agrupar_figuras_une_paneles_cercanos_y_separa_figuras_lejanas():
    from pdf2md.orden_lectura import agrupar_figuras
    paneles = [(40, 100, 200, 250), (210, 100, 370, 250), (380, 100, 540, 250),   # fila 1, huecos de 10 pt
               (40, 258, 200, 400), (210, 258, 370, 400)]                          # fila 2, hueco de 8 pt
    lejana = [(40, 500, 540, 700)]
    grupos = agrupar_figuras(paneles + lejana, margen=12)
    assert sorted(sorted(g) for g in grupos) == [[0, 1, 2, 3, 4], [5]]
    assert agrupar_figuras([], margen=12) == []


def test_fusionar_residuales_une_continuaciones_de_parrafo():
    from pdf2md.orden_lectura import fusionar_residuales
    # (bbox, tipo, texto): un párrafo cuyo bbox Docling recortó y su continuación residual justo debajo
    entradas = [
        ((38, 100, 290, 160), "parrafo", "primera parte del párrafo"),
        ((38, 162, 290, 200), "sin_clasificar", "continuación del párrafo"),
        ((38, 230, 290, 260), "sin_clasificar", "bloque suelto lejos"),
        ((307, 100, 560, 140), "seccion", "2. Métodos"),
        ((307, 142, 560, 180), "sin_clasificar", "texto tras un título no se fusiona"),
    ]
    resultado = fusionar_residuales(entradas)
    assert [(t, x) for _bb, t, x in resultado] == [
        ("parrafo", "primera parte del párrafo\ncontinuación del párrafo"),
        ("sin_clasificar", "bloque suelto lejos"),
        ("seccion", "2. Métodos"),
        ("sin_clasificar", "texto tras un título no se fusiona"),
    ]


def test_agrupar_figuras_no_une_logo_con_insignia_de_distinto_tamano():
    from pdf2md.orden_lectura import agrupar_figuras
    # logo de la revista (54 x 68 pt) y sello CrossMark (27 x 28 pt) a 10 pt: tamaños muy distintos
    assert agrupar_figuras([(500, 54, 554, 122), (500, 132, 527, 160)], margen=24) == [[0], [1]]
    # dos paneles de tamaño parecido sí se unen
    assert agrupar_figuras([(69, 356, 231, 501), (248, 355, 379, 501)], margen=24) == [[0, 1]]


def test_repartir_por_pagina_emite_un_fragmento_por_procedencia():
    from types import SimpleNamespace as NS
    from pdf2md.orden_lectura import repartir_por_pagina
    # Docling fusiona en un solo ítem el párrafo partido entre columnas o páginas (varias `prov`)
    partido = NS(prov=[NS(page_no=2), NS(page_no=3)])
    dos_columnas = NS(prov=[NS(page_no=3), NS(page_no=3)])
    sin_prov = NS(prov=[])
    reparto = repartir_por_pagina([partido, dos_columnas, sin_prov], [1, 2, 3])
    assert reparto == {1: [], 2: [(partido, 0)], 3: [(partido, 1), (dos_columnas, 0), (dos_columnas, 1)]}
    # con --paginas, una procedencia fuera del rango convertido se ignora
    assert repartir_por_pagina([partido], [2]) == {2: [(partido, 0)]}


def test_celda_de_imagen_por_solape_con_filas_y_columnas():
    from pdf2md.orden_lectura import celda_de_imagen
    # (fila, col, bbox) de las celdas con texto; las columnas 1 y 2 solo tienen cabecera
    celdas = [
        (0, 0, (40, 440, 110, 460)), (0, 1, (130, 440, 220, 460)), (0, 2, (240, 440, 340, 460)),
        (0, 3, (380, 440, 440, 460)),
        (1, 0, (50, 505, 100, 515)), (1, 3, (370, 505, 460, 515)),
        (2, 0, (50, 600, 100, 610)), (2, 3, (370, 600, 460, 610)),
    ]
    assert celda_de_imagen(celdas, (154, 471, 202, 555)) == (1, 1)   # imagen en fila 1, col 1
    assert celda_de_imagen(celdas, (262, 562, 317, 649)) == (2, 2)   # imagen en fila 2, col 2
    assert celda_de_imagen([], (0, 0, 10, 10)) is None


def test_vineta_huerfana_de_sangria_francesa():
    """Con sangría francesa (p. ej. MIS Quarterly): la viñeta «•» está en x 72-75 y el texto del ítem
    empieza en x 90; Docling deja la viñeta fuera del ítem y salía como SinClasificar suelto."""
    items = [(90, 104, 267, 180), (90, 224, 267, 290), (90, 296, 267, 400), (300, 224, 520, 400)]
    assert vineta_huerfana((72, 224, 75, 234), items) == 1
    assert vineta_huerfana((72, 296, 75, 306), items) == 2
    assert vineta_huerfana((72, 150, 75, 160), items) is None      # a media altura de un párrafo
    assert vineta_huerfana((20, 224, 23, 234), items) is None      # texto demasiado lejos

