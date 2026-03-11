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
    Ejecuta un ciclo de sincronizacion con candados de BD (Database Locking).
    Preparado para multiples workers concurrentes (Enterprise).
    """
    from django.db.models import Q
    from django.db import transaction  # <-- Importamos el control de transacciones
    from .models import Cliente, Propiedad
    from .utils import sync_record_to_ghl, rate_limit_wait

    sync_filter = Q(sync_status='pending') | Q(ghl_contact_id__isnull=True) | Q(ghl_contact_id='')

    # Contar pendientes para los logs (esto no bloquea la base de datos)
    clientes_pendientes = Cliente.objects.filter(sync_filter, agencia__active=True).count()
    propiedades_pendientes = Propiedad.objects.filter(sync_filter, agencia__active=True).count()

    if clientes_pendientes == 0 and propiedades_pendientes == 0:
        return  # Nada que hacer

    logger.info(f"Sync worker detectó: {clientes_pendientes} clientes y {propiedades_pendientes} propiedades pendientes")

    # --- 1. PROCESAR CLIENTES CON CANDADO (LOCK) ---
    cliente_ids_to_process = []
    
    # Abrimos una transacción rápida para poner el candado
    with transaction.atomic():
        # skip_locked=True es la magia: ignora los que otro worker ya haya agarrado
        clientes_locked = Cliente.objects.select_for_update(skip_locked=True).filter(
            sync_filter, agencia__active=True
        )[:50]
        
        for c in clientes_locked:
            cliente_ids_to_process.append(c.pk)
        
        # Los marcamos rapidísimo como 'syncing' para liberar la BD
        if cliente_ids_to_process:
            Cliente.objects.filter(pk__in=cliente_ids_to_process).update(sync_status='syncing')

    # Ahora los enviamos a GHL con calma, fuera del candado de la BD para no saturar
    clientes_ok = 0
    if cliente_ids_to_process:
        clientes = Cliente.objects.filter(pk__in=cliente_ids_to_process).select_related('agencia')
        for cliente in clientes:
            if sync_record_to_ghl(cliente, 'cliente'):
                clientes_ok += 1
            rate_limit_wait(default_wait=0.3)

    # --- 2. PROCESAR PROPIEDADES CON CANDADO (LOCK) ---
    propiedad_ids_to_process = []
    
    with transaction.atomic():
        propiedades_locked = Propiedad.objects.select_for_update(skip_locked=True).filter(
            sync_filter, agencia__active=True
        )[:50]
        
        for p in propiedades_locked:
            propiedad_ids_to_process.append(p.pk)
        
        if propiedad_ids_to_process:
            Propiedad.objects.filter(pk__in=propiedad_ids_to_process).update(sync_status='syncing')

    propiedades_ok = 0
    if propiedad_ids_to_process:
        propiedades = Propiedad.objects.filter(pk__in=propiedad_ids_to_process).select_related('agencia', 'zona')
        for propiedad in propiedades:
            if sync_record_to_ghl(propiedad, 'propiedad'):
                propiedades_ok += 1
            rate_limit_wait(default_wait=0.3)

    # Log de resumen solo si realmente se procesó algo
    if cliente_ids_to_process or propiedad_ids_to_process:
        logger.info(
            f"Sync worker completado: "
            f"Clientes {clientes_ok}/{len(cliente_ids_to_process)} | "
            f"Propiedades {propiedades_ok}/{len(propiedad_ids_to_process)}"
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

