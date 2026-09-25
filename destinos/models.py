from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from clientes.models import Cliente
from cotizaciones.models import Moneda
from pagos.validators import validar_numero_billetera

from .validators import validar_documento_titular, validar_numero_cuenta

User = get_user_model()


class TipoDestinoAcreditacion(models.TextChoices):
    """Define los tipos de destino donde un cliente puede recibir una acreditación."""
    CUENTA_BANCARIA = "CUENTA_BANCARIA", "Cuenta bancaria"
    BILLETERA_ELECTRONICA = "BILLETERA_ELECTRONICA", "Billetera electrónica"


class TipoCuentaBancaria(models.TextChoices):
    """Define las modalidades de cuenta bancaria admitidas."""
    CAJA_AHORRO = "CAJA_AHORRO", "Caja de ahorro"
    CUENTA_CORRIENTE = "CUENTA_CORRIENTE", "Cuenta corriente"


class DestinoAcreditacion(models.Model):
    """Representa una cuenta bancaria o billetera electrónica donde el cliente recibe sus fondos.

    Cada destino se registra en una moneda concreta, porque una cuenta solo
    puede recibir acreditaciones en la moneda en la que fue abierta. Esa
    restricción es la que permite ofrecer al cliente únicamente los destinos
    compatibles con la divisa que está comprando.
    """
    id_destino = models.BigAutoField(primary_key=True)
    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.CASCADE,
        related_name="destinos_acreditacion",
        verbose_name="Cliente",
    )
    tipo = models.CharField(
        max_length=25,
        choices=TipoDestinoAcreditacion.choices,
        verbose_name="Tipo",
    )
    alias = models.CharField(
        max_length=60,
        blank=True,
        verbose_name="Alias",
        help_text="Nombre con el que querés identificar este destino.",
    )
    titular = models.CharField(max_length=150, verbose_name="Titular")
    documento_titular = models.CharField(
        max_length=20,
        verbose_name="Documento del titular",
        validators=[validar_documento_titular],
    )
    moneda = models.ForeignKey(
        Moneda,
        on_delete=models.PROTECT,
        related_name="destinos_acreditacion",
        verbose_name="Moneda",
    )
    banco = models.CharField(max_length=100, blank=True, verbose_name="Banco")
    tipo_cuenta = models.CharField(
        max_length=20,
        choices=TipoCuentaBancaria.choices,
        blank=True,
        verbose_name="Tipo de cuenta",
    )
    numero_cuenta = models.CharField(
        max_length=30,
        blank=True,
        verbose_name="Número de cuenta",
        validators=[validar_numero_cuenta],
    )
    proveedor_billetera = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Proveedor de la billetera",
    )
    numero_billetera = models.CharField(
        max_length=20,
        blank=True,
        verbose_name="Celular asociado",
        validators=[validar_numero_billetera],
    )
    activo = models.BooleanField(default=True, verbose_name="Activo")
    creado_en = models.DateTimeField(auto_now_add=True, verbose_name="Creado el")
    actualizado_en = models.DateTimeField(auto_now=True, verbose_name="Última modificación")

    class Meta:
        """Define el orden, la presentación y la unicidad de los destinos de acreditación."""
        ordering = ["-creado_en"]
        verbose_name = "Destino de acreditación"
        verbose_name_plural = "Destinos de acreditación"
        constraints = [
            models.UniqueConstraint(
                fields=["cliente", "moneda", "numero_cuenta"],
                condition=Q(tipo=TipoDestinoAcreditacion.CUENTA_BANCARIA),
                name="destino_cuenta_unica_por_cliente_moneda",
            ),
        ]

    @property
    def es_billetera(self):
        """Indica si el destino es una billetera electrónica.

        Returns:
            bool: True si el tipo del destino es billetera electrónica.
        """
        return self.tipo == TipoDestinoAcreditacion.BILLETERA_ELECTRONICA

    @property
    def identificacion(self):
        """Identifica el destino en listados y confirmaciones.

        Returns:
            str: Proveedor y celular si es una billetera, o banco y últimos
            cuatro dígitos de la cuenta si es una cuenta bancaria.
        """
        if self.es_billetera:
            return f"{self.proveedor_billetera} · {self.numero_billetera}"
        return f"{self.banco} · ••••{self.numero_cuenta[-4:]}"

    @property
    def etiqueta(self):
        """Devuelve el alias del destino o, si no tiene, su identificación.

        Returns:
            str: Texto con el que se presenta el destino al cliente.
        """
        return self.alias or self.identificacion

    def clean(self):
        """Exige los datos propios del tipo de destino y descarta los del otro tipo.

        Raises:
            django.core.exceptions.ValidationError: Si faltan campos
                obligatorios para el tipo elegido, si alguno no supera su
                validación específica o si la moneda está deshabilitada.
        """
        super().clean()
        errores = {}

        if self.es_billetera:
            for campo in ("proveedor_billetera", "numero_billetera"):
                valor = getattr(self, campo).strip()
                setattr(self, campo, valor)
                if not valor:
                    errores[campo] = "Este campo es obligatorio para una billetera electrónica."
            if self.numero_billetera:
                try:
                    self.numero_billetera = validar_numero_billetera(self.numero_billetera)
                except ValidationError as error:
                    errores["numero_billetera"] = error.messages
            self.banco = ""
            self.tipo_cuenta = ""
            self.numero_cuenta = ""
        else:
            for campo in ("banco", "tipo_cuenta", "numero_cuenta"):
                valor = getattr(self, campo).strip()
                setattr(self, campo, valor)
                if not valor:
                    errores[campo] = "Este campo es obligatorio para una cuenta bancaria."
            if self.numero_cuenta:
                try:
                    self.numero_cuenta = validar_numero_cuenta(self.numero_cuenta)
                except ValidationError as error:
                    errores["numero_cuenta"] = error.messages
            self.proveedor_billetera = ""
            self.numero_billetera = ""

        if self.moneda_id and not self.moneda.activa:
            errores["moneda"] = "La moneda seleccionada está deshabilitada."

        if errores:
            raise ValidationError(errores)

    def __str__(self):
        """Devuelve una etiqueta legible del destino de acreditación.

        Returns:
            str: Tipo, identificación y moneda del destino.
        """
        return f"{self.get_tipo_display()} {self.identificacion} ({self.moneda_id})"


