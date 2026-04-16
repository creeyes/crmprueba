import logging
import hmac
import hashlib
import requests
from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework import status
from django.db.models import Q
from django.db import transaction

from .models import Agencia, Propiedad, Cliente, GHLToken, Provincia, Municipio, Zona
from .tasks import sync_associations_background, funcionAsyncronaZonas
from .utils import (
    get_valid_token, get_association_type_id, initialize_ghl_setup, 
    get_location_name, _recent_syncs, 
    ghl_delete_property_record, ghl_delete_contact
)
from .helpers import (
    clean_currency, clean_int, preferenciasTraductor1,
    preferenciasTraductor2, estadoPropTrad, guardadorURL,
    parse_zona_nombres, parse_property_data
)
from .matching import (
    buscar_clientes_para_propiedad, buscar_propiedades_para_cliente,
    actualizar_relaciones_propiedad, actualizar_relaciones_cliente
)
from .ImgCloudinary import upload_img_model, eliminar_recurso_cloudinary, extraer_public_id

logger = logging.getLogger(__name__)


def verify_webhook_signature(request):
    """
    Verifica la firma HMAC del webhook de GHL.
    Si GHL_WEBHOOK_SECRET no esta configurado, se salta la verificacion (desarrollo).
    """
    secret = settings.GHL_WEBHOOK_SECRET
    if not secret:
        return True

    signature = request.headers.get('X-GHL-Signature', '')
    if not signature:
        logger.warning("Webhook recibido sin cabecera X-GHL-Signature")
        return False

    expected = hmac.new(
        secret.encode('utf-8'),
        request.body,
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(signature, expected)


# --- HEALTH CHECK ---
class HomeView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        from django.db import connection

        health_status = {
            "status": "healthy",
            "message": "Server is running",
            "checks": {}
        }

        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            health_status["checks"]["database"] = "connected"
        except Exception as e:
            health_status["status"] = "unhealthy"
            health_status["checks"]["database"] = "disconnected"
            logger.error(f"Health check DB failed: {str(e)}")

        status_code = 200 if health_status["status"] == "healthy" else 503
        return Response(health_status, status=status_code)


# -------------------------------------------------------------------------
# VISTA 1: OAUTH CALLBACK
# -------------------------------------------------------------------------
class GHLOAuthCallbackView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        code = request.query_params.get('code')
        if not code:
            return Response({"error": "No code provided"}, status=400)

        token_url = "https://services.leadconnectorhq.com/oauth/token"
        data = {
            'client_id': settings.GHL_CLIENT_ID,
            'client_secret': settings.GHL_CLIENT_SECRET,
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': settings.GHL_REDIRECT_URI,
        }

        try:
            response = requests.post(token_url, data=data, timeout=15)
            tokens = response.json()

            if response.status_code == 200:
                with transaction.atomic():
                    location_id = tokens.get('locationId')
                    access_token = tokens['access_token']

                    GHLToken.objects.update_or_create(
                        location_id=location_id,
                        defaults={
                            'access_token': access_token,
                            'refresh_token': tokens['refresh_token'],
                            'token_type': tokens['token_type'],
                            'expires_in': tokens['expires_in'],
                            'scope': tokens['scope']
                        }
                    )

                    agencia, created = Agencia.objects.get_or_create(
                        location_id=location_id, defaults={'active': True}
                    )

                    # Obtener y guardar el nombre de la agencia desde GHL API
                    try:
                        location_name = get_location_name(access_token, location_id)
                        if location_name:
                            agencia.nombre = location_name
                            agencia.save()
                            logger.info(f"Nombre de agencia guardado: {location_name}")
                        else:
                            logger.warning(f"No se pudo obtener el nombre de la agencia para {location_id}")
                    except Exception as name_error:
                        logger.error(f"Error obteniendo nombre de agencia: {str(name_error)}", exc_info=True)
                        # Continuar incluso si falla (no es crítico)


                    logger.info(f"Iniciando Setup Wizard para {location_id}...")
                    # Ejecutamos el setup completo (busqueda de IDs, creacion de dummies, etc.)
                    # Esto actualiza la instancia 'agencia' internamente.
                    setup_success = initialize_ghl_setup(access_token, location_id, agencia)

                    if setup_success:
                        logger.info(f"Setup completado para {location_id}.")
                    else:
                        logger.warning(f"Setup finalizado con advertencias para {location_id}. Revisar logs.")

                return Response({"message": "App instalada y configurada.", "location_id": location_id}, status=200)

            logger.error(f"Error OAuth GHL Respuesta: {tokens}")
            return Response({"error": "Fallo en la autenticacion con GHL."}, status=400)

        except Exception as e:
            logger.error(f"Excepcion critica en OAuth: {str(e)}", exc_info=True)
            return Response(
                {"error": "Ha ocurrido un error interno durante la instalacion."},
                status=500
            )





# -------------------------------------------------------------------------
# VISTA 3: WEBHOOK CLIENTE
# -------------------------------------------------------------------------
class WebhookClienteView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        if not verify_webhook_signature(request):
            return Response({'error': 'Invalid signature'}, status=403)

        try:
            data = request.data
            logger.info(f"Webhook Cliente recibido: {data}")

            custom_data = data.get('customData', {})
            location_data = data.get('location', {})
            location_id = location_data.get('id') or custom_data.get('location_id')

            if not location_id:
                return Response({'error': 'Missing location_id'}, status=400)

            agencia = get_object_or_404(Agencia, location_id=location_id)
            ghl_contact_id = data.get('id') or custom_data.get('contact_id')
            if not ghl_contact_id:
                return Response({'error': 'Missing Contact ID'}, status=400)

            # Bounce-back prevention: si nosotros creamos este contacto, ignorar webhook
            if _recent_syncs.check_and_remove(ghl_contact_id):
                logger.info(f"Bounce-back webhook detectado para Cliente {ghl_contact_id}. Ignorando.")
                return Response({'status': 'bounce_back'})

            with transaction.atomic():
                # Fix: Capturar las propiedades con las que coincidia ANTES de actualizar
                # Para saber cuales hay que actualizar si deja de coincidir.
                cliente_existente = Cliente.objects.filter(ghl_contact_id=ghl_contact_id, agencia=agencia).first()
                if cliente_existente:
                     old_matched_ids = list(cliente_existente.propiedades_interes.values_list('id', flat=True))
                else:
                     old_matched_ids = []

                cliente_data = {
                    'agencia': agencia,
                    'ghl_contact_id': ghl_contact_id,
                    'nombre': custom_data.get('full_name'),
                    'presupuesto_maximo': clean_currency(custom_data.get('presupuesto') or data.get('presupuesto')),
                    'habitaciones_minimas': clean_int(custom_data.get('habitaciones') or data.get('habitaciones_min')),
                    'animales': preferenciasTraductor1(custom_data.get('animales')),
                    'metrosMinimo': clean_int(custom_data.get('metros')),
                    'balcon': preferenciasTraductor2(custom_data.get('balcon')),
                    'garaje': preferenciasTraductor2(custom_data.get('garaje')),
                    'patioInterior': preferenciasTraductor2(custom_data.get('patioInterior')),
                }

                cliente, created = Cliente.objects.update_or_create(
                    agencia=agencia,
                    ghl_contact_id=ghl_contact_id,
                    defaults=cliente_data
                )

                zona_nombre = custom_data.get("zona_interes")
                if zona_nombre:
                    if isinstance(zona_nombre, list):
                        zona_lista_bruta = [str(z).strip() for z in zona_nombre]
                    else:
                        zona_lista_bruta = [z.strip() for z in str(zona_nombre).split(",")]
                        
                    zona_lista = []
                    for z in zona_lista_bruta:
                        z_nombre = z.split("--")[0].strip()
                        if z_nombre:
                            zona_lista.append(z_nombre)

                    logger.debug(f"Procesando zonas de interes para {ghl_contact_id}: {zona_lista}")

                    zonas = Zona.objects.filter(nombre__in=zona_lista)
                    cliente.zona_interes.set(zonas)
                    cliente.save()

                propiedades_match = buscar_propiedades_para_cliente(cliente, agencia)
                matches_count = actualizar_relaciones_cliente(cliente, propiedades_match)
                logger.info(f"Matches encontrados para {cliente.ghl_contact_id}: {matches_count}")

            # Sincronizacion con GHL (fuera de la transaccion)
            # Sincronizacion con GHL (fuera de la transaccion)
            if not agencia.association_type_id:
                logger.warning(f"Agencia {location_id} no tiene 'association_type_id'. Cruzado saltado.")
                return Response({'status': 'warning', 'msg': 'Falta Association ID', 'matches_found': matches_count})

            access_token = get_valid_token(location_id)

            if access_token:
                # El objetivo es que este Cliente este asociado con ESTAS propiedades.
                # Cualquier otra asociacion sera borrada por sync_associations_background.
                target_prop_ids = [p.ghl_contact_id for p in propiedades_match]

                sync_associations_background(
                    access_token=access_token,
                    location_id=location_id,
                    origin_record_id=cliente.ghl_contact_id,
                    target_ids_list=target_prop_ids,
                    association_id_val=agencia.association_type_id,
                    origin_is_contact=True  # IMPORTANTE: Indica que origin es Cliente
                )
            else:
                logger.warning(f"No valid token found for {location_id}")

            return Response({'status': 'success', 'matches_found': matches_count})

        except Exception as e:
            logger.error(f"Error en Webhook Cliente: {str(e)}", exc_info=True)
            return Response({"error": "Error interno procesando cliente"}, status=500)


# -------------------------------------------------------------------------
# ENDPOINTS AUXILIARES
# -------------------------------------------------------------------------
class ZonasTreeView(APIView):
    """Endpoint para obtener el arbol de zonas."""
    permission_classes = [AllowAny]

    def get(self, request):
        try:
            provincias = Provincia.objects.prefetch_related('municipios__zonas').all()
            arbol = []
            for p in provincias:
                municipios_p = []
                for m in p.municipios.all():
                    municipios_p.append({
                        "nombre": m.nombre,
                        "zonas": list(m.zonas.values_list('nombre', flat=True))
                    })
                arbol.append({
                    "provincia": p.nombre,
                    "municipios": municipios_p
                })
            return Response({"zonas": arbol})
        except Exception as e:
            logger.error(f"Error obteniendo zonas: {str(e)}", exc_info=True)
            return Response({"error": "Error interno"}, status=500)


class RegistrarUbicacionView(APIView):
    """Endpoint para registrar nueva ubicacion."""
    permission_classes = [AllowAny]

    def post(self, request):
        try:
            datos = request.data
            nombre_prov = str(datos.get('provincia', '')).strip()
            nombre_muni = str(datos.get('municipio', '')).strip()
            nombre_zona = str(datos.get('zona', '')).strip()

            if not nombre_prov or not nombre_muni or not nombre_zona:
                return Response({
                    'status': 'error',
                    'message': 'Faltan datos obligatorios. Debes indicar Zona, Municipio y Provincia.'
                }, status=400)

            with transaction.atomic():
                prov_obj, prov_creada = Provincia.objects.get_or_create(
                    nombre__iexact=nombre_prov,
                    defaults={'nombre': nombre_prov}
                )
                muni_obj, muni_creado = Municipio.objects.get_or_create(
                    nombre__iexact=nombre_muni,
                    provincia=prov_obj,
                    defaults={'nombre': nombre_muni}
                )
                zona_obj, zona_creada = Zona.objects.get_or_create(
                    nombre__iexact=nombre_zona,
                    municipio=muni_obj,
                    defaults={'nombre': nombre_zona}
                )

            if zona_creada:
                funcionAsyncronaZonas()

            si_algo_es_nuevo = prov_creada or muni_creado or zona_creada

            return Response({
                'status': 'success',
                'message': 'Se ha creado el registro correctamente' if si_algo_es_nuevo else 'No se ha hecho nada (ya existia todo)'
            })

        except Exception as e:
            logger.error(f"Error registrando ubicacion: {str(e)}", exc_info=True)
            return Response({
                'status': 'error',
                'message': 'Error interno del servidor.'
            }, status=500)


# -------------------------------------------------------------------------
# VISTA 4: WEBHOOK PROPIEDAD DELETE
# -------------------------------------------------------------------------
class WebhookPropiedadDeleteView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        if not verify_webhook_signature(request):
            return Response({'error': 'Invalid signature'}, status=403)

        try:
            data = request.data
            logger.info(f"Webhook Propiedad DELETE recibido: {data}")
            print(f"--- INFO DELETE PROPIEDAD: {data} ---") # Print explicito para verificacion rapida en consola

            custom_data = data.get('customData', {})
            id_django = custom_data.get('id_django')

            if not id_django:
                logger.info("Webhook Delete recibido sin id_django en customData. Ignorando borrado.")
                return Response({'status': 'ignored', 'message': 'No id_django provided in customData, skipping deletion'})
                
            try:
                # Buscamos la propiedad en nuestra base de datos para obtener su agencia y el location_id
                propiedad = Propiedad.objects.get(id=id_django)
                agencia = propiedad.agencia
                location_id = agencia.location_id
            except Propiedad.DoesNotExist:
                # Si no existe, no hacemos nada en GHL
                logger.warning(f"Propiedad con id_django={id_django} no encontrada para borrar.")
                return Response({'status': 'ignored', 'message': 'Propiedad no encontrada en local'})

            # Borrar de GHL primero si estaba vinculada
            if not agencia.property_object_id:
                return Response({'error': 'Falta el id del objeto propiedad (property_object_id) en la agencia'}, status=400)
            
            if not propiedad.ghl_contact_id:
                logger.warning(f"Propiedad local con id {id_django} no tiene ghl_contact_id asignado.")
                return Response({'status': 'deleted_locally', 'message': 'Error en borrado.'})

            access_token = get_valid_token(location_id)
            if not access_token:
                return Response({'error': 'No se pudo obtener token valido para borrar la propiedad en GHL'}, status=500)

            # Usamos el helper que creamos
            ghl_deleted = ghl_delete_property_record(access_token, agencia.property_object_id, propiedad.ghl_contact_id)
            
            if ghl_deleted:
                # Si se borro bien de GHL, borramos imágenes de Cloudinary y luego de BBDD local
                if propiedad.imagenesUrl and isinstance(propiedad.imagenesUrl, list):
                    eliminar_recurso_cloudinary(propiedad.imagenesUrl, resource_type="image")
                
                propiedad.delete()
                return Response({'status': 'deleted', 'message': 'Propiedad borrada correctamente de GHL y BBDD local'})
            else:
                return Response({'error': 'Error intentando borrar la propiedad de GHL'}, status=500)

        except Exception as e:
            logger.error(f"Error en Webhook Propiedad Delete: {str(e)}", exc_info=True)
            return Response({"error": "Error interno procesando delete propiedad"}, status=500)


# -------------------------------------------------------------------------
# VISTA 5: WEBHOOK CLIENTE DELETE
# -------------------------------------------------------------------------
class WebhookClienteDeleteView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        if not verify_webhook_signature(request):
            return Response({'error': 'Invalid signature'}, status=403)

        try:
            data = request.data
            logger.info(f"Webhook Cliente DELETE recibido: {data}")
            print(f"--- INFO DELETE CLIENTE: {data} ---") # Print explicito para verificacion rapida en consola

            custom_data = data.get('customData', {})
            id_django = custom_data.get('id_django')

            if not id_django:
                logger.info("Webhook Delete recibido sin id_django en customData. Ignorando borrado.")
                return Response({'status': 'ignored', 'message': 'No id_django provided in customData, skipping deletion'})
                
            try:
                # Buscamos el cliente en nuestra base de datos para obtener su agencia y el location_id
                cliente = Cliente.objects.get(id=id_django)
                agencia = cliente.agencia
                location_id = agencia.location_id
            except Cliente.DoesNotExist:
                logger.warning(f"Cliente con id_django={id_django} no encontrado para borrar.")
                return Response({'status': 'ignored', 'message': 'Cliente no encontrado en local'})

            if not cliente.ghl_contact_id:
                logger.warning(f"Cliente local con id {id_django} no tiene ghl_contact_id asignado.")
                # Si no tiene ID de GHL, lo borramos solo localmente si quieres, o damos error.
                # Siguiendo el patron de propiedad: volvemos error de borrado.
                return Response({'status': 'deleted_locally', 'message': 'Error en borrado.'})

            access_token = get_valid_token(location_id)
            if not access_token:
                return Response({'error': 'No se pudo obtener token valido para borrar el cliente en GHL'}, status=500)

            # Usamos el helper que creamos
            ghl_deleted = ghl_delete_contact(access_token, cliente.ghl_contact_id)
            
            if ghl_deleted:
                # Si se borro bien de GHL, lo borramos localmente
                cliente.delete()
                return Response({'status': 'deleted', 'message': 'Cliente borrado correctamente de GHL y BBDD local'})
            else:
                return Response({'error': 'Error intentando borrar el cliente de GHL'}, status=500)

        except Exception as e:
            logger.error(f"Error en Webhook Cliente Delete: {str(e)}", exc_info=True)
            return Response({"error": "Error interno procesando delete cliente"}, status=500)


from .deletion_handler import process_delete_request

# -------------------------------------------------------------------------
# VISTA 6: UNIVERSAL DELETE VIEW (Reemplaza a GlobalDebugView)
# -------------------------------------------------------------------------
class UniversalDeleteView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        """
        Recibe webhooks de GHL.
        Si es un evento de borrado valido (Cliente o Propiedad), lo procesa.
        Si no, lo loguea y devuelve 200 para no generar errores en GHL.
        """
        if not verify_webhook_signature(request):
            return Response({'error': 'Invalid signature'}, status=403)

        try:
            data = request.data
            # Delegamos la logica de filtrado y borrado al handler
            processed = process_delete_request(data)

            if processed:
                return Response({'status': 'deleted', 'message': 'Registro procesado correctamente'})
            else:
                return Response({'status': 'ignored', 'message': 'No es un evento de borrado valido o no coincidio'})

        except Exception as e:
            logger.error(f"Error en UniversalDeleteView: {str(e)}", exc_info=True)
            return Response({"error": "Error interno"}, status=500)


# -------------------------------------------------------------------------
# VISTA 7: GESTION DE PROPIEDADES (CREAR/EDITAR DESDE FRONTEND)
# -------------------------------------------------------------------------
import threading
from .utils import sync_record_to_ghl

class ApiGestionPropiedadView(APIView):
    """
    Endpoint (CQRS Command) para el Frontend.
    El Frontend usa este endpoint para CREAR o ACTUALIZAR propiedades localmente,
    y el middleware automatiza la creacion o actualizacion en GHL asi como el matching.
    """
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        """Crear o actualizar propiedad desde el Frontend"""
        try:
            data = request.data
            agency_id = data.get('agencia') or request.query_params.get('agency_id')
            
            if not agency_id:
                return Response({"error": "agency_id es requerido"}, status=400)
            
            agencia = get_object_or_404(Agencia, location_id=agency_id)
            if not agencia.property_object_id:
                return Response({'error': 'La agencia no tiene configurado el Property Object ID'}, status=400)

            # Buscar si existe por ghl_contact_id para update
            ghl_record_id = data.get('ghl_record_id') or data.get('ghl_contact_id')
            
            # Obtener propiedad existente para no perder imagenes que ya estaban (neutras)
            prop_existente = None
            if ghl_record_id:
                prop_existente = Propiedad.objects.filter(ghl_contact_id=ghl_record_id, agencia=agencia).first()

            with transaction.atomic():
                prop_data = parse_property_data(data)
                prop_data['agencia'] = agencia

                # --- LÓGICA DE IMÁGENES (Cloudinary) ---
                # 1. Recuperamos lo que ya habia en la base de datos
                current_pids = list(prop_existente.imagenesUrl) if (prop_existente and prop_existente.imagenesUrl) else []

                # 2. Procesar borrados si existen (Cloudinary + Local)
                imagenes_borrar = data.get('imagenes_borrar', [])
                if isinstance(imagenes_borrar, list) and imagenes_borrar:
                    ids_a_borrar = [extraer_public_id(url) for url in imagenes_borrar if url]
                    ids_a_borrar = [pid for pid in ids_a_borrar if pid]
                    if ids_a_borrar:
                        eliminar_recurso_cloudinary(ids_a_borrar)
                        # Quitamos de nuestra lista local los IDs que hemos borrado en Cloudinary
                        current_pids = [pid for pid in current_pids if pid not in ids_a_borrar]

                # 3. Subir nuevas imágenes (request.FILES)
                archivos = request.FILES.getlist('imagenes') or request.FILES.getlist('images') or request.FILES.getlist('file')
                if archivos:
                    new_public_ids = upload_img_model(archivos)
                    if new_public_ids:
                        current_pids.extend(new_public_ids)
                
                # Asignamos la lista final (antiguas mantenidas + nuevas subidas)
                prop_data['imagenesUrl'] = current_pids

                # Portales (Pendiente para futura funcionalidad de filtrado web)
                publicar_en_raw = data.get('publicar_en', [])
                portales = [p.strip().lower() for p in publicar_en_raw] if isinstance(publicar_en_raw, list) else [p.strip().lower() for p in str(publicar_en_raw).split(',') if p.strip()]

                if ghl_record_id:
                    prop_data['ghl_contact_id'] = ghl_record_id
                    propiedad, created = Propiedad.objects.update_or_create(
                        ghl_contact_id=ghl_record_id,
                        agencia=agencia,
                        defaults=prop_data
                    )
                else:
                    prop_data['ghl_contact_id'] = None
                    propiedad = Propiedad.objects.create(**prop_data)
                    created = True

                # Zonas
                zona_input = data.get("location") or data.get("zona")
                z_nombres = parse_zona_nombres(zona_input)
                if z_nombres:
                    zonas_objs = Zona.objects.filter(nombre__in=z_nombres)
                    propiedad.zonas.set(zonas_objs)

            # Enviar a GHL en background para no bloquear el frontend HTTP
            threading.Thread(
                target=sync_record_to_ghl,
                args=(propiedad, 'propiedad', created)
            ).start()

            return Response({
                "status": "success",
                "message": "Propiedad procesada y sincronizacion enviada.",
                "local_id": propiedad.id,
                "ghl_record_id": propiedad.ghl_contact_id
            }, status=201 if created else 200)

        except Exception as e:
            logger.error(f"Error en ApiGestionPropiedadView: {str(e)}", exc_info=True)
            return Response({"error": "Error interno"}, status=500)





