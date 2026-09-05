from django.db import models

class TipoCliente(models.TextChoices):
    """Define los tipos de persona admitidos para un cliente.
    """
    FISICA = "FISICA", "Persona física"
    JURIDICA = "JURIDICA", "Persona jurídica"

class CategoriaCliente(models.TextChoices):
    """Define las categorías comerciales disponibles para los clientes.
    """
    MINORISTA = "MINORISTA", "Minorista"
    CORPORATIVO = "CORPORATIVO", "Corporativo"
    VIP = "VIP", "VIP"

# Create your models here.
class Cliente(models.Model):
    """Almacena los datos de identificación y clasificación de un cliente.
    """
    id_cliente = models.BigAutoField(primary_key=True)
    ruc = models.CharField(max_length=20, unique=True)
    nombre = models.CharField(max_length=150)
    categoria = models.CharField(
    max_length=11,
    choices=CategoriaCliente.choices
    )
    tipo = models.CharField(
        max_length=8,
        choices=TipoCliente.choices
    )
    activo = models.BooleanField(default=True)
