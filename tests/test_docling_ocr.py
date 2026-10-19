from pathlib import Path

import pytest
from docling.datamodel.accelerator_options import AcceleratorOptions
from docling.datamodel.pipeline_options import RapidOcrOptions
from docling.models.stages.ocr.rapid_ocr_model import RapidOcrModel

from pdf2md.docling_adaptador import OpcionesConversion, construir_convertidor


def test_construir_convertidor_con_ocr():
    from docling.datamodel.base_models import InputFormat
    op = OpcionesConversion(ocr=True, hilos=4)
    conv = construir_convertidor(op)
    pipeline_opts = conv.format_to_options[InputFormat.PDF].pipeline_options
    assert pipeline_opts.do_ocr is True
    assert isinstance(pipeline_opts.ocr_options, RapidOcrOptions)
    assert pipeline_opts.ocr_options.backend == "torch"
    assert pipeline_opts.ocr_options.lang == ["es"]


@pytest.mark.modelos
def test_modelos_rapidocr_presentes():
    cache_dir = Path.home() / ".cache" / "docling" / "models" / "RapidOcr"
    assert cache_dir.exists(), f"El directorio {cache_dir} debe existir"
    archivos_esperados = [
        "PP-OCRv6_det_small.pth",
        "ch_ptocr_mobile_v2.0_cls_mobile.pth",
        "PP-OCRv6_rec_small.pth",
        "ppocrv6_dict.txt",
    ]
    for arch in archivos_esperados:
        p = cache_dir / arch
        assert p.is_file(), f"Falta el modelo {arch} en {cache_dir}"
        assert p.stat().st_size > 0, f"El archivo {arch} no debe estar vacío"


@pytest.mark.modelos
def test_inicializar_rapidocr_model():
    cache_base = Path.home() / ".cache" / "docling" / "models"
    options = RapidOcrOptions(backend="torch", lang=["es"])
    ocr_model = RapidOcrModel(
        enabled=True,
        artifacts_path=cache_base,
        options=options,
        accelerator_options=AcceleratorOptions(),
    )
    assert ocr_model is not None

