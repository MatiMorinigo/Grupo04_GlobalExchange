from rest_framework import serializers
from rest_framework.validators import UniqueValidator
from .models import Cliente


class ClienteSerializer(serializers.ModelSerializer):
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