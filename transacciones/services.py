import logging
from decimal import Decimal
from enum import StrEnum

from django.db import IntegrityError
from django.db import transaction as db_transaction
from django.utils import timezone

from cotizaciones.models import ConfiguracionComision, TasaCambio
from cotizaciones.services import (
    SimulacionConversionError,
    obtener_beneficio_categoria,
    redondear_monto,
)
from integrations.proveedores_pago import (
    MetodoPagoNoHabilitadoError,
    ProveedorPagoError,
    StripeProveedor,
    get_proveedor,
)

from .models import (
    ESTADOS_PAGO_ACTIVOS,
    ESTADOS_PAGO_FINALES,
    EstadoPago,
    EstadoTransaccion,
    Pago,
    ProveedorPago,
    TipoOperacion,
    Transaccion,
)


logger = logging.getLogger(__name__)

PYG = "PYG"
CIEN = Decimal("100")


class OperacionCambiariaError(ValueError):
    """Indica que una operación cambiaria no puede calcularse o registrarse."""
    pass


class PagoNoIniciableError(OperacionCambiariaError):
    """Indica que no puede iniciarse el pago de una transacción.

    El mensaje está pensado para mostrarse al cliente tal cual.
    """
    pass


MENSAJE_PAGO_EN_PROCESO = "Ya hay un pago en proceso para esta operación."


def obtener_tasa_vigente_compra(moneda_codigo):
    """Obtiene la tasa vigente del par entre una divisa y el guaraní.

    Solo considera tasas marcadas como vigentes cuyas dos monedas estén
    habilitadas, con el mismo criterio que utiliza el simulador de
    conversiones.

    Args:
        moneda_codigo (str): Código de la moneda extranjera de la operación.

    Returns:
        cotizaciones.models.TasaCambio: Tasa vigente del par divisa/PYG.

    Raises:
        OperacionCambiariaError: Si la moneda es el guaraní o si no existe
            una tasa vigente para el par requerido.
    """
    codigo = (moneda_codigo or "").upper()

    if codigo == PYG:
        raise OperacionCambiariaError("La operación debe involucrar una moneda extranjera.")

    tasa = (
        TasaCambio.objects.select_related("moneda_origen", "moneda_destino")
        .filter(
            moneda_origen_id=codigo,
            moneda_destino_id=PYG,
            vigente=True,
            moneda_origen__activa=True,
            moneda_destino__activa=True,
        )
        .first()
    )

    if not tasa:
        raise OperacionCambiariaError(
            "No existe una cotización vigente para la moneda seleccionada."
        )

    return tasa


