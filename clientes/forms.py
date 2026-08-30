from django import forms

from .models import CategoriaCliente, Cliente, TipoCliente


class ClienteForm(forms.ModelForm):
    class Meta:
        model = Cliente
        fields = ["ruc", "nombre", "categoria", "tipo"]
        labels = {
            "ruc": "RUC",
            "nombre": "Nombre",
            "categoria": "Categoría",
            "tipo": "Tipo de cliente",
        }
        widgets = {
            "ruc": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Ej. 80012345-6",
                    "autocomplete": "off",
                }
            ),
            "nombre": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Nombre o razón social",
                    "autocomplete": "organization",
                }
            ),
            "categoria": forms.Select(
                choices=CategoriaCliente.choices,
                attrs={"class": "form-select"},
            ),
            "tipo": forms.Select(
                choices=TipoCliente.choices,
                attrs={"class": "form-select"},
            ),
        }
        error_messages = {
            "ruc": {
                "required": "El RUC es obligatorio.",
                "blank": "El RUC no puede estar vacío.",
                "unique": "Ya existe un cliente registrado con este RUC.",
            },
            "nombre": {
                "required": "El nombre es obligatorio.",
                "blank": "El nombre no puede estar vacío.",
            },
            "categoria": {
                "required": "La categoría es obligatoria.",
                "invalid_choice": "La categoría ingresada no es válida.",
            },
            "tipo": {
                "required": "El tipo de cliente es obligatorio.",
                "invalid_choice": "El tipo de cliente ingresado no es válido.",
            },
        }
