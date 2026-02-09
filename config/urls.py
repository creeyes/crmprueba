from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('ghl_middleware.urls')),
    path('front/', include('GHL_Front.urls')),
]
