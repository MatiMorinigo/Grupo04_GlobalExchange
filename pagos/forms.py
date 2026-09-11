from django import forms

from .models import MetodoPago
from .validators import validar_numero_tarjeta, validar_vencimiento_no_vencido


class MetodoPagoForm(forms.ModelForm):
    """Permite registrar y editar métodos de pago del cliente activo.

    El tipo de tarjeta no puede modificarse al editar un método de pago ya
    existente. El número de tarjeta nunca se almacena completo: se solicita
    para validarlo (formato y algoritmo de Luhn) y solo se conservan sus
    últimos cuatro dígitos.
    """
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
        fields = ["tipo", "titular", "fecha_vencimiento"]
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
        if self.instance.pk:
            self.fields["tipo"].disabled = True
            self.fields["numero_tarjeta"].help_text = (
                f"Dejalo en blanco para mantener la tarjeta actual "
                f"(•••• {self.instance.ultimos_cuatro_digitos})."
            )
        else:
            self.fields["numero_tarjeta"].required = True

    def clean_tipo(self):
        """Impide cambiar el tipo de tarjeta al editar un método existente.

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
        if numero:
            instance.ultimos_cuatro_digitos = numero[-4:]
        if commit:
            instance.save()
        return instance
