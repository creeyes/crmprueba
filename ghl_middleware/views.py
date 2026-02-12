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
from .utils import get_valid_token, get_association_type_id
from .helpers import (
    clean_currency, clean_int, preferenciasTraductor1,
    preferenciasTraductor2, estadoPropTrad, guardadorURL
)
from .matching import (
    buscar_clientes_para_propiedad, buscar_propiedades_para_cliente,
    actualizar_relaciones_propiedad, actualizar_relaciones_cliente
)

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

                    logger.info(f"Buscando ID de asociacion para {location_id}...")
                    found_id = get_association_type_id(access_token, location_id, object_key="propiedad")

                    if found_id:
                        agencia.association_type_id = found_id
                        agencia.save()
                        logger.info(f"ID de asociacion detectado y guardado: {found_id}")
                    else:
                        logger.warning(f"No se pudo detectar el ID automaticamente para {location_id}.")

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
# VISTA 2: WEBHOOK PROPIEDAD
# -------------------------------------------------------------------------
class WebhookPropiedadView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        if not verify_webhook_signature(request):
            return Response({'error': 'Invalid signature'}, status=403)

        try:
            data = request.data
            logger.info(f"Webhook Propiedad recibido: {data}")

            custom_data = data.get('customData', {})
            location_data = data.get('location', {})
            location_id = location_data.get('id') or custom_data.get('location_id')

            if not location_id:
                return Response({'error': 'Missing location_id'}, status=400)

            agencia = get_object_or_404(Agencia, location_id=location_id)
            ghl_record_id = custom_data.get('contact_id') or data.get('id')

            if not ghl_record_id:
                return Response({'error': 'Missing Record ID'}, status=400)

            with transaction.atomic():
                prop_data = {
                    'agencia': agencia,
                    'ghl_contact_id': ghl_record_id,
                    'precio': clean_currency(custom_data.get('precio') or data.get('precio')),
                    'habitaciones': clean_int(custom_data.get('habitaciones') or data.get('habitaciones')),
                    'estado': estadoPropTrad(custom_data.get("estado")),
                    'animales': preferenciasTraductor1(custom_data.get('animales')),
                    'metros': clean_int(custom_data.get('metros')),
                    'balcon': preferenciasTraductor1(custom_data.get('balcon')),
                    'garaje': preferenciasTraductor1(custom_data.get('garaje')),
                    'patioInterior': preferenciasTraductor1(custom_data.get('patioInterior')),
                    'imagenesUrl': guardadorURL(custom_data.get('imagenesUrl')),
                }

                propiedad, created = Propiedad.objects.update_or_create(
                    agencia=agencia,
                    ghl_contact_id=ghl_record_id,
                    defaults=prop_data
                )

                zona = custom_data.get("zona")
                if zona:
                    zona_limpio = zona.replace("_", " ").lower().strip()
                    zona_obj = Zona.objects.filter(nombre__iexact=zona_limpio).first()
                    if zona_obj:
                        propiedad.zona = zona_obj
                        propiedad.save()

                if propiedad.estado == Propiedad.estadoPiso.ACTIVO:
                    clientes_match = buscar_clientes_para_propiedad(propiedad, agencia)
                    matches_count = actualizar_relaciones_propiedad(propiedad, clientes_match)
                else:
                    clientes_match = Cliente.objects.none()
                    matches_count = 0

            # Sincronizacion con GHL (fuera de la transaccion: llamadas HTTP externas)
            # Fix: Sincronizar SIEMPRE, incluso si matches_count es 0, para limpiar asociaciones viejas.
            if not agencia.association_type_id:
                logger.warning(f"Agencia {location_id} no tiene 'association_type_id'. Cruzado saltado.")
                return Response({'status': 'warning', 'msg': 'Falta Association ID', 'matches_found': matches_count})

            access_token = get_valid_token(location_id)

            if access_token:
                target_ids = [c.ghl_contact_id for c in clientes_match]  # Sera [] si matches_count == 0

                sync_associations_background(
                    access_token=access_token,
                    location_id=location_id,
                    origin_record_id=propiedad.ghl_contact_id,
                    target_ids_list=target_ids,
                    association_id_val=agencia.association_type_id
                )
            else:
                logger.warning(f"No valid token found for {location_id}")

            return Response({'status': 'success', 'matches_found': matches_count})

        except Exception as e:
            logger.error(f"Error en Webhook Propiedad: {str(e)}", exc_info=True)
            return Response({"error": "Error interno procesando propiedad"}, status=500)


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
                    zona_lista = [z.strip() for z in str(zona_nombre).split(",")]
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

            # AQUI IMPLEMENTAREMOS LA LOGICA DE BORRADO MAS ADELANTE
            
            return Response({'status': 'received', 'action': 'delete_property'})

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

            # AQUI IMPLEMENTAREMOS LA LOGICA DE BORRADO MAS ADELANTE

            return Response({'status': 'received', 'action': 'delete_client'})

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

