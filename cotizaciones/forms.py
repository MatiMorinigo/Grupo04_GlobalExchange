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
    """Recoge la moneda extranjera y los precios iniciales para crear una tasa de cambio.

    La moneda de destino no es seleccionable: el sistema siempre registra y
    busca las tasas como moneda extranjera/PYG (ver
    ``services.obtener_tasa_para_simulacion``), así que se fija en PYG.
    """
    moneda_origen = forms.ModelChoiceField(
        queryset=Moneda.objects.none(),
        to_field_name="codigo",
        label="Moneda extranjera",
        empty_label="Seleccione una moneda",
        error_messages={
            "required": "Seleccione la moneda extranjera.",
            "invalid_choice": "La moneda seleccionada no es válida.",
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
        """Inicializa el formulario y carga las monedas extranjeras activas ordenadas por código.

        Excluye PYG de las opciones de moneda extranjera, ya que la moneda de
        destino se fija en PYG y una tasa PYG/PYG no tiene sentido.

        Args:
            *args: Argumentos posicionales del formulario base de Django.
            **kwargs: Opciones del formulario base, como datos e iniciales.
        """
        super().__init__(*args, **kwargs)
        self.fields["moneda_origen"].queryset = (
            Moneda.objects.filter(activa=True).exclude(codigo="PYG").order_by("codigo")
        )

    def clean(self):
        """Fija la moneda de destino en PYG y valida que el par no tenga ya una tasa vigente.

        Returns:
            dict: Datos limpiados del formulario, con `moneda_destino` agregado.

        Raises:
            django.forms.ValidationError: Si PYG no está habilitada como
                moneda, o si ya existe una tasa vigente para el par.
        """
        cleaned_data = super().clean()
        origen = cleaned_data.get("moneda_origen")

        if origen:
            destino = Moneda.objects.filter(codigo="PYG", activa=True).first()
            if not destino:
                raise forms.ValidationError(
                    "El guaraní paraguayo (PYG) debe estar habilitado para registrar tasas de cambio."
                )
            cleaned_data["moneda_destino"] = destino

            if TasaCambio.objects.filter(
                vigente=True, moneda_origen=origen, moneda_destino=destino
            ).exists():
                raise forms.ValidationError(
                    "Ya existe una tasa vigente para este par de monedas. "
                    "Utilice la opción Editar."
                )

        return cleaned_data


class MonedaForm(forms.ModelForm):
    """Permite crear y editar monedas admitidas mediante la interfaz web.

    El código no puede modificarse al editar una moneda existente, ya que
    es su clave primaria.
    """
    class Meta:
        """Configura los campos y la presentación del formulario de monedas."""
        model = Moneda
        fields = ["codigo", "nombre", "simbolo"]
        labels = {
            "codigo": "Código",
            "nombre": "Nombre",
            "simbolo": "Símbolo",
        }
        widgets = {
            "codigo": forms.TextInput(
                attrs={
                    "class": "form-control text-uppercase",
                    "placeholder": "Ej. USD",
                    "maxlength": "3",
                    "autocomplete": "off",
                }
            ),
            "nombre": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Ej. Dólar estadounidense",
                    "autocomplete": "off",
                }
            ),
            "simbolo": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Ej. US$",
                    "autocomplete": "off",
                }
            ),
        }
        error_messages = {
            "codigo": {
                "required": "El código es obligatorio.",
                "unique": "Ya existe una moneda registrada con este código.",
            },
            "nombre": {
                "required": "El nombre es obligatorio.",
                "blank": "El nombre no puede estar vacío.",
            },
            "simbolo": {
                "required": "El símbolo es obligatorio.",
                "blank": "El símbolo no puede estar vacío.",
            },
        }

    def __init__(self, *args, **kwargs):
        """Deshabilita el código al editar una moneda existente.

        Args:
            *args: Argumentos posicionales del formulario base de Django.
            **kwargs: Opciones del formulario base, como datos e instancia.
        """
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["codigo"].disabled = True

    def clean_codigo(self):
        """Normaliza el código de la moneda a mayúsculas.

        Returns:
            str: Código de la moneda en mayúsculas.
        """
        if self.instance.pk:
            return self.instance.pk
        return self.cleaned_data["codigo"].upper()


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
