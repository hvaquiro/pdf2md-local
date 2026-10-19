"""Modelo neutro de bloques Markdown. Sin dependencias externas.

Es el contrato entre el adaptador de Docling (que decide qué es cada región del PDF)
y el renderizador (que decide cómo se escribe en Markdown). Ninguno de los dos conoce al otro.
"""
from __future__ import annotations

from dataclasses import dataclass, field

TIPOS_BLOQUE = (
    "titulo", "seccion", "parrafo", "lista", "leyenda", "nota", "formula", "codigo",
    "tabla", "figura", "encabezado", "pie", "numero_pagina", "sin_clasificar",
)


@dataclass
class Celda:
    fila: int
    col: int
    fila_span: int = 1
    col_span: int = 1
    texto: str = ""
    encabezado: bool = False
    figuras: list[str] = field(default_factory=list)  # rutas de las imágenes que están dentro de la celda


@dataclass
class Tabla:
    filas: int
    cols: int
    celdas: list[Celda]
    caption: str = ""
    notas: list[str] = field(default_factory=list)


@dataclass
class Bloque:
    tipo: str
    texto: str = ""
    nivel: int = 1
    latex: str | None = None
    numero_ecuacion: str | None = None
    tabla: Tabla | None = None
    figura_ruta: str | None = None
    alt: str = ""
    marcador_lista: str = "-"


@dataclass
class Pagina:
    numero: int
    total: int
    encabezados: list[Bloque] = field(default_factory=list)
    cuerpo: list[Bloque] = field(default_factory=list)
    pies: list[Bloque] = field(default_factory=list)

