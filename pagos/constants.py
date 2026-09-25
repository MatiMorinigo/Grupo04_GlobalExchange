"""Catálogos compartidos por los formularios que registran datos de pago o acreditación."""


PROVEEDORES_BILLETERA = [
    ("Tigo Money", "Tigo Money"),
    ("Personal Pay", "Personal Pay"),
    ("Giros Claro", "Giros Claro"),
]
"""list[tuple[str, str]]: Proveedores de billetera electrónica admitidos.

Se comparte entre los métodos de pago del cliente y sus destinos de
acreditación para que ambos ofrezcan exactamente el mismo catálogo.
"""
