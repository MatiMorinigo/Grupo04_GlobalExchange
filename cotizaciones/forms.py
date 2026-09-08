from django import forms

from .models import Moneda


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
