# ghl_middleware/tasks.py
"""
CORRECCIÓN #17: Implementado ThreadPoolExecutor con max_workers para limitar
la cantidad de hilos concurrentes y evitar sobrecarga del sistema.
"""
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from .utils import ghl_associate_records, ghl_get_current_associations, ghl_delete_association, ghlActualizarZonaAPI
from .models import Zona, Agencia, GHLToken


logger = logging.getLogger(__name__)

# CORRECCIÓN #17: Pool de hilos global con límite de workers
# Esto evita crear hilos infinitos si llegan muchos webhooks simultáneos
_executor = ThreadPoolExecutor(max_workers=10, thread_name_prefix="ghl_sync_")


def sync_associations_background(access_token, location_id, origin_record_id, target_ids_list, association_id_val, association_type="contact"):
    """
    Sincroniza asociaciones en background usando ThreadPoolExecutor.
    CORRECCIÓN #17: Ya no crea hilos ilimitados, usa el pool global.
    """
    def _worker_process():
        try:
            # 1. Obtener estado actual
            current_map = ghl_get_current_associations(access_token, location_id, origin_record_id)
            current_ids = set(current_map.keys()) 
            target_ids = set(target_ids_list)
            
            # 2. Calcular diferencias
            ids_to_add = target_ids - current_ids
            ids_to_remove = current_ids - target_ids

            logger.info(f"🔄 Sync Propiedad {origin_record_id}: +{len(ids_to_add)} | -{len(ids_to_remove)}")

            # 3. Borrar excedentes
            for contact_id in ids_to_remove:
                rel_info = current_map.get(contact_id)
                if rel_info and rel_info.get('id'):
                    ghl_delete_association(access_token, location_id, rel_info.get('id'))

            # 4. Añadir faltantes
            for contact_id in ids_to_add:
                ghl_associate_records(access_token, location_id, origin_record_id, contact_id, association_id_val)
                
        except Exception as e:
            logger.error(f"❌ Error en sync_associations para {origin_record_id}: {str(e)}", exc_info=True)

    # Enviar tarea al pool en vez de crear un hilo nuevo
    future = _executor.submit(_worker_process)
    # Opcional: callback para loguear errores
    future.add_done_callback(lambda f: f.result() if not f.exception() else logger.error(f"Task failed: {f.exception()}"))


def funcionAsyncronaZonas():
    """
    Actualiza las zonas en GHL para todas las agencias.
    CORRECCIÓN #17: Usa ThreadPoolExecutor en vez de threading.Thread.
    """
    def actualizacionZonasAgencias():
        try:
            opcionesPropiedad = []
            opcionesCliente = []
            for zona in Zona.objects.all():
                label = zona.nombre             
                value = label.lower().strip().replace(" ", "_")
                
                opcionesPropiedad.append({
                    "label": label,
                    "value": value
                })
                opcionesCliente.append(label)

            # Estos dos de momento están hardcodeados, pero luego se ha de cambiar para que sea automatico y lo lea por agencia
            idPropiedad = ["hS4cEeTEOSITPlkOyYx5", "otsVf8GDT9QyqTeVbNs5"]
            idCliente = ["kAMWAxQudbtRtEWWL4eE", "dTS9Cyfwu7pbK28roBMK"]

            for i, agencia in enumerate(Agencia.objects.all()):
                locationId = agencia.location_id
                if locationId:
                    try:
                        token = GHLToken.objects.get(location_id=locationId).access_token
                        # Validar que el índice existe antes de usar
                        if i < len(idPropiedad):
                            urlPropiedad = f"https://services.leadconnectorhq.com/custom-fields/{idPropiedad[i]}/"
                            urlCliente = f"https://services.leadconnectorhq.com/locations/{locationId}/customFields/{idCliente[i]}/"
                            ghlActualizarZonaAPI(locationId, opcionesPropiedad, token, urlPropiedad, True)
                            ghlActualizarZonaAPI(locationId, opcionesCliente, token, urlCliente, False)
                        else:
                            logger.warning(f"⚠️ Índice {i} fuera de rango para IDs de campos personalizados")
                    except GHLToken.DoesNotExist:
                        logger.warning(f"⚠️ No existe token para agencia {locationId}")
                else:
                    logger.warning("No existe location ID. Por lo que se presupone que no existe la agencia")
                    
        except Exception as e:
            logger.error(f"❌ Error actualizando zonas: {str(e)}", exc_info=True)

    # Usar el pool de hilos global
    _executor.submit(actualizacionZonasAgencias)


def shutdown_executor():
    """
    Función para cerrar el pool de hilos limpiamente al apagar el servidor.
    Llamar desde AppConfig.ready() o al cerrar Django.
    """
    _executor.shutdown(wait=True)
    logger.info("🛑 ThreadPoolExecutor cerrado correctamente")
