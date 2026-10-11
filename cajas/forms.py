from django import forms
from cotizaciones.models import Moneda
from .models import DenominacionBillete
from .services import MAX_LINEAS_INVENTARIO
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


class DenominacionBilleteForm(forms.ModelForm):
    """Reutiliza las validaciones de valor y unicidad del catálogo."""

    class Meta:
        model = DenominacionBillete
        fields = ["moneda", "valor"]
        labels = {"valor": "Valor de denominación"}
        widgets = {
            "moneda": forms.Select(attrs={"class": "form-select"}),
            "valor": forms.NumberInput(attrs={
                "class": "form-control", "min": "0.01", "step": "0.01",
            }),
        }


class InventarioInicialForm(forms.Form):
    moneda = forms.ModelChoiceField(
        queryset=Moneda.objects.filter(activa=True),
        widget=forms.Select(attrs={"class": "form-select moneda"}),
    )
    denominacion = forms.ModelChoiceField(
        queryset=DenominacionBillete.objects.filter(activa=True, moneda__activa=True),
        label="Denominación", widget=forms.Select(attrs={"class": "form-select denominacion"}),
    )
    cantidad = forms.IntegerField(
        min_value=0, max_value=2147483647,
        widget=forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": 1}),
    )

    def clean(self):
        datos = super().clean()
        moneda, denominacion = datos.get("moneda"), datos.get("denominacion")
        if moneda and denominacion and denominacion.moneda_id != moneda.pk:
            self.add_error("denominacion", "La denominación no corresponde a la moneda seleccionada.")
        return datos


class BaseInventarioInicialFormSet(forms.BaseFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        denominaciones = set()
        for form in self.forms:
            datos = form.cleaned_data
            if not datos or datos.get("DELETE"):
                continue
            denominacion_id = datos["denominacion"].pk
            if denominacion_id in denominaciones:
                raise forms.ValidationError("No repita denominaciones dentro del inventario.")
            denominaciones.add(denominacion_id)
        if not denominaciones:
            raise forms.ValidationError("Registre al menos una línea de inventario.")

    def inventario(self):
        """Solo utilizar después de is_valid()."""
        return [
            {"denominacion_id": form.cleaned_data["denominacion"].pk,
             "cantidad": form.cleaned_data["cantidad"]}
            for form in self.forms if form.cleaned_data and not form.cleaned_data.get("DELETE")
        ]


InventarioInicialFormSet = forms.formset_factory(
    InventarioInicialForm, formset=BaseInventarioInicialFormSet,
    extra=0, min_num=1, validate_min=True, can_delete=True,
    max_num=MAX_LINEAS_INVENTARIO, validate_max=True, absolute_max=MAX_LINEAS_INVENTARIO,
)
