"""Catálogo de entidades bancarias admitidas como destino de acreditación."""


BANCOS = [
    ("Banco Continental", "Banco Continental"),
    ("Itaú Paraguay", "Itaú Paraguay"),
    ("Banco Nacional de Fomento", "Banco Nacional de Fomento"),
    ("Ueno Bank", "Ueno Bank"),
    ("Banco Sudameris", "Banco Sudameris"),
    ("Banco Familiar", "Banco Familiar"),
    ("Banco Atlas", "Banco Atlas"),
    ("Banco Río", "Banco Río"),
    ("Visión Banco", "Visión Banco"),
    ("Banco Basa", "Banco Basa"),
]
"""list[tuple[str, str]]: Bancos donde un cliente puede registrar una cuenta.

Se declara como catálogo fijo, igual que los proveedores de billetera de la
aplicación de pagos, porque no existe un módulo de administración de
entidades bancarias.
"""
