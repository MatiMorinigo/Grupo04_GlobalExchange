from rest_framework import serializers

from .models import MetodoPago


class MetodoPagoSerializer(serializers.ModelSerializer):
    """Serializa los métodos de pago para los endpoints de la API.

    Los campos de trazabilidad son de solo lectura; el campo creado_por
    y modificado_por se rellenan desde la vista, no desde el cliente.
    """

    creado_por = serializers.StringRelatedField(read_only=True)
    modificado_por = serializers.StringRelatedField(read_only=True)

    class Meta:
        """Define los campos expuestos por la API."""

        model = MetodoPago
        fields = [
            "id_metodo_pago",
            "nombre",
            "descripcion",
            "habilitado",
            "creado_en",
            "actualizado_en",
            "creado_por",
            "modificado_por",
        ]
        read_only_fields = [
            "id_metodo_pago",
            "creado_en",
            "actualizado_en",
            "creado_por",
            "modificado_por",
        ]
