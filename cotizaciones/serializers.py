from decimal import Decimal

from rest_framework import serializers

from .models import Moneda, TasaCambio
from .services import SimulacionConversionError, simular_conversion


class MonedaSerializer(serializers.ModelSerializer):
    """Serializa el código, nombre, símbolo y estado de una moneda."""
    class Meta:
        """Selecciona el modelo Moneda y los campos expuestos por la API."""
        model = Moneda
        fields = ["codigo", "nombre", "simbolo", "activa"]


class TasaCambioSerializer(serializers.ModelSerializer):
    """Serializa tasas con los nombres de las monedas y sus variaciones de precio."""
    moneda_origen_nombre = serializers.CharField(source="moneda_origen.nombre", read_only=True)
    moneda_destino_nombre = serializers.CharField(source="moneda_destino.nombre", read_only=True)
    variacion_compra = serializers.SerializerMethodField()
    variacion_venta = serializers.SerializerMethodField()

    class Meta:
        """Selecciona el modelo TasaCambio y los campos expuestos por la API."""
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
        """Obtiene la variación de compra como texto.

        Args:
            obj (TasaCambio): Tasa cuya variación se desea serializar.

        Returns:
            str or None: Diferencia de compra en formato decimal textual, o None
            si no existe una tasa anterior.
        """
        variacion = obj.variacion_compra()
        return None if variacion is None else str(variacion)

    def get_variacion_venta(self, obj):
        """Obtiene la variación de venta como texto.

        Args:
            obj (TasaCambio): Tasa cuya variación se desea serializar.

        Returns:
            str or None: Diferencia de venta en formato decimal textual, o None
            si no existe una tasa anterior.
        """
        variacion = obj.variacion_venta()
        return None if variacion is None else str(variacion)


class SimulacionConversionSerializer(serializers.Serializer):
    """Valida las monedas y el monto para obtener una simulación sin persistirla."""
    moneda_origen = serializers.CharField(max_length=3)
    moneda_destino = serializers.CharField(max_length=3)
    monto = serializers.DecimalField(max_digits=18, decimal_places=2, min_value=Decimal("0.01"))

    def validate_moneda_origen(self, value):
        """Normaliza y valida la disponibilidad de la moneda de origen.

        Args:
            value (str): Código recibido para la moneda de origen.

        Returns:
            str: Código de la moneda en mayúsculas.

        Raises:
            rest_framework.serializers.ValidationError: Si no existe una moneda
                activa con el código indicado.
        """
        codigo = value.upper()
        if not Moneda.objects.filter(codigo=codigo, activa=True).exists():
            raise serializers.ValidationError("La moneda de origen no está disponible.")
        return codigo

    def validate_moneda_destino(self, value):
        """Normaliza y valida la disponibilidad de la moneda de destino.

        Args:
            value (str): Código recibido para la moneda de destino.

        Returns:
            str: Código de la moneda en mayúsculas.

        Raises:
            rest_framework.serializers.ValidationError: Si no existe una moneda
                activa con el código indicado.
        """
        codigo = value.upper()
        if not Moneda.objects.filter(codigo=codigo, activa=True).exists():
            raise serializers.ValidationError("La moneda de destino no está disponible.")
        return codigo

    def create(self, validated_data):
        """Ejecuta la simulación con los datos validados sin crear registros.

        Args:
            validated_data (dict): Monedas de origen y destino y monto validados.

        Returns:
            dict: Resultado calculado por simular_conversion.

        Raises:
            rest_framework.serializers.ValidationError: Si el servicio rechaza
                la simulación mediante SimulacionConversionError.
        """
        try:
            return simular_conversion(**validated_data)
        except SimulacionConversionError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
