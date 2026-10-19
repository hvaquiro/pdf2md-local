---
name: Reporte de error (Bug report)
about: Informa un problema de conversión, diseño o fallo en la línea de comandos
title: "[BUG] "
labels: bug
assignees: ''
---

> ⚠️ **AVISO DE DERECHOS DE AUTOR Y PRIVACIDAD:**
> **NO adjuntes archivos PDF completos con derechos de autor ni documentos con información privada o confidencial.**
> Si el problema ocurre en una página o tabla concreta, describe cómo reproducirlo con un PDF sintético (usando `pymupdf`) o adjunta únicamente un recorte mínimo libre de derechos / anonimizado.

## Descripción del problema
Describe de forma clara y concisa qué falló o qué diferencia observas entre el PDF y el Markdown generado.

## Comando ejecutado
```bash
# Ejemplo: uv run pdf2md --origen muestra.pdf --destino salida
```

## Comportamiento esperado vs. obtenido
- **Esperado:**
- **Obtenido:**

## Salida del verificador o registro (si aplica)
Pega aquí las líneas relevantes de `_conversion.log` o del informe en `_verificacion/reporte.md`.

## Entorno
- **Sistema operativo:** (p. ej., Windows 11, Ubuntu 24.04, macOS 15)
- **Versión de Python:** (`python --version`)
- **Procesador y RAM:** (p. ej., 8 núcleos, 16 GB RAM)
- **Versión del paquete:** (`uv run pdf2md --help` / commit)

