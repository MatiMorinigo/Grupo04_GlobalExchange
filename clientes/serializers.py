from rest_framework import serializers
from .models import Cliente


class ClienteSerializer(serializers.ModelSerializer):
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