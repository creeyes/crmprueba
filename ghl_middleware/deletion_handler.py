import logging
from .models import Cliente, Propiedad

logger = logging.getLogger(__name__)

def process_delete_request(data):
    """
    Procesa la solicitud de borrado basandose en el tipo de dato.
    Retorna True si se proceso un borrado, False si se ignoro.
    """
    record_type = data.get('type')
    
    if record_type == 'ContactDelete':
        return _handle_client_delete(data)
    
    # Verificacion estricta para Propiedades: type='RecordDelete' AND objectKey='custom_objects.propiedades'
    elif record_type == 'RecordDelete' and data.get('objectKey') == 'custom_objects.propiedades':
        return _handle_property_delete(data)
    
    else:
        logger.warning(f"Solicitud de borrado ignorada. Type: {record_type}, ObjectKey: {data.get('objectKey')}")
        return False

def _handle_client_delete(data):
    ghl_id = data.get('id')
    if not ghl_id:
        logger.error("Intento de borrar Cliente sin ID")
        return False

    try:
        cliente = Cliente.objects.filter(ghl_contact_id=ghl_id).first()
        if cliente:
            cliente.delete()
            logger.info(f"Cliente {ghl_id} borrado correctamente (y sus asociaciones).")
            return True
        else:
            logger.info(f"Cliente {ghl_id} no encontrado en BBDD local. Nada que borrar.")
            return True # Consideramos exito aunque no exista
    except Exception as e:
        logger.error(f"Error borrando Cliente {ghl_id}: {str(e)}", exc_info=True)
        return False

def _handle_property_delete(data):
    ghl_id = data.get('id')
    if not ghl_id:
        logger.error("Intento de borrar Propiedad sin ID")
        return False

    try:
        propiedad = Propiedad.objects.filter(ghl_contact_id=ghl_id).first()
        if propiedad:
            propiedad.delete()
            logger.info(f"Propiedad {ghl_id} borrada correctamente (y sus asociaciones).")
            return True
        else:
            logger.info(f"Propiedad {ghl_id} no encontrado en BBDD local. Nada que borrar.")
            return True
    except Exception as e:
        logger.error(f"Error borrando Propiedad {ghl_id}: {str(e)}", exc_info=True)
        return False
