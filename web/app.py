import json
import re
import subprocess
import tempfile
import zipfile
from html import unescape
from pathlib import Path
from xml.etree import ElementTree

from flask import Flask, jsonify, render_template, request

ROOT = Path(__file__).resolve().parents[1]
COMPILER = ROOT / "bin" / "delivery_compiler.exe"
EXAMPLE = ROOT / "examples" / "pedido_basico.dsl"
ALLOWED_RULE_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".csv", ".txt"}

app = Flask(__name__)


def load_example() -> str:
    return EXAMPLE.read_text(encoding="utf-8")


def xml_text(path: Path, xml_names: list[str]) -> str:
    chunks = []
    with zipfile.ZipFile(path) as archive:
        for name in xml_names:
            if name not in archive.namelist():
                continue
            root = ElementTree.fromstring(archive.read(name))
            for node in root.iter():
                if node.text and node.text.strip():
                    chunks.append(node.text.strip())
    return "\n".join(chunks)


def extract_docx(path: Path) -> str:
    return xml_text(path, ["word/document.xml"])


def extract_xlsx(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        shared = []
        if "xl/sharedStrings.xml" in names:
            root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
            for node in root.iter():
                if node.tag.endswith("}t") and node.text:
                    shared.append(node.text)

        chunks = []
        sheets = [name for name in names if name.startswith("xl/worksheets/sheet") and name.endswith(".xml")]
        for sheet in sheets:
            root = ElementTree.fromstring(archive.read(sheet))
            for cell in root.iter():
                if not cell.tag.endswith("}c"):
                    continue
                cell_type = cell.attrib.get("t")
                value = None
                for child in cell:
                    if child.tag.endswith("}v") and child.text is not None:
                        value = child.text
                        break
                if value is None:
                    continue
                if cell_type == "s" and value.isdigit() and int(value) < len(shared):
                    chunks.append(shared[int(value)])
                else:
                    chunks.append(value)
        return "\n".join(chunks)


def extract_pdf_best_effort(path: Path) -> str:
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        pages = [page.extract_text() or "" for page in reader.pages]
        extracted = "\n".join(page.strip() for page in pages if page.strip())
        if extracted.strip():
            return extracted
    except Exception:
        pass

    data = path.read_bytes()
    text = data.decode("latin-1", errors="ignore")
    literal_strings = re.findall(r"\(([^()]{2,})\)", text)
    cleaned = [unescape(item.replace("\\n", " ").replace("\\r", " ")) for item in literal_strings]
    return "\n".join(cleaned)


def clean_extracted_text(text: str) -> str:
    normalized = []
    for char in text:
        code = ord(char)
        if char in "\n\r\t" or 32 <= code <= 126 or char in "áéíóúÁÉÍÓÚñÑüÜ":
            normalized.append(char)
        else:
            normalized.append(" ")

    lines = []
    for line in "".join(normalized).splitlines():
        compact = " ".join(line.split())
        if len(compact) < 2:
            continue
        printable = sum(1 for char in compact if char.isalnum() or char in " :;.,-_/>=<\"")
        words = re.findall(r"[A-Za-zÁÉÍÓÚáéíóúÑñÜü0-9]{2,}", compact)
        average_word_length = sum(len(word) for word in words) / max(len(words), 1)
        if printable / max(len(compact), 1) >= 0.65:
            if len(words) >= 2 and average_word_length >= 3:
                lines.append(compact)
    return "\n".join(lines)


def build_dsl_draft(rules_text: str) -> str:
    lower = rules_text.lower()
    validations = ["VALIDAR stock", "VALIDAR direccion", "VALIDAR pago"]
    if "cliente" in lower:
        validations.append("VALIDAR cliente")
    if "producto" in lower:
        validations.append("VALIDAR producto")

    unique_validations = []
    for validation in validations:
        if validation not in unique_validations:
            unique_validations.append(validation)

    return "\n".join(
        [
            "PEDIDO {",
            '    cliente: "Cliente desde reglas"',
            '    producto: "Producto desde reglas"',
            "    total: 80",
            "    pago: YAPE",
            '    direccion: "Direccion pendiente"',
            "    stock: 1",
            "}",
            "",
            *unique_validations,
            "",
            "SI total > 50 {",
            "    ASIGNAR prioridad_alta",
            "}",
            "",
            "ASIGNAR repartidor",
            "INICIAR entrega",
            "FINALIZAR pedido",
        ]
    )


def extract_business_rules(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".docx":
        return extract_docx(path)
    if suffix == ".xlsx":
        return extract_xlsx(path)
    if suffix == ".pdf":
        return extract_pdf_best_effort(path)
    if suffix in {".csv", ".txt"}:
        return path.read_text(encoding="utf-8", errors="ignore")
    raise ValueError("Formato no soportado. Usa PDF, Word, Excel, CSV o TXT.")


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


@app.post("/upload-rules")
def upload_rules():
    file = request.files.get("rules")
    if not file or not file.filename:
        return jsonify({"success": False, "errors": ["No se recibio ningun archivo."]}), 400

    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_RULE_EXTENSIONS:
        return jsonify({"success": False, "errors": ["Formato no soportado. Usa PDF, Word, Excel, CSV o TXT."]}), 400

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp:
        file.save(temp.name)
        temp_path = Path(temp.name)

    try:
        raw_text = extract_business_rules(temp_path).strip()
        text = clean_extracted_text(raw_text)
        if not text:
            text = "No se pudo extraer texto legible del archivo. Si es PDF escaneado, convierte el contenido a texto."
        dsl_draft = build_dsl_draft(text)
        return jsonify(
            {
                "success": True,
                "filename": file.filename,
                "text": text[:12000],
                "dsl_draft": dsl_draft,
                "message": "Archivo procesado. Se genero una plantilla DSL compilable a partir de las reglas.",
            }
        )
    except Exception as exc:
        return jsonify({"success": False, "errors": [str(exc)]}), 400
    finally:
        temp_path.unlink(missing_ok=True)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)
