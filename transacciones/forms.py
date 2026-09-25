from django import forms

from cotizaciones.models import Moneda
from destinos.models import DestinoAcreditacion
from pagos.models import MetodoPago


class MetodoPagoChoiceField(forms.ModelChoiceField):
    """Presenta cada método de pago con su tipo y su identificación enmascarada."""

    def label_from_instance(self, obj):
        """Construye la etiqueta visible de un método de pago.

        Args:
            obj (pagos.models.MetodoPago): Método de pago a describir.

        Returns:
            str: Tipo del método junto con su identificación.
        """
        return f"{obj.get_tipo_display()} · {obj.identificacion}"


class DestinoAcreditacionChoiceField(forms.ModelChoiceField):
    """Presenta cada destino con su moneda, para que la elección sea inequívoca."""

    def label_from_instance(self, obj):
        """Construye la etiqueta visible de un destino de acreditación.

        Args:
            obj (destinos.models.DestinoAcreditacion): Destino a describir.

        Returns:
            str: Moneda y etiqueta del destino.
        """
        return f"[{obj.moneda_id}] {obj.etiqueta}"


class CompraDivisaForm(forms.Form):
    """Recoge los datos de una compra de divisas y su paso de confirmación.

    Solo ofrece monedas extranjeras habilitadas que tengan una cotización
    vigente, y destinos de acreditación y métodos de pago activos del cliente
    que opera. La compatibilidad entre el destino elegido y la moneda se
    verifica al limpiar el formulario.

    Los campos ocultos ``confirmado`` e ``id_tasa_vista`` sostienen el paso de
    confirmación sin recurrir a la sesión: el primero distingue el envío que
    solo pide el resumen del que registra la operación, y el segundo permite
    detectar si la cotización cambió mientras el cliente revisaba el resumen.
    """
    moneda = forms.ModelChoiceField(
        label="Moneda a comprar",
        queryset=Moneda.objects.none(),
        to_field_name="codigo",
        empty_label="Seleccioná una moneda",
        widget=forms.Select(attrs={"class": "form-select"}),
        error_messages={
            "required": "Seleccioná la moneda que querés comprar.",
            "invalid_choice": "Seleccioná una moneda con cotización vigente.",
        },
    )
    monto_divisa = forms.DecimalField(
        label="Monto a comprar",
        min_value=0.01,
        max_digits=18,
        decimal_places=2,
        widget=forms.NumberInput(
            attrs={
                "class": "form-control",
                "step": "0.01",
                "min": "0.01",
                "placeholder": "Ej.: 100.00",
                "autocomplete": "off",
            }
        ),
        error_messages={
            "required": "Ingresá el monto de la operación.",
            "min_value": "El monto debe ser mayor a cero.",
            "invalid": "Ingresá un monto válido.",
        },
    )
    destino_acreditacion = DestinoAcreditacionChoiceField(
        label="Destino de acreditación",
        queryset=DestinoAcreditacion.objects.none(),
        required=False,
        empty_label="Elegirlo más adelante",
        widget=forms.Select(attrs={"class": "form-select"}),
        error_messages={
            "invalid_choice": "Seleccioná un destino de acreditación propio y activo.",
        },
    )
    metodo_pago = MetodoPagoChoiceField(
        label="Método de pago",
        queryset=MetodoPago.objects.none(),
        empty_label="Seleccioná un método de pago",
        widget=forms.Select(attrs={"class": "form-select"}),
        error_messages={
            "required": "Seleccioná con qué método vas a pagar la operación.",
            "invalid_choice": "Seleccioná un método de pago propio y activo.",
        },
    )
    confirmado = forms.BooleanField(required=False, widget=forms.HiddenInput())
    id_tasa_vista = forms.IntegerField(required=False, widget=forms.HiddenInput())

    def __init__(self, *args, cliente=None, **kwargs):
        """Acota las opciones del formulario al cliente que realiza la operación.

        Args:
            *args: Argumentos posicionales del formulario base de Django.
            cliente (clientes.models.Cliente or None): Cliente activo cuyos
                destinos de acreditación pueden seleccionarse.
            **kwargs: Opciones del formulario base, como los datos enviados.
        """
        super().__init__(*args, **kwargs)
        self.cliente = cliente

        self.fields["moneda"].queryset = (
            Moneda.objects.filter(
                activa=True,
                tasas_origen__vigente=True,
                tasas_origen__moneda_destino_id="PYG",
            )
            .exclude(codigo="PYG")
            .distinct()
            .order_by("codigo")
        )

        if cliente:
            self.fields["destino_acreditacion"].queryset = (
                DestinoAcreditacion.objects.filter(cliente=cliente, activo=True)
                .select_related("moneda")
                .order_by("moneda_id", "-creado_en")
            )
            self.fields["metodo_pago"].queryset = MetodoPago.objects.filter(
                cliente=cliente, activo=True
            ).order_by("-creado_en")

    def clean(self):
        """Comprueba que el destino elegido admita la moneda de la operación.

        Returns:
            dict: Datos limpiados del formulario.
        """
        cleaned_data = super().clean()
        moneda = cleaned_data.get("moneda")
        destino = cleaned_data.get("destino_acreditacion")

        if moneda and destino and destino.moneda_id != moneda.codigo:
            self.add_error(
                "destino_acreditacion",
                f"El destino seleccionado recibe {destino.moneda_id} "
                f"y la operación es en {moneda.codigo}.",
            )

        return cleaned_data
