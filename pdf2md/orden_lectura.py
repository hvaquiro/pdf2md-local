"""Orden de lectura por corte XY recursivo y agrupación de líneas residuales en bloques.

Docling clasifica bien las regiones pero su orden de lectura falla en la primera página de los
artículos de Elsevier (resumen a la derecha de la columna de información). El corte XY recursivo
"por el hueco más ancho primero" recupera el orden de lectura esperado en maquetaciones complejas:
en cada nivel se busca el mayor hueco libre, horizontal (banda) o vertical (columna), se parte
por él y se recurre. Todos los bbox son (x0, y0, x1, y1) en puntos, origen arriba.
"""
from __future__ import annotations

HUECO_H = 8.0  # pt: hueco horizontal mínimo para partir en bandas (un hueco de párrafo mide ~3 pt)
HUECO_V = 6.0  # pt: hueco vertical mínimo para partir en columnas (el medianil mide ~15 pt)


def _mayor_hueco(elementos, eje: str, minimo: float) -> tuple[float, float] | None:
    """Devuelve (tamaño, posición de corte) del mayor hueco libre en el eje, o None."""
    a, b = (1, 3) if eje == "h" else (0, 2)
    intervalos = sorted((bb[a], bb[b]) for bb, _ in elementos)
    mejor: tuple[float, float] | None = None
    fin = intervalos[0][1]
    for ini, fin_i in intervalos[1:]:
        hueco = ini - fin
        if hueco >= minimo and (mejor is None or hueco > mejor[0]):
            mejor = (hueco, (fin + ini) / 2)
        fin = max(fin, fin_i)
    return mejor


def ordenar_xy(elementos, hueco_h: float = HUECO_H, hueco_v: float = HUECO_V):
    """elementos: lista de (bbox, obj). Devuelve la misma lista en orden de lectura."""
    if len(elementos) <= 1:
        return list(elementos)
    h = _mayor_hueco(elementos, "h", hueco_h)
    v = _mayor_hueco(elementos, "v", hueco_v)
    if h is None and v is None:
        return sorted(elementos, key=lambda el: (el[0][1], el[0][0]))
    if v is None or (h is not None and h[0] >= v[0]):
        eje, corte = 1, h[1]
    else:
        eje, corte = 0, v[1]
    antes = [el for el in elementos if el[0][eje] <= corte]
    despues = [el for el in elementos if el[0][eje] > corte]
    if not antes or not despues:  # no debería ocurrir; evita recursión infinita
        return sorted(elementos, key=lambda el: (el[0][1], el[0][0]))
    return ordenar_xy(antes, hueco_h, hueco_v) + ordenar_xy(despues, hueco_h, hueco_v)


def agrupar_lineas_en_bloques(lineas, factor_hueco: float = 1.6, solo_continuacion: bool = False):
    """lineas: lista de (bbox, texto). Agrupa cada línea con el bloque abierto que la precede
    verticalmente (solape horizontal y separación menor que factor_hueco × alto de línea), de
    modo que dos columnas cuyas líneas se intercalan al ordenar por y forman bloques distintos.
    Con solo_continuacion=True (encabezados y pies) solo se une una línea si la anterior de su
    bloque llegaba al margen derecho (línea partida) y ambas empiezan en la misma x.
    Devuelve [(bbox_union, [textos])] en orden de aparición."""
    bloques: list[list] = []  # [bbox_union, [textos], ultima_linea_bbox]
    margen_derecho = max((bb[2] for bb, _ in lineas), default=0.0)
    for bb, texto in sorted(lineas, key=lambda l: (round(l[0][1]), l[0][0])):
        alto = max(1.0, bb[3] - bb[1])
        destino = None
        for b in bloques:
            ubb, ultima = b[0], b[2]
            solape_x = min(bb[2], ubb[2]) - max(bb[0], ubb[0])
            # las cajas de línea de MuPDF son más altas que el paso de línea: se toleran solapes
            # de hasta medio alto de línea entre líneas consecutivas
            if solape_x <= 0 or not (-0.5 * alto <= bb[1] - ubb[3] < factor_hueco * alto):
                continue
            if solo_continuacion and not (ultima[2] >= 0.9 * margen_derecho and abs(bb[0] - ultima[0]) <= 3.0):
                continue
            destino = b
            break
        if destino is None:
            bloques.append([bb, [texto], bb])
        else:
            ubb = destino[0]
            destino[0] = (min(ubb[0], bb[0]), min(ubb[1], bb[1]), max(ubb[2], bb[2]), max(ubb[3], bb[3]))
            destino[1].append(texto)
            destino[2] = bb
    return [(tuple(b[0]), b[1]) for b in bloques]


def repartir_por_pagina(items, numeros) -> dict[int, list]:
    """{página: [(item, k)]} con un fragmento por cada procedencia `item.prov[k]`. Docling fusiona
    en un solo ítem el párrafo que continúa en otra columna o página; leer solo `prov[0]` deja el
    resto del párrafo sin dueño. Las procedencias de páginas no convertidas se ignoran."""
    por_pagina: dict[int, list] = {n: [] for n in numeros}
    for it in items:
        for k, prov in enumerate(it.prov):
            if prov.page_no in por_pagina:
                por_pagina[prov.page_no].append((it, k))
    return por_pagina


