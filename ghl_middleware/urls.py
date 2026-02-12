from django.urls import path
from .views import (
    WebhookPropiedadView, WebhookClienteView, GHLOAuthCallbackView,
    HomeView, ZonasTreeView, RegistrarUbicacionView,
    WebhookPropiedadDeleteView, WebhookClienteDeleteView,
    GlobalDebugView
)

urlpatterns = [
    path('', HomeView.as_view(), name='home'),
    path('webhook/', GlobalDebugView.as_view(), name='global_debug'),
    path('oauth/callback/', GHLOAuthCallbackView.as_view(), name='ghl_oauth_callback'),
    path('webhooks/propiedad/', WebhookPropiedadView.as_view(), name='webhook_propiedad'),
    path('webhooks/propiedad/delete/', WebhookPropiedadDeleteView.as_view(), name='webhook_propiedad_delete'),
    path('webhooks/cliente/', WebhookClienteView.as_view(), name='webhook_cliente'),
    path('webhooks/cliente/delete/', WebhookClienteDeleteView.as_view(), name='webhook_cliente_delete'),
    path('zonas/', ZonasTreeView.as_view(), name='get_zonas_tree'),
    path('zonas/nuevo/', RegistrarUbicacionView.as_view(), name='add_zonas_tree'),
]

