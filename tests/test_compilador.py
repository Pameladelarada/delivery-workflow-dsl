"""Pruebas del compilador del DSL.

Ejercitan el binario ya compilado, que es como lo usa la web: se le pasa un
archivo .dsl y se lee su salida JSON por stdout.

    pytest tests/ -v

Requiere haber compilado antes:  make   (o build.ps1 en Windows)
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
COMPILADOR = RAIZ / "bin" / ("delivery_compiler.exe" if os.name == "nt" else "delivery_compiler")

pytestmark = pytest.mark.skipif(
    not COMPILADOR.exists(),
    reason=f"No existe {COMPILADOR.name}. Compila primero con 'make'.",
)


def compilar(fuente: str, tmp_path: Path, timeout: int = 10):
    """Escribe el DSL en un archivo, ejecuta el compilador y devuelve
    (codigo_de_salida, json_parseado)."""
    archivo = tmp_path / "programa.dsl"
    archivo.write_text(fuente, encoding="utf-8")

    proceso = subprocess.run(
        [str(COMPILADOR), str(archivo)],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    try:
        salida = json.loads(proceso.stdout)
    except json.JSONDecodeError as exc:
        pytest.fail(
            f"El compilador no devolvio JSON valido: {exc}\n"
            f"stdout: {proceso.stdout[:500]}\nstderr: {proceso.stderr[:500]}"
        )
    return proceso.returncode, salida


PEDIDO_VALIDO = """PEDIDO {
    cliente: "Carlos"
    producto: "Pizza Familiar"
    total: 80
    pago: YAPE
    direccion: "Av. Lima 123"
    stock: 4
}

VALIDAR stock
VALIDAR direccion
VALIDAR pago

SI total > 50 {
    ASIGNAR prioridad_alta
}

