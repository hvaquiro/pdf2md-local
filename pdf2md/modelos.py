#!/usr/bin/env python3
"""Descarga y aprovisionamiento de todos los modelos requeridos por pdf2md.

1. Modelos de Docling (layout-heron, TableFormer y CodeFormulaV2) desde Hugging Face.
2. Modelos de RapidOCR (PP-OCRv6 multilingüe y script latino para PyTorch CPU) desde ModelScope,
   con resolución DNS-over-HTTPS (Google / Cloudflare) como respaldo cuando el resolvedor DNS
   local rechaza el CDN de ModelScope.

Uso:
    pdf2md-modelos [--destino RUTA] [--forzar] [--solo-ocr] [--sin-ocr]
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import urllib.request
from pathlib import Path

# Modelos oficiales requeridos por Docling 2.128 + RapidOCR 3.9.2 con backend PyTorch (torch)
MODELOS_RAPIDOCR = [
    # PP-OCRv6 (Multilingüe unificado: español, inglés, portugués, chino, etc.)
    (
        "PP-OCRv6_det_small.pth",
        "https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.9.2/torch/PP-OCRv6/det/PP-OCRv6_det_small.pth",
    ),
    (
        "ch_ptocr_mobile_v2.0_cls_mobile.pth",
        "https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.9.2/torch/PP-OCRv4/cls/ch_ptocr_mobile_v2.0_cls_mobile.pth",
    ),
    (
        "PP-OCRv6_rec_small.pth",
        "https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.9.2/torch/PP-OCRv6/rec/PP-OCRv6_rec_small.pth",
    ),
    (
        "ppocrv6_dict.txt",
        "https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.9.2/paddle/PP-OCRv6/rec/PP-OCRv6_rec_small/ppocrv6_dict.txt",
    ),
    # PP-OCRv4 / v3 (Fallback específico para script latino puro 'latin')
    (
        "ch_PP-OCRv4_det_mobile.pth",
        "https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.9.2/torch/PP-OCRv4/det/ch_PP-OCRv4_det_mobile.pth",
    ),
    (
        "latin_PP-OCRv3_rec_mobile.pth",
        "https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.9.2/torch/PP-OCRv4/rec/latin_PP-OCRv3_rec_mobile.pth",
    ),
    (
        "latin_dict.txt",
        "https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.9.2/paddle/PP-OCRv4/rec/latin_PP-OCRv3_rec_mobile/latin_dict.txt",
    ),
]

_DNS_CACHE: dict[str, list[str]] = {}
_ORIG_GETADDRINFO = socket.getaddrinfo


def _resolver_doh(host: str) -> list[str]:
    """Resuelve un hostname usando DoH público (Google / Cloudflare)."""
    if host in _DNS_CACHE:
        return _DNS_CACHE[host]
    for doh_url in [
        f"https://dns.google/resolve?name={host}&type=A",
        f"https://cloudflare-dns.com/dns-query?name={host}&type=A",
    ]:
        try:
            req = urllib.request.Request(
                doh_url,
                headers={"User-Agent": "RapidOcrDownloader/1.0", "Accept": "application/dns-json"},
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                ips = [ans["data"] for ans in data.get("Answer", []) if ans.get("type") == 1]
                if ips:
                    _DNS_CACHE[host] = ips
                    return ips
        except Exception:
            continue
    return []


def _patched_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    if isinstance(host, str) and ("modelscope.cn" in host or "kunlunaq.com" in host):
        ips = _resolver_doh(host)
        if ips:
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ips[0], port))]
    return _ORIG_GETADDRINFO(host, port, family, type, proto, flags)


def activar_parche_dns():
    socket.getaddrinfo = _patched_getaddrinfo


def descargar_archivo(url: str, destino: Path, forzar: bool = False) -> bool:
    """Descarga un archivo con streaming y reporte de progreso."""
    if destino.exists() and not forzar and destino.stat().st_size > 0:
        print(f"  [OK] {destino.name} ya existe ({destino.stat().st_size:,} bytes)")
        return True

    import requests

    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = destino.with_suffix(destino.suffix + ".tmp")

    print(f"  -> Descargando {destino.name}...")
    try:
        with requests.get(url, stream=True, timeout=30) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length", 0))
            descargado = 0
            with open(tmp_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
                        descargado += len(chunk)
                        if total > 0:
                            pct = (descargado / total) * 100
                            sys.stdout.write(f"\r     {descargado:,} / {total:,} bytes ({pct:.1f}%)")
                        else:
                            sys.stdout.write(f"\r     {descargado:,} bytes")
                        sys.stdout.flush()
        print()
        tmp_path.replace(destino)
        print(f"  [OK] Guardado en {destino}")
        return True
    except Exception as e:
        print(f"\n  [ERROR] Falló la descarga de {destino.name}: {e}")
        if tmp_path.exists():
            tmp_path.unlink()
        return False


def ruta_base_modelos() -> Path:
    """Determina la carpeta raíz donde se guardan los modelos de Docling y RapidOCR."""
    env_path = os.environ.get("DOCLING_ARTIFACTS_PATH")
    if env_path:
        return Path(env_path)
    return Path.home() / ".cache" / "docling" / "models"


def ruta_destino_modelos() -> Path:
    """Determina la ruta destino estándar para los modelos RapidOCR."""
    return ruta_base_modelos() / "RapidOcr"


def descargar_modelos_docling(destino_base: Path, forzar: bool = False) -> bool:
    """Descarga layout, tableformer y code_formula con el descargador de Docling."""
    from docling.utils.model_downloader import download_models

    print("=== Descarga de modelos de Docling (layout, tableformer, code_formula) ===")
    print(f"Destino: {destino_base}")
    try:
        download_models(
            output_dir=destino_base,
            force=forzar,
            progress=True,
            with_layout=True,
            with_tableformer=True,
            with_tableformer_v2=False,
            with_code_formula=True,
            with_picture_classifier=False,
            with_smolvlm=False,
            with_granitedocling=False,
            with_granitedocling_mlx=False,
            with_granitedocling_2stage=False,
            with_smoldocling=False,
            with_smoldocling_mlx=False,
            with_granite_vision=False,
            with_granite_chart_extraction=False,
            with_granite_chart_extraction_v4=False,
            with_rapidocr=False,
            with_easyocr=False,
            with_nemotron_ocr=False,
        )
        print("  [OK] Modelos de Docling listos.")
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"  [ERROR] Falló la descarga de modelos de Docling: {exc}", file=sys.stderr)
        return False


def descargar_modelos_ocr(destino_ocr: Path, forzar: bool = False) -> int:
    """Descarga los pesos de RapidOCR en `destino_ocr`. Devuelve el número de fallos."""
    print(f"=== Descarga de modelos RapidOCR ===")
    print(f"Destino: {destino_ocr}")
    activar_parche_dns()

    fallos = 0
    for nombre, url in MODELOS_RAPIDOCR:
        dest = destino_ocr / nombre
        if not descargar_archivo(url, dest, forzar=forzar):
            fallos += 1
    return fallos


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument(
        "--destino",
        type=Path,
        default=ruta_base_modelos(),
        help="Carpeta raíz para los modelos (por defecto DOCLING_ARTIFACTS_PATH o ~/.cache/docling/models)",
    )
    ap.add_argument("--forzar", action="store_true", help="Volver a descargar aunque ya existan")
    ap.add_argument("--solo-ocr", action="store_true", help="Descargar únicamente los modelos de RapidOCR")
    ap.add_argument("--sin-ocr", action="store_true", help="Omitir los modelos de RapidOCR")
    args = ap.parse_args()

    base = args.destino
    ok = True
    if not args.solo_ocr:
        ok = descargar_modelos_docling(base, forzar=args.forzar)

    if not args.sin_ocr:
        # Si el usuario pasó directamente una carpeta llamada RapidOcr, no anidar otra
        dir_ocr = base if base.name.lower() == "rapidocr" else (base / "RapidOcr")
        fallos_ocr = descargar_modelos_ocr(dir_ocr, forzar=args.forzar)
        if fallos_ocr > 0:
            print(f"\n[ALERTA] Hubo {fallos_ocr} archivo(s) de RapidOCR que no se pudieron descargar.")
            ok = False

    if not ok:
        return 1
    print("\nTodos los modelos solicitados están listos.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

