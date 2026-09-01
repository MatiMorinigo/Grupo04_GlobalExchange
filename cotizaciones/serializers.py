from decimal import Decimal

from rest_framework import serializers

from .models import Moneda, TasaCambio
from .services import SimulacionConversionError, simular_conversion


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


class SimulacionConversionSerializer(serializers.Serializer):
    moneda_origen = serializers.CharField(max_length=3)
    moneda_destino = serializers.CharField(max_length=3)
    monto = serializers.DecimalField(max_digits=18, decimal_places=2, min_value=Decimal("0.01"))

    def validate_moneda_origen(self, value):
        codigo = value.upper()
        if not Moneda.objects.filter(codigo=codigo, activa=True).exists():
            raise serializers.ValidationError("La moneda de origen no está disponible.")
        return codigo

    def validate_moneda_destino(self, value):
        codigo = value.upper()
        if not Moneda.objects.filter(codigo=codigo, activa=True).exists():
            raise serializers.ValidationError("La moneda de destino no está disponible.")
        return codigo

    def create(self, validated_data):
        try:
            return simular_conversion(**validated_data)
        except SimulacionConversionError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
