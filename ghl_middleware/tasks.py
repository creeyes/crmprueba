import threading
import logging
from .utils import ghl_associate_records, ghl_get_current_associations, ghl_delete_association, ghlActualizarZonaAPI
from .models import Zona, Agencia, GHLToken


logger = logging.getLogger(__name__)

# MODIFICADO: Se añade 'association_id_val' a los argumentos
def sync_associations_background(access_token, location_id, origin_record_id, target_ids_list, association_id_val, association_type="contact"):
    
    def _worker_process():
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
            # MODIFICADO: Se pasa el ID dinámico a la función de utilidad
            ghl_associate_records(access_token, location_id, origin_record_id, contact_id, association_id_val)

    task_thread = threading.Thread(target=_worker_process)
    task_thread.start()

def funcionAsyncronaZonas():
    def actualizacionZonasAgencias():
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
        idPropiedad = ["hS4cEeTEOSITPlkOyYx5","otsVf8GDT9QyqTeVbNs5"]
        idCliente = ["kAMWAxQudbtRtEWWL4eE","dTS9Cyfwu7pbK28roBMK"]

        for i, agencia in enumerate(Agencia.objects.all()):
            locationId = agencia.location_id
            if locationId:
                token = GHLToken.objects.get(location_id = locationId).access_token
                urlPropiedad = f"https://services.leadconnectorhq.com/custom-fields/{idPropiedad[i]}/"
                urlCliente = f"https://services.leadconnectorhq.com/locations/{locationId}/customFields/{idCliente[i]}/"
                ghlActualizarZonaAPI(locationId, opcionesPropiedad, token, urlPropiedad, True)
                ghlActualizarZonaAPI(locationId, opcionesCliente, token, urlCliente, False)
            else:
                print("No existe location ID. Por lo que se presupone que no existe la agencia")

    task_thread = threading.Thread(target=actualizacionZonasAgencias)
    task_thread.start()