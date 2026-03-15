import json
import base64
import hashlib
import logging
from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404

from rest_framework import generics
from rest_framework.pagination import PageNumberPagination
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status as http_status

from ghl_middleware.models import Agencia, Propiedad, Zona
from ghl_middleware.utils import (
    get_valid_token, ghl_create_placeholder_property, 
    ghl_update_property_record, _recent_syncs
)
from ghl_middleware.helpers import (
    clean_currency, clean_int, preferenciasTraductor1, 
    estadoPropTrad, guardadorURL
)
from .serializers import PropiedadPublicaSerializer

logger = logging.getLogger(__name__)


# ========== SSO DECRYPT ENDPOINT ==========

class DecryptSSO(APIView):
    """
    Desencripta el payload SSO que GHL envía via postMessage.
    
    GHL usa CryptoJS.AES.encrypt(JSON, sharedSecret) que internamente:
    1. Genera salt aleatorio de 8 bytes
    2. Deriva key (32 bytes) + iv (16 bytes) usando EVP_BytesToKey con MD5
    3. Encripta con AES-256-CBC
    4. Devuelve "Salted__" + salt + ciphertext, todo en Base64
    
    Respuesta desencriptada contiene:
    - activeLocation: el location_id de la agencia actual
    - userId, companyId, role, userName, email, etc.
    """
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        encrypted_data = request.data.get('encryptedData')
        
        if not encrypted_data:
            return Response(
                {'error': 'encryptedData es requerido'},
                status=http_status.HTTP_400_BAD_REQUEST
            )
        
        shared_secret = settings.GHL_APP_SHARED_SECRET
        if not shared_secret:
            logger.error("GHL_APP_SHARED_SECRET no está configurado en las variables de entorno")
            return Response(
                {'error': 'Configuración del servidor incompleta'},
                status=http_status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        try:
            user_data = self._decrypt_cryptojs_aes(encrypted_data, shared_secret)
            logger.info(f"SSO desencriptado exitosamente para usuario: {user_data.get('email', 'N/A')}")
            return Response(user_data)
            
        except Exception as e:
            logger.error(f"Error al desencriptar SSO: {e}")
            return Response(
                {'error': 'No se pudo desencriptar el payload SSO'},
                status=http_status.HTTP_400_BAD_REQUEST
            )

    @staticmethod
    def _evp_bytes_to_key(password: bytes, salt: bytes, key_len: int = 32, iv_len: int = 16):
        """
        Replica la derivación de clave de OpenSSL EVP_BytesToKey con MD5.
        Es lo que CryptoJS usa internamente.
        """
        d = b''
        d_list = []
        while len(b''.join(d_list)) < key_len + iv_len:
            block = d + password + salt
            d = hashlib.md5(block).digest()
            d_list.append(d)
        derived = b''.join(d_list)
        return derived[:key_len], derived[key_len:key_len + iv_len]

    @staticmethod
    def _decrypt_cryptojs_aes(encrypted_b64: str, passphrase: str) -> dict:
        """
        Desencripta un string encriptado con CryptoJS.AES.encrypt().
        """
        from Crypto.Cipher import AES
        from Crypto.Util.Padding import unpad
        
        # 1. Decodificar Base64
        raw = base64.b64decode(encrypted_b64)
        
        # 2. Verificar prefijo "Salted__" (8 bytes) y extraer salt (8 bytes)
        if raw[:8] != b'Salted__':
            raise ValueError("Formato inválido: no tiene prefijo 'Salted__'")
        
        salt = raw[8:16]
        ciphertext = raw[16:]
        
        # 3. Derivar key e IV usando EVP_BytesToKey
        key, iv = DecryptSSO._evp_bytes_to_key(passphrase.encode('utf-8'), salt)
        
        # 4. Desencriptar con AES-256-CBC
        cipher = AES.new(key, AES.MODE_CBC, iv)
        decrypted = unpad(cipher.decrypt(ciphertext), AES.block_size)
        
        # 5. Parsear JSON
        return json.loads(decrypted.decode('utf-8'))



# CORRECCIÓN #23: Paginación para evitar devolver todos los datos de golpe
class PropiedadPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class PublicPropertyList(generics.ListAPIView):
    serializer_class = PropiedadPublicaSerializer
    authentication_classes = []  # API abierta
    permission_classes = []
    pagination_class = PropiedadPagination  # CORRECCIÓN #23

    def get_queryset(self):
        # VERSIÓN SIMPLE:
        # Esperamos que nos pasen el ID en la URL: ?agency_id=ABC-123
        agency_id = self.request.query_params.get('agency_id')

        if agency_id:
            # Filtramos propiedades de esa agencia que estén activas
            # CORRECCIÓN #22: prefetch_related para evitar N+1 queries
            return Propiedad.objects.prefetch_related('zonas__municipio').filter(
                agencia__location_id=agency_id, 
                estado='activo'
            )
        
        # Si no pasan ID, devolvemos vacío para no mezclar datos
        return Propiedad.objects.none()

    def post(self, request):
        """
        Crea una nueva propiedad tanto en GHL como en la base de datos local.
        """
        data = request.data
        agency_id = data.get('agencia') or request.query_params.get('agency_id')
        
        if not agency_id:
            return Response({"error": "agency_id es requerido"}, status=http_status.HTTP_400_BAD_REQUEST)
            
        agencia = get_object_or_404(Agencia, location_id=agency_id)
        
        # 1. Crear en GHL primero
        if not agencia.property_object_id:
             return Response({'error': 'La agencia no tiene configurado el Property Object ID'}, status=http_status.HTTP_400_BAD_REQUEST)
             
        access_token = get_valid_token(agency_id)
        if not access_token:
             return Response({'error': 'No se pudo obtener el token de acceso de GHL'}, status=http_status.HTTP_500_INTERNAL_SERVER_ERROR)
             
        # Crear placeholder en GHL
        ghl_record_id = ghl_create_placeholder_property(access_token, agency_id, agencia.property_object_id)
        if not ghl_record_id:
             return Response({'error': 'Fallo al crear el registro en GHL'}, status=http_status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Registrar el ID para evitar el bounce-back del webhook
        _recent_syncs.add(ghl_record_id)

        try:
            with transaction.atomic():
                # Limpieza de datos usando helpers
                estado_base = estadoPropTrad(data.get("estado"))
                
                prop_data = {
                    'agencia': agencia,
                    'ghl_contact_id': ghl_record_id,
                    'precio': clean_currency(data.get('precio')),
                    'habitaciones': clean_int(data.get('habitaciones')),
                    'estado': estado_base,
                    'animales': preferenciasTraductor1(data.get('animales')),
                    'metros': clean_int(data.get('metros')),
                    'balcon': preferenciasTraductor1(data.get('balcon')),
                    'garaje': preferenciasTraductor1(data.get('garaje')),
                    'patioInterior': preferenciasTraductor1(data.get('patioInterior')),
                    'imagenesUrl': data.get('imagenesUrl', []),
                }
                
                propiedad = Propiedad.objects.create(**prop_data)
                
                # Asignar zona si viene en el request
                zona_nombre = data.get("location")
                if zona_nombre:
                    zona_objs = Zona.objects.filter(nombre__iexact=zona_nombre)
                    if zona_objs.exists():
                        propiedad.zonas.set(zona_objs)
                
                # Retornar la propiedad creada usando el serializer público
                serializer = self.get_serializer(propiedad)
                return Response(serializer.data, status=http_status.HTTP_201_CREATED)
                
        except Exception as e:
            logger.error(f"Error en POST /api/properties/: {str(e)}", exc_info=True)
            return Response({"error": "Error interno al guardar la propiedad"}, status=http_status.HTTP_500_INTERNAL_SERVER_ERROR)


class PublicPropertyDetail(generics.RetrieveUpdateAPIView):
    """
    Vista para obtener el detalle de una sola propiedad usando su GHL Contact ID.
    """
    serializer_class = PropiedadPublicaSerializer
    lookup_field = 'ghl_contact_id'  # IMPORTANTE: Buscamos por el ID de GHL, no el ID numérico de Django
    authentication_classes = []
    permission_classes = []

    def get_queryset(self):
        # CORRECCIÓN #21: Filtrar por agency_id para que una agencia no vea propiedades de otra
        agency_id = self.request.query_params.get('agency_id')

        # CORRECCIÓN #22: prefetch_related para evitar N+1 queries
        queryset = Propiedad.objects.prefetch_related('zonas__municipio').filter(estado='activo')

        if agency_id:
            queryset = queryset.filter(agencia__location_id=agency_id)

        return queryset

    def update(self, request, *args, **kwargs):
        """
        Actualiza una propiedad existente tanto en GHL como localmente.
        """
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        data = request.data
        
        # Registrar para evitar bounce-back
        _recent_syncs.add(instance.ghl_contact_id)
        
        # 1. Intentar actualizar en GHL
        access_token = get_valid_token(instance.agencia.location_id)
        if access_token and instance.agencia.property_object_id:
             # Mapeo simple de campos para GHL (puedes expandir esto según necesites)
             ghl_payload = {
                 "precio": str(data.get('precio', instance.precio)),
                 "habitaciones": str(data.get('habitaciones', instance.habitaciones)),
                 "metros": str(data.get('metros', instance.metros)),
                 "estado": data.get('estado', instance.estado),
                 "animales": data.get('animales', instance.animales),
                 "balcon": data.get('balcon', instance.balcon),
                 "garaje": data.get('garaje', instance.garaje),
                 "patioInterior": data.get('patioInterior', instance.patioInterior),
                 "zona": data.get('location', instance.zonas.first().nombre if instance.zonas.exists() else "")
             }
             
             ghl_update_property_record(
                 access_token, 
                 instance.agencia.location_id, 
                 instance.agencia.property_object_id, 
                 instance.ghl_contact_id, 
                 ghl_payload
             )

        # 2. Actualizar localmente
        # Preparamos los datos para el update local
        if 'estado' in data: instance.estado = estadoPropTrad(data['estado'])
        if 'precio' in data: instance.precio = clean_currency(data['precio'])
        if 'habitaciones' in data: instance.habitaciones = clean_int(data['habitaciones'])
        if 'metros' in data: instance.metros = clean_int(data['metros'])
        if 'animales' in data: instance.animales = preferenciasTraductor1(data['animales'])
        if 'balcon' in data: instance.balcon = preferenciasTraductor1(data['balcon'])
        if 'garaje' in data: instance.garaje = preferenciasTraductor1(data['garaje'])
        if 'patioInterior' in data: instance.patioInterior = preferenciasTraductor1(data['patioInterior'])
        if 'imagenesUrl' in data: instance.imagenesUrl = data['imagenesUrl']

        # Manejo de zonas en el update
        if 'location' in data:
            zona_objs = Zona.objects.filter(nombre__iexact=data['location'])
            if zona_objs.exists():
                instance.zonas.set(zona_objs)

        instance.save()

        # Retornamos los datos actualizados usando el serializer público
        serializer = self.get_serializer(instance)
        return Response(serializer.data)


# ========== NUEVOS ENDPOINTS CON FILTROS AVANZADOS ==========

class PublicPropertyFilteredList(generics.ListAPIView):
    """
    Endpoint con filtros avanzados para búsqueda de propiedades.

    Query params disponibles:
    - agency_id (requerido): ID de la agencia
    - type: Villa | Apartment | Studio
    - location: Nombre de la zona
    - min_price: Precio mínimo
    - max_price: Precio máximo
    - beds: Número exacto de habitaciones
    - min_sqm: Metros cuadrados mínimos
    - features: Balcón,Garaje,Mascotas,Patio (separados por coma)
    - ordering: Campo de ordenamiento (default: -precio)
    """
    serializer_class = PropiedadPublicaSerializer
    authentication_classes = []
    permission_classes = []
    pagination_class = PropiedadPagination

    def get_queryset(self):
        agency_id = self.request.query_params.get('agency_id')

        if not agency_id:
            return Propiedad.objects.none()

        # Base queryset
        queryset = Propiedad.objects.prefetch_related('zonas__municipio').filter(
            agencia__location_id=agency_id,
            estado='activo'
        )

        # Filtro por tipo de propiedad
        tipo = self.request.query_params.get('type')
        if tipo == 'Villa':
            queryset = queryset.filter(habitaciones__gt=4)
        elif tipo == 'Studio':
            queryset = queryset.filter(habitaciones=0)
        elif tipo == 'Apartment':
            queryset = queryset.filter(habitaciones__gte=1, habitaciones__lte=4)

        # Filtro por ubicación (zona)
        location = self.request.query_params.get('location')
        if location:
            queryset = queryset.filter(zonas__nombre__iexact=location)

        # Filtros por precio
        min_price = self.request.query_params.get('min_price')
        max_price = self.request.query_params.get('max_price')
        if min_price:
            queryset = queryset.filter(precio__gte=min_price)
        if max_price:
            queryset = queryset.filter(precio__lte=max_price)

        # Filtro por número de habitaciones
        beds = self.request.query_params.get('beds')
        if beds:
            queryset = queryset.filter(habitaciones=beds)

        # Filtro por metros cuadrados mínimos
        min_sqm = self.request.query_params.get('min_sqm')
        if min_sqm:
            queryset = queryset.filter(metros__gte=min_sqm)

        # Filtros por características
        features = self.request.query_params.get('features')
        if features:
            feature_list = [f.strip().lower() for f in features.split(',')]

            if 'balcón' in feature_list or 'balcon' in feature_list:
                queryset = queryset.filter(balcon='si')

            if 'garaje' in feature_list:
                queryset = queryset.filter(garaje='si')

            if 'mascotas' in feature_list or 'animales' in feature_list:
                queryset = queryset.filter(animales='si')

            if 'patio' in feature_list:
                queryset = queryset.filter(patioInterior='si')

        # Ordenamiento
        ordering = self.request.query_params.get('ordering', '-precio')
        queryset = queryset.order_by(ordering)

        return queryset


class PublicLocationsList(APIView):
    """
    Devuelve todas las ubicaciones (zonas) disponibles para una agencia.
    Útil para popular dropdowns de filtros en el frontend.

    Query params:
    - agency_id (requerido): ID de la agencia
    """
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        agency_id = request.query_params.get('agency_id')

        if not agency_id:
            return Response(
                {'error': 'agency_id es requerido'},
                status=http_status.HTTP_400_BAD_REQUEST
            )

        # Obtener TODAS las zonas registradas en la base de datos (GHL)
        zonas = Zona.objects.all().select_related('municipio', 'municipio__provincia').values(
            'nombre',
            'municipio__nombre',
            'municipio__provincia__nombre'
        ).order_by('nombre')

        # Formatear respuesta
        locations = [
            {
                'zona': z['nombre'],
                'municipio': z['municipio__nombre'],
                'provincia': z['municipio__provincia__nombre']
            }
            for z in zonas
        ]

        return Response({
            'count': len(locations),
            'locations': locations
        })
