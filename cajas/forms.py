from django import forms
from .models import Sucursal, Caja
from .models import AsignacionCaja, Caja
from .keycloak_service import (
    obtener_cajeros_keycloak,
    obtener_cajero_verificado,
    KeycloakServiceError,
)

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


class AsignacionCajaForm(forms.ModelForm):

    cajero_keycloak_id = forms.ChoiceField(
        label="Cajero",
        widget=forms.Select(attrs={"class": "form-select"})
    )

    class Meta:
        model = AsignacionCaja
        fields = [
            "caja",
            "cajero_keycloak_id",
            "turno",
            "fecha_inicio",
            "fecha_fin",
        ]

        widgets = {
            "caja": forms.Select(attrs={
                "class": "form-select"
            }),
            "turno": forms.TextInput(attrs={
                "class": "form-control"
            }),
            "fecha_inicio": forms.DateTimeInput(
                attrs={
                    "class": "form-control",
                    "type": "datetime-local",
                },
                format="%Y-%m-%dT%H:%M"
            ),
            "fecha_fin": forms.DateTimeInput(
                attrs={
                    "class": "form-control",
                    "type": "datetime-local",
                },
                format="%Y-%m-%dT%H:%M"
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.cajero_verificado = None
        self.error_keycloak = False

        # Solo mostrar cajas habilitadas.
        self.fields["caja"].queryset = Caja.objects.filter(
            activa=True,
            sucursal__activa=True
        )

        # Obtener los cajeros directamente de Keycloak.
        try:
            cajeros = obtener_cajeros_keycloak()
        except KeycloakServiceError:
            cajeros = []
            self.error_keycloak = True

        self.fields["cajero_keycloak_id"].choices = [
            ("", "Seleccione un cajero")
        ] + [
            (cajero["id"], cajero["username"])
            for cajero in cajeros
        ]

    def clean(self):
        cleaned_data = super().clean()

        if self.error_keycloak:
            raise forms.ValidationError(
                "No se pudo consultar la lista de cajeros "
                "en Keycloak. Intente nuevamente."
            )

        cajero_id = cleaned_data.get("cajero_keycloak_id")

        if cajero_id:
            try:
                cajero = obtener_cajero_verificado(cajero_id)

            except KeycloakServiceError:
                raise forms.ValidationError(
                    "No se pudo verificar el rol del cajero "
                    "en Keycloak."
                )

            if cajero is None:
                self.add_error(
                    "cajero_keycloak_id",
                    "El usuario seleccionado no está habilitado "
                    "o no tiene el rol cajero."
                )
            else:
                self.cajero_verificado = cajero

        return cleaned_data
