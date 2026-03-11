import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Cliente, Propiedad

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Cliente)
def sync_cliente_to_ghl(sender, instance, created, **kwargs):
    """
    Sincroniza nuevos Clientes a GHL cuando se crean sin ghl_contact_id.
    Solo se dispara para saves via ORM (admin, API, shell).
    No se dispara para inserciones SQL directas.
    """
    if not instance.ghl_contact_id and instance.sync_status == 'pending':
        from .tasks import sync_to_ghl_background
        logger.info(f"Signal: Cliente PK={instance.pk} sin ghl_contact_id, lanzando sync background")
        sync_to_ghl_background(instance.pk, 'cliente')


@receiver(post_save, sender=Propiedad)
def sync_propiedad_to_ghl(sender, instance, created, **kwargs):
    """
    Sincroniza nuevas Propiedades a GHL cuando se crean sin ghl_contact_id.
    Solo se dispara para saves via ORM (admin, API, shell).
    No se dispara para inserciones SQL directas.
    """
    if not instance.ghl_contact_id and instance.sync_status == 'pending':
        from .tasks import sync_to_ghl_background
        logger.info(f"Signal: Propiedad PK={instance.pk} sin ghl_contact_id, lanzando sync background")
        sync_to_ghl_background(instance.pk, 'propiedad')
