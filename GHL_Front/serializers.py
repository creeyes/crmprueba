from rest_framework import serializers
from ghl_middleware.models import Propiedad

class PropiedadPublicaSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source='ghl_contact_id')
    title = serializers.SerializerMethodField()
    price = serializers.DecimalField(source='precio', max_digits=12, decimal_places=0)
    location = serializers.SerializerMethodField()
    beds = serializers.IntegerField(source='habitaciones')
    # CORRECCIÓN #20: Eliminado baths=1 hardcodeado - campo eliminado hasta añadir baños al modelo
    sqm = serializers.IntegerField(source='metros')
    
    # --- IMÁGENES Y DESCRIPCIÓN ---
    image = serializers.SerializerMethodField()     # Para la portada (Card)
    images = serializers.SerializerMethodField()    # Para la galería (Detalle)
    description = serializers.SerializerMethodField()
    # ------------------------------

    type = serializers.SerializerMethodField()
    features = serializers.SerializerMethodField()
    isFeatured = serializers.SerializerMethodField()

    class Meta:
        model = Propiedad
        fields = [
            'id', 'title', 'price', 'location', 
            'beds', 'sqm', 'type',  # CORRECCIÓN #20: Eliminado 'baths'
            'image', 'images', 'features', 'isFeatured',
            'description' 
        ]

    def get_title(self, obj):
        zona = obj.zona.nombre if obj.zona else "Zona Exclusiva"
        municipio = ""
        if obj.zona and obj.zona.municipio:
            municipio = obj.zona.municipio.nombre   
        if municipio:
            return f"Oportunidad en {zona}, {municipio}"
        return f"Oportunidad en {zona}"

    def get_location(self, obj):
        if obj.zona: return obj.zona.nombre
        return "Consultar Ubicación"

    def get_image(self, obj):
        # Devuelve la primera imagen o un placeholder si no hay
        if obj.imagenesUrl and isinstance(obj.imagenesUrl, list) and len(obj.imagenesUrl) > 0:
            return obj.imagenesUrl[0]
        return "https://placehold.co/600x400?text=Sin+Imagen"

    def get_images(self, obj):
        # Devuelve siempre una lista, aunque esté vacía, para no romper el front
        if not obj.imagenesUrl or not isinstance(obj.imagenesUrl, list):
            return []
        return obj.imagenesUrl

    def get_type(self, obj):
        if obj.habitaciones > 4: return "Villa"
        elif obj.habitaciones == 0: return "Studio"
        return "Apartment"

    def get_features(self, obj):
        features = []
        # CORRECCIÓN #24: Usar constantes del modelo en vez de strings mágicos 'si'
        if obj.balcon == Propiedad.Preferencias1.SI: features.append('Balcón')
        if obj.garaje == Propiedad.Preferencias1.SI: features.append('Garaje')
        if obj.patioInterior == Propiedad.Preferencias1.SI: features.append('Patio Interior')
        if obj.animales == Propiedad.Preferencias1.SI: features.append('Admite Mascotas')
        # CORRECCIÓN #26: Quitada zona de features (ya está en location, era redundante)
        return features
        
    def get_isFeatured(self, obj):
        # CORRECCIÓN #25: Usa el umbral configurable por agencia
        umbral = getattr(obj.agencia, 'umbral_featured', 500000)
        return obj.precio > umbral

    def get_description(self, obj):
        # Generamos descripción automática para evitar errores
        ubicacion = self.get_location(obj)
        tipo = self.get_type(obj)
        return f"Excelente {tipo} en {ubicacion} con {obj.metros}m² y {obj.habitaciones} habitaciones. Contáctanos para visitar."
