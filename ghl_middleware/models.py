from django.db import models

# --- 1. MODELO DE INFRAESTRUCTURA (CRUZADO / OAUTH) ---

class GHLToken(models.Model):
    """
    Guarda los tokens de acceso generados por el Marketplace de GHL.
    Es vital para validar que la App está instalada legalmente y para refrescar tokens.
    """
    location_id = models.CharField(max_length=255, primary_key=True, help_text="ID de la subcuenta que instaló la app")
    access_token = models.TextField()
    refresh_token = models.TextField()
    token_type = models.CharField(max_length=50)
    expires_in = models.IntegerField(default=86400)
    scope = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Token GHL - {self.location_id}"


# --- 2. MODELOS DE NEGOCIO (INMOBILIARIA) ---

class Agencia(models.Model):
    """
    Modelo Tenant que representa una agencia inmobiliaria (Subcuenta de GHL).
    """
    location_id = models.CharField(
        max_length=255, 
        unique=True, 
        primary_key=True, 
        help_text="ID único de la subcuenta de GHL"
    )
    api_key = models.CharField(
        max_length=255, 
        blank=True, 
        null=True, 
        help_text="Token de autorización (Opcional si usas OAuth)"
    )
    nombre = models.CharField(max_length=255, blank=True, null=True)
    active = models.BooleanField(default=True, help_text="Desactiva la agencia si deja de pagar")

    # --- CAMPO IMPRESCINDIBLE AÑADIDO ---
    association_type_id = models.CharField(
        max_length=255, 
        blank=True, 
        null=True, 
        help_text="ID de asociación dinámico para esta subcuenta (vía GHL API)"
    )
    # ------------------------------------
    
    # CORRECCIÓN #25: Umbral configurable para propiedades destacadas
    umbral_featured = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=500000,
        help_text="Precio mínimo para marcar una propiedad como destacada (isFeatured)"
    )

    def __str__(self):
        return f"{self.nombre or 'Agencia Sin Nombre'} ({self.location_id})"

class Provincia(models.Model):
    nombre = models.CharField(max_length=50, unique=True, db_index=True) # Ej: "Barcelona"

    def __str__(self):
        return self.nombre

class Municipio(models.Model):
    provincia = models.ForeignKey(Provincia, on_delete=models.CASCADE, related_name="municipios")
    nombre = models.CharField(max_length=100, db_index=True) # Ej: "Cornellà de Llobregat" o "Barcelona" (ciudad)

    class Meta:
        unique_together = ('provincia', 'nombre') # Evita duplicar "Madrid" en provincias distintas

    def __str__(self):
        return f"{self.nombre} ({self.provincia.nombre})"

class Zona(models.Model):
    municipio = models.ForeignKey(Municipio, on_delete=models.CASCADE, related_name="zonas")
    nombre = models.CharField(max_length=100, db_index=True) # Ej: "Almeda" o "Gràcia"

    def __str__(self):
        return self.nombre

