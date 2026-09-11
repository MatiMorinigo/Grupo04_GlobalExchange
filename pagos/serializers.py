from rest_framework import serializers

from .models import MetodoPago, TipoMetodoPago
from .validators import validar_numero_billetera, validar_numero_tarjeta, validar_vencimiento_no_vencido


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
            "proveedor_billetera",
            "numero_billetera",
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
        if value:
            validar_vencimiento_no_vencido(value)
        return value

    def validate(self, attrs):
        """Exige los campos del tipo original, también en actualizaciones parciales."""
        tipo = self.instance.tipo if self.instance else attrs.get("tipo")
        if self.instance:
            attrs.pop("tipo", None)
        es_billetera = tipo == TipoMetodoPago.BILLETERA_ELECTRONICA
        requeridos = ("proveedor_billetera", "numero_billetera") if es_billetera else ("fecha_vencimiento",)
        errores = {}
        for campo in requeridos:
            valor = attrs.get(campo, getattr(self.instance, campo, ""))
            if not valor:
                errores[campo] = "Este campo es obligatorio."
        if not es_billetera and self.instance is None and not attrs.get("numero_tarjeta"):
            errores["numero_tarjeta"] = "El número de tarjeta es obligatorio."
        if errores:
            raise serializers.ValidationError(errores)
        if es_billetera:
            attrs.pop("numero_tarjeta", None)
            attrs["ultimos_cuatro_digitos"] = ""
            attrs["fecha_vencimiento"] = ""
        else:
            attrs["proveedor_billetera"] = ""
            attrs["numero_billetera"] = ""
        return attrs

    def validate_numero_billetera(self, value):
        """Normaliza el celular validado por el modelo."""
        return validar_numero_billetera(value) if value else value

    def create(self, validated_data):
        """Crea el método de pago derivando los últimos 4 dígitos del número ingresado.

        Args:
            validated_data (dict): Datos validados, incluyendo numero_tarjeta.

        Returns:
            MetodoPago: Método de pago creado.
        """
        numero = validated_data.pop("numero_tarjeta", "")
        validated_data["ultimos_cuatro_digitos"] = numero[-4:]
        return super().create(validated_data)

    def update(self, instance, validated_data):
        """Actualiza el método de pago, sin permitir modificar el tipo de método de pago.

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
