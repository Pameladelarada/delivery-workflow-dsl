# Delivery Workflow DSL

Un lenguaje propio para describir flujos de reparto, con su compilador escrito desde cero en C++ y una web donde se escribe el código y se ve el análisis en vivo.

[![CI](https://github.com/Pameladelarada/delivery-workflow-dsl/actions/workflows/c-cpp.yml/badge.svg)](https://github.com/Pameladelarada/delivery-workflow-dsl/actions/workflows/c-cpp.yml)
![C++](https://img.shields.io/badge/C%2B%2B-17-00599C)
![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB)
![Licencia](https://img.shields.io/badge/licencia-MIT-green)

<!-- TODO: reemplazar por un GIF escribiendo DSL y viendo aparecer los tokens.
     Guardarlo en docs/demo.gif y descomentar la linea de abajo. -->
<!-- ![Demostración](docs/demo.gif) -->

---

## Qué es

En vez de programar cada flujo de reparto a mano, se describe en un lenguaje hecho para eso:

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

El compilador recorre las tres fases clásicas —**análisis léxico, sintáctico y semántico**— y devuelve un JSON con los tokens, el árbol sintáctico, el árbol semántico anotado, el registro del flujo y los errores encontrados.

La web muestra cada fase por separado, así que se ve exactamente qué hace el compilador en cada paso.

---

## El lenguaje

### Tokens

| Tipo | Qué reconoce | Ejemplo |
|---|---|---|
| `RESERVED` | Las seis palabras del lenguaje | `PEDIDO`, `VALIDAR`, `SI`, `ASIGNAR`, `INICIAR`, `FINALIZAR` |
| `IDENTIFIER` | Letra o `_`, seguido de letras, dígitos o `_` | `cliente`, `prioridad_alta` |
| `NUMBER` | Entero o decimal | `80`, `12.5` |
| `STRING` | Texto entre comillas dobles | `"Av. Lima 123"` |
| `LBRACE` / `RBRACE` | Delimitadores de bloque | `{` `}` |
| `COLON` | Separador de propiedad | `:` |
| `OPERATOR` | Comparación | `>` `<` `>=` `<=` `==` `!=` |

Cada token guarda su **línea y columna**, que es lo que permite señalar dónde está cada error.

### Gramática

```bnf
programa      ::= instruccion*

instruccion   ::= pedido | validacion | condicional | accion

pedido        ::= "PEDIDO" "{" propiedad* "}"
propiedad     ::= identificador ":" valor
valor         ::= cadena | numero | identificador

validacion    ::= "VALIDAR" campo
campo         ::= "stock" | "direccion" | "pago"
                | "cliente" | "producto" | "total"

condicional   ::= "SI" identificador operador valor "{" instruccion* "}"
operador      ::= ">" | "<" | ">=" | "<=" | "==" | "!="

accion        ::= ("ASIGNAR" | "INICIAR" | "FINALIZAR") identificador

identificador ::= (letra | "_") (letra | digito | "_")*
numero        ::= digito+ ("." digito+)?
cadena        ::= '"' caracter* '"'
```

### Reglas semánticas

El análisis sintáctico comprueba la forma; el semántico comprueba el sentido:

| Regla | Error si no se cumple |
|---|---|
| Todo programa define un bloque `PEDIDO` | `el programa debe definir un bloque PEDIDO` |
| `VALIDAR` solo acepta los seis campos del dominio | `VALIDAR <campo> no pertenece al dominio permitido` |
| El campo validado existe en el `PEDIDO` | `no se puede validar '<campo>' porque no existe en PEDIDO` |
| `stock` es un número mayor que cero | `stock debe ser un numero mayor que cero` |
| `direccion` y `pago` no están vacíos | `<campo> no puede estar vacio` |
| La variable de un `SI` existe en el `PEDIDO` | `la variable '<x>' no existe en PEDIDO` |
| El operador es válido para los tipos comparados | `operador '<op>' no valido para los tipos comparados` |

El bloque de un `SI` cuya condición es falsa se salta sin analizarse, igual que en un lenguaje real.

### Códigos de salida

| Código | Significado |
|---|---|
| `0` | El programa es válido |
| `1` | No se pudo leer el archivo, o hubo un error léxico |
| `2` | El programa tiene errores sintácticos o semánticos |

La salida es **siempre** JSON válido, incluso cuando falla. Es el contrato con la web, y hay pruebas que lo verifican con entradas corruptas.

---

## Arquitectura

```
    programa.dsl
         │
         ▼
  ┌─────────────┐
  │   Lexer     │  caracteres → tokens (con línea y columna)
  └──────┬──────┘
         ▼
  ┌─────────────┐
  │   Parser    │  tokens → árbol sintáctico
  │             │  descendente recursivo, con recuperación de errores
  └──────┬──────┘
         ▼
  ┌─────────────┐
  │  Semántico  │  árbol → árbol anotado + registro del flujo
  └──────┬──────┘
         ▼
    salida JSON  ──────►  web Flask  ──────►  navegador
```

El parser **no se detiene en el primer error**: registra lo que encontró, se sincroniza con la siguiente instrucción y sigue analizando, de modo que un programa con varios errores los reporta todos de una vez.

### Estructura del repositorio

```
compiler/main.cpp     El compilador completo: lexer, parser y análisis semántico
web/app.py            Servidor Flask y extracción de reglas desde documentos
web/static/app.js     Interfaz: tokens, árboles y registro del flujo
web/templates/        Plantilla de la página
examples/             Programas DSL de prueba, válido y con error
tests/                Pruebas del compilador y de la web
docs/                 Especificación del proyecto
tools/                Generadores de las guías en Word (material del curso)
Dockerfile            Imagen para Railway: compila el C++ e instala Flask
Makefile              Compilar, probar y levantar la web
```

---

## Cómo ejecutarlo

### Con make (Linux, macOS, WSL, Git Bash)

```bash
make          # compila el compilador del DSL
make venv     # crea el entorno virtual e instala dependencias
make web      # levanta la web en http://127.0.0.1:5000
make test     # ejecuta las 54 pruebas
```

### Con PowerShell en Windows

```powershell
powershell -ExecutionPolicy Bypass -File .\run_web.ps1
```

El script crea `.venv`, instala las dependencias, compila el programa C++ y abre la web.

### Con Docker

```bash
docker build -t delivery-workflow-dsl .
docker run -p 5000:5000 -e PORT=5000 delivery-workflow-dsl
```

Es la misma imagen que usa Railway.

### Solo el compilador, por línea de comandos

```bash
./bin/delivery_compiler examples/pedido_basico.dsl
```

---

## API

| Método | Endpoint | Qué hace |
|---|---|---|
| `GET` | `/` | La página con el editor |
| `POST` | `/compile` | Compila el DSL del cuerpo y devuelve tokens, árboles, registro y errores |
| `POST` | `/upload-rules` | Extrae reglas de un PDF, Word, Excel, CSV, JSON o TXT y genera una plantilla DSL |

```bash
curl -X POST http://127.0.0.1:5000/compile \
     -H 'Content-Type: application/json' \
     -d '{"source": "PEDIDO { cliente: \"Ana\" stock: 3 }\nVALIDAR stock"}'
```

---

## Pruebas

```bash
make test
```

54 pruebas con pytest, sin dependencias más allá del propio pytest:

- **37 del compilador**, que ejercitan el binario igual que lo hace la web
- **17 de la web**, con el cliente de pruebas de Flask

Cubren las tres fases del análisis, el contrato de la salida JSON y una prueba de regresión por cada bug corregido. El CI las ejecuta en Ubuntu y macOS, contra Python 3.10, 3.11 y 3.12, y además construye la imagen de Docker y comprueba que el contenedor arranca y responde.

---

## Decisiones técnicas

- **Compilador escrito desde cero**, sin generadores como Lex o Yacc. El objetivo del proyecto es entender cada fase, no automatizarla.
- **Recuperación de errores en el parser.** Al encontrar un error registra el problema, consume tokens hasta la siguiente instrucción y continúa. Garantizar que esa sincronización siempre avanza es lo que evita que el análisis se estanque.
- **La salida es JSON, siempre.** Incluso ante un fallo del lector de archivos, para que la web nunca reciba algo que no pueda interpretar.
- **Validación en el servidor y escapado en el cliente.** Los lexemas se muestran con `textContent`, nunca interpolados en HTML, porque provienen del texto que escribe el usuario.
- **Límites explícitos en la subida de archivos.** 5 MB por archivo y 50 MB al descomprimir un `.docx` o un `.xlsx`, que son archivos ZIP y pueden expandirse mucho más de lo que ocupan.

---

## Limitaciones conocidas

- El lenguaje no tiene bucles ni funciones: describe un flujo lineal con condicionales, que es lo que el dominio necesita.
- El `SI` compara una variable del `PEDIDO` contra un literal; no admite expresiones compuestas ni operadores lógicos.
- La extracción de reglas desde PDF es de mejor esfuerzo: un PDF escaneado sin capa de texto no se puede leer.
- `tools/` contiene los generadores de las guías en Word del curso; no forman parte del producto.

---

## Licencia

MIT — ver [LICENSE](LICENSE).
