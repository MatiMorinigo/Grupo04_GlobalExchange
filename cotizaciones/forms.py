from decimal import Decimal

from django import forms
from django.core.validators import MinValueValidator

from .models import Moneda, TasaCambio


class TasaCambioEditarForm(forms.Form):
    """Recoge los nuevos precios de compra y venta para modificar una tasa de cambio.

    Incluye un campo oculto confirmado que distingue el primer envío, donde se
    solicitan los nuevos precios, del envío de confirmación, donde se aplica
    la modificación.
    """
    precio_compra = forms.DecimalField(
        label="Nuevo precio de compra",
        max_digits=18,
        decimal_places=4,
        validators=[MinValueValidator(Decimal("0.0001"))],
        error_messages={
            "required": "Ingrese el nuevo precio de compra.",
            "min_value": "El precio de compra debe ser mayor a cero.",
        },
        widget=forms.NumberInput(
            attrs={"class": "form-control", "step": "0.0001", "min": "0.0001"}
        ),
    )
    precio_venta = forms.DecimalField(
        label="Nuevo precio de venta",
        max_digits=18,
        decimal_places=4,
        validators=[MinValueValidator(Decimal("0.0001"))],
        error_messages={
            "required": "Ingrese el nuevo precio de venta.",
            "min_value": "El precio de venta debe ser mayor a cero.",
        },
        widget=forms.NumberInput(
            attrs={"class": "form-control", "step": "0.0001", "min": "0.0001"}
        ),
    )
    confirmado = forms.BooleanField(required=False, widget=forms.HiddenInput())


class TasaCambioCrearForm(forms.Form):
    """Recoge el par de monedas y los precios iniciales para crear una tasa de cambio."""
    moneda_origen = forms.ModelChoiceField(
        queryset=Moneda.objects.none(),
        to_field_name="codigo",
        label="Moneda de origen",
        empty_label="Seleccione una moneda",
        error_messages={
            "required": "Seleccione la moneda de origen.",
            "invalid_choice": "La moneda de origen seleccionada no es válida.",
        },
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    moneda_destino = forms.ModelChoiceField(
        queryset=Moneda.objects.none(),
        to_field_name="codigo",
        label="Moneda de destino",
        empty_label="Seleccione una moneda",
        error_messages={
            "required": "Seleccione la moneda de destino.",
            "invalid_choice": "La moneda de destino seleccionada no es válida.",
        },
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    precio_compra = forms.DecimalField(
        label="Precio de compra",
        max_digits=18,
        decimal_places=4,
        validators=[MinValueValidator(Decimal("0.0001"))],
        error_messages={
            "required": "Ingrese el precio de compra.",
            "min_value": "El precio de compra debe ser mayor a cero.",
        },
        widget=forms.NumberInput(
            attrs={"class": "form-control", "step": "0.0001", "min": "0.0001"}
        ),
    )
    precio_venta = forms.DecimalField(
        label="Precio de venta",
        max_digits=18,
        decimal_places=4,
        validators=[MinValueValidator(Decimal("0.0001"))],
        error_messages={
            "required": "Ingrese el precio de venta.",
            "min_value": "El precio de venta debe ser mayor a cero.",
        },
        widget=forms.NumberInput(
            attrs={"class": "form-control", "step": "0.0001", "min": "0.0001"}
        ),
    )

    def __init__(self, *args, **kwargs):
        """Inicializa el formulario y carga las monedas activas ordenadas por código.

        Args:
            *args: Argumentos posicionales del formulario base de Django.
            **kwargs: Opciones del formulario base, como datos e iniciales.
        """
        super().__init__(*args, **kwargs)
        monedas = Moneda.objects.filter(activa=True).order_by("codigo")
        self.fields["moneda_origen"].queryset = monedas
        self.fields["moneda_destino"].queryset = monedas

    def clean(self):
        """Valida que las monedas sean distintas y que el par no tenga ya una tasa vigente.

        Returns:
            dict: Datos limpiados del formulario.

        Raises:
            django.forms.ValidationError: Si ambas monedas coinciden o si ya
                existe una tasa vigente para el par seleccionado.
        """
        cleaned_data = super().clean()
        origen = cleaned_data.get("moneda_origen")
        destino = cleaned_data.get("moneda_destino")

        if origen and destino:
            if origen.codigo == destino.codigo:
                raise forms.ValidationError("La moneda de origen y destino deben ser distintas.")

            if TasaCambio.objects.filter(
                vigente=True, moneda_origen=origen, moneda_destino=destino
            ).exists():
                raise forms.ValidationError(
                    "Ya existe una tasa vigente para este par de monedas. "
                    "Utilice la opción Editar."
                )

        return cleaned_data


class SimulacionConversionForm(forms.Form):
    """
    Recoge las monedas, el monto y la categoría del cliente
    para simular una conversión monetaria.
    """
    moneda_origen = forms.ModelChoiceField(
        queryset=Moneda.objects.none(),
        to_field_name="codigo",
        label="Moneda de origen",
        empty_label="Seleccione una moneda",
        error_messages={
            "required": "Seleccione la moneda de origen.",
            "invalid_choice": "La moneda de origen seleccionada no es válida.",
        },
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    moneda_destino = forms.ModelChoiceField(
        queryset=Moneda.objects.none(),
        to_field_name="codigo",
        label="Moneda de destino",
        empty_label="Seleccione una moneda",
        error_messages={
            "required": "Seleccione la moneda de destino.",
            "invalid_choice": "La moneda de destino seleccionada no es válida.",
        },
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    monto = forms.DecimalField(
        label="Monto",
        min_value=0.01,
        max_digits=18,
        decimal_places=2,
        widget=forms.NumberInput(
            attrs={
                "class": "form-control",
                "placeholder": "Ej. 100000",
                "step": "0.01",
                "min": "0.01",
            }
        ),
    )

    def __init__(self, *args, **kwargs):
        """Inicializa el formulario y carga las monedas activas ordenadas por código.

        Args:
            *args: Argumentos posicionales del formulario base de Django.
            **kwargs: Opciones del formulario base, como datos e iniciales.
        """
        super().__init__(*args, **kwargs)
        monedas = Moneda.objects.filter(activa=True).order_by("codigo")
        self.fields["moneda_origen"].queryset = monedas
        self.fields["moneda_destino"].queryset = monedas

    def clean(self):
        """Comprueba que las monedas seleccionadas sean distintas.

        Returns:
            dict: Datos limpiados del formulario.

        Raises:
            django.forms.ValidationError: Si ambas monedas están presentes
                y sus códigos coinciden.
        """
        cleaned_data = super().clean()
        origen = cleaned_data.get("moneda_origen")
        destino = cleaned_data.get("moneda_destino")

        if origen and destino and origen.codigo == destino.codigo:
            raise forms.ValidationError("La moneda de origen y destino deben ser distintas.")

        return cleaned_data
