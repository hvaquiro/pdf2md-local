from pdf2md.md_modelo import Bloque, Celda, Pagina, Tabla
from pdf2md.md_render import (
    a_subindice,
    a_superindice,
    es_numero_pagina,
    nivel_por_numeracion,
    normalizar_glifos,
    parece_latex,
    render_bloque,
    render_documento,
    render_pagina,
    render_tabla_html,
)


# --- correcciones deterministas -------------------------------------------------------------

def test_normalizar_grado_y_ligaduras():
    assert normalizar_glifos("25 ◦C y 50 ºC") == "25 °C y 50 °C"
    assert normalizar_glifos("ﬁbra ﬂujo eﬀecto") == "fibra flujo effecto"


def test_guion_blando_tras_guion_o_a_mitad_de_linea_no_se_ve():
    # Wiley pone «-» y detrás un U+00AD de ancho cero: salía «Thin--layer»
    assert normalizar_glifos("Thin-­layer y anti‐­inflammatory") == "Thin-layer y anti‐inflammatory"
    assert normalizar_glifos("con­\ntributes") == "con-\ntributes"   # corte de línea: se ve
    assert normalizar_glifos("sosteni­") == "sosteni-"
    assert normalizar_glifos("sosteni­ ") == "sosteni- "
    assert normalizar_glifos("in­ter") == "inter"                    # a mitad de línea no se dibuja
    # corte de línea dentro de un enlace (bibliografía de Elsevier)
    assert normalizar_glifos("2-arachi­](http://refhub.elsevier.com/S0141-8130(25)03430-0/rf1880)") == \
        "2-arachi-](http://refhub.elsevier.com/S0141-8130(25)03430-0/rf1880)"


def test_normalizar_elimina_area_privada_y_nbsp():
    assert normalizar_glifos("a\uf0b7b\u00a0c") == "ab c"


def test_normalizar_conserva_menos_unicode_y_griegas():
    assert normalizar_glifos("g−¹ φ ±") == "g−¹ φ ±"


def test_superindice_mapeable_y_no_mapeable():
    assert a_superindice("2") == "²"
    assert a_superindice("-1") == "⁻¹"
    assert a_superindice("−1") == "⁻¹"
    assert a_superindice("abc") is None
    assert a_superindice("") is None


def test_subindice():
    assert a_subindice("0") == "₀"
    assert a_subindice("10") == "₁₀"
    assert a_subindice("x") is None


def test_es_numero_pagina():
    assert es_numero_pagina("4")
    assert es_numero_pagina(" 2 of 27 ")
    assert not es_numero_pagina("Foods 2026, 15, 1701")
    assert not es_numero_pagina("")


def test_parece_latex():
    assert parece_latex(r"\frac{a}{b}")
    assert parece_latex("x^{2}")
    assert parece_latex("A_{0}")
    assert not parece_latex("Xyl")
    assert not parece_latex("")


def test_nivel_por_numeracion():
    assert nivel_por_numeracion("2.5.1. Protein content") == 3
    assert nivel_por_numeracion("2.1 Materials") == 2
    assert nivel_por_numeracion("1. Introduction") == 1
    assert nivel_por_numeracion("Abstract") is None
    assert nivel_por_numeracion("2025 was a year") is None


# --- render -----------------------------------------------------------------------------------

def test_render_tabla_html_con_caption_spans_y_br():
    tabla = Tabla(filas=3, cols=3, caption="Table 1. Composición", celdas=[
        Celda(0, 0, texto="Component", encabezado=True),
        Celda(0, 1, col_span=2, texto="(g/100 g dm)", encabezado=True),
        Celda(1, 0, fila_span=2, texto="Water"),
        Celda(1, 1, texto="0.7"), Celda(1, 2, texto="±\n0.2"),
        Celda(2, 1, texto="a < b"), Celda(2, 2, texto="x"),
    ])
    esperado = (
        "<table>\n<caption>Table 1. Composición</caption>\n"
        "<tr>\n<th>Component</th>\n<th colspan=\"2\">(g/100 g dm)</th>\n</tr>\n"
        "<tr>\n<td rowspan=\"2\">Water</td>\n<td>0.7</td>\n<td>±<br>0.2</td>\n</tr>\n"
        "<tr>\n<td>a &lt; b</td>\n<td>x</td>\n</tr>\n</table>"
    )
    assert render_tabla_html(tabla) == esperado


