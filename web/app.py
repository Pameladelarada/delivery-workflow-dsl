import csv
import json
import os
import re
import subprocess
import tempfile
import zipfile
from html import unescape
from pathlib import Path
from xml.etree import ElementTree

from flask import Flask, jsonify, render_template, request

ROOT = Path(__file__).resolve().parents[1]
COMPILER_NAME = "delivery_compiler.exe" if os.name == "nt" else "delivery_compiler"
COMPILER = ROOT / "bin" / COMPILER_NAME
EXAMPLE = ROOT / "examples" / "pedido_basico.dsl"
ALLOWED_RULE_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".csv", ".json", ".txt"}

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


def extract_json(path: Path) -> str:
    data = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    lines = []

    def walk(value, prefix=""):
        if isinstance(value, dict):
            for key, item in value.items():
                label = f"{prefix}.{key}" if prefix else str(key)
                walk(item, label)
        elif isinstance(value, list):
            for index, item in enumerate(value, start=1):
                walk(item, f"{prefix}[{index}]")
        else:
            lines.append(f"{prefix}: {value}")

    walk(data)
    return "\n".join(lines)


def extract_csv(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="ignore")
    sample = text.splitlines()
    if len(sample) < 2:
        return text

    reader = csv.DictReader(sample)
    rows = list(reader)
    if not rows:
        return text

    first = rows[0]
    return "\n".join(f"{key}: {value}" for key, value in first.items() if key and value)


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
        looks_like_field = ":" in compact and bool(re.search(r"[A-Za-z_]{2,}\s*:", compact))
        if printable / max(len(compact), 1) >= 0.65:
            if looks_like_field or (len(words) >= 2 and average_word_length >= 3):
                lines.append(compact)
    return "\n".join(lines)


def build_dsl_draft(rules_text: str) -> str:
    lower = rules_text.lower()
    fields = {
        "cliente": "Cliente desde reglas",
        "producto": "Producto desde reglas",
        "total": "80",
        "pago": "YAPE",
        "direccion": "Direccion pendiente",
        "stock": "1",
    }

    patterns = {
        "cliente": r"cliente\s*[:=,]\s*([A-Za-zÁÉÍÓÚáéíóúÑñÜü0-9 ._-]+)",
        "producto": r"producto\s*[:=,]\s*([A-Za-zÁÉÍÓÚáéíóúÑñÜü0-9 ._-]+)",
        "total": r"total\s*[:=,]\s*(\d+(?:\.\d+)?)",
        "pago": r"pago\s*[:=,]\s*([A-Za-zÁÉÍÓÚáéíóúÑñÜü0-9_-]+)",
        "direccion": r"direccion\s*[:=,]\s*([A-Za-zÁÉÍÓÚáéíóúÑñÜü0-9 ._-]+)",
        "stock": r"stock\s*[:=,]\s*(\d+(?:\.\d+)?)",
    }

    for field, pattern in patterns.items():
        match = re.search(pattern, rules_text, flags=re.IGNORECASE)
        if match:
            fields[field] = match.group(1).strip()[:80]

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
            f'    cliente: "{fields["cliente"]}"',
            f'    producto: "{fields["producto"]}"',
            f"    total: {fields['total']}",
            f"    pago: {fields['pago']}",
            f'    direccion: "{fields["direccion"]}"',
            f"    stock: {fields['stock']}",
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
    if suffix == ".json":
        return extract_json(path)
    if suffix == ".csv":
        return extract_csv(path)
    if suffix == ".txt":
        return path.read_text(encoding="utf-8", errors="ignore")
    raise ValueError("Formato no soportado. Usa PDF, Word, Excel, CSV, JSON o TXT.")


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
                    f"No se encontro {COMPILER.relative_to(ROOT)}. Compila primero el programa C++."
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
        return jsonify({"success": False, "errors": ["Formato no soportado. Usa PDF, Word, Excel, CSV, JSON o TXT."]}), 400

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
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
