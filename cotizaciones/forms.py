from django import forms

from .models import Moneda


class SimulacionConversionForm(forms.Form):
    """Recoge las monedas activas y el monto para simular una conversión."""
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