def calcular_compra(cliente, moneda_codigo, monto_divisa, tasa=None):
    """Calcula los importes de una compra de divisas para un cliente.

    El cliente entrega guaraníes y recibe la moneda extranjera indicada, por
    lo que se aplica el precio de venta de la cotización vigente. Sobre el
    subtotal se descuenta el beneficio correspondiente a la categoría del
    cliente, acotado por su límite configurado, y se suma la comisión de
    compra vigente en el sistema.

    Args:
        cliente (clientes.models.Cliente): Cliente que realiza la operación.
        moneda_codigo (str): Código de la moneda extranjera a comprar.
        monto_divisa (decimal.Decimal or str or int): Cantidad de divisa que
            el cliente desea adquirir.
        tasa (cotizaciones.models.TasaCambio or None): Tasa a utilizar. Si
            se omite, se busca la vigente para el par.

    Returns:
        dict: Importes y condiciones de la operación, con las claves que
        necesita el modelo Transaccion para registrarse.

    Raises:
        OperacionCambiariaError: Si el monto no es positivo, si no hay una
            cotización vigente o si la categoría del cliente no tiene
            configuración de beneficios.
    """
    monto = Decimal(str(monto_divisa))

    if monto <= 0:
        raise OperacionCambiariaError("El monto de la operación debe ser mayor a cero.")

    if tasa is None:
        tasa = obtener_tasa_vigente_compra(moneda_codigo)

    tasa_aplicada = tasa.precio_venta
    subtotal_pyg = redondear_monto(monto * tasa_aplicada)

    try:
        configuracion = obtener_beneficio_categoria(cliente.categoria_efectiva)
    except SimulacionConversionError as error:
        raise OperacionCambiariaError(str(error)) from error

    beneficio_porcentaje = Decimal("0.00")
    limite_beneficio_pyg = Decimal("0.00")

    if configuracion:
        beneficio_porcentaje = configuracion.porcentaje_beneficio
        limite_beneficio_pyg = configuracion.limite_mensual_pyg

    # Un límite en cero desactiva el beneficio, igual que en el simulador.
    if beneficio_porcentaje == 0 or limite_beneficio_pyg == 0:
        monto_beneficiado_pyg = Decimal("0.00")
        beneficio_monto_pyg = Decimal("0.00")
    else:
        monto_beneficiado_pyg = min(subtotal_pyg, limite_beneficio_pyg)
        beneficio_monto_pyg = redondear_monto(
            monto_beneficiado_pyg * beneficio_porcentaje / CIEN
        )

    comision_porcentaje = ConfiguracionComision.obtener().porcentaje_compra
    comision_monto_pyg = redondear_monto(subtotal_pyg * comision_porcentaje / CIEN)

    total_pyg = redondear_monto(subtotal_pyg - beneficio_monto_pyg + comision_monto_pyg)

    return {
        "tipo_operacion": TipoOperacion.COMPRA,
        "moneda": tasa.moneda_origen,
        "tasa_cambio": tasa,
        "tasa_aplicada": tasa_aplicada,
        "fecha_vigencia_tasa": tasa.fecha_vigencia,
        "monto_divisa": redondear_monto(monto),
        "subtotal_pyg": subtotal_pyg,
        "categoria_aplicada": cliente.categoria_efectiva,
        "beneficio_porcentaje": beneficio_porcentaje,
        "limite_beneficio_pyg": redondear_monto(limite_beneficio_pyg),
        "monto_beneficiado_pyg": redondear_monto(monto_beneficiado_pyg),
        "beneficio_monto_pyg": beneficio_monto_pyg,
        "comision_porcentaje": comision_porcentaje,
        "comision_monto_pyg": comision_monto_pyg,
        "total_pyg": total_pyg,
    }


def crear_transaccion_compra(
    cliente,
    usuario,
    moneda_codigo,
    monto_divisa,
    destino=None,
    metodo_pago=None,
    tasa=None,
):
    """Registra una compra de divisas en estado pendiente.

    Args:
        cliente (clientes.models.Cliente): Cliente que realiza la operación.
        usuario (django.contrib.auth.models.User): Usuario que la registra.
        moneda_codigo (str): Código de la moneda extranjera a comprar.
        monto_divisa (decimal.Decimal): Cantidad de divisa a adquirir.
        destino (destinos.models.DestinoAcreditacion or None): Destino donde
            se acreditará la divisa, si el cliente ya lo eligió.
        metodo_pago (pagos.models.MetodoPago or None): Medio con el que el
            cliente abonará la operación.
        tasa (cotizaciones.models.TasaCambio or None): Cotización a aplicar.
            Si se omite, se toma la vigente para el par.

    Returns:
        Transaccion: Transacción creada en estado pendiente.

    Raises:
        OperacionCambiariaError: Si los datos de la operación no permiten
            calcularla.
        django.core.exceptions.ValidationError: Si la transacción resultante
            no supera las validaciones del modelo.
    """
    with db_transaction.atomic():
        calculo = calcular_compra(cliente, moneda_codigo, monto_divisa, tasa=tasa)
        transaccion = Transaccion(
            cliente=cliente,
            creada_por=usuario,
            destino_acreditacion=destino,
            metodo_pago=metodo_pago,
            **calculo,
        )
        transaccion.full_clean()
        transaccion.save()

    return transaccion


