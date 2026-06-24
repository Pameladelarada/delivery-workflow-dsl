# Especificacion del proyecto

## Titulo

Diseno e implementacion de un DSL con compilador en C++ para automatizar workflows logisticos de delivery mediante una interfaz web en Flask.

## Problema

Muchas empresas pequenas de delivery administran pedidos con Excel, WhatsApp o procesos manuales. Esto genera pedidos duplicados, estados inconsistentes, errores de validacion y poca trazabilidad.

## Objetivo general

Construir un lenguaje especifico de dominio para describir procesos logisticos de delivery y un compilador capaz de analizar, validar y ejecutar esos workflows desde una pagina web.

## Objetivos especificos

- Disenar la sintaxis de un DSL orientado a pedidos, pagos, validaciones, asignaciones y entregas.
- Implementar un analizador lexico que convierta el codigo fuente en tokens.
- Implementar un analizador sintactico que valide la estructura del programa.
- Implementar un analizador semantico que detecte errores logicos del workflow.
- Generar una salida JSON con resultados, logs, tokens y errores.
- Integrar el compilador C++ con Flask para ejecutarlo desde un navegador.

## Alcance del DSL

Instrucciones soportadas:

- `PEDIDO { ... }`: define los datos base del pedido.
- `VALIDAR campo`: valida campos obligatorios como `stock`, `direccion` y `pago`.
- `SI condicion { ... }`: ejecuta acciones solo si una condicion se cumple.
- `ASIGNAR recurso`: registra asignacion de prioridad, repartidor u otro recurso.
- `INICIAR proceso`: inicia una fase del workflow.
- `FINALIZAR proceso`: finaliza una fase del workflow.

## Ejemplo

```txt
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

SI total > 50 {
    ASIGNAR prioridad_alta
}

ASIGNAR repartidor
INICIAR entrega
FINALIZAR pedido
```

## Arquitectura

```text
Navegador
   |
   v
Aplicacion Flask
   |
   v
Archivo temporal DSL
   |
   v
Compilador C++
   |
   v
JSON de salida
   |
   v
Resultado web
```

## Componentes del compilador

### Analizador lexico

Lee caracteres y produce tokens: palabras reservadas, identificadores, numeros, cadenas, operadores, llaves y dos puntos.

### Analizador sintactico

Usa un parser descendente recursivo LL(1), comprueba que el programa cumpla la gramatica del DSL y construye un arbol sintactico abstracto (AST). El arbol se incluye en `syntax.tree` aunque una rama condicional no se ejecute, porque reconocer la estructura y ejecutar el workflow son fases independientes.

Gramatica libre de contexto:

```text
<programa>    -> <sentencia>*
<sentencia>   -> <pedido> | <validacion> | <condicional> | <accion>
<pedido>      -> PEDIDO { <propiedad>* }
<propiedad>   -> IDENTIFIER : <valor>
<valor>       -> STRING | NUMBER | IDENTIFIER
<validacion>  -> VALIDAR IDENTIFIER
<condicional> -> SI <condicion> { <sentencia>* }
<condicion>   -> IDENTIFIER OPERATOR <valor>
<accion>      -> (ASIGNAR | INICIAR | FINALIZAR) IDENTIFIER
```

### Analizador semantico

La evaluacion semantica recorre el AST y expone una tabla de simbolos y atributos por nodo:

- Atributos heredados (recorrido descendente): ambito visible y contexto de ejecucion.
- Atributos sintetizados (recorrido ascendente): tipo, valor y validez calculados desde los hijos.

Ademas valida reglas de negocio:

- No se puede validar un campo que no existe.
- No se puede usar una variable inexistente en una condicion.
- El stock debe ser mayor a cero para aprobar `VALIDAR stock`.
- La direccion no debe estar vacia.
- El pago debe tener un metodo registrado.

## Salida esperada

El compilador devuelve un JSON con:

- `success`: indica si el programa es valido.
- `tokens`: lista de tokens reconocidos.
- `order`: datos del pedido.
- `syntax`: estrategia del parser y AST visualizable.
- `semantic`: tabla de simbolos, atributos heredados/sintetizados y comprobaciones.
- `logs`: pasos ejecutados del workflow.
- `errors`: errores lexicos, sintacticos o semanticos.

## Tecnologias

- C++17 para el compilador.
- Flask para la aplicacion web.
- HTML, CSS y JavaScript para la interfaz.
- JSON como formato de comunicacion entre compilador y web.

## Limitaciones

Este proyecto es un prototipo academico. No se conecta a pasarelas de pago reales, mapas ni bases de datos. Su objetivo principal es demostrar el diseno del DSL, el proceso de compilacion y la automatizacion del workflow.
