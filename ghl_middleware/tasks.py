import logging
import atexit
from concurrent.futures import ThreadPoolExecutor
from .utils import ghl_associate_records, ghl_get_current_associations, ghl_delete_association, ghlActualizarZonaAPI, get_valid_token
from .models import Zona, Agencia, GHLToken


logger = logging.getLogger(__name__)

# Pool de hilos global con limite de workers
_executor = ThreadPoolExecutor(max_workers=10, thread_name_prefix="ghl_sync_")

# Registrar shutdown automatico al apagar el proceso
atexit.register(lambda: _executor.shutdown(wait=False))


def sync_associations_background(access_token, location_id, origin_record_id, target_ids_list, association_id_val, origin_is_contact=False):
    """
    Sincroniza asociaciones en background usando ThreadPoolExecutor.
    origin_is_contact=True implica que origin_record_id es el Contacto y target_ids_list son Propiedades.
    """
    def _worker_process():
        try:
            current_map = ghl_get_current_associations(access_token, location_id, origin_record_id)
            current_ids = set(current_map.keys())
            target_ids = set(target_ids_list)

            ids_to_add = target_ids - current_ids
            ids_to_remove = current_ids - target_ids

            logger.info(f"Sync {'Cliente' if origin_is_contact else 'Propiedad'} {origin_record_id}: +{len(ids_to_add)} | -{len(ids_to_remove)}")

            for target_id in ids_to_remove:
                rel_info = current_map.get(target_id)
                if rel_info and rel_info.get('id'):
                    ghl_delete_association(access_token, location_id, rel_info.get('id'))

            for target_id in ids_to_add:
                if origin_is_contact:
                    # Origin es Cliente (contact_id), Target es Propiedad (property_id)
                    ghl_associate_records(access_token, location_id, target_id, origin_record_id, association_id_val)
                else:
                    # Origin es Propiedad (property_id), Target es Cliente (contact_id)
                    ghl_associate_records(access_token, location_id, origin_record_id, target_id, association_id_val)

        except Exception as e:
            logger.error(f"Error en sync_associations para {origin_record_id}: {str(e)}", exc_info=True)

    future = _executor.submit(_worker_process)
    future.add_done_callback(lambda f: f.result() if not f.exception() else logger.error(f"Task failed: {f.exception()}"))


def funcionAsyncronaZonas():
    """
    Actualiza las zonas en GHL para todas las agencias.
    Lee los IDs de campos personalizados desde el modelo Agencia (dinamico, sin hardcodear).
    """
    def actualizacion_zonas_agencias():
        try:
            opciones_propiedad = []
            opciones_cliente = []
            for zona in Zona.objects.all():
                label = zona.nombre
                value = label.lower().strip().replace(" ", "_")
                # Los nombres de abajo han de ser así. No estan mal puestos.
                opciones_propiedad.append({
                    "key": value,
                    "label": label
                })
                opciones_cliente.append(label)

            for agencia in Agencia.objects.filter(active=True):
                location_id = agencia.location_id
                if not location_id:
                    continue

                # Saltar agencias que no tienen IDs de campos personalizados configurados
                if not agencia.ghl_custom_field_propiedad_zona or not agencia.ghl_custom_field_cliente_zona:
                    logger.warning(f"Agencia {location_id} no tiene custom field IDs de zona configurados. Saltando.")
                    continue

                try:
                    token = get_valid_token(location_id)
                    if not token:
                        logger.warning(f"No se pudo obtener token válido para agencia {location_id}")
                        continue

                    url_propiedad = f"https://services.leadconnectorhq.com/custom-fields/{agencia.ghl_custom_field_propiedad_zona}/"
                    url_cliente = f"https://services.leadconnectorhq.com/locations/{location_id}/customFields/{agencia.ghl_custom_field_cliente_zona}/"

                    ghlActualizarZonaAPI(location_id, opciones_propiedad, token, url_propiedad, True)
                    ghlActualizarZonaAPI(location_id, opciones_cliente, token, url_cliente, False)

                except Exception as e:
                    logger.error(f"Error obteniendo token para agencia {location_id}: {str(e)}")

        except Exception as e:
            logger.error(f"Error actualizando zonas: {str(e)}", exc_info=True)

    _executor.submit(actualizacion_zonas_agencias)


def shutdown_executor():
    """Cierra el pool de hilos limpiamente."""
    _executor.shutdown(wait=True)
    logger.info("ThreadPoolExecutor cerrado correctamente")