def obtener_tasa_vigente_venta(moneda_codigo):
    """Obtiene la tasa vigente del par entre una divisa y el guaraní para venta.

    Reutiliza la misma búsqueda que la compra: el par siempre es divisa→PYG.
    La distinción entre compra y venta se establece al seleccionar el precio
    (compra usa ``precio_venta``, venta usa ``precio_compra``).

    Args:
        moneda_codigo (str): Código de la moneda extranjera de la operación.

    Returns:
        cotizaciones.models.TasaCambio: Tasa vigente del par divisa/PYG.

    Raises:
        OperacionCambiariaError: Si la moneda es el guaraní o si no existe
            una tasa vigente para el par requerido.
    """
    return obtener_tasa_vigente_compra(moneda_codigo)


def calcular_venta(cliente, moneda_codigo, monto_divisa, tasa=None):
    """Calcula los importes de una venta de divisas para un cliente.

    El cliente entrega la moneda extranjera indicada y recibe guaraníes, por
    lo que se aplica el precio de compra de la cotización vigente. Sobre el
    subtotal se suma el beneficio correspondiente a la categoría del cliente,
    acotado por su límite configurado, y se descuenta la comisión de venta
    vigente en el sistema.

    Args:
        cliente (clientes.models.Cliente): Cliente que realiza la operación.
        moneda_codigo (str): Código de la moneda extranjera a vender.
        monto_divisa (decimal.Decimal or str or int): Cantidad de divisa que
            el cliente desea entregar.
        tasa (cotizaciones.models.TasaCambio or None): Tasa a utilizar. Si
            se omite, se busca la vigente para el par.

    Returns:
        dict: Importes y condiciones de la operación, con las claves que
        necesita el modelo Transaccion para registrarse.

    Raises:
        OperacionCambiariaError: Si el monto no es positivo, si no hay una
            cotización vigente o si la categoría del cliente no tiene
            configuración de beneficios.
    """
    monto = Decimal(str(monto_divisa))

    if monto <= 0:
        raise OperacionCambiariaError("El monto de la operación debe ser mayor a cero.")

    if tasa is None:
        tasa = obtener_tasa_vigente_venta(moneda_codigo)

    # En venta el cliente entrega divisas y recibe PYG: se aplica precio_compra.
    tasa_aplicada = tasa.precio_compra
    subtotal_pyg = redondear_monto(monto * tasa_aplicada)

    try:
        configuracion = obtener_beneficio_categoria(cliente.categoria_efectiva)
    except SimulacionConversionError as error:
        raise OperacionCambiariaError(str(error)) from error

    beneficio_porcentaje = Decimal("0.00")
    limite_beneficio_pyg = Decimal("0.00")

    if configuracion:
        beneficio_porcentaje = configuracion.porcentaje_beneficio
        limite_beneficio_pyg = configuracion.limite_mensual_pyg

    # Un límite en cero desactiva el beneficio, igual que en compra.
    if beneficio_porcentaje == 0 or limite_beneficio_pyg == 0:
        monto_beneficiado_pyg = Decimal("0.00")
        beneficio_monto_pyg = Decimal("0.00")
    else:
        monto_beneficiado_pyg = min(subtotal_pyg, limite_beneficio_pyg)
        beneficio_monto_pyg = redondear_monto(
            monto_beneficiado_pyg * beneficio_porcentaje / CIEN
        )

    # En venta: la comisión se descuenta de lo que recibe el cliente.
    comision_porcentaje = ConfiguracionComision.obtener().porcentaje_venta
    comision_monto_pyg = redondear_monto(subtotal_pyg * comision_porcentaje / CIEN)

    # Cliente recibe: subtotal + beneficio - comision
    total_pyg = redondear_monto(subtotal_pyg + beneficio_monto_pyg - comision_monto_pyg)

    return {
        "tipo_operacion": TipoOperacion.VENTA,
        "moneda": tasa.moneda_origen,
        "tasa_cambio": tasa,
        "tasa_aplicada": tasa_aplicada,
        "fecha_vigencia_tasa": tasa.fecha_vigencia,
        "monto_divisa": redondear_monto(monto),
        "subtotal_pyg": subtotal_pyg,
        "categoria_aplicada": cliente.categoria_efectiva,
        "beneficio_porcentaje": beneficio_porcentaje,
        "limite_beneficio_pyg": redondear_monto(limite_beneficio_pyg),
        "monto_beneficiado_pyg": redondear_monto(monto_beneficiado_pyg),
        "beneficio_monto_pyg": beneficio_monto_pyg,
        "comision_porcentaje": comision_porcentaje,
        "comision_monto_pyg": comision_monto_pyg,
        "total_pyg": total_pyg,
    }


