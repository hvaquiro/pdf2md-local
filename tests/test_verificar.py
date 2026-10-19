from pdf2md.verificar import alertas_y_notas, cobertura, normalizar_md, tokens, urls_ausentes, urls_md


def test_normalizar_md_quita_marcadores_tags_y_enlaces():
    md = ("<!-- PageHeader: X -->\n# Titulo\n<table><tr><td>a</td></tr></table>\n"
          "[ancla](https://u.org) $$x^2$$\n![alt](figures/d/1.1.jpg)")
    assert normalizar_md(md) == "X Titulo a ancla $$x^2$$ alt"  # el texto del encabezado se conserva


def test_tokens_normaliza_glifos_y_filtra():
    # "°" no es alfanumérico: "◦C" y "°C" producen ambos el token "c", que se descarta por longitud 1
    assert tokens("25 ◦C, m² fibra‐x ab") == ["25", "m2", "fibra", "ab"]  # NFKC: m² -> m2
    assert tokens("25 ◦C") == tokens("25 °C")


def test_cobertura_cuenta_multiplicidad():
    pct, faltantes = cobertura(["a", "a", "b", "c"], ["a", "b"])
    assert pct == 50.0 and faltantes == [("a", 1), ("c", 1)]


def test_urls_md():
    assert urls_md("x [t](https://a.org/1) y [u](https://b.org/2.) z") == {"https://a.org/1", "https://b.org/2"}


def test_normalizar_md_no_confunde_menor_que_con_etiqueta():
    md = "valores (p < 0.05) y luego\n<table><tr><td>a</td></tr></table>\nfin (p > 0.1)"
    assert normalizar_md(md) == "valores (p < 0.05) y luego a fin (p > 0.1)"


def test_urls_ausentes_acepta_parentesis_y_mailto():
    md = "[x](https://doi.org/10.1016/S0076-6879(99)99017-1) [m](mailto:a@b.c) [y](https://z.org/1.)"
    assert urls_ausentes({"https://doi.org/10.1016/S0076-6879(99)99017-1", "mailto:a@b.c", "https://z.org/1", "https://no.org"}, md) == ["https://no.org"]


def test_normalizar_md_conserva_texto_de_encabezados_y_pies():
    md = "<!-- PageHeader: Foods 2026, 15, 1701 -->\n<!-- PageNumber: 2 of 27 -->\ncuerpo\n<!-- PageFooter: [doi](https://x.org) -->\n<!-- PageBreak -->"
    assert normalizar_md(md) == "Foods 2026, 15, 1701 2 of 27 cuerpo doi"


def test_tokens_pliega_superindices_unicode():
    assert tokens("Ca\u00b2\u207a y \u03b7p\u00b2") == tokens("Ca2+ y \u03b7p2")


def test_enlace_con_parentesis_en_la_url_no_se_come_el_texto():
    # refhub de Elsevier: «S0960-3085(17)30154-2»; sin admitir paréntesis equilibrados la regex se
    # cortaba en «(» y, con un enlace por palabra, se desalineaba y borraba palabras.
    u = "http://refhub.elsevier.com/S0960-3085(17)30154-2/sbref0110"
    md = f"[Enzymatic]({u}) [synthesis]({u}). [Food Chem.]({u})"
    assert normalizar_md(md) == "Enzymatic synthesis. Food Chem."
    assert urls_md(md) == {u}


def test_tokens_acento_suelto_del_pdf_coincide_con_la_letra_compuesta_del_md():
    # Elsevier dibuja el acento como glifo aparte, antes o después de su letra;
    # el MD lo compone: «Gonz´alez», «Sa´nchez» y «Go¨lge» son «González», «Sánchez», «Gölge».
    assert tokens("Gonz´alez, Sa´nchez y Go¨lge") == tokens("González, Sánchez y Gölge")


def test_cobertura_acepta_palabras_que_el_pdf_trae_pegadas():
    # la capa de texto de npj pega palabras ("canbe", "awisthewater"); el MD las separa con el
    # espacio sintético, y eso no es texto perdido. Una palabra de verdad ausente sí cuenta.
    pct, faltantes = cobertura(["canbe", "awisthewater", "perdida"], ["can", "be", "aw", "is", "the", "water"])
    assert faltantes == [("perdida", 1)] and pct == 66.67


def test_alertas_solo_por_cobertura_y_enlaces():
    # solo alertan la cobertura y los enlaces faltantes; los marcadores de diagnóstico son notas
    base = {"cobertura_pct": 99.0, "enlaces_faltantes": [], "tablas": 4, "figuras": 12,
            "sin_clasificar": 1, "formulas_sin_latex": 3, "marcas_de_agua": 2, "privados_sin_mapa": 5}
    alertas, notas = alertas_y_notas(base)
    assert alertas == []
    assert notas == [
        "SinClasificar=1 FormulaSinLatex=3",
        "2 rótulos de marca de agua apartados",
        "5 caracteres de uso privado sin mapa (eliminados)",
    ]
    malo = dict(base, cobertura_pct=96.4, enlaces_faltantes=["https://x.org"])
    assert alertas_y_notas(malo)[0] == ["cobertura 96.4% < 97.0%", "1 enlaces del PDF ausentes"]
    limpio = {"cobertura_pct": 99.0, "enlaces_faltantes": [], "tablas": 4, "figuras": 3,
              "sin_clasificar": 0, "formulas_sin_latex": 0}
    assert alertas_y_notas(limpio) == ([], [])


def test_cobertura_acepta_superindices_que_el_md_une_a_su_base():
    # el PDF da el exponente como token aparte ("hp" "2" en ηp²) y el MD
    # lo escribe unido (hp² -> "hp2"): las dos piezas están presentes
    pct, faltantes = cobertura(["hp", "2", "hp", "2", "otra"], ["hp2", "hp2"])
    assert faltantes == [("otra", 1)] and pct == 80.0

