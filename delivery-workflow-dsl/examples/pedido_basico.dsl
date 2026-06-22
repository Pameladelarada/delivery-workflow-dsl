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