class Propiedad(models.Model):
    """
    Representa el Custom Object 'Propiedad' de GHL.
    """
    class Preferencias1(models.TextChoices):
        SI = "si", "Si"
        NO = "no", "No"

    class estadoPiso(models.TextChoices):
        ACTIVO = "activo", "Activo"
        VENDIDO = "vendido", "Vendido"
        NoOficial = "noficial", "No Oficial"

    agencia = models.ForeignKey(Agencia, on_delete=models.CASCADE, related_name='propiedades')
    ghl_contact_id = models.CharField(max_length=255, help_text="ID del REGISTRO (Record ID) del Custom Object en GHL")
    
    precio = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    zona = models.ForeignKey(Zona, blank=True, null=True, related_name="propiedades", on_delete=models.SET_NULL)
    habitaciones = models.IntegerField(default=0, help_text="Nº de habitaciones que tiene la propiedad")
    estado = models.CharField(max_length=20, choices=estadoPiso.choices, default='activo')
    imagenesUrl = models.JSONField(default=list)
    metros = models.IntegerField(default=0)
    animales = models.CharField(max_length=3, choices=Preferencias1.choices, default=Preferencias1.NO) #Default es el indiferente. A la hora de buscar errores, se ha de tener esto en cuenta.
    balcon = models.CharField(max_length=3, choices=Preferencias1.choices, default=Preferencias1.NO) #Default es el indiferente. A la hora de buscar errores, se ha de tener esto en cuenta.
    garaje = models.CharField(max_length=3, choices=Preferencias1.choices, default=Preferencias1.NO) #Default es el indiferente. A la hora de buscar errores, se ha de tener esto en cuenta.
    patioInterior = models.CharField(max_length=3, choices=Preferencias1.choices, default=Preferencias1.NO) #Default es el indiferente. A la hora de buscar errores, se ha de tener esto en cuenta.

    class Meta:
        unique_together = ('agencia', 'ghl_contact_id')
        # CORRECCIÓN #36: Índices compuestos para consultas frecuentes de filtrado
        indexes = [
            models.Index(fields=['agencia', 'estado', 'precio'], name='prop_agencia_estado_precio_idx'),
            models.Index(fields=['agencia', 'zona'], name='prop_agencia_zona_idx'),
        ]

    def __str__(self):
        return f"Propiedad {self.ghl_contact_id} - {self.zona} ({self.habitaciones} habs)"


class Cliente(models.Model):
    """
    Representa el Contacto (Buyer Lead) de GHL.
    """
    class Preferencias1(models.TextChoices):
        SI = "si", "Si"
        NO = "no", "No"

    class Preferencias2(models.TextChoices):
        SI = "si", "Si"
        IND = "ind", "Indiferente"


    agencia = models.ForeignKey(Agencia, on_delete=models.CASCADE, related_name='clientes')
    ghl_contact_id = models.CharField(max_length=255, help_text="ID del CONTACTO en GHL")
    nombre = models.CharField(max_length=255, blank=True, default="Desconocido")
    presupuesto_maximo = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    zona_interes = models.ManyToManyField(Zona, blank=True, related_name="clientes")

    # NUEVO CAMPO SOLICITADO:
    habitaciones_minimas = models.IntegerField(default=0, help_text="Nº mínimo de habitaciones que busca el cliente")

    created_at = models.DateTimeField(auto_now_add=True)

    # NUEVO CAMPO DE RELACIÓN (Many-to-Many): 
    # Esto permite guardar qué propiedades se han emparejado con este cliente.
    # 'blank=True' permite crear clientes sin propiedades asignadas.
    propiedades_interes = models.ManyToManyField(
        Propiedad, 
        related_name='interesados', 
        blank=True,
        help_text="Historial de propiedades que hacen match con este cliente"
    )
    metrosMinimo = models.IntegerField(default=0)
    animales = models.CharField(max_length=3, choices=Preferencias1.choices, default=Preferencias1.NO) #Default es el indiferente. A la hora de buscar errores, se ha de tener esto en cuenta.
    balcon = models.CharField(max_length=3, choices=Preferencias2.choices, default=Preferencias2.IND) #Default es el indiferente. A la hora de buscar errores, se ha de tener esto en cuenta.
    garaje = models.CharField(max_length=3, choices=Preferencias2.choices, default=Preferencias2.IND) #Default es el indiferente. A la hora de buscar errores, se ha de tener esto en cuenta.
    patioInterior = models.CharField(max_length=3, choices=Preferencias2.choices, default=Preferencias2.IND) #Default es el indiferente. A la hora de buscar errores, se ha de tener esto en cuenta.

    class Meta:
        unique_together = ('agencia', 'ghl_contact_id')
        # CORRECCIÓN #36: Índice compuesto para consultas frecuentes
        indexes = [
            models.Index(fields=['agencia', 'presupuesto_maximo'], name='cli_agencia_presupuesto_idx'),
        ]

    def __str__(self):
        return f"Cliente {self.nombre}"
