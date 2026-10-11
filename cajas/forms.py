from django import forms

from .models import Sucursal, Caja


class SucursalForm(forms.ModelForm):
    class Meta:
        model = Sucursal
        fields = [
            "codigo",
            "nombre",
            "direccion",
        ]

        widgets = {
            "codigo": forms.TextInput(
                attrs={"class": "form-control"}
            ),
            "nombre": forms.TextInput(
                attrs={"class": "form-control"}
            ),
            "direccion": forms.TextInput(
                attrs={"class": "form-control"}
            ),
        }


class CajaForm(forms.ModelForm):
    class Meta:
        model = Caja
        fields = [
            "sucursal",
            "codigo",
            "nombre",
        ]

        widgets = {
            "sucursal": forms.Select(
                attrs={"class": "form-select"}
            ),
            "codigo": forms.TextInput(
                attrs={"class": "form-control"}
            ),
            "nombre": forms.TextInput(
                attrs={"class": "form-control"}
            ),
        }