def crear_transaccion_venta(
    cliente,
    usuario,
    moneda_codigo,
    monto_divisa,
    destino=None,
    metodo_pago=None,
    tasa=None,
):
    """Registra una venta de divisas en estado pendiente.

    Args:
        cliente (clientes.models.Cliente): Cliente que realiza la operación.
        usuario (django.contrib.auth.models.User): Usuario que la registra.
        moneda_codigo (str): Código de la moneda extranjera a vender.
        monto_divisa (decimal.Decimal): Cantidad de divisa que el cliente entrega.
        destino (destinos.models.DestinoAcreditacion or None): Destino donde
            se acreditará la divisa, si el cliente ya lo eligió.
        metodo_pago (pagos.models.MetodoPago or None): Medio con el que el
            cliente realizará la operación.
        tasa (cotizaciones.models.TasaCambio or None): Cotización a aplicar.
            Si se omite, se toma la vigente para el par.

    Returns:
        Transaccion: Transacción creada en estado pendiente.

    Raises:
        OperacionCambiariaError: Si los datos de la operación no permiten
            calcularla.
        django.core.exceptions.ValidationError: Si la transacción resultante
            no supera las validaciones del modelo.
    """
    with db_transaction.atomic():
        calculo = calcular_venta(cliente, moneda_codigo, monto_divisa, tasa=tasa)
        transaccion = Transaccion(
            cliente=cliente,
            creada_por=usuario,
            destino_acreditacion=destino,
            metodo_pago=metodo_pago,
            **calculo,
        )
        transaccion.full_clean()
        transaccion.save()

    return transaccion


def importe_a_cobrar(transaccion):
    """Determina el importe y la moneda que el cliente paga en una operación.

    En una compra el cliente paga el total en guaraníes; en una venta entrega
    la divisa que vende.

    Args:
        transaccion (Transaccion): Operación a pagar.

    Returns:
        tuple[decimal.Decimal, str]: Importe y código de la moneda a cobrar.
    """
    if transaccion.tipo_operacion == TipoOperacion.COMPRA:
        return transaccion.total_pyg, PYG
    return transaccion.monto_divisa, transaccion.moneda_id


def metodo_permite_pagar(transaccion):
    """Indica si el método de pago actual de la operación permite iniciar el pago.

    Aplica las mismas comprobaciones previas que ``iniciar_pago`` sin crear
    ningún pago ni contactar al proveedor.

    Args:
        transaccion (Transaccion): Operación a pagar.

    Returns:
        bool: False si la operación no tiene método, si está inactivo, si no
        es del cliente o si el proveedor no lo habilita para este importe.
    """
    metodo = transaccion.metodo_pago
    if metodo is None or not metodo.activo or metodo.cliente_id != transaccion.cliente_id:
        return False
    monto, moneda = importe_a_cobrar(transaccion)
    try:
        get_proveedor(metodo).validar(metodo, monto, moneda)
    except MetodoPagoNoHabilitadoError:
        return False
    return True