class AccionAuditoriaDestino(models.TextChoices):
    """Define las acciones que registra la auditoría de destinos de acreditación."""
    CREACION = "CREACION", "Creación"
    MODIFICACION = "MODIFICACION", "Modificación"
    DESACTIVACION = "DESACTIVACION", "Desactivación"
    ACTIVACION = "ACTIVACION", "Activación"
    ELIMINACION = "ELIMINACION", "Eliminación"


class AuditoriaDestinoManager(models.Manager):
    """Crea registros de auditoría para las acciones sobre destinos de acreditación."""

    def registrar(self, destino, accion, realizado_por, datos_anteriores=None, datos_nuevos=None):
        """Crea un registro de auditoría para una acción sobre un destino.

        Args:
            destino (DestinoAcreditacion): Destino afectado por la acción.
            accion (str): Acción realizada, según AccionAuditoriaDestino.
            realizado_por (django.contrib.auth.models.User or None): Usuario
                que realizó la acción, o None si no pudo determinarse.
            datos_anteriores (dict or None): Datos previos a la acción, si
                corresponde.
            datos_nuevos (dict or None): Datos vigentes luego de la acción,
                si corresponde. No aplica, por ejemplo, en una eliminación.

        Returns:
            AuditoriaDestinoAcreditacion: Registro de auditoría creado.
        """
        return self.create(
            destino=destino,
            accion=accion,
            realizado_por=realizado_por,
            datos_anteriores=datos_anteriores,
            datos_nuevos=datos_nuevos,
        )


class AuditoriaDestinoAcreditacion(models.Model):
    """Registra cada alta, modificación, baja o eliminación de un destino de acreditación.

    El vínculo con ``DestinoAcreditacion`` usa ``SET_NULL`` en lugar de
    ``CASCADE`` para que, al eliminar definitivamente un destino, la fila que
    deja constancia de esa eliminación no se borre junto con él.
    """
    destino = models.ForeignKey(
        DestinoAcreditacion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="auditorias",
        verbose_name="Destino de acreditación",
    )
    accion = models.CharField(
        max_length=20,
        choices=AccionAuditoriaDestino.choices,
        verbose_name="Acción",
    )
    datos_anteriores = models.JSONField(null=True, blank=True, verbose_name="Datos anteriores")
    datos_nuevos = models.JSONField(null=True, blank=True, verbose_name="Datos nuevos")
    realizado_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="modificaciones_destinos",
        verbose_name="Realizado por",
    )
    fecha = models.DateTimeField(auto_now_add=True, verbose_name="Fecha")

    objects = AuditoriaDestinoManager()

    class Meta:
        """Define el orden y los nombres de presentación de la auditoría de destinos."""
        ordering = ["-fecha"]
        verbose_name = "Auditoría de destino de acreditación"
        verbose_name_plural = "Auditorías de destinos de acreditación"

    def __str__(self):
        """Devuelve una etiqueta legible del registro de auditoría.

        Returns:
            str: Acción realizada e identificador del destino afectado.
        """
        return f"{self.get_accion_display()} - {self.destino_id}"
