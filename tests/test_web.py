"""Pruebas de la aplicacion Flask.

Usan el cliente de pruebas de Flask, asi que no levantan un servidor real.

    pytest tests/ -v
"""

import io
import json
import zipfile

import pytest

import app as web_app


@pytest.fixture()
def cliente():
    web_app.app.config.update(TESTING=True)
    with web_app.app.test_client() as c:
        yield c


PEDIDO_VALIDO = """PEDIDO {
    cliente: "Carlos"
    producto: "Pizza"
    total: 80
    pago: YAPE
    direccion: "Av. Lima 123"
    stock: 4
}

VALIDAR stock
ASIGNAR repartidor
FINALIZAR pedido
"""

necesita_compilador = pytest.mark.skipif(
    not web_app.COMPILER.exists(),
    reason=f"No existe {web_app.COMPILER.name}. Compila primero con 'make'.",
)


# ─── Pagina principal ─────────────────────────────────────────────
def test_la_pagina_carga(cliente):
    respuesta = cliente.get("/")
    assert respuesta.status_code == 200
    assert b"PEDIDO" in respuesta.data, "debe precargar el ejemplo en el editor"


# ─── /compile ─────────────────────────────────────────────────────
def test_compile_con_el_editor_vacio(cliente):
    respuesta = cliente.post("/compile", json={"source": "   "})
    datos = respuesta.get_json()
    assert datos["success"] is False
    assert any("vacio" in e for e in datos["errors"])


def test_compile_sin_cuerpo_no_revienta(cliente):
    respuesta = cliente.post("/compile", json={})
    assert respuesta.status_code == 200
    assert respuesta.get_json()["success"] is False


def test_compile_con_source_que_no_es_texto(cliente):
    respuesta = cliente.post("/compile", json={"source": 12345})
    assert respuesta.status_code == 200
    assert respuesta.get_json()["success"] is False


@necesita_compilador
def test_compile_con_dsl_valido(cliente):
    datos = cliente.post("/compile", json={"source": PEDIDO_VALIDO}).get_json()
    assert datos["success"] is True
    assert datos["errors"] == []
    assert len(datos["tokens"]) > 10
    assert datos["order"]["cliente"] == "Carlos"


@necesita_compilador
def test_compile_con_dsl_invalido_devuelve_errores(cliente):
    datos = cliente.post("/compile", json={"source": "VALIDAR stock\n"}).get_json()
    assert datos["success"] is False
    assert datos["errors"]


@necesita_compilador
def test_regresion_compile_no_se_cuelga_con_una_llave(cliente):
    """Regresion: este contenido colgaba el compilador diez segundos (hasta el
    timeout de subprocess) mientras consumia cientos de MB de memoria."""
    import time

    inicio = time.time()
    datos = cliente.post("/compile", json={"source": "}"}).get_json()
    transcurrido = time.time() - inicio

    assert transcurrido < 5, f"tardo {transcurrido:.1f}s; antes agotaba el timeout"
    assert datos["success"] is False
    assert datos["errors"]


@necesita_compilador
def test_compile_siempre_devuelve_las_claves_del_contrato(cliente):
    for fuente in (PEDIDO_VALIDO, "}", "basura", 'PEDIDO {'):
        datos = cliente.post("/compile", json={"source": fuente}).get_json()
        for clave in ("success", "tokens", "order", "logs", "errors"):
            assert clave in datos, f"falta '{clave}' con la entrada {fuente!r}"


# ─── /upload-rules ────────────────────────────────────────────────
def test_upload_sin_archivo(cliente):
    respuesta = cliente.post("/upload-rules", data={})
    assert respuesta.status_code == 400
    assert respuesta.get_json()["success"] is False


def test_upload_rechaza_extensiones_no_permitidas(cliente):
    for nombre in ("reglas.zip", "reglas.exe", "reglas.doc", "reglas"):
        respuesta = cliente.post(
            "/upload-rules",
            data={"rules": (io.BytesIO(b"contenido"), nombre)},
            content_type="multipart/form-data",
        )
        assert respuesta.status_code == 400, f"{nombre} deberia rechazarse"


