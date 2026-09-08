[English](README.md) · [Español](README.es.md)

# Delivery Workflow DSL

A domain-specific language for last-mile delivery workflows. I wrote the compiler from scratch in C++; the web IDE that visualises each stage of the analysis was a team effort.

[![CI](https://github.com/Pameladelarada/delivery-workflow-dsl/actions/workflows/c-cpp.yml/badge.svg)](https://github.com/Pameladelarada/delivery-workflow-dsl/actions/workflows/c-cpp.yml)
![C++](https://img.shields.io/badge/C%2B%2B-17-00599C)
![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB)
![License](https://img.shields.io/badge/license-MIT-green)

---

## The problem

Delivery operations are a sequence of decisions that barely changes between companies: check stock, check the address, check the payment method, escalate the order if it is above a threshold, assign a courier, start and close the delivery.

Coding that flow by hand in a general-purpose language buries the business rules inside control flow. An operations person cannot read it, and changing a threshold means touching production code.

So I designed a small language where the flow *is* the rule:

```
PEDIDO {
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
```

> **Why are the keywords in Spanish?** The domain is Peruvian last-mile delivery. `YAPE` is a local mobile payment method with no English equivalent, and the people who would write these rules work in Spanish. A domain-specific language should speak the language of its domain — that is the whole point of building one instead of using a general-purpose language.

## What I built

A compiler that runs the three classic stages and a web front end that shows each one separately, so the analysis is visible rather than a black box.

```
    program.dsl
         │
         ▼
  ┌─────────────┐
  │   Lexer     │  characters → tokens, each carrying line and column
  └──────┬──────┘
         ▼
  ┌─────────────┐
  │   Parser    │  tokens → syntax tree
  │             │  recursive descent, with error recovery
  └──────┬──────┘
         ▼
  ┌─────────────┐
  │  Semantics  │  tree → annotated tree + workflow log
  └──────┬──────┘
         ▼
     JSON output  ──────►  Flask server  ──────►  browser
```

No parser generators. No Lex, no Yacc, no ANTLR. The point of the exercise was to understand each stage, not to automate it away.

**The parser does not stop at the first error.** It records what it found, resynchronises with the next statement and keeps going, so a program with five mistakes reports all five at once instead of one per run.

---

## Engineering notes

These are the three problems that actually taught me something.

### 1. Error recovery that could not make progress

The recovery routine advanced until it found a reserved word or a closing brace, then returned control — **without consuming that token**. If the offending token *was* a closing brace, nothing advanced: the parser statement threw again on the same token, recovery returned again, and the loop never ended. The error list grew without bound.

A file containing a single `}` was enough:

```
$ timeout 5 ./bin/delivery_compiler input.dsl
exit=124        # never terminates
RSS after 5s:   350 MB and climbing
```

This mattered beyond the binary. The web server runs the compiler with a 10-second subprocess timeout, so every request with that content burned a full core for ten seconds and reached roughly 700 MB. Two or three concurrent requests would take down the container.

The fix has two halves, and the second is the one I would defend in a review:

- Recovery now **consumes** the closing brace before returning. Reserved words are left in place, because they open a statement the parser still has to handle.
- The main loop **compares the token position before and after each statement** and advances if nothing was consumed. Even if some future code path fails to consume, the loop cannot stall.

The first half fixes the bug I found. The second makes the whole class of bug impossible.

### 2. A deployment that was broken twice over, silently

The container built fine and then died on startup, for two independent reasons:

- The `Dockerfile` started the app with `gunicorn`, but `gunicorn` was not in `requirements.txt`.
- `app.py` looked for `bin/delivery_compiler.exe` while the `Dockerfile` compiled `bin/delivery_compiler`. Inside a Linux container, the app told the user to run a PowerShell script.

Neither was visible from the code: both only appear when the container actually runs. So the fix is not just the two lines — it is the **CI job that builds the image, starts the container and posts a DSL program to it**. A regression of this shape cannot go unnoticed again.

### 3. The output is a contract

The web front end does `json.loads()` on the compiler's stdout. That makes "always emit valid JSON" a contract, not a nicety — and the escaping routine did not cover control characters, so a single `0x01` inside a string produced output the front end could not read. The user saw *"the compiler did not return valid JSON"* instead of the actual analysis.

Now control characters are emitted as `\uXXXX`, and there are parametrised tests that feed the compiler corrupt input and assert the five contract keys are always present.

---

## The language

### Tokens

| Type | Matches | Example |
|---|---|---|
| `RESERVED` | The six keywords | `PEDIDO`, `VALIDAR`, `SI`, `ASIGNAR`, `INICIAR`, `FINALIZAR` |
| `IDENTIFIER` | Letter or `_`, then letters, digits or `_` | `cliente`, `prioridad_alta` |
| `NUMBER` | Integer or decimal | `80`, `12.5` |
| `STRING` | Text between double quotes | `"Av. Lima 123"` |
| `LBRACE` / `RBRACE` | Block delimiters | `{` `}` |
| `COLON` | Property separator | `:` |
| `OPERATOR` | Comparison | `>` `<` `>=` `<=` `==` `!=` |

Every token carries its **line and column**, which is what makes precise error messages possible.

### Grammar

```bnf
program       ::= statement*

statement     ::= order | validation | conditional | action

order         ::= "PEDIDO" "{" property* "}"
property      ::= identifier ":" value
value         ::= string | number | identifier

validation    ::= "VALIDAR" field
field         ::= "stock" | "direccion" | "pago"
                | "cliente" | "producto" | "total"

conditional   ::= "SI" identifier operator value "{" statement* "}"
operator      ::= ">" | "<" | ">=" | "<=" | "==" | "!="

action        ::= ("ASIGNAR" | "INICIAR" | "FINALIZAR") identifier

identifier    ::= (letter | "_") (letter | digit | "_")*
number        ::= digit+ ("." digit+)?
string        ::= '"' character* '"'
```

### Semantic rules

Parsing checks the shape; semantic analysis checks the meaning:

| Rule | Error when violated |
|---|---|
| Every program defines a `PEDIDO` block | `el programa debe definir un bloque PEDIDO` |
| `VALIDAR` only accepts the six domain fields | `VALIDAR <field> no pertenece al dominio permitido` |
| The validated field exists in the order | `no se puede validar '<field>' porque no existe en PEDIDO` |
| `stock` is a number greater than zero | `stock debe ser un numero mayor que cero` |
| `direccion` and `pago` are not empty | `<field> no puede estar vacio` |
| A conditional's variable exists in the order | `la variable '<x>' no existe en PEDIDO` |
| The operator is valid for the compared types | `operador '<op>' no valido para los tipos comparados` |

The body of a conditional whose test is false is skipped without being analysed, as in a real language.

### Exit codes

| Code | Meaning |
|---|---|
| `0` | The program is valid |
| `1` | The file could not be read, or a lexical error occurred |
| `2` | The program has syntax or semantic errors |

The output is **always** valid JSON, including on failure.

---

## Running it

### With make (Linux, macOS, WSL, Git Bash)

```bash
make          # build the compiler
make venv     # create the virtualenv and install dependencies
make web      # serve at http://127.0.0.1:5000
make test     # run the 54 tests
```

### With PowerShell on Windows

```powershell
powershell -ExecutionPolicy Bypass -File .\run_web.ps1
```

### With Docker

```bash
docker build -t delivery-workflow-dsl .
docker run -p 5000:5000 -e PORT=5000 delivery-workflow-dsl
```

Same image Railway deploys.

### Compiler only

```bash
./bin/delivery_compiler examples/pedido_basico.dsl
```

---

## API

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/` | The editor page |
| `POST` | `/compile` | Compiles the DSL in the body; returns tokens, trees, log and errors |
| `POST` | `/upload-rules` | Extracts rules from a PDF, Word, Excel, CSV, JSON or TXT file and drafts a DSL template |

```bash
curl -X POST http://127.0.0.1:5000/compile \
     -H 'Content-Type: application/json' \
     -d '{"source": "PEDIDO { cliente: \"Ana\" stock: 3 }\nVALIDAR stock"}'
```

---

## Testing and CI

```bash
make test
```

54 tests with pytest and no dependencies beyond pytest itself:

- **37 compiler tests** that drive the binary exactly as the web server does
- **17 web tests** using Flask's test client, without starting a server

They cover the three analysis stages, the JSON output contract, and one regression test per bug fixed — including a parametrised case that feeds eight kinds of garbage and asserts the compiler always terminates.

CI runs three jobs on every push and pull request: the compiler builds and its tests run on **Ubuntu and macOS**; the suite runs against **Python 3.10, 3.11 and 3.12**; and the **Docker image is built, started and sent a program**, which is the job that would have caught the deployment problem described above.

---

## Design decisions

- **Hand-written compiler.** No parser generators, so every stage is code I can explain.
- **Error recovery with a progress guarantee**, so the analysis can neither stop at the first mistake nor stall.
- **JSON on every path**, including read failures, because the front end depends on it.
- **Server-side validation, client-side escaping.** Lexemes are rendered with `textContent`, never interpolated into HTML, because they come from text the user typed.
- **Explicit upload limits.** 5 MB per file and 50 MB uncompressed for `.docx` and `.xlsx`, which are ZIP archives and can expand far beyond their size on disk.

## Known limitations

- No loops or functions: the language describes a linear flow with conditionals, which is what the domain needs.
- Conditionals compare one order variable against a literal; no compound expressions or logical operators.
- PDF rule extraction is best-effort — a scanned PDF with no text layer cannot be read.
- `tools/` holds the generators for the course's Word guides and is not part of the product.

## What I would do next

- Compile the workflow to an executable artifact instead of only validating it.
- Let conditionals compare two order fields, not just a field against a literal.
- Replace the string-based semantic errors with structured ones carrying line and column, so the editor can underline the exact token.

---

## Credits

The compiler — lexer, parser and semantic analysis — is my work, as is the
hardening described in the engineering notes above.

Two classmates contributed to the web front end:

- [Josué Gutierrez](https://github.com/jussepe06) built the syntax and semantic
  tree panels.
- [Ernest Arellano](https://github.com/ErnestArel) built the token table grouped
  by type and lexeme.

---

## License

MIT — see [LICENSE](LICENSE).
