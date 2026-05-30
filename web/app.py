import json
import subprocess
import tempfile
from pathlib import Path

from flask import Flask, jsonify, render_template, request

ROOT = Path(__file__).resolve().parents[1]
COMPILER = ROOT / "bin" / "delivery_compiler.exe"
EXAMPLE = ROOT / "examples" / "pedido_basico.dsl"

app = Flask(__name__)


def load_example() -> str:
    return EXAMPLE.read_text(encoding="utf-8")


@app.route("/")
def index():
    return render_template("index.html", example=load_example())


@app.post("/compile")
def compile_dsl():
    payload = request.get_json(silent=True) or {}
    source = payload.get("source", "")
    if not isinstance(source, str):
        source = ""
    if not source.strip():
        return jsonify(
            {
                "success": False,
                "tokens": [],
                "order": {},
                "logs": [],
                "errors": ["El editor esta vacio. Escribe un workflow DSL."],
            }
        )

    if not COMPILER.exists():
        return jsonify(
            {
                "success": False,
                "tokens": [],
                "order": {},
                "logs": [],
                "errors": [
                    "No se encontro bin/delivery_compiler.exe. Ejecuta primero .\\build.ps1 para compilar el programa C++."
                ],
            }
        )

    with tempfile.NamedTemporaryFile("w", suffix=".dsl", delete=False, encoding="utf-8") as file:
        file.write(source)
        temp_path = Path(file.name)

    try:
        completed = subprocess.run(
            [str(COMPILER), str(temp_path)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=10,
        )
        try:
            return jsonify(json.loads(completed.stdout))
        except json.JSONDecodeError:
            return jsonify(
                {
                    "success": False,
                    "tokens": [],
                    "order": {},
                    "logs": [],
                    "errors": [
                        "El compilador no devolvio JSON valido.",
                        completed.stderr.strip(),
                        completed.stdout.strip(),
                    ],
                }
            )
    finally:
        temp_path.unlink(missing_ok=True)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)