def test_render_tabla_sin_caption_y_con_notas():
    tabla = Tabla(filas=1, cols=1, celdas=[Celda(0, 0, texto="a")], notas=["* nota"])
    assert render_bloque(Bloque("tabla", tabla=tabla)) == "<table>\n<tr>\n<td>a</td>\n</tr>\n</table>\n\n* nota"


def test_render_bloques_texto():
    assert render_bloque(Bloque("titulo", texto="Brewer's\nSpent Grain")) == "# Brewer's Spent Grain"
    assert render_bloque(Bloque("seccion", texto="1. Introduction", nivel=1)) == "## 1. Introduction"
    assert render_bloque(Bloque("seccion", texto="2.1. Materials", nivel=2)) == "### 2.1. Materials"
    assert render_bloque(Bloque("parrafo", texto="línea 1\nlínea 2")) == "línea 1\nlínea 2"
    assert render_bloque(Bloque("lista", texto="uno\ndos")) == "- uno dos"
    assert render_bloque(Bloque("lista", texto="uno", marcador_lista="1.")) == "1. uno"
    assert render_bloque(Bloque("leyenda", texto="Figure 1. X")) == "Figure 1. X"
    assert render_bloque(Bloque("nota", texto="* Corresponding")) == "* Corresponding"
    assert render_bloque(Bloque("codigo", texto="x = 1")) == "```\nx = 1\n```"


def test_render_formula_con_y_sin_latex():
    assert render_bloque(Bloque("formula", latex=r"P = m \cdot C_p", numero_ecuacion="(2)")) == "$$P = m \\cdot C_p$$\n(2)"
    assert render_bloque(Bloque("formula", latex=r"E = mc^2")) == "$$E = mc^2$$"
    assert render_bloque(Bloque("formula", texto="EAI = 2 x T", latex=None)) == "<!-- FormulaSinLatex -->\nEAI = 2 x T"


def test_render_figura_y_sin_clasificar():
    assert render_bloque(Bloque("figura", figura_ruta="figures/doc/3.1.jpg", alt="a ] b\nc")) == "![a b c](figures/doc/3.1.jpg)"
    assert render_bloque(Bloque("figura", figura_ruta="figures/doc/3.2.jpg")) == "![](figures/doc/3.2.jpg)"
    assert render_bloque(Bloque("sin_clasificar", texto="perdido")) == "<!-- SinClasificar -->\nperdido"


def test_render_pagina_completa():
    pagina = Pagina(
        numero=2, total=3,
        encabezados=[Bloque("numero_pagina", texto="2 of 3"), Bloque("encabezado", texto="Foods 2026,\n15, 1701"),
                     Bloque("figura", figura_ruta="figures/doc/2.1.jpg", alt="MDPI")],
        cuerpo=[Bloque("seccion", texto="2. Methods", nivel=1), Bloque("parrafo", texto="Texto.")],
        pies=[Bloque("pie", texto="doi"), Bloque("numero_pagina", texto="2")],
    )
    esperado = (
        "<!-- PageNumber: 2 of 3 -->\n<!-- PageHeader: Foods 2026, 15, 1701 -->\n"
        "<!-- PageHeader: ![MDPI](figures/doc/2.1.jpg) -->\n\n"
        "## 2. Methods\n\nTexto.\n\n"
        "<!-- PageFooter: doi -->\n<!-- PageNumber: 2 -->\n"
    )
    assert render_pagina(pagina) == esperado


def test_render_pagina_dos_lineas_en_blanco_antes_de_titulos_tablas_y_figuras():
    pagina = Pagina(1, 1, cuerpo=[
        Bloque("parrafo", texto="p"), Bloque("seccion", texto="S", nivel=1), Bloque("parrafo", texto="q"),
        Bloque("figura", figura_ruta="figures/d/1.1.jpg"), Bloque("parrafo", texto="r"),
        Bloque("tabla", tabla=Tabla(1, 1, [Celda(0, 0, texto="c")])),
    ])
    assert render_pagina(pagina) == (
        "p\n\n\n## S\n\nq\n\n\n![](figures/d/1.1.jpg)\n\nr\n\n\n<table>\n<tr>\n<td>c</td>\n</tr>\n</table>\n"
    )


