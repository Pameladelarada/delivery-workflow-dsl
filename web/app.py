import csv
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
EXAMPLE = ROOT / "examples" / "pedido_basico.dsl"
ALLOWED_RULE_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".csv", ".json", ".txt"}

app = Flask(__name__)

FIELD_ALIASES = {
    "cliente": [
        "cliente",
        "nombre",
        "nombre cliente",
        "cliente nombre",
        "razon social",
        "senor",
        "comprador",
        "destinatario",
    ],
    "producto": [
        "producto",
        "descripcion",
        "descripcion producto",
        "detalle",
        "item",
        "articulo",
        "servicio",
        "pedido",
        "plato",
    ],
    "total": [
        "total",
        "total pagar",
        "total a pagar",
        "importe total",
        "monto total",
        "monto",
        "precio total",
        "valor total",
        "subtotal",
    ],
    "pago": [
        "pago",
        "metodo pago",
        "metodo de pago",
        "forma pago",
        "forma de pago",
        "medio pago",
        "medio de pago",
    ],
    "direccion": [
        "direccion",
        "direccion entrega",
        "direccion de entrega",
        "domicilio",
        "ubicacion",
        "entrega",
        "lugar entrega",
    ],
    "stock": [
        "stock",
        "cantidad",
        "cant",
        "qty",
        "unidades",
    ],
}


def strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value))
    return "".join(char for char in normalized if not unicodedata.combining(char))


def normalize_label(value: str) -> str:
    value = strip_accents(value).lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


FIELD_ALIASES_REVERSE = {
    alias: field
    for field, aliases in FIELD_ALIASES.items()
    for alias in aliases
}


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

        sheets_text = []
        sheets = [name for name in names if name.startswith("xl/worksheets/sheet") and name.endswith(".xml")]
        for sheet in sheets:
            root = ElementTree.fromstring(archive.read(sheet))
            rows = {}
            for cell in root.iter():
                if not cell.tag.endswith("}c"):
                    continue
                coordinate = cell.attrib.get("r", "")
                row_match = re.search(r"\d+", coordinate)
                row_number = int(row_match.group(0)) if row_match else 0
                cell_type = cell.attrib.get("t")
                value = None
                for child in cell:
                    if child.tag.endswith("}v") and child.text is not None:
                        value = child.text
                        break
                    if child.tag.endswith("}is"):
                        inline_parts = [node.text for node in child.iter() if node.tag.endswith("}t") and node.text]
                        if inline_parts:
                            value = "".join(inline_parts)
                            break
                if value is None:
                    continue
                if cell_type == "s" and value.isdigit() and int(value) < len(shared):
                    value = shared[int(value)]
                rows.setdefault(row_number, []).append(str(value))

            ordered_rows = [rows[key] for key in sorted(rows) if rows[key]]
            if not ordered_rows:
                continue
            headers = ordered_rows[0]
            normalized_headers = [normalize_label(value) for value in headers]
            has_headers = any(header in FIELD_ALIASES_REVERSE for header in normalized_headers)
            if has_headers:
                for index, row in enumerate(ordered_rows[1:], start=1):
                    pairs = []
                    for column, value in enumerate(row):
                        if column < len(headers) and str(value).strip():
                            pairs.append(f"{headers[column]}: {value}")
                    if pairs:
                        sheets_text.append(f"fila {index}: " + " | ".join(pairs))
            else:
                sheets_text.extend(" | ".join(row) for row in ordered_rows)
        return "\n".join(sheets_text)


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

    lines = []
    for index, row in enumerate(rows, start=1):
        pairs = [f"{key}: {value}" for key, value in row.items() if key and str(value).strip()]
        if pairs:
            lines.append(f"fila {index}: " + " | ".join(pairs))
    return "\n".join(lines)


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


def sanitize_string(value: str, fallback: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(value).replace('"', "'")).strip(" :;,-")
    return cleaned[:90] if cleaned else fallback


def sanitize_identifier(value: str, fallback: str) -> str:
    cleaned = strip_accents(value).upper()
    cleaned = re.sub(r"[^A-Z0-9_]+", "_", cleaned).strip("_")
    return cleaned[:40] if cleaned else fallback


def parse_decimal(value: str) -> str | None:
    match = re.search(r"[-+]?\d[\d.,]*", str(value))
    if not match:
        return None
    number = match.group(0)
    if "," in number and "." in number:
        number = number.replace(",", "")
    else:
        number = number.replace(",", ".")
    try:
        parsed = float(number)
    except ValueError:
        return None
    if parsed.is_integer():
        return str(int(parsed))
    return f"{parsed:.2f}".rstrip("0").rstrip(".")


def split_pairs(line: str) -> list[tuple[str, str]]:
    pairs = []
    for chunk in re.split(r"\s+\|\s+|;\s*", line):
        match = re.match(r"^\s*(?:fila\s+\d+\s*:\s*)?([^:=]{2,45})\s*[:=]\s*(.+?)\s*$", chunk, re.IGNORECASE)
        if match:
            pairs.append((match.group(1), match.group(2)))
    return pairs