def iniciar_pago(transaccion, usuario, metodo_pago=None):
    """Inicia el pago de una transacción pendiente ante el proveedor externo.

    El proceso tiene dos fases. Primero, con la transacción bloqueada, valida
    que esté pendiente, que no tenga otro pago en curso y que su método de
    pago esté habilitado para el proveedor, y registra el pago como
    ``INICIADO``. Después, fuera de la transacción de base de datos, envía la
    solicitud al proveedor y guarda su respuesta. Iniciar el pago nunca
    modifica el estado de la transacción: la confirmación llega más tarde.

    Si se indica un método de pago distinto del de la operación (por ejemplo,
    después de que el proveedor rechazó la tarjeta), pasa a ser el método de la
    operación siempre que el pago pueda iniciarse. Los intentos anteriores
    conservan el método con el que se hicieron.

    Args:
        transaccion (Transaccion): Operación a pagar.
        usuario (django.contrib.auth.models.User): Usuario que inicia el pago.
        metodo_pago (pagos.models.MetodoPago or None): Método con el que se
            quiere pagar. Si se omite, se usa el de la operación.

    Returns:
        Pago: Pago ``EN_PROCESO`` con la referencia externa del proveedor.

    Raises:
        PagoNoIniciableError: Si la transacción no está pendiente, ya tiene
            un pago en curso, el método elegido no es un método activo del
            cliente, su método de pago no está habilitado o el proveedor
            rechazó o no pudo procesar la solicitud. En los dos últimos casos
            el pago queda registrado como ``RECHAZADO`` o ``ERROR``.
    """
    try:
        with db_transaction.atomic():
            transaccion = (
                # Solo se bloquea la transacción: PostgreSQL no admite FOR UPDATE
                # sobre el método de pago, que es el lado nulable del JOIN.
                Transaccion.objects.select_for_update(of=("self",))
                .select_related("metodo_pago")
                .get(pk=transaccion.pk)
            )
            if transaccion.estado != EstadoTransaccion.PENDIENTE:
                raise PagoNoIniciableError(
                    "Solo se pueden pagar operaciones en estado pendiente."
                )
            if transaccion.pagos.filter(estado__in=ESTADOS_PAGO_ACTIVOS).exists():
                raise PagoNoIniciableError(MENSAJE_PAGO_EN_PROCESO)

            if metodo_pago is not None and metodo_pago.pk != transaccion.metodo_pago_id:
                if not metodo_pago.activo or metodo_pago.cliente_id != transaccion.cliente_id:
                    raise PagoNoIniciableError(
                        "El método de pago seleccionado no está disponible."
                    )
                transaccion.metodo_pago = metodo_pago
                transaccion.save(update_fields=["metodo_pago", "actualizada_en"])

            metodo = transaccion.metodo_pago
            if metodo is None or not metodo.activo or metodo.cliente_id != transaccion.cliente_id:
                raise PagoNoIniciableError(
                    "La operación no tiene un método de pago activo para realizar el pago."
                )

            monto, moneda = importe_a_cobrar(transaccion)
            try:
                proveedor = get_proveedor(metodo)
                proveedor.validar(metodo, monto, moneda)
            except MetodoPagoNoHabilitadoError as error:
                raise PagoNoIniciableError(str(error)) from error

            pago = Pago.objects.create(
                transaccion=transaccion,
                metodo_pago=metodo,
                proveedor=proveedor.codigo,
                monto=proveedor.monto_a_cobrar(monto, moneda),
                moneda_id=moneda,
                iniciado_por=usuario,
            )
    except IntegrityError as error:
        # Otra solicitud registró un pago activo en paralelo.
        raise PagoNoIniciableError(MENSAJE_PAGO_EN_PROCESO) from error

    try:
        resultado = proveedor.iniciar_pago(pago)
    except ProveedorPagoError as error:
        _registrar_respuesta_inicio(
            pago,
            estado=EstadoPago.RECHAZADO if error.rechazado else EstadoPago.ERROR,
            referencia_externa=error.referencia_externa or None,
            mensaje_proveedor=error.detalle or error.mensaje_usuario,
        )
        raise PagoNoIniciableError(error.mensaje_usuario) from error

    _registrar_respuesta_inicio(
        pago,
        estado=EstadoPago.EN_PROCESO,
        referencia_externa=resultado.referencia_externa,
    )
    return pago


def _registrar_respuesta_inicio(pago, **campos):
    """Guarda la respuesta del proveedor al iniciar un pago, si nadie la resolvió antes.

    La confirmación del proveedor puede llegar (por webhook) antes de que
    termine la llamada que inició el pago. Por eso la respuesta solo se
    guarda si el pago sigue ``INICIADO``: nunca pisa un resultado definitivo.
    En cualquier caso, ``pago`` queda actualizado con el estado de la base.

    Args:
        pago (Pago): Pago recién enviado al proveedor.
        **campos: Valores a guardar (estado, referencia y mensaje).
    """
    campos["actualizado_en"] = timezone.now()
    Pago.objects.filter(pk=pago.pk, estado=EstadoPago.INICIADO).update(**campos)
    pago.refresh_from_db()