def test_render_documento_une_paginas_con_pagebreak():
    p1 = Pagina(1, 2, cuerpo=[Bloque("parrafo", texto="a")])
    p2 = Pagina(2, 2, cuerpo=[Bloque("parrafo", texto="b")])
    assert render_documento([p1, p2]) == "a\n<!-- PageBreak -->\n\nb\n"


# --- fórmulas: compactación del LaTeX y control de calidad contra el texto del PDF -----------

def test_compactar_latex_une_letras_sueltas_sin_tocar_comandos():
    from pdf2md.md_render import compactar_latex
    assert compactar_latex(r"\mathrm { E A I } \left( \frac { m ^ { 2 } } { g } \right) = x \, 1 0 0") == \
        r"\mathrm { EAI } \left( \frac { m ^ { 2 } } { g } \right) = x \, 100"
    assert compactar_latex(r"A c t i v i t y \, r a t e") == r"Activity \, rate"
    assert compactar_latex(r"\text {Specific activity} + P") == r"\text {Specific activity} + P"


def test_latex_es_fiable_detecta_alucinaciones_del_modelo():
    from pdf2md.md_render import latex_es_fiable
    pdf = "Product mass yield (%)=Dry product recoveredafter encapsulation (g)\nTotalsolid materialfedtothe spray dryer (g) x 100\n(1)"
    malo = r"P r o d u c t m a s s y i e l d = \frac { D r y p r o d u c t } { T o t a l s o i l d m a t i e r a l } \text {Prote} \text {Prote} \text {Brad}"
    assert not latex_es_fiable(malo, pdf)
    bueno = r"A c t i v i t y \, r e c o v e r y \, r a t e = \frac { T o t a l \, E n z y m e } { a f t e r \, e n c a p s u l a t i o n }"
    assert latex_es_fiable(bueno, "Activity recovery rate (%) = Total Enzyme activity after encapsulation (U)")
    # una fórmula simbólica sin palabras siempre es fiable
    assert latex_es_fiable(r"\frac { 2 \times T \times A _ { 0 } } { \varphi \times C \times L }", "2 x T x A0 / phi x C x L")
    assert not latex_es_fiable("", "x")


# --- niveles de encabezados no numerados ------------------------------------------------------

def test_ajustar_niveles_encabezados_no_numerados():
    from pdf2md.md_render import ajustar_niveles_encabezados
    def sec(t, n=1):
        return Bloque("seccion", texto=t, nivel=n)
    p1 = Pagina(1, 2, cuerpo=[sec("ABSTRACT"), sec("1. Introduction"), sec("2. Methods"), sec("2.5. Chemical", 2),
                              sec("2.5.3. Polyphenols", 3), sec("Determination of antioxidant activity."),
                              sec("2.5.4. Alkaloids", 3)])
    p2 = Pagina(2, 2, cuerpo=[sec("3. Results"), sec("Acknowledgements"), sec("References")])
    ajustar_niveles_encabezados([p1, p2])
    assert [b.nivel for b in p1.cuerpo] == [1, 1, 1, 2, 3, 4, 3]
    assert [b.nivel for b in p2.cuerpo] == [1, 1, 1]


# --- título de portada y marcadores de lista --------------------------------------------------

def test_elegir_titulo_prefiere_fuente_grande_y_texto_largo():
    from pdf2md.md_render import elegir_titulo
    candidatos = [  # (texto, tamaño de fuente, tipo)
        ("Ultrasonics Sonochemistry", 16.0, "seccion"),                       # nombre de revista: corto
        ("High-power ultrasound pretreatment for enhanced protein extraction from lupin flour", 14.0, "parrafo"),
        ("Contents lists available at ScienceDirect", 8.0, "parrafo"),
        ("Quality of lupin protein is considerably compromised by the presence of anti-nutritional factors", 9.0, "parrafo"),
    ]
    assert elegir_titulo(candidatos, tam_mediana=9.0) == 1
    # sin ningún bloque claramente mayor que el texto normal no hay título
    assert elegir_titulo([("Un párrafo normal y bastante largo para pasar el filtro", 9.2, "parrafo")], tam_mediana=9.0) is None
    assert elegir_titulo([], tam_mediana=9.0) is None


