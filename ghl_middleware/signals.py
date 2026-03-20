import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Cliente, Propiedad

logger = logging.getLogger(__name__)

# Campos internos del sistema de sync: un save que solo toca estos campos NO debe
# relanzar el sync (evita bucle infinito).
_INTERNAL_SYNC_FIELDS = {'sync_status', 'sync_error', 'ghl_contact_id'}


@receiver(post_save, sender=Cliente)
def sync_cliente_to_ghl(sender, instance, created, **kwargs):
    """
    Sincroniza Clientes a GHL cuando se crean o actualizan via ORM (admin, API, shell).
    No se dispara para inserciones SQL directas.
    - CREATE: si no tiene ghl_contact_id y sync_status='pending'
    - UPDATE: si ya tiene ghl_contact_id y no es un registro nuevo
    """
    # Ignorar saves internos del sistema de sync (evita bucle infinito)
    update_fields = kwargs.get('update_fields')
    if update_fields and set(update_fields) <= _INTERNAL_SYNC_FIELDS:
        return

    from .tasks import sync_to_ghl_background

    if not instance.ghl_contact_id and instance.sync_status == 'pending':
        # CREATE: no existe aún en GHL
        logger.info(f"Signal: Cliente PK={instance.pk} sin ghl_contact_id, lanzando sync CREATE background")
        sync_to_ghl_background(instance.pk, 'cliente', created=True)

    elif not created and instance.ghl_contact_id:
        # UPDATE: ya existe en GHL, hay que actualizar
        logger.info(f"Signal: Cliente PK={instance.pk} actualizado, lanzando sync UPDATE background")
        sync_to_ghl_background(instance.pk, 'cliente', created=False)


@receiver(post_save, sender=Propiedad)
def sync_propiedad_to_ghl(sender, instance, created, **kwargs):
    """
    Sincroniza Propiedades a GHL cuando se crean o actualizan via ORM (admin, API, shell).
    No se dispara para inserciones SQL directas.
    - CREATE: si no tiene ghl_contact_id y sync_status='pending'
    - UPDATE: si ya tiene ghl_contact_id y no es un registro nuevo
    """
    # Ignorar saves internos del sistema de sync (evita bucle infinito)
    update_fields = kwargs.get('update_fields')
    if update_fields and set(update_fields) <= _INTERNAL_SYNC_FIELDS:
        return

    from .tasks import sync_to_ghl_background

    if not instance.ghl_contact_id and instance.sync_status == 'pending':
        # CREATE: no existe aún en GHL
        logger.info(f"Signal: Propiedad PK={instance.pk} sin ghl_contact_id, lanzando sync CREATE background")
        sync_to_ghl_background(instance.pk, 'propiedad', created=True)

    elif not created and instance.ghl_contact_id:
        # UPDATE: ya existe en GHL, hay que actualizar
        logger.info(f"Signal: Propiedad PK={instance.pk} actualizada, lanzando sync UPDATE background")
        sync_to_ghl_background(instance.pk, 'propiedad', created=False)