ASIGNAR repartidor
INICIAR entrega
FINALIZAR pedido
"""


# ─── Analisis lexico ──────────────────────────────────────────────
def test_reconoce_los_tipos_de_token(tmp_path):
    _, salida = compilar(PEDIDO_VALIDO, tmp_path)
    tipos = {token["type"] for token in salida["tokens"]}
    assert {"RESERVED", "IDENTIFIER", "NUMBER", "STRING", "LBRACE", "RBRACE",
            "COLON", "OPERATOR"} <= tipos


def test_registra_linea_y_columna(tmp_path):
    _, salida = compilar(PEDIDO_VALIDO, tmp_path)
    primero = salida["tokens"][0]
    assert primero["lexeme"] == "PEDIDO"
    assert primero["line"] == 1
    assert primero["column"] == 1

    for token in salida["tokens"]:
        assert token["line"] >= 1
        assert token["column"] >= 1


def test_las_cadenas_conservan_los_espacios(tmp_path):
    _, salida = compilar(PEDIDO_VALIDO, tmp_path)
    cadenas = [t["lexeme"] for t in salida["tokens"] if t["type"] == "STRING"]
    assert "Pizza Familiar" in cadenas
    assert "Av. Lima 123" in cadenas


def test_caracter_no_reconocido_da_error(tmp_path):
    codigo, salida = compilar("PEDIDO {\n    cliente: @\n}\n", tmp_path)
    assert codigo != 0
    assert salida["errors"]


# ─── Analisis sintactico ──────────────────────────────────────────
def test_pedido_valido_no_tiene_errores(tmp_path):
    codigo, salida = compilar(PEDIDO_VALIDO, tmp_path)
    assert codigo == 0
    assert salida["success"] is True
    assert salida["errors"] == []


def test_lee_los_campos_del_pedido(tmp_path):
    _, salida = compilar(PEDIDO_VALIDO, tmp_path)
    assert salida["order"]["cliente"] == "Carlos"
    assert salida["order"]["total"] == 80
    assert salida["order"]["stock"] == 4


def test_llave_sin_cerrar_da_error(tmp_path):
    codigo, salida = compilar('PEDIDO {\n    cliente: "Ana"\n', tmp_path)
    assert codigo != 0
    assert salida["errors"]


def test_cadena_sin_cerrar_da_error(tmp_path):
    codigo, salida = compilar('PEDIDO {\n    cliente: "Ana\n}\n', tmp_path)
    assert codigo != 0
    assert salida["errors"]


# ─── Analisis semantico ───────────────────────────────────────────
def test_exige_un_bloque_pedido(tmp_path):
    codigo, salida = compilar("VALIDAR stock\n", tmp_path)
    assert codigo != 0
    assert any("PEDIDO" in e for e in salida["errors"])


def test_rechaza_validar_fuera_del_dominio(tmp_path):
    codigo, salida = compilar(
        'PEDIDO {\n    cliente: "Ana"\n}\nVALIDAR color_favorito\n', tmp_path
    )
    assert codigo != 0
    assert any("dominio" in e for e in salida["errors"])


def test_no_valida_un_campo_ausente(tmp_path):
    codigo, salida = compilar(
        'PEDIDO {\n    cliente: "Ana"\n}\nVALIDAR stock\n', tmp_path
    )
    assert codigo != 0
    assert any("no existe en PEDIDO" in e for e in salida["errors"])


def test_stock_debe_ser_positivo(tmp_path):
    codigo, salida = compilar(
        'PEDIDO {\n    cliente: "Ana"\n    stock: 0\n}\nVALIDAR stock\n', tmp_path
    )
    assert codigo != 0
    assert any("mayor que cero" in e for e in salida["errors"])


def test_condicion_sobre_variable_inexistente_da_error(tmp_path):
    codigo, salida = compilar(
        'PEDIDO {\n    cliente: "Ana"\n}\nSI descuento > 10 {\n'
        "    ASIGNAR prioridad_alta\n}\n",
        tmp_path,
    )
    assert codigo != 0
    assert any("descuento" in e for e in salida["errors"])


def test_la_condicion_si_se_evalua(tmp_path):
    _, salida = compilar(PEDIDO_VALIDO, tmp_path)
    condiciones = [log for log in salida["logs"] if log.startswith("Condicion SI")]
    assert condiciones
    assert "aprobada" in condiciones[0]


# ─── Regresiones de bugs corregidos ───────────────────────────────
def test_regresion_llave_suelta_no_cuelga(tmp_path):
    """Regresion: una llave de cierre suelta colgaba el compilador para
    siempre y consumia 350 MB de RAM en cinco segundos.

    synchronize() devolvia el control sin consumir la llave, asi que parse()
    encontraba el mismo token una y otra vez.
    """
    codigo, salida = compilar("}\n", tmp_path, timeout=5)
    assert codigo != 0
    assert salida["errors"]
    assert len(salida["errors"]) <= 101, "la lista de errores debe estar acotada"


def test_regresion_numero_enorme_no_cuelga(tmp_path):
    """Regresion: un numero que desborda double hacia lanzar a std::stod y el
    flujo terminaba en el mismo bucle infinito."""
    enorme = "9" * 320
    codigo, _ = compilar(f"PEDIDO {{\n    total: {enorme}\n}}\n", tmp_path, timeout=5)
    assert codigo != 0


@pytest.mark.parametrize(
    "basura",
    ["}", "}}}}}}", "{{{{{{", "}{}{}{", ":::", "PEDIDO }", "VALIDAR", "SI"],
    ids=["una-llave", "muchas-cierre", "muchas-apertura", "alternadas",
         "dos-puntos", "pedido-mal", "validar-solo", "si-solo"],
)
def test_regresion_ninguna_basura_cuelga(basura, tmp_path):
    """Ninguna entrada debe hacer que el compilador deje de terminar."""
    codigo, _ = compilar(basura + "\n", tmp_path, timeout=5)
    assert codigo is not None


def test_regresion_caracter_de_control_produce_json_valido(tmp_path):
    """Regresion: jsonEscape no escapaba los caracteres de control, asi que la
    salida dejaba de ser JSON y la web mostraba 'no devolvio JSON valido'.

    Que compilar() no llame a pytest.fail ya prueba que el JSON es valido.
    """
    codigo, salida = compilar('PEDIDO {\n    cliente: "A\x01B"\n}\n', tmp_path)
    cadenas = [t["lexeme"] for t in salida["tokens"] if t["type"] == "STRING"]
    assert cadenas == ["A\x01B"], "el caracter debe sobrevivir al viaje de ida y vuelta"


def test_regresion_el_log_no_aprueba_lo_que_fallo(tmp_path):
    """Regresion: el log decia 'Validacion aprobada: stock' junto al error que
    declaraba ese mismo stock invalido."""
    _, salida = compilar(
        'PEDIDO {\n    cliente: "Ana"\n    stock: 0\n    direccion: ""\n}\n'
        "VALIDAR stock\nVALIDAR direccion\nVALIDAR cliente\n",
        tmp_path,
    )
    assert "Validacion aprobada: stock" not in salida["logs"]
    assert "Validacion aprobada: direccion" not in salida["logs"]
    assert "Validacion aprobada: cliente" in salida["logs"], (
        "el campo correcto si debe aparecer como aprobado"
    )


# ─── Contrato con la web ──────────────────────────────────────────
@pytest.mark.parametrize(
    "fuente",
    [PEDIDO_VALIDO, "}", "", "PEDIDO {", "basura sin sentido", '"cadena suelta"'],
    ids=["valido", "llave", "vacio", "incompleto", "basura", "cadena"],
)
def test_la_salida_siempre_tiene_la_forma_esperada(fuente, tmp_path):
    """La web hace json.loads() de la salida y lee estas cuatro claves.
    Todas deben existir siempre, pase lo que pase con la entrada."""
    _, salida = compilar(fuente, tmp_path, timeout=5)
    for clave in ("success", "tokens", "order", "logs", "errors"):
        assert clave in salida, f"falta la clave '{clave}'"
    assert isinstance(salida["tokens"], list)
    assert isinstance(salida["logs"], list)
    assert isinstance(salida["errors"], list)


def test_success_es_falso_si_y_solo_si_hay_errores(tmp_path):
    for fuente in (PEDIDO_VALIDO, "}", 'PEDIDO {\n    cliente: "A"\n}\nVALIDAR stock\n'):
        _, salida = compilar(fuente, tmp_path, timeout=5)
        assert salida["success"] == (len(salida["errors"]) == 0)


# ─── Los ejemplos del proyecto ────────────────────────────────────
def test_ejemplo_pedido_basico_es_valido():
    proceso = subprocess.run(
        [str(COMPILADOR), str(RAIZ / "examples" / "pedido_basico.dsl")],
        capture_output=True, text=True, timeout=10,
    )
    assert proceso.returncode == 0
    assert json.loads(proceso.stdout)["success"] is True


def test_ejemplo_error_semantico_falla_como_se_espera():
    proceso = subprocess.run(
        [str(COMPILADOR), str(RAIZ / "examples" / "error_semantico.dsl")],
        capture_output=True, text=True, timeout=10,
    )
    assert proceso.returncode == 2
    salida = json.loads(proceso.stdout)
    assert salida["success"] is False
    assert salida["errors"]


def test_sin_argumentos_no_revienta():
    proceso = subprocess.run([str(COMPILADOR)], capture_output=True, text=True, timeout=10)
    assert proceso.returncode != 0


def test_archivo_inexistente_devuelve_json(tmp_path):
    proceso = subprocess.run(
        [str(COMPILADOR), str(tmp_path / "no_existe.dsl")],
        capture_output=True, text=True, timeout=10,
    )
    assert proceso.returncode != 0
    salida = json.loads(proceso.stdout)
    assert salida["success"] is False
    assert salida["errors"]
