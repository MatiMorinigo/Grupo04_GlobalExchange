from rest_framework import serializers

from .models import Moneda, TasaCambio


class MonedaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Moneda
        fields = ["codigo", "nombre", "simbolo", "activa"]


class TasaCambioSerializer(serializers.ModelSerializer):
    moneda_origen_nombre = serializers.CharField(source="moneda_origen.nombre", read_only=True)
    moneda_destino_nombre = serializers.CharField(source="moneda_destino.nombre", read_only=True)
    variacion_compra = serializers.SerializerMethodField()
    variacion_venta = serializers.SerializerMethodField()

    class Meta:
        model = TasaCambio
        fields = [
            "id_tasa",
            "moneda_origen",
            "moneda_origen_nombre",
            "moneda_destino",
            "moneda_destino_nombre",
            "precio_compra",
            "precio_venta",
            "vigente",
            "fecha_vigencia",
            "variacion_compra",
            "variacion_venta",
        ]

    def get_variacion_compra(self, obj):
        variacion = obj.variacion_compra()
        return None if variacion is None else str(variacion)

    def get_variacion_venta(self, obj):
        variacion = obj.variacion_venta()
        return None if variacion is None else str(variacion)
