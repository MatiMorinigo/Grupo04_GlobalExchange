from django import forms

from .models import MetodoPago


class MetodoPagoForm(forms.ModelForm):
    """Permite crear y editar métodos de pago mediante la interfaz web.

    Incluye nombre, descripción y estado de habilitación. Los campos
    de trazabilidad (creado_por, modificado_por) se gestionan en la
    vista, no en el formulario.
    """

    class Meta:
        """Configura los campos y la presentación del formulario."""

        model = MetodoPago
        fields = ["nombre", "descripcion", "habilitado"]
        labels = {
            "nombre": "Nombre",
            "descripcion": "Descripción",
            "habilitado": "Habilitado",
        }
        widgets = {
            "nombre": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Ej. Transferencia bancaria",
                    "autocomplete": "off",
                }
            ),
            "descripcion": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": "Descripción opcional del método de pago",
                }
            ),
            "habilitado": forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            ),
        }
        error_messages = {
            "nombre": {
                "required": "El nombre es obligatorio.",
                "blank": "El nombre no puede estar vacío.",
                "unique": "Ya existe un método de pago registrado con este nombre.",
                "max_length": "El nombre no puede superar los 100 caracteres.",
            },
        }
