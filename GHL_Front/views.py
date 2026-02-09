from rest_framework import generics
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny
from ghl_middleware.models import Propiedad
from .serializers import PropiedadPublicaSerializer


class PropiedadPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class PublicPropertyList(generics.ListAPIView):
    serializer_class = PropiedadPublicaSerializer
    authentication_classes = []
    permission_classes = [AllowAny]
    pagination_class = PropiedadPagination

    def get_queryset(self):
        agency_id = self.request.query_params.get('agency_id')

        if agency_id:
            return Propiedad.objects.select_related('zona__municipio', 'agencia').filter(
                agencia__location_id=agency_id,
                estado='activo'
            )

        return Propiedad.objects.none()


class PublicPropertyDetail(generics.RetrieveAPIView):
    """Detalle de una propiedad por su GHL Contact ID. Requiere agency_id."""
    serializer_class = PropiedadPublicaSerializer
    lookup_field = 'ghl_contact_id'
    authentication_classes = []
    permission_classes = [AllowAny]

    def get_queryset(self):
        agency_id = self.request.query_params.get('agency_id')

        # Obligar a pasar agency_id para mantener aislamiento multi-tenant
        if not agency_id:
            return Propiedad.objects.none()

        return Propiedad.objects.select_related('zona__municipio', 'agencia').filter(
            agencia__location_id=agency_id,
            estado='activo'
        )
