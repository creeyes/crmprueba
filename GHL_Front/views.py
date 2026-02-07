from rest_framework import generics
from ghl_middleware.models import Propiedad
from .serializers import PropiedadPublicaSerializer

class PublicPropertyList(generics.ListAPIView):
    serializer_class = PropiedadPublicaSerializer
    authentication_classes = [] # API abierta
    permission_classes = []

    def get_queryset(self):
        # VERSIÓN SIMPLE:
        # Esperamos que nos pasen el ID en la URL: ?agency_id=ABC-123
        agency_id = self.request.query_params.get('agency_id')

        if agency_id:
            # Filtramos propiedades de esa agencia que estén activas
            return Propiedad.objects.filter(agencia__location_id=agency_id, estado='activo')
        
        # Si no pasan ID, devolvemos vacío para no mezclar datos
        return Propiedad.objects.none()

class PublicPropertyDetail(generics.RetrieveAPIView):
    """
    Vista para obtener el detalle de una sola propiedad usando su GHL Contact ID.
    """
    queryset = Propiedad.objects.filter(estado='activo')
    serializer_class = PropiedadPublicaSerializer
    lookup_field = 'ghl_contact_id'  # IMPORTANTE: Buscamos por el ID de GHL, no el ID numérico de Django
    authentication_classes = []
    permission_classes = []
