"""
Worker automatico que sincroniza registros locales con GHL cada N segundos.
Corre como thread daemon dentro del proceso web (no requiere servicio extra en Railway).
"""
import os
import time
import logging
import threading

logger = logging.getLogger(__name__)

_worker_started = False
_worker_lock = threading.Lock()

# Intervalo configurable via variable de entorno (default: 300 segundos = 5 minutos)
SYNC_INTERVAL = int(os.environ.get('SYNC_INTERVAL_SECONDS', 300))


def _sync_loop():
    """
    Loop principal del worker. Busca registros pendientes y los sincroniza con GHL.
    Corre indefinidamente como thread daemon.
    """
    # Esperar 30 segundos al arrancar para dar tiempo a que la app se inicialice
    time.sleep(30)
    logger.info(f"Sync worker iniciado. Intervalo: {SYNC_INTERVAL}s")

    while True:
        try:
            _run_sync_cycle()
        except Exception as e:
            logger.error(f"Error en ciclo de sync worker: {str(e)}", exc_info=True)

        time.sleep(SYNC_INTERVAL)


def _run_sync_cycle():
    """
    Ejecuta un ciclo de sincronizacion: busca registros pendientes y los envia a GHL.
    """
    from django.db.models import Q
    from .models import Cliente, Propiedad, Agencia
    from .utils import sync_record_to_ghl, rate_limit_wait

    sync_filter = Q(sync_status='pending') | Q(ghl_contact_id__isnull=True) | Q(ghl_contact_id='')

    # Contar pendientes
    clientes_pendientes = Cliente.objects.filter(sync_filter, agencia__active=True).count()
    propiedades_pendientes = Propiedad.objects.filter(sync_filter, agencia__active=True).count()

    if clientes_pendientes == 0 and propiedades_pendientes == 0:
        return  # Nada que hacer, sin log para no llenar los logs

    logger.info(f"Sync worker: {clientes_pendientes} clientes + {propiedades_pendientes} propiedades pendientes")

    # Sincronizar clientes
    clientes = Cliente.objects.filter(
        sync_filter, agencia__active=True
    ).select_related('agencia')[:50]

    clientes_ok = 0
    for cliente in clientes:
        if sync_record_to_ghl(cliente, 'cliente'):
            clientes_ok += 1
        rate_limit_wait(default_wait=0.3)

    # Sincronizar propiedades
    propiedades = Propiedad.objects.filter(
        sync_filter, agencia__active=True
    ).select_related('agencia', 'zona')[:50]

    propiedades_ok = 0
    for propiedad in propiedades:
        if sync_record_to_ghl(propiedad, 'propiedad'):
            propiedades_ok += 1
        rate_limit_wait(default_wait=0.3)

    logger.info(
        f"Sync worker completado: "
        f"Clientes {clientes_ok}/{clientes_pendientes} | "
        f"Propiedades {propiedades_ok}/{propiedades_pendientes}"
    )


def start_sync_loop():
    """
    Arranca el worker de sync como thread daemon.
    Solo arranca una vez (protegido con lock para gunicorn multi-worker).
    """
    global _worker_started

    with _worker_lock:
        if _worker_started:
            return
        _worker_started = True

    thread = threading.Thread(target=_sync_loop, name="ghl_sync_worker", daemon=True)
    thread.start()
    logger.info("Sync worker thread lanzado")
