import json
import os
import re
import subprocess
import tempfile
import unicodedata
import zipfile
from html import unescape
from pathlib import Path
from xml.etree import ElementTree

from flask import Flask, jsonify, render_template, request

ROOT = Path(__file__).resolve().parents[1]
COMPILER_NAME = "delivery_compiler.exe" if os.name == "nt" else "delivery_compiler"
COMPILER = ROOT / "bin" / COMPILER_NAME
ALLOWED_RULE_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".csv", ".txt"}

app = Flask(__name__)


@app.after_request
def disable_html_cache(response):
    if response.mimetype == "text/html":
        response.headers["Cache-Control"] = "no-store, max-age=0"
        response.headers["Pragma"] = "no-cache"
    return response


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
        if not compact:
            continue
        printable = sum(1 for char in compact if char.isalnum() or char in " :;.,-_/>=<\"")
        if printable / max(len(compact), 1) >= 0.65 and re.search(r"[A-Za-z0-9ÁÉÍÓÚáéíóúÑñÜü]", compact):
            lines.append(compact)
    return "\n".join(lines)


RULE_LABELS = {
    "PEDIDO": "pedido_id",
    "EMPRESA": "empresa",
    "RUC": "ruc",
    "FECHA": "fecha",
    "CLIENTE": "cliente",
    "DIRECCION": "direccion",
    "PRODUCTO": "producto",
    "SUBTOTAL": "subtotal",
    "COSTO ENVIO": "costo_envio",
    "IGV": "igv",
    "TOTAL": "total",
    "METODO PAGO": "pago",
    "PAGO": "pago",
    "ESTADO": "estado",
    "STOCK": "stock",
}


def normalize_rule_label(value: str) -> str:
    ascii_value = "".join(
        char for char in unicodedata.normalize("NFD", value) if unicodedata.category(char) != "Mn"
    )
    return re.sub(r"[^A-Z0-9]+", " ", ascii_value.upper()).strip()


def extract_rule_fields(rules_text: str) -> dict[str, str]:
    lines = [" ".join(line.split()) for line in rules_text.splitlines() if line.strip()]
    fields = {}
    for index, line in enumerate(lines):
        pair = re.match(r"^([^,:=]{2,40})\s*[:,=]\s*(.+)$", line)
        if pair:
            field = RULE_LABELS.get(normalize_rule_label(pair.group(1)))
            if field:
                fields[field] = pair.group(2).strip()
                continue

        field = RULE_LABELS.get(normalize_rule_label(line))
        if field and index + 1 < len(lines):
            next_line = lines[index + 1]
            if normalize_rule_label(next_line) not in RULE_LABELS:
                fields[field] = next_line
    return fields


def dsl_string(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().replace('"', "'")[:160]


def dsl_number(value: str, fallback: str) -> str:
    match = re.search(r"\d[\d.,]*", value)
    if not match:
        return fallback
    number = match.group(0)
    if "," in number and "." in number:
        number = number.replace(",", "")
    else:
        number = number.replace(",", ".")
    try:
        parsed = float(number)
    except ValueError:
        return fallback
    return str(int(parsed)) if parsed.is_integer() else f"{parsed:.2f}".rstrip("0").rstrip(".")


def dsl_identifier(value: str, fallback: str) -> str:
    identifier = normalize_rule_label(value).replace(" ", "_")
    return identifier[:60] or fallback


def build_dsl_draft(rules_text: str) -> str:
    extracted = extract_rule_fields(rules_text)
    fields = {
        "cliente": extracted.get("cliente", "Cliente no identificado"),
        "producto": extracted.get("producto", "Producto no identificado"),
        "total": dsl_number(extracted.get("total", ""), "0"),
        "pago": dsl_identifier(extracted.get("pago", ""), "NO_IDENTIFICADO"),
        "direccion": extracted.get("direccion", "Direccion no identificada"),
    }

    quantities = re.findall(r"\bx\s*(\d+(?:[.,]\d+)?)", fields["producto"], flags=re.IGNORECASE)
    inferred_stock = sum(float(quantity.replace(",", ".")) for quantity in quantities)
    stock_fallback = str(int(inferred_stock)) if inferred_stock and inferred_stock.is_integer() else "1"
    fields["stock"] = dsl_number(extracted.get("stock", ""), stock_fallback)

    property_specs = [
        ("pedido_id", "texto"),
        ("empresa", "texto"),
        ("ruc", "texto"),
        ("fecha", "texto"),
        ("cliente", "texto"),
        ("direccion", "texto"),
        ("producto", "texto"),
        ("subtotal", "numero"),
        ("costo_envio", "numero"),
        ("igv", "numero"),
        ("total", "numero"),
        ("pago", "identificador"),
        ("estado", "identificador"),
        ("stock", "numero"),
    ]
    values = {**extracted, **fields}
    properties = []
    for name, value_type in property_specs:
        if name not in values:
            continue
        value = values[name]
        if value_type == "texto":
            rendered = f'"{dsl_string(value)}"'
        elif value_type == "numero":
            rendered = dsl_number(value, "0")
        else:
            rendered = dsl_identifier(value, "NO_IDENTIFICADO")
        properties.append(f"    {name}: {rendered}")

    validations = ["VALIDAR stock", "VALIDAR direccion", "VALIDAR pago"]
    if "cliente" in extracted:
        validations.append("VALIDAR cliente")
    if "producto" in extracted:
        validations.append("VALIDAR producto")

    unique_validations = []
    for validation in validations:
        if validation not in unique_validations:
            unique_validations.append(validation)

    return "\n".join(
        [
            "PEDIDO {",
            *properties,
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
    return render_template("index.html")


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
                    f"No se encontro bin/{COMPILER_NAME}. Compila primero el programa C++."
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