def celda_de_imagen(celdas, img) -> tuple[int, int] | None:
    """(fila, col) de la tabla donde cae una imagen. celdas: [(fila, col, bbox)] de las celdas con
    bbox y sin combinar (una tabla con fotografías no tiene celda de texto donde va la foto).
    Fila = la de mayor solape vertical con la imagen; columna = la de mayor solape horizontal;
    sin solape, la más cercana por el centro."""
    if not celdas:
        return None

    def mejor(clave: int, a: int, b: int) -> int:
        rangos: dict[int, tuple[float, float]] = {}
        for c in celdas:
            ini, fin = rangos.get(c[clave], (c[2][a], c[2][b]))
            rangos[c[clave]] = (min(ini, c[2][a]), max(fin, c[2][b]))
        centro = (img[a] + img[b]) / 2

        def puntuacion(r):
            solape = min(img[b], r[1]) - max(img[a], r[0])
            return (max(solape, 0.0), -abs((r[0] + r[1]) / 2 - centro))
        return max(rangos, key=lambda k: puntuacion(rangos[k]))

    return mejor(0, 1, 3), mejor(1, 0, 2)


def agrupar_figuras(bboxes, margen: float = 12.0) -> list[list[int]]:
    """Índices de figuras agrupadas por cercanía: dos figuras van juntas si sus cajas, ampliadas
    en `margen` puntos, se cruzan (paneles a, b, c… de una misma figura). Unión-búsqueda simple."""
    padre = list(range(len(bboxes)))

    def raiz(i):
        while padre[i] != i:
            padre[i] = padre[padre[i]]
            i = padre[i]
        return i

    def parecidas(a, b, factor: float = 2.2) -> bool:
        # los paneles de una figura tienen tamaños parecidos; un logo y un sello CrossMark, no
        wa, ha = max(a[2] - a[0], 1.0), max(a[3] - a[1], 1.0)
        wb, hb = max(b[2] - b[0], 1.0), max(b[3] - b[1], 1.0)
        return max(wa, wb) / min(wa, wb) <= factor and max(ha, hb) / min(ha, hb) <= factor

    for i in range(len(bboxes)):
        a = bboxes[i]
        for j in range(i + 1, len(bboxes)):
            b = bboxes[j]
            if (a[0] - margen < b[2] and b[0] - margen < a[2] and a[1] - margen < b[3] and b[1] - margen < a[3]
                    and parecidas(a, b)):
                padre[raiz(i)] = raiz(j)
    grupos: dict[int, list[int]] = {}
    for i in range(len(bboxes)):
        grupos.setdefault(raiz(i), []).append(i)
    return list(grupos.values())


VINETAS = frozenset("•◦▪●○■□▸►‣⁃")


def vineta_huerfana(bb, cajas, dx_max: float = 40.0) -> int | None:
    """Índice de la caja de texto que empieza a la derecha de la viñeta `bb` y en su misma línea
    (a ≤ dx_max pt), o None. Con sangría francesa (p. ej. MIS Quarterly) Docling deja la viñeta fuera
    del ítem de lista y quedaba como bloque residual suelto."""
    alto = max(bb[3] - bb[1], 4.0)
    mejor, mejor_dx = None, dx_max
    for i, c in enumerate(cajas):
        dx = c[0] - bb[2]
        if -1.0 <= dx <= mejor_dx and abs(c[1] - bb[1]) <= alto:
            mejor, mejor_dx = i, dx
    return mejor


def fusionar_residuales(entradas, unir=None, hueco_max: float = 14.0):
    """entradas: [(bbox, tipo, obj)] en orden de lectura. Un bloque `sin_clasificar` que está justo
    debajo de un párrafo (misma columna, hueco < hueco_max pt) es la continuación de ese párrafo
    cuyo bbox Docling recortó: se le une con `unir(obj_previo, obj)` (por defecto, textos con salto
    de línea). Devuelve la lista fusionada."""
    if unir is None:
        def unir(a, b):
            return a.rstrip() + "\n" + b.lstrip()
    salida: list = []
    for bb, tipo, obj in entradas:
        if tipo == "sin_clasificar" and salida:
            pbb, ptipo, pobj = salida[-1]
            solape_x = min(bb[2], pbb[2]) - max(bb[0], pbb[0])
            ancho = min(bb[2] - bb[0], pbb[2] - pbb[0])
            if (ptipo in ("parrafo", "lista", "leyenda", "nota") and solape_x > 0.5 * max(ancho, 1.0)
                    and -2.0 <= bb[1] - pbb[3] < hueco_max):
                salida[-1] = ((min(pbb[0], bb[0]), min(pbb[1], bb[1]), max(pbb[2], bb[2]), max(pbb[3], bb[3])),
                              ptipo, unir(pobj, obj))
                continue
        salida.append((bb, tipo, obj))
    return salida

