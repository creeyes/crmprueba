from rest_framework import serializers
from .models import Agencia, Propiedad, Cliente

# 1. Serializer de Agencia (Protegido)
class AgenciaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Agencia
        # Excluimos api_key o tokens para no revelarlos por error en una respuesta JSON
        exclude = ['api_key'] 

# 2. Serializer de Propiedad (Estándar)
class PropiedadSerializer(serializers.ModelSerializer):
    ghl_id = serializers.CharField(source='ghl_contact_id', read_only=True)

    class Meta:
        model = Propiedad
        fields = [
            'id', 'ghl_id', 'agencia', 'ghl_contact_id', 'precio', 'habitaciones', 
            'estado', 'imagenesUrl', 'metros', 'animales', 'balcon', 'garaje', 
            'patioInterior', 'descripcion', 'calle', 'sync_status', 'sync_error'
        ]

# 3. Serializer de Cliente (Enriquecido para el Matching)
class ClienteSerializer(serializers.ModelSerializer):
    ghl_id = serializers.CharField(source='ghl_contact_id', read_only=True)
    # Campo extra: Esto nos permite ver los detalles de las propiedades asignadas
    # en lugar de solo sus IDs (Primary Keys).
    # 'read_only=True' significa que este campo es solo para VER, no para escribir.
    matches_detalles = PropiedadSerializer(source='propiedades_interes', many=True, read_only=True)

    class Meta:
        model = Cliente
        fields = [
            'id', 'ghl_id', 'agencia', 'ghl_contact_id', 'nombre', 'presupuesto_maximo',
            'habitaciones_minimas', 'created_at', 'propiedades_interes', 'matches_detalles',
            'metrosMinimo', 'animales', 'balcon', 'garaje', 'patioInterior', 
            'sync_status', 'sync_error'
        ]
        # Opcional: Si quieres que 'propiedades_interes' (los IDs) no salgan en el JSON
        # y solo salga 'matches_detalles', puedes configurarlo aquí.
        extra_kwargs = {
            'propiedades_interes': {'write_only': True, 'required': False}
        }