class ResultadoProcesamiento(StrEnum):
    """Indica qué hizo el sistema con un resultado informado por un proveedor."""

    CONFIRMADO = "CONFIRMADO"
    """El pago se confirmó (y la operación pendiente se completó)."""
    RECHAZADO = "RECHAZADO"
    """El pago se registró como rechazado; la operación sigue pendiente."""
    DUPLICADO = "DUPLICADO"
    """El pago ya tenía un resultado definitivo; no se modificó nada."""
    IGNORADO = "IGNORADO"
    """No existe un pago del sistema con esos datos."""
    INVALIDO = "INVALIDO"
    """Los datos no coinciden con el pago registrado; no se modificó nada."""


ESTADOS_PAGO_RESOLUBLES = (EstadoPago.INICIADO, EstadoPago.EN_PROCESO, EstadoPago.ERROR)
"""tuple[str, ...]: Estados de un pago que todavía aceptan un resultado del proveedor.

``ERROR`` se incluye porque un fallo de comunicación de nuestro lado no
impide que el proveedor haya cobrado el pago.
"""


def _buscar_pago(proveedor_codigo, resultado):
    """Encuentra el pago al que se refiere un resultado del proveedor.

    Prioriza el ``id_pago`` que el sistema envió al iniciar el cobro, porque
    sigue funcionando aunque la referencia todavía no se haya guardado.
    """
    pagos = Pago.objects.filter(proveedor=proveedor_codigo)
    if resultado.id_pago is not None:
        return pagos.filter(pk=resultado.id_pago).first()
    if resultado.referencia_externa:
        return pagos.filter(referencia_externa=resultado.referencia_externa).first()
    return None