def resolve_field(label: str) -> str | None:
    normalized = normalize_label(label)
    if normalized in FIELD_ALIASES_REVERSE:
        return FIELD_ALIASES_REVERSE[normalized]
    for alias, field in FIELD_ALIASES_REVERSE.items():
        if alias in normalized or normalized in alias:
            return field
    return None


def collect_structured_fields(rules_text: str) -> dict[str, list[str]]:
    found = {field: [] for field in FIELD_ALIASES}
    for line in rules_text.splitlines():
        for key, value in split_pairs(line):
            field = resolve_field(key)
            if field and value.strip():
                found[field].append(value.strip())
    return found


def find_labeled_value(text: str, field: str) -> str | None:
    aliases = FIELD_ALIASES[field]
    if field == "total":
        aliases = ["total"] + [alias for alias in aliases if alias != "total" and alias != "subtotal"] + ["subtotal"]
    else:
        aliases = sorted(aliases, key=len, reverse=True)
    for alias in aliases:
        pattern = rf"(?im)\b{re.escape(alias)}\b\s*(?:[:=]|-)?\s*([^\n|;]+)"
        match = re.search(pattern, text)
        if match:
            value = match.group(1).strip()
            if value and normalize_label(value) != alias:
                return value
    return None


def build_dsl_draft(rules_text: str) -> str:
    normalized_text = "\n".join(strip_accents(line) for line in rules_text.splitlines())
    lower = normalized_text.lower()
    structured = collect_structured_fields(rules_text)
    fields = {
        "cliente": "Cliente no identificado",
        "producto": "Producto no identificado",
        "total": "0",
        "pago": "NO_IDENTIFICADO",
        "direccion": "Direccion no identificada",
        "stock": "1",
    }

    for field in ("cliente", "direccion"):
        value = next((item for item in structured[field] if item.strip()), None)
        if not value:
            value = find_labeled_value(normalized_text, field)
        if value:
            fields[field] = sanitize_string(value, fields[field])

    product_values = []
    for value in structured["producto"]:
        product = sanitize_string(value, "")
        if product and product not in product_values:
            product_values.append(product)
    if product_values:
        fields["producto"] = ", ".join(product_values[:4])
    else:
        product = find_labeled_value(normalized_text, "producto")
        if product:
            fields["producto"] = sanitize_string(product, fields["producto"])

    payment = next((item for item in structured["pago"] if item.strip()), None)
    if not payment:
        payment = find_labeled_value(normalized_text, "pago")
    if payment:
        fields["pago"] = sanitize_identifier(payment, fields["pago"])

    stock = next((parse_decimal(item) for item in structured["stock"] if parse_decimal(item)), None)
    if not stock:
        stock = parse_decimal(find_labeled_value(normalized_text, "stock") or "")
    if stock:
        fields["stock"] = stock

    total_candidates = []
    for value in structured["total"]:
        parsed = parse_decimal(value)
        if parsed is not None:
            total_candidates.append(float(parsed))
    labeled_total = parse_decimal(find_labeled_value(normalized_text, "total") or "")
    if labeled_total is not None:
        total_candidates.append(float(labeled_total))
    if not total_candidates:
        amounts = re.findall(r"(?:S/|S\.|PEN|\$)?\s*(\d+(?:[.,]\d{1,2})?)", normalized_text, flags=re.IGNORECASE)
        for amount in amounts:
            parsed = parse_decimal(amount)
            if parsed is not None:
                total_candidates.append(float(parsed))
    if total_candidates:
        total = max(total_candidates)
        fields["total"] = str(int(total)) if total.is_integer() else f"{total:.2f}".rstrip("0").rstrip(".")

    validations = ["VALIDAR stock", "VALIDAR direccion", "VALIDAR pago"]
    if "cliente" in lower or fields["cliente"] != "Cliente no identificado":
        validations.append("VALIDAR cliente")
    if "producto" in lower or fields["producto"] != "Producto no identificado":
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


def clean_extracted_text(text: str) -> str:
    normalized = []
    for char in text:
        code = ord(char)
        if char in "\n\r\t" or 32 <= code <= 126 or code >= 160:
            normalized.append(char)
        else:
            normalized.append(" ")

    lines = []
    for line in "".join(normalized).splitlines():
        compact = " ".join(line.split())
        if len(compact) < 2:
            continue
        printable = sum(1 for char in compact if char.isalnum() or char in " :;.,-_/>=<\"$|")
        ascii_text = strip_accents(compact)
        words = re.findall(r"[A-Za-z0-9]{2,}", ascii_text)
        average_word_length = sum(len(word) for word in words) / max(len(words), 1)
        looks_like_field = ":" in compact and bool(re.search(r"[A-Za-z_]{2,}\s*:", ascii_text))
        normalized_label = normalize_label(compact)
        looks_like_known_label = normalized_label in FIELD_ALIASES_REVERSE
        looks_like_amount = bool(re.fullmatch(r"(?:S/|S\.|PEN|\$)?\s*\d+(?:[.,]\d+)?", compact, flags=re.IGNORECASE))
        if printable / max(len(compact), 1) >= 0.65:
            if looks_like_known_label or looks_like_amount or looks_like_field or (len(words) >= 2 and average_word_length >= 3):
                lines.append(compact)
    return "\n".join(lines)


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
        dsl_draft = build_dsl_draft(raw_text)
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
