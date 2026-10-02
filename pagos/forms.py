from django import forms

from .constants import PROVEEDORES_BILLETERA
from .models import MetodoPago, TipoMetodoPago
from .validators import validar_numero_tarjeta, validar_vencimiento_no_vencido


class MetodoPagoForm(forms.ModelForm):
    """Permite registrar y editar métodos de pago del cliente activo.

    El tipo de método no puede modificarse al editar un método de pago ya
    existente. El número de tarjeta nunca se almacena completo: se solicita
    para validarlo (formato y algoritmo de Luhn) y solo se conservan sus
    últimos cuatro dígitos.
    """
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
    numero_tarjeta = forms.CharField(
        label="Número de tarjeta",
        max_length=19,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "•••• •••• •••• ••••",
                "autocomplete": "off",
                "inputmode": "numeric",
            }
        ),
    )

    class Meta:
        """Configura los campos y la presentación del formulario de métodos de pago."""
        model = MetodoPago
        fields = ["tipo", "titular", "fecha_vencimiento", "proveedor_billetera", "numero_billetera"]
        labels = {
            "tipo": "Tipo",
            "titular": "Titular",
            "fecha_vencimiento": "Vencimiento",
        }
        widgets = {
            "tipo": forms.Select(attrs={"class": "form-select"}),
            "titular": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Nombre tal como figura en la tarjeta",
                    "autocomplete": "off",
                }
            ),
            "numero_billetera": forms.TextInput(attrs={
                "class": "form-control", "placeholder": "Ej.: 0981 123 456",
                "autocomplete": "off", "inputmode": "tel", "type": "tel",
            }),
            "fecha_vencimiento": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "MM/AA",
                    "autocomplete": "off",
                }
            ),
        }
        error_messages = {
            "tipo": {"required": "El tipo es obligatorio."},
            "titular": {
                "required": "El titular es obligatorio.",
                "blank": "El titular no puede estar vacío.",
            },
            "fecha_vencimiento": {"required": "El vencimiento es obligatorio."},
        }

    def __init__(self, *args, **kwargs):
        """Deshabilita el tipo y adapta el número de tarjeta al editar un método existente.

        Args:
            *args: Argumentos posicionales del formulario base de Django.
            **kwargs: Opciones del formulario base, como datos e instancia.
        """
        super().__init__(*args, **kwargs)
        # Conserva proveedores registrados antes de incorporar el selector.
        proveedor_actual = self.instance.proveedor_billetera
        opciones = self.fields["proveedor_billetera"].choices
        if self.instance.pk and proveedor_actual and proveedor_actual not in dict(opciones):
            self.fields["proveedor_billetera"].choices = [
                *opciones, (proveedor_actual, proveedor_actual),
            ]
        if self.instance.pk:
            self.fields["tipo"].disabled = True
            self.fields["numero_tarjeta"].help_text = (
                f"Dejalo en blanco para mantener la tarjeta actual "
                f"(•••• {self.instance.ultimos_cuatro_digitos})."
            )
        tipo = self.instance.tipo if self.instance.pk else (
            self.data.get(self.add_prefix("tipo")) if self.is_bound else self.initial.get("tipo")
        )
        self.es_billetera = tipo == TipoMetodoPago.BILLETERA_ELECTRONICA
        self.fields["numero_tarjeta"].required = not self.es_billetera and not self.instance.pk
        self.fields["fecha_vencimiento"].required = not self.es_billetera
        for campo in ("proveedor_billetera", "numero_billetera"):
            self.fields[campo].required = self.es_billetera
        inactivos = ("numero_tarjeta", "fecha_vencimiento") if self.es_billetera else (
            "proveedor_billetera", "numero_billetera"
        )
        for campo in inactivos:
            self.fields[campo].disabled = True
            self.initial[campo] = ""
        if self.es_billetera:
            self.fields["titular"].widget.attrs["placeholder"] = "Nombre del titular de la billetera"

    def clean_tipo(self):
        """Impide cambiar el tipo de método de pago al editar un método existente.

        Returns:
            str: Tipo original si se está editando, o el tipo ingresado si
            se está creando un método de pago nuevo.
        """
        if self.instance.pk:
            return self.instance.tipo
        return self.cleaned_data["tipo"]

    def clean_numero_tarjeta(self):
        """Valida el número de tarjeta ingresado, si se completó.

        Returns:
            str: Número de tarjeta validado y sin espacios, o cadena vacía
            si se dejó en blanco al editar.
        """
        numero = self.cleaned_data.get("numero_tarjeta", "")
        if not numero:
            return ""
        return validar_numero_tarjeta(numero)

    def clean_fecha_vencimiento(self):
        """Valida que la fecha de vencimiento no corresponda a una tarjeta ya vencida.

        Returns:
            str: Fecha de vencimiento validada, en formato MM/AA.
        """
        valor = self.cleaned_data["fecha_vencimiento"]
        if not self.es_billetera:
            validar_vencimiento_no_vencido(valor)
        return valor

    def save(self, commit=True):
        """Guarda el método de pago, derivando los últimos 4 dígitos del número ingresado.

        Args:
            commit (bool): Si es True, persiste la instancia en la base de
                datos antes de devolverla.

        Returns:
            MetodoPago: Instancia guardada (o pendiente de guardar si
            commit es False).
        """
        instance = super().save(commit=False)
        numero = self.cleaned_data.get("numero_tarjeta")
        if instance.es_billetera:
            instance.ultimos_cuatro_digitos = ""
            instance.fecha_vencimiento = ""
        elif numero:
            instance.ultimos_cuatro_digitos = numero[-4:]
        if commit:
            instance.save()
        return instance
