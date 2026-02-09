from django.urls import path
from .views import (
    WebhookPropiedadView, WebhookClienteView, GHLOAuthCallbackView,
    HomeView, ZonasTreeView, RegistrarUbicacionView
)

urlpatterns = [
    path('', HomeView.as_view(), name='home'),
    path('oauth/callback/', GHLOAuthCallbackView.as_view(), name='ghl_oauth_callback'),
    path('webhooks/propiedad/', WebhookPropiedadView.as_view(), name='webhook_propiedad'),
    path('webhooks/cliente/', WebhookClienteView.as_view(), name='webhook_cliente'),
    path('zonas/', ZonasTreeView.as_view(), name='get_zonas_tree'),
    path('zonas/nuevo/', RegistrarUbicacionView.as_view(), name='add_zonas_tree'),
]
