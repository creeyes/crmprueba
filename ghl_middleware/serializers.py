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
    class Meta:
        model = Propiedad
        fields = '__all__'

# 3. Serializer de Cliente (Enriquecido para el Matching)
class ClienteSerializer(serializers.ModelSerializer):
    # Campo extra: Esto nos permite ver los detalles de las propiedades asignadas
    # en lugar de solo sus IDs (Primary Keys).
    # 'read_only=True' significa que este campo es solo para VER, no para escribir.
    matches_detalles = PropiedadSerializer(source='propiedades_interes', many=True, read_only=True)

    class Meta:
        model = Cliente
        fields = '__all__'
        # Opcional: Si quieres que 'propiedades_interes' (los IDs) no salgan en el JSON
        # y solo salga 'matches_detalles', puedes configurarlo aquí.
        extra_kwargs = {
            'propiedades_interes': {'write_only': True, 'required': False}
        }