def procesar_resultado_pago(proveedor_codigo, resultado):
    """Aplica el resultado de un pago informado por el proveedor, una sola vez.

    Es el único punto donde se confirma o se rechaza un pago: lo usan el
    webhook de Stripe, el simulador de billetera y el comando
    ``sincronizar_pagos``. Antes de aplicar el resultado comprueba que la
    referencia, el importe y la moneda coincidan con el pago registrado.

    Si el pago fue aprobado, queda ``CONFIRMADO`` con la fecha de
    confirmación y la transacción pendiente pasa a ``COMPLETADA`` con esa
    misma fecha. Si fue rechazado, queda ``RECHAZADO`` y la transacción no
    cambia. Un pago que ya tiene un resultado definitivo no se modifica, por
    lo que una notificación repetida no completa dos veces la operación.

    Args:
        proveedor_codigo (str): Valor de ``ProveedorPago`` del proveedor que
            informa el resultado.
        resultado (integrations.proveedores_pago.ResultadoPago): Resultado
            ya validado por el proveedor.

    Returns:
        ResultadoProcesamiento: Qué se hizo con el resultado.
    """
    pago = _buscar_pago(proveedor_codigo, resultado)
    if pago is None:
        logger.info(
            "Resultado de pago ignorado: no existe un pago de %s con id %s ni referencia %s.",
            proveedor_codigo, resultado.id_pago, resultado.referencia_externa,
        )
        return ResultadoProcesamiento.IGNORADO

    with db_transaction.atomic():
        # Mismo orden de bloqueo que iniciar_pago: primero la operación, después el pago.
        transaccion = Transaccion.objects.select_for_update().get(pk=pago.transaccion_id)
        pago = Pago.objects.select_for_update().get(pk=pago.pk)

        if pago.referencia_externa and pago.referencia_externa != resultado.referencia_externa:
            logger.warning(
                "Resultado de pago inválido: el pago %s tiene la referencia %s y se recibió %s.",
                pago.pk, pago.referencia_externa, resultado.referencia_externa,
            )
            return ResultadoProcesamiento.INVALIDO
        if (resultado.monto is not None and resultado.monto != pago.monto) or (
            resultado.moneda is not None and resultado.moneda != pago.moneda_id
        ):
            logger.warning(
                "Resultado de pago inválido: el pago %s es de %s %s y se informó %s %s.",
                pago.pk, pago.monto, pago.moneda_id, resultado.monto, resultado.moneda,
            )
            return ResultadoProcesamiento.INVALIDO
        if pago.estado in ESTADOS_PAGO_FINALES:
            logger.info("Resultado repetido para el pago %s (%s): sin cambios.", pago.pk, pago.estado)
            return ResultadoProcesamiento.DUPLICADO

        campos = ["estado", "mensaje_proveedor", "actualizado_en"]
        if not pago.referencia_externa:
            pago.referencia_externa = resultado.referencia_externa
            campos.append("referencia_externa")

        if not resultado.aprobado:
            pago.estado = EstadoPago.RECHAZADO
            pago.mensaje_proveedor = resultado.detalle or "El proveedor rechazó el pago."
            pago.save(update_fields=campos)
            return ResultadoProcesamiento.RECHAZADO

        ahora = timezone.now()
        pago.estado = EstadoPago.CONFIRMADO
        pago.confirmado_en = ahora
        pago.mensaje_proveedor = ""
        if transaccion.estado == EstadoTransaccion.PENDIENTE:
            transaccion.estado = EstadoTransaccion.COMPLETADA
            transaccion.completada_en = ahora
            transaccion.save(update_fields=["estado", "completada_en", "actualizada_en"])
        else:
            pago.mensaje_proveedor = (
                f"Pago confirmado sobre una operación {transaccion.get_estado_display().lower()}: "
                "requiere revisión."
            )
            logger.warning(
                "El pago %s se confirmó pero la operación %s está %s.",
                pago.pk, transaccion.pk, transaccion.estado,
            )
        pago.save(update_fields=campos + ["confirmado_en"])
        return ResultadoProcesamiento.CONFIRMADO


def sincronizar_pagos_stripe(id_pago=None):
    """Consulta a Stripe el resultado de los pagos que siguen sin confirmar.

    Es el respaldo del webhook: sirve cuando la notificación no llegó (por
    ejemplo, en desarrollo sin la Stripe CLI). Cada resultado obtenido se
    aplica con ``procesar_resultado_pago``, igual que si viniera del webhook.

    Args:
        id_pago (int or None): Si se indica, solo se consulta ese pago.

    Returns:
        dict[str, int]: Cantidad de pagos ``consultados``, ``confirmados``,
        ``rechazados``, ``sin_cambios`` (Stripe todavía no tiene un
        resultado, o el pago ya estaba resuelto) y ``errores`` de
        comunicación.
    """
    pagos = Pago.objects.filter(
        proveedor=ProveedorPago.STRIPE,
        estado__in=ESTADOS_PAGO_RESOLUBLES,
        referencia_externa__isnull=False,
    ).order_by("creado_en")
    if id_pago is not None:
        pagos = pagos.filter(pk=id_pago)

    resumen = {"consultados": 0, "confirmados": 0, "rechazados": 0, "sin_cambios": 0, "errores": 0}
    proveedor = StripeProveedor()
    for pago in pagos:
        resumen["consultados"] += 1
        try:
            resultado = proveedor.consultar_pago(pago)
        except ProveedorPagoError as error:
            logger.warning("No se pudo consultar el pago %s en Stripe: %s", pago.pk, error.detalle)
            resumen["errores"] += 1
            continue

        if resultado is None:
            resumen["sin_cambios"] += 1
            continue

        procesamiento = procesar_resultado_pago(pago.proveedor, resultado)
        if procesamiento == ResultadoProcesamiento.CONFIRMADO:
            resumen["confirmados"] += 1
        elif procesamiento == ResultadoProcesamiento.RECHAZADO:
            resumen["rechazados"] += 1
        else:
            resumen["sin_cambios"] += 1
    return resumen
