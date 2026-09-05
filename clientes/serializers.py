from rest_framework import serializers
from rest_framework.validators import UniqueValidator
from .models import Cliente


class ClienteSerializer(serializers.ModelSerializer):
    """Valida y serializa los datos de clientes para la API.

    Comprueba la unicidad del RUC y personaliza los mensajes de validación.
    El identificador y el estado activo son campos de solo lectura.
    """
    ruc = serializers.CharField(
        max_length=20,
        validators=[
            UniqueValidator(
                queryset=Cliente.objects.all(),
                message="Ya existe un cliente registrado con este RUC."
            )
        ],
        error_messages={
            "required": "El RUC es obligatorio.",
            "blank": "El RUC no puede estar vacío.",
        }
    )
    class Meta:
        """Configura el modelo, los campos y los mensajes del serializador.
        """
        model = Cliente
        fields = [
            "id_cliente",
            "ruc",
            "nombre",
            "categoria",
            "tipo",
            "activo",
        ]
        read_only_fields = [
            "id_cliente",
            "activo",
        ]
        extra_kwargs = {
            "ruc": {
                "error_messages": {
                    "required": "El RUC es obligatorio.",
                    "blank": "El RUC no puede estar vacío.",
                }
            },
            "nombre": {
                "error_messages": {
                    "required": "El nombre es obligatorio.",
                    "blank": "El nombre no puede estar vacío.",
                }
            },
            "categoria": {
                "error_messages": {
                    "required": "La categoría es obligatoria.",
                    "invalid_choice": "La categoría ingresada no es válida.",
                }
            },
            "tipo": {
                "error_messages": {
                    "required": "El tipo de cliente es obligatorio.",
                    "invalid_choice": "El tipo de cliente ingresado no es válido.",
                }
            },
        }