def test_upload_acepta_un_txt_y_genera_dsl(cliente):
    contenido = b"cliente: Ana\nproducto: Pizza\ntotal: 90\nstock: 3\n"
    respuesta = cliente.post(
        "/upload-rules",
        data={"rules": (io.BytesIO(contenido), "reglas.txt")},
        content_type="multipart/form-data",
    )
    assert respuesta.status_code == 200

    datos = respuesta.get_json()
    assert datos["success"] is True
    assert "PEDIDO" in datos["dsl_draft"]


@necesita_compilador
def test_el_dsl_generado_desde_reglas_compila(cliente):
    """La plantilla que produce /upload-rules debe ser compilable: si no, el
    boton 'usar en el editor' entrega codigo roto."""
    contenido = b"cliente: Ana\nproducto: Pizza\ntotal: 90\nstock: 3\n"
    subida = cliente.post(
        "/upload-rules",
        data={"rules": (io.BytesIO(contenido), "reglas.txt")},
        content_type="multipart/form-data",
    ).get_json()

    resultado = cliente.post("/compile", json={"source": subida["dsl_draft"]}).get_json()
    assert resultado["success"] is True, f"la plantilla no compila: {resultado['errors']}"


def test_upload_rechaza_un_archivo_por_encima_del_limite(cliente):
    grande = b"a" * (web_app.MAX_UPLOAD_BYTES + 1024)
    respuesta = cliente.post(
        "/upload-rules",
        data={"rules": (io.BytesIO(grande), "reglas.txt")},
        content_type="multipart/form-data",
    )
    assert respuesta.status_code == 413
    assert respuesta.get_json()["success"] is False, "el 413 debe responder JSON, no HTML"


def test_upload_rechaza_una_bomba_zip(cliente, tmp_path):
    """Un .xlsx es un ZIP: uno pequeño puede descomprimirse en varios GB."""
    bomba = tmp_path / "bomba.xlsx"
    with zipfile.ZipFile(bomba, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("xl/worksheets/sheet1.xml", b"\0" * (web_app.MAX_UNCOMPRESSED_BYTES + 1024))

    assert bomba.stat().st_size < web_app.MAX_UPLOAD_BYTES, "la bomba pasa el filtro de tamaño"

    respuesta = cliente.post(
        "/upload-rules",
        data={"rules": (io.BytesIO(bomba.read_bytes()), "reglas.xlsx")},
        content_type="multipart/form-data",
    )
    assert respuesta.status_code == 400
    assert any("descomprimido" in e for e in respuesta.get_json()["errors"])


def test_los_errores_no_filtran_rutas_del_servidor(cliente):
    """Un fallo interno no debe devolver str(exc), que puede llevar rutas."""
    respuesta = cliente.post(
        "/upload-rules",
        data={"rules": (io.BytesIO(b"esto no es un docx"), "reglas.docx")},
        content_type="multipart/form-data",
    )
    assert respuesta.status_code == 400

    texto = json.dumps(respuesta.get_json())
    for fragmento in ("/home/", "C:\\", "Traceback", "site-packages"):
        assert fragmento not in texto, f"la respuesta filtra '{fragmento}'"


# ─── Configuracion ────────────────────────────────────────────────
def test_el_nombre_del_compilador_depende_del_sistema():
    """Regresion: app.py buscaba delivery_compiler.exe siempre, mientras que
    el Dockerfile compila delivery_compiler. En Linux nunca lo encontraba."""
    import os

    esperado = "delivery_compiler.exe" if os.name == "nt" else "delivery_compiler"
    assert web_app.COMPILER.name == esperado


def test_hay_limite_de_subida_configurado():
    assert web_app.app.config["MAX_CONTENT_LENGTH"] == web_app.MAX_UPLOAD_BYTES
