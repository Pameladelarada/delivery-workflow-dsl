# DSL Delivery Workflow Compiler

Proyecto academico-practico que combina compiladores, lenguajes DSL y automatizacion de workflows logisticos para delivery.

## Que incluye

- `compiler/`: compilador en C++ para el DSL.
- `web/`: aplicacion Flask para escribir y ejecutar workflows desde el navegador.
- `examples/`: programas DSL de prueba.
- `docs/`: especificacion tecnica del proyecto.
- `Guia_instalacion_flask_y_uso_web.docx`: guia Word para instalar Flask y ver la pagina web.

## Ejecucion rapida

1. Compila el compilador C++:

```powershell
.\build.ps1
```

2. Crea un entorno virtual e instala Flask:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

3. Ejecuta la web:

```powershell
.\.venv\Scripts\python.exe web\app.py
```

4. Abre:

```text
http://127.0.0.1:5000
```

## Ejemplo DSL

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
VALIDAR pago

SI total > 50 {
    ASIGNAR prioridad_alta
}

ASIGNAR repartidor
INICIAR entrega
FINALIZAR pedido
```

El compilador valida el codigo, genera logs del workflow y produce una salida JSON.
