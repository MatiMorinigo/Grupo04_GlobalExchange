from rest_framework import serializers

from .models import MetodoPago
from .validators import validar_numero_tarjeta, validar_vencimiento_no_vencido


class MetodoPagoSerializer(serializers.ModelSerializer):
    """Serializa los métodos de pago del cliente activo, sin exponer el número completo de tarjeta."""
    numero_tarjeta = serializers.CharField(write_only=True, required=False, max_length=19)

    class Meta:
        """Selecciona el modelo MetodoPago y los campos expuestos por la API."""
        model = MetodoPago
        fields = [
            "id_metodo_pago",
            "tipo",
            "titular",
            "ultimos_cuatro_digitos",
            "fecha_vencimiento",
            "numero_tarjeta",
            "activo",
            "creado_en",
            "actualizado_en",
        ]
        read_only_fields = ["id_metodo_pago", "ultimos_cuatro_digitos", "activo", "creado_en", "actualizado_en"]

    def validate_numero_tarjeta(self, value):
        """Valida el número de tarjeta ingresado, si se completó.

        Args:
            value (str): Número de tarjeta recibido.

        Returns:
            str: Número de tarjeta validado y sin espacios.
        """
        return validar_numero_tarjeta(value)

    def validate_fecha_vencimiento(self, value):
        """Valida que la fecha de vencimiento no corresponda a una tarjeta ya vencida.

        Args:
            value (str): Fecha de vencimiento recibida, en formato MM/AA.

        Returns:
            str: Fecha de vencimiento validada.
        """
        validar_vencimiento_no_vencido(value)
        return value

    def validate(self, attrs):
        """Exige el número de tarjeta al crear un método de pago nuevo.

        Args:
            attrs (dict): Datos ya validados campo por campo.

        Returns:
            dict: Los mismos datos recibidos, sin modificaciones.

        Raises:
            rest_framework.serializers.ValidationError: Si se está creando
                un método de pago y no se incluyó el número de tarjeta.
        """
        if self.instance is None and not attrs.get("numero_tarjeta"):
            raise serializers.ValidationError({"numero_tarjeta": "El número de tarjeta es obligatorio."})
        return attrs

    def create(self, validated_data):
        """Crea el método de pago derivando los últimos 4 dígitos del número ingresado.

        Args:
            validated_data (dict): Datos validados, incluyendo numero_tarjeta.

        Returns:
            MetodoPago: Método de pago creado.
        """
        numero = validated_data.pop("numero_tarjeta")
        validated_data["ultimos_cuatro_digitos"] = numero[-4:]
        return super().create(validated_data)

    def update(self, instance, validated_data):
        """Actualiza el método de pago, sin permitir modificar el tipo de tarjeta.

        Args:
            instance (MetodoPago): Método de pago a actualizar.
            validated_data (dict): Datos validados a aplicar.

        Returns:
            MetodoPago: Método de pago actualizado.
        """
        numero = validated_data.pop("numero_tarjeta", None)
        if numero:
            validated_data["ultimos_cuatro_digitos"] = numero[-4:]
        validated_data.pop("tipo", None)
        return super().update(instance, validated_data)
