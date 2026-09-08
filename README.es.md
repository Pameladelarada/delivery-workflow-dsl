[English](README.md) · [Español](README.es.md)

# Delivery Workflow DSL

Un lenguaje de dominio específico para flujos de reparto de última milla, con su compilador escrito desde cero en C++ y una web que muestra cada fase del análisis.

[![CI](https://github.com/Pameladelarada/delivery-workflow-dsl/actions/workflows/c-cpp.yml/badge.svg)](https://github.com/Pameladelarada/delivery-workflow-dsl/actions/workflows/c-cpp.yml)
![C++](https://img.shields.io/badge/C%2B%2B-17-00599C)
![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB)
![Licencia](https://img.shields.io/badge/licencia-MIT-green)

<!-- TODO: grabar un GIF escribiendo DSL y viendo aparecer los tokens.
     Guardarlo en docs/demo.gif y descomentar la línea de abajo. -->
<!-- ![Demostración](docs/demo.gif) -->

---

## El problema

Una operación de reparto es una secuencia de decisiones que apenas cambia entre empresas: comprobar el stock, comprobar la dirección, comprobar el método de pago, escalar el pedido si supera un umbral, asignar repartidor, iniciar y cerrar la entrega.

Programar ese flujo a mano en un lenguaje de propósito general entierra las reglas de negocio dentro del control de flujo. Alguien de operaciones no puede leerlo, y cambiar un umbral obliga a tocar código en producción.

Así que diseñé un lenguaje pequeño donde el flujo **es** la regla:

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

> **¿Por qué las palabras clave están en español?** El dominio es el reparto de última milla en Perú. `YAPE` es un método de pago local sin equivalente en inglés, y quien escribiría estas reglas trabaja en español. Un lenguaje de dominio específico debe hablar el idioma de su dominio: es justamente la razón de construir uno en vez de usar un lenguaje de propósito general.

## Qué construí

Un compilador que recorre las tres fases clásicas y una web que muestra cada una por separado, para que el análisis se vea en lugar de ser una caja negra.

```
    programa.dsl
         │
         ▼
  ┌─────────────┐
  │   Lexer     │  caracteres → tokens, cada uno con línea y columna
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
    salida JSON  ──────►  servidor Flask  ──────►  navegador
```

Sin generadores de parsers. Ni Lex, ni Yacc, ni ANTLR. El objetivo del ejercicio era entender cada fase, no automatizarla.

**El parser no se detiene en el primer error.** Registra lo que encontró, se sincroniza con la siguiente instrucción y sigue, de modo que un programa con cinco fallos los reporta los cinco de una vez.

---

## Notas de ingeniería

Estos son los tres problemas que de verdad me enseñaron algo.

### 1. Una recuperación de errores que no avanzaba

La rutina de recuperación avanzaba hasta encontrar una palabra reservada o una llave de cierre, y devolvía el control **sin consumir ese token**. Si el token conflictivo *era* una llave de cierre, no avanzaba nada: la instrucción volvía a lanzar sobre el mismo token, la recuperación volvía a devolver el control, y el bucle no terminaba nunca. La lista de errores crecía sin límite.

Bastaba un archivo con una sola `}`:

```
$ timeout 5 ./bin/delivery_compiler entrada.dsl
exit=124              # nunca termina
RSS a los 5 s:        350 MB y subiendo
```

Esto importaba más allá del binario. El servidor ejecuta el compilador con un timeout de 10 segundos, así que cada petición con ese contenido gastaba un núcleo completo durante diez segundos y llegaba a unos 700 MB. Dos o tres peticiones simultáneas tumbaban el contenedor.

El arreglo tiene dos mitades, y la segunda es la que defendería en una revisión:

- La recuperación ahora **consume** la llave de cierre antes de devolver el control. Las palabras reservadas se conservan, porque abren una instrucción que el parser todavía tiene que analizar.
- El bucle principal **compara la posición del token antes y después de cada instrucción** y avanza si no se consumió nada. Aunque algún camino futuro no consuma, el bucle no puede estancarse.

La primera mitad arregla el bug que encontré. La segunda hace imposible toda esa clase de bug.

### 2. Un despliegue roto dos veces, en silencio

El contenedor construía bien y moría al arrancar, por dos motivos independientes:

- El `Dockerfile` arrancaba la app con `gunicorn`, pero `gunicorn` no estaba en `requirements.txt`.
- `app.py` buscaba `bin/delivery_compiler.exe` mientras el `Dockerfile` compilaba `bin/delivery_compiler`. Dentro de un contenedor Linux, la app le pedía al usuario que ejecutara un script de PowerShell.

Ninguno de los dos se veía leyendo el código: solo aparecen cuando el contenedor arranca de verdad. Por eso el arreglo no son las dos líneas, sino el **trabajo de CI que construye la imagen, levanta el contenedor y le manda un programa DSL**. Una regresión de esta forma ya no puede pasar desapercibida.

### 3. La salida es un contrato

La web hace `json.loads()` de la salida del compilador. Eso convierte «emitir siempre JSON válido» en un contrato, no en un detalle — y la rutina de escapado no cubría los caracteres de control, así que un solo `0x01` dentro de una cadena producía una salida que la web no podía leer. El usuario veía *«el compilador no devolvió JSON válido»* en lugar del análisis real.

Ahora los caracteres de control se emiten como `\uXXXX`, y hay pruebas parametrizadas que alimentan al compilador con entradas corruptas y comprueban que las cinco claves del contrato están siempre presentes.

---

## El lenguaje

### Tokens

| Tipo | Qué reconoce | Ejemplo |
|---|---|---|
| `RESERVED` | Las seis palabras clave | `PEDIDO`, `VALIDAR`, `SI`, `ASIGNAR`, `INICIAR`, `FINALIZAR` |
| `IDENTIFIER` | Letra o `_`, luego letras, dígitos o `_` | `cliente`, `prioridad_alta` |
| `NUMBER` | Entero o decimal | `80`, `12.5` |
| `STRING` | Texto entre comillas dobles | `"Av. Lima 123"` |
| `LBRACE` / `RBRACE` | Delimitadores de bloque | `{` `}` |
| `COLON` | Separador de propiedad | `:` |
| `OPERATOR` | Comparación | `>` `<` `>=` `<=` `==` `!=` |

Cada token guarda su **línea y columna**, que es lo que permite dar mensajes de error precisos.

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

La salida es **siempre** JSON válido, incluso cuando falla.

---

## Cómo ejecutarlo

### Con make (Linux, macOS, WSL, Git Bash)

```bash
make          # compila el compilador
make venv     # crea el entorno virtual e instala dependencias
make web      # sirve en http://127.0.0.1:5000
make test     # ejecuta las 54 pruebas
```

### Con PowerShell en Windows

```powershell
powershell -ExecutionPolicy Bypass -File .\run_web.ps1
```

### Con Docker

```bash
docker build -t delivery-workflow-dsl .
docker run -p 5000:5000 -e PORT=5000 delivery-workflow-dsl
```

Es la misma imagen que despliega Railway.

### Solo el compilador

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

## Pruebas y CI

```bash
make test
```

54 pruebas con pytest, sin dependencias más allá del propio pytest:

- **37 del compilador**, que ejercitan el binario igual que lo hace el servidor
- **17 de la web**, con el cliente de pruebas de Flask, sin levantar un servidor

Cubren las tres fases del análisis, el contrato de la salida JSON y una prueba de regresión por cada bug corregido — incluida una parametrizada que alimenta ocho tipos de basura y comprueba que el compilador siempre termina.

El CI ejecuta tres trabajos en cada push y cada pull request: el compilador se construye y se prueba en **Ubuntu y macOS**; la suite corre contra **Python 3.10, 3.11 y 3.12**; y la **imagen de Docker se construye, se arranca y recibe un programa**, que es el trabajo que habría detectado el problema de despliegue descrito arriba.

---

## Decisiones de diseño

- **Compilador escrito a mano.** Sin generadores, así que cada fase es código que puedo explicar.
- **Recuperación de errores con garantía de progreso**, para que el análisis ni se detenga en el primer fallo ni se estanque.
- **JSON en todos los caminos**, incluso al fallar la lectura del archivo, porque la web depende de ello.
- **Validación en el servidor, escapado en el cliente.** Los lexemas se muestran con `textContent`, nunca interpolados en HTML, porque vienen del texto que escribe el usuario.
- **Límites explícitos en la subida.** 5 MB por archivo y 50 MB al descomprimir `.docx` y `.xlsx`, que son ZIP y pueden expandirse mucho más de lo que ocupan.

## Limitaciones conocidas

- Sin bucles ni funciones: el lenguaje describe un flujo lineal con condicionales, que es lo que el dominio necesita.
- Los condicionales comparan una variable del pedido contra un literal; no admiten expresiones compuestas ni operadores lógicos.
- La extracción de reglas desde PDF es de mejor esfuerzo: un PDF escaneado sin capa de texto no se puede leer.
- `tools/` contiene los generadores de las guías en Word del curso y no forma parte del producto.

## Qué haría después

- Compilar el workflow a un artefacto ejecutable, no solo validarlo.
- Permitir que los condicionales comparen dos campos del pedido, no solo un campo contra un literal.
- Sustituir los errores semánticos basados en cadenas por errores estructurados con línea y columna, para que el editor pueda subrayar el token exacto.

---

## Licencia

MIT — ver [LICENSE](LICENSE).