def test_marcador_de_lista():
    from pdf2md.md_render import marcador_de_lista
    assert marcador_de_lista("• Item con viñeta propia", "-", False) == ""
    assert marcador_de_lista("a Grupo ASPA, Institute of Food Engineering", "a", False) == ""
    assert marcador_de_lista("a Grupo ASPA, Institute of Food Engineering", "-", False) == ""
    assert marcador_de_lista("Item sin viñeta", "-", False) == "-"
    assert marcador_de_lista("Item numerado por Docling", "1.", True) == "1."
    assert marcador_de_lista("1. Ya numerado en el PDF", "1.", True) == ""
    assert marcador_de_lista("(a) Ya numerado en el PDF", "(a)", True) == ""


def test_marcador_de_lista_referencia_entre_corchetes():
    # En algunas revistas de Elsevier la referencia ya trae "[6]" y el marcador de Docling lo duplicaba
    from pdf2md.md_render import marcador_de_lista
    assert marcador_de_lista("[6] Goetzberger A, Zastrow A. On the coexistence", "[6]", True) == ""
    assert marcador_de_lista("[127] Duffie J a, Beckman W a", "[127]", True) == ""
    # En otras revistas el número va pegado al enlace de la referencia
    assert marcador_de_lista("[14][Official methods and recommended practices](https://x.org)", "[14]", True) == ""


def test_marcador_de_lista_afiliaciones_numeradas():
    from pdf2md.md_render import marcador_de_lista
    assert marcador_de_lista("1 Department of Chemistry, University of the Balearic Islands", "-", False) == ""
    assert marcador_de_lista("2 Analysis and Simulation of Agro-Food Processes Group", "2", True) == ""


def test_espacio_tras_numeracion_de_encabezado():
    from pdf2md.md_render import nivel_por_numeracion, normalizar_encabezado
    # la capa de texto de RSC omite el espacio tras el número: "2Materials", "2.1.Reagents"
    assert normalizar_encabezado("2Materials and methods") == "2 Materials and methods"
    assert normalizar_encabezado("2.1.Reagents") == "2.1. Reagents"
    assert normalizar_encabezado("2.3.1. Film characterisation") == "2.3.1. Film characterisation"
    assert normalizar_encabezado("Abstract") == "Abstract"
    assert nivel_por_numeracion("2Materials and methods") == 1
    assert nivel_por_numeracion("2.1.Reagents") == 2
    assert nivel_por_numeracion("2025 was a year") is None


def test_render_tabla_con_fotos_en_celdas_y_sin_filas_vacias():
    # fotos dentro de celdas (tabla de variedades con fotografías): ![](ruta), varias con <br>;
    # una fila cuyas celdas quedaron todas vacías (texto oculto del PDF descartado) no se emite
    tabla = Tabla(filas=3, cols=2, celdas=[
        Celda(0, 0, texto="Variety", encabezado=True), Celda(0, 1, texto="Photograph", encabezado=True),
        Celda(1, 0, texto="Sample A"), Celda(1, 1, figuras=["figures/d/11.1.jpg", "figures/d/11.2.jpg"]),
        Celda(2, 0, texto=""), Celda(2, 1, texto=" "),
    ])
    assert render_tabla_html(tabla) == (
        "<table>\n<tr>\n<th>Variety</th>\n<th>Photograph</th>\n</tr>\n"
        "<tr>\n<td>Sample A</td>\n<td>![](figures/d/11.1.jpg)<br>![](figures/d/11.2.jpg)</td>\n</tr>\n</table>"
    )


def test_respaldo_docling_solo_sin_capa_de_texto():
    from pdf2md.md_render import respaldo_docling
    # con capa de texto, una región sin caracteres visibles es texto oculto (recortado) que solo
    # ve el parser de Docling: "Gels 2025, 11, x FOR PEER REVIEW" repetido bajo una tabla
    assert respaldo_docling("Gels 2025 , 11 , x FOR PEER REVIEW", hay_capa_texto=True) == ""
    assert respaldo_docling("texto de OCR a 25 ◦C", hay_capa_texto=False) == "texto de OCR a 25 °C"
    assert respaldo_docling(None, hay_capa_texto=False) == ""


def test_ligaduras_en_area_de_uso_privado_de_rsc():
    # las fuentes AdvOT de RSC codifican fi, fl, ft y fb en el área de uso privado; descartarlas
    # dejaba "lms" por "films" y "signicant" por "significant"
    assert normalizar_glifos("pectin \ue103lms, air\ue104ow, so\ue09dware, d6\ue09200037a") == \
        "pectin films, airflow, software, d6fb00037a"
    assert normalizar_glifos("x\ue000y") == "xy"  # el resto del área privada se sigue eliminando

