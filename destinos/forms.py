from django import forms

from cotizaciones.models import Moneda
from pagos.constants import PROVEEDORES_BILLETERA

from .constants import BANCOS
from .models import DestinoAcreditacion, TipoDestinoAcreditacion


class DestinoAcreditacionForm(forms.ModelForm):
    """Permite registrar y editar destinos de acreditación del cliente activo.

    El tipo de destino no puede modificarse al editar un destino existente,
    porque cambiarlo dejaría sin sentido los datos ya cargados. Los campos
    que no corresponden al tipo elegido se deshabilitan y se vacían.
    """
    banco = forms.ChoiceField(
        label="Banco",
        required=False,
        choices=[("", "Seleccioná un banco"), *BANCOS],
        widget=forms.Select(attrs={"class": "form-select"}),
        error_messages={
            "required": "Seleccioná un banco.",
            "invalid_choice": "Seleccioná un banco de la lista.",
        },
    )
    proveedor_billetera = forms.ChoiceField(
        label="Proveedor de la billetera",
        required=False,
        choices=[("", "Seleccioná un proveedor"), *PROVEEDORES_BILLETERA],
        widget=forms.Select(attrs={"class": "form-select"}),
        error_messages={
            "required": "Seleccioná un proveedor de billetera.",
            "invalid_choice": "Seleccioná un proveedor de la lista.",
        },
    )

    class Meta:
        """Configura los campos y la presentación del formulario de destinos."""
        model = DestinoAcreditacion
        fields = [
            "tipo",
            "alias",
            "moneda",
            "titular",
            "documento_titular",
            "banco",
            "tipo_cuenta",
            "numero_cuenta",
            "proveedor_billetera",
            "numero_billetera",
        ]
        labels = {
            "tipo": "Tipo de destino",
            "alias": "Alias",
            "moneda": "Moneda",
            "titular": "Titular",
            "documento_titular": "Documento del titular",
            "tipo_cuenta": "Tipo de cuenta",
            "numero_cuenta": "Número de cuenta",
            "numero_billetera": "Celular asociado",
        }
        widgets = {
            "tipo": forms.Select(attrs={"class": "form-select"}),
            "moneda": forms.Select(attrs={"class": "form-select"}),
            "tipo_cuenta": forms.Select(attrs={"class": "form-select"}),
            "alias": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Ej.: Mi cuenta en dólares",
                    "autocomplete": "off",
                }
            ),
            "titular": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Nombre completo del titular",
                    "autocomplete": "off",
                }
            ),
            "documento_titular": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Ej.: 1234567 o 80012345-6",
                    "autocomplete": "off",
                }
            ),
            "numero_cuenta": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Solo números",
                    "autocomplete": "off",
                    "inputmode": "numeric",
                }
            ),
            "numero_billetera": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Ej.: 0981 123 456",
                    "autocomplete": "off",
                    "inputmode": "tel",
                    "type": "tel",
                }
            ),
        }
        error_messages = {
            "tipo": {
                "required": "El tipo de destino es obligatorio.",
                "invalid_choice": "El tipo de destino ingresado no es válido.",
            },
            "moneda": {
                "required": "La moneda es obligatoria.",
                "invalid_choice": "Seleccioná una moneda habilitada.",
            },
            "titular": {
                "required": "El titular es obligatorio.",
                "blank": "El titular no puede estar vacío.",
            },
            "documento_titular": {
                "required": "El documento del titular es obligatorio.",
                "blank": "El documento del titular no puede estar vacío.",
            },
        }

    def __init__(self, *args, **kwargs):
        """Adapta los campos obligatorios al tipo de destino y acota las monedas.

        Args:
            *args: Argumentos posicionales del formulario base de Django.
            **kwargs: Opciones del formulario base, como datos e instancia.
        """
        super().__init__(*args, **kwargs)
        self.fields["moneda"].queryset = Moneda.objects.filter(activa=True).order_by("codigo")

        # Conserva bancos y proveedores registrados antes de incorporar los selectores.
        for campo in ("banco", "proveedor_billetera"):
            valor_actual = getattr(self.instance, campo)
            opciones = self.fields[campo].choices
            if self.instance.pk and valor_actual and valor_actual not in dict(opciones):
                self.fields[campo].choices = [*opciones, (valor_actual, valor_actual)]

        if self.instance.pk:
            self.fields["tipo"].disabled = True

        tipo = self.instance.tipo if self.instance.pk else (
            self.data.get(self.add_prefix("tipo")) if self.is_bound else self.initial.get("tipo")
        )
        self.es_billetera = tipo == TipoDestinoAcreditacion.BILLETERA_ELECTRONICA

        for campo in ("banco", "tipo_cuenta", "numero_cuenta"):
            self.fields[campo].required = not self.es_billetera
        for campo in ("proveedor_billetera", "numero_billetera"):
            self.fields[campo].required = self.es_billetera

        inactivos = ("banco", "tipo_cuenta", "numero_cuenta") if self.es_billetera else (
            "proveedor_billetera", "numero_billetera"
        )
        for campo in inactivos:
            self.fields[campo].disabled = True
            self.initial[campo] = ""

    def clean_tipo(self):
        """Impide cambiar el tipo de destino al editar un destino existente.

        Returns:
            str: Tipo original si se está editando, o el tipo ingresado si
            se está creando un destino nuevo.
        """
        if self.instance.pk:
            return self.instance.tipo
        return self.cleaned_data["tipo"]
