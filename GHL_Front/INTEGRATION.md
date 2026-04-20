# Guía de Integración GHL_Front API

## 📋 Introducción

Esta guía explica cómo conectar tu web React/Vue/Angular a la API de GHL_Front para mostrar propiedades inmobiliarias dinámicamente.

**Para quién es esta guía:**
- Desarrolladores web creando sitios inmobiliarios
- Equipos frontend integrando propiedades desde el backend
- Agencias que necesitan conectar múltiples webs a GHL_Front

---

## 🎯 Requisitos Previos

- [ ] Tener un `agency_id` (Location ID de GHL)
- [ ] Conocimientos básicos de JavaScript/TypeScript
- [ ] Familiaridad con fetch API o libraries HTTP (axios, etc.)

---

## 🚀 Inicio Rápido (5 pasos)

### Paso 1: Obtén tu Agency ID

Tu `agency_id` es el **Location ID** de tu subcuenta de GoHighLevel.

Ejemplo: `WpWPYfkF9tMdy8HV4UHM`

### Paso 2: Configura variables de entorno

**React (Vite):**
```env
# .env
VITE_API_URL=https://web-production-2573f.up.railway.app
VITE_AGENCY_ID=WpWPYfkF9tMdy8HV4UHM
```

**Next.js:**
```env
# .env.local
NEXT_PUBLIC_API_URL=https://web-production-2573f.up.railway.app
NEXT_PUBLIC_AGENCY_ID=WpWPYfkF9tMdy8HV4UHM
```

**Vue/Nuxt:**
```env
# .env
VITE_API_URL=https://web-production-2573f.up.railway.app
VITE_AGENCY_ID=WpWPYfkF9tMdy8HV4UHM
```

### Paso 3: Crea archivo de configuración

```typescript
// src/config.ts
export const API_CONFIG = {
  baseUrl: import.meta.env.VITE_API_URL || 'https://web-production-2573f.up.railway.app',
  agencyId: import.meta.env.VITE_AGENCY_ID || '',
};

export const ENDPOINTS = {
  properties: `${API_CONFIG.baseUrl}/api/properties/?agency_id=${API_CONFIG.agencyId}`,
  propertiesSearch: `${API_CONFIG.baseUrl}/api/properties/search/`,
  propertyDetail: (id: string) => `${API_CONFIG.baseUrl}/api/properties/${id}/?agency_id=${API_CONFIG.agencyId}`,
  locations: `${API_CONFIG.baseUrl}/api/locations/?agency_id=${API_CONFIG.agencyId}`,
};
```

### Paso 4: Realiza tu primera petición

```javascript
import { API_CONFIG, ENDPOINTS } from './config';

// Obtener todas las propiedades
async function fetchProperties() {
  const response = await fetch(ENDPOINTS.properties);
  const data = await response.json();
  console.log(data.results); // Array de propiedades
}

fetchProperties();
```

### Paso 5: ¡Listo! Ahora usa los endpoints avanzados

Consulta la sección **Ejemplos de Código** más abajo para hooks, componentes y patrones avanzados.

---

## 📡 Endpoints Disponibles

### 1. Listar Todas las Propiedades

**Endpoint:** `/api/properties/`
**Uso:** Página de inicio, listados básicos

```javascript
const response = await fetch(
  `https://web-production-2573f.up.railway.app/api/properties/?agency_id=${AGENCY_ID}`
);
const data = await response.json();
// data.results contiene el array de propiedades
```

---

### 2. Buscar con Filtros ⭐ NUEVO

**Endpoint:** `/api/properties/search/`
**Uso:** Página de búsqueda, filtros avanzados

**Filtros disponibles:**
- `type`: `"Villa"` | `"Apartment"` | `"Studio"`
- `location`: Nombre de zona (ej: `"Gràcia"`)
- `min_price` / `max_price`: Rango de precio
- `beds`: Número exacto de habitaciones
- `min_sqm`: Metros cuadrados mínimos
- `features`: `"Balcón,Garaje,Mascotas,Patio"` (separados por coma)
- `ordering`: `"precio"`, `"-precio"`, `"habitaciones"`, `"-habitaciones"`

**Ejemplo con filtros:**
```javascript
const params = new URLSearchParams({
  agency_id: 'ABC123',
  type: 'Apartment',
  location: 'Gràcia',
  min_price: '200000',
  max_price: '500000',
  beds: '3',
  features: 'Balcón,Garaje',
  ordering: '-precio' // Más caros primero
});

const response = await fetch(
  `https://web-production-2573f.up.railway.app/api/properties/search/?${params}`
);
const properties = await response.json();
```

---

### 3. Detalle de Propiedad

**Endpoint:** `/api/properties/<id>/`
**Uso:** Página de detalle de propiedad

```javascript
const propertyId = 'contact_abc123';
const response = await fetch(
  `https://web-production-2573f.up.railway.app/api/properties/${propertyId}/?agency_id=${AGENCY_ID}`
);
const property = await response.json();
```

---

### 4. Obtener Ubicaciones ⭐ NUEVO

**Endpoint:** `/api/locations/`
**Uso:** Popular dropdowns de filtros

```javascript
const response = await fetch(
  `https://web-production-2573f.up.railway.app/api/locations/?agency_id=${AGENCY_ID}`
);
const data = await response.json();
// data.locations es un array de { zona, municipio, provincia }
```

---

## 💻 Ejemplos de Código

### React Hook Personalizado

```typescript
// src/hooks/useProperties.ts
import { useState, useEffect } from 'react';
import { API_CONFIG, ENDPOINTS } from '../config';

interface Filters {
  type?: string;
  location?: string;
  minPrice?: number;
  maxPrice?: number;
  beds?: number;
  features?: string[];
}

export const useProperties = (filters?: Filters) => {
  const [properties, setProperties] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchProperties = async () => {
      setLoading(true);
      setError(null);

      const params = new URLSearchParams({
        agency_id: API_CONFIG.agencyId,
      });

      // Agregar filtros si existen
      if (filters?.type) params.append('type', filters.type);
      if (filters?.location) params.append('location', filters.location);
      if (filters?.minPrice) params.append('min_price', filters.minPrice.toString());
      if (filters?.maxPrice) params.append('max_price', filters.maxPrice.toString());
      if (filters?.beds) params.append('beds', filters.beds.toString());
      if (filters?.features?.length) params.append('features', filters.features.join(','));

      try {
        const response = await fetch(`${ENDPOINTS.propertiesSearch}?${params}`);

        if (!response.ok) {
          throw new Error('Error al obtener propiedades');
        }

        const data = await response.json();
        setProperties(data.results || data);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Error desconocido');
        console.error('Error fetching properties:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchProperties();
  }, [
    filters?.type,
    filters?.location,
    filters?.minPrice,
    filters?.maxPrice,
    filters?.beds,
    filters?.features?.join(',')
  ]);

  return { properties, loading, error };
};
```

**Uso del hook:**
```typescript
import { useProperties } from '../hooks/useProperties';

function PropertiesPage() {
  const [filters, setFilters] = useState({
    type: 'Apartment',
    minPrice: 200000,
    maxPrice: 500000,
  });

  const { properties, loading, error } = useProperties(filters);

  if (loading) return <div>Cargando propiedades...</div>;
  if (error) return <div>Error: {error}</div>;

  return (
    <div>
      <h1>Propiedades Disponibles</h1>
      <div className="properties-grid">
        {properties.map(property => (
          <PropertyCard key={property.id} property={property} />
        ))}
      </div>
    </div>
  );
}
```

---

### Vanilla JavaScript (Sin frameworks)

```javascript
// Función para obtener todas las propiedades
async function getAllProperties() {
  const AGENCY_ID = 'ABC123';

  try {
    const response = await fetch(
      `https://web-production-2573f.up.railway.app/api/properties/?agency_id=${AGENCY_ID}`
    );

    if (!response.ok) throw new Error('Error al obtener propiedades');

    const data = await response.json();
    return data.results;
  } catch (error) {
    console.error('Error:', error);
    return [];
  }
}

// Función para buscar con filtros
async function searchProperties(filters = {}) {
  const AGENCY_ID = 'ABC123';

  const params = new URLSearchParams({
    agency_id: AGENCY_ID,
    ...filters
  });

  try {
    const response = await fetch(
      `https://web-production-2573f.up.railway.app/api/properties/search/?${params}`
    );

    if (!response.ok) throw new Error('Error al buscar propiedades');

    const data = await response.json();
    return data.results || data;
  } catch (error) {
    console.error('Error:', error);
    return [];
  }
}

// Uso
searchProperties({
  type: 'Villa',
  min_price: 500000,
  location: 'Marbella'
}).then(properties => {
  console.log(`Encontradas ${properties.length} propiedades`);
  properties.forEach(prop => {
    console.log(`${prop.title} - ${prop.price}€`);
  });
});
```

---

### Vue 3 Composition API

```typescript
// composables/useProperties.ts
import { ref, watchEffect } from 'vue';
import { API_CONFIG, ENDPOINTS } from '../config';

export function useProperties(filters = {}) {
  const properties = ref([]);
  const loading = ref(true);
  const error = ref(null);

  watchEffect(async () => {
    loading.value = true;
    error.value = null;

    const params = new URLSearchParams({
      agency_id: API_CONFIG.agencyId,
      ...filters
    });

    try {
      const response = await fetch(`${ENDPOINTS.propertiesSearch}?${params}`);
      if (!response.ok) throw new Error('Error al obtener propiedades');

      const data = await response.json();
      properties.value = data.results || data;
    } catch (err) {
      error.value = err.message;
    } finally {
      loading.value = false;
    }
  });

  return { properties, loading, error };
}
```

**Uso en componente Vue:**
```vue
<script setup>
import { ref } from 'vue';
import { useProperties } from '@/composables/useProperties';

const filters = ref({
  type: 'Apartment',
  min_price: 200000
});

const { properties, loading, error } = useProperties(filters);
</script>

<template>
  <div>
    <div v-if="loading">Cargando...</div>
    <div v-else-if="error">Error: {{ error }}</div>
    <div v-else class="grid">
      <PropertyCard
        v-for="property in properties"
        :key="property.id"
        :property="property"
      />
    </div>
  </div>
</template>
```

---

## 🎨 Definiciones TypeScript

```typescript
// src/types.ts

export interface Property {
  id: string;              // ghl_contact_id
  title: string;           // Título generado
  price: number;           // Precio en euros (sin decimales)
  location: string;        // Nombre de la zona
  beds: number;            // Número de habitaciones
  sqm: number;             // Metros cuadrados
  type: 'Villa' | 'Apartment' | 'Studio';
  image: string;           // URL de la imagen principal
  images: string[];        // Array de URLs de imágenes
  features: string[];      // ["Balcón", "Garaje", "Mascotas", "Patio"]
  description: string;     // Descripción generada
}

export interface Location {
  zona: string;
  municipio: string;
  provincia: string;
}

export interface PropertiesResponse {
  count: number;
  next: string | null;
  previous: string | null;
  results: Property[];
}
```

---

## 🧩 Componente de Ejemplo Completo

```typescript
// components/PropertySearch.tsx
import React, { useState } from 'react';
import { useProperties } from '../hooks/useProperties';

const PropertySearch: React.FC = () => {
  const [filters, setFilters] = useState({
    type: '',
    location: '',
    minPrice: undefined,
    maxPrice: undefined,
  });

  const { properties, loading, error } = useProperties(filters);

  const handleFilterChange = (key: string, value: any) => {
    setFilters(prev => ({ ...prev, [key]: value }));
  };

  return (
    <div className="property-search">
      {/* Filtros */}
      <div className="filters">
        <select
          value={filters.type}
          onChange={(e) => handleFilterChange('type', e.target.value)}
        >
          <option value="">Todos los tipos</option>
          <option value="Villa">Villa</option>
          <option value="Apartment">Apartamento</option>
          <option value="Studio">Estudio</option>
        </select>

        <input
          type="number"
          placeholder="Precio mínimo"
          onChange={(e) => handleFilterChange('minPrice', Number(e.target.value) || undefined)}
        />

        <input
          type="number"
          placeholder="Precio máximo"
          onChange={(e) => handleFilterChange('maxPrice', Number(e.target.value) || undefined)}
        />

        <button onClick={() => setFilters({ type: '', location: '', minPrice: undefined, maxPrice: undefined })}>
          Limpiar filtros
        </button>
      </div>

      {/* Resultados */}
      {loading && (
        <div className="loading">Cargando propiedades...</div>
      )}

      {error && (
        <div className="error">Error: {error}</div>
      )}

      {!loading && !error && (
        <>
          <div className="results-count">
            {properties.length} propiedad{properties.length !== 1 ? 'es' : ''} encontrada{properties.length !== 1 ? 's' : ''}
          </div>

          <div className="properties-grid">
            {properties.map(property => (
              <div key={property.id} className="property-card">
                <img src={property.image} alt={property.title} />
                <h3>{property.title}</h3>
                <p className="price">{property.price.toLocaleString('es-ES')} €</p>
                <div className="specs">
                  <span>{property.beds} hab</span>
                  <span>{property.sqm} m²</span>
                  <span>{property.location}</span>
                </div>
                <div className="features">
                  {property.features.map(feature => (
                    <span key={feature} className="badge">{feature}</span>
                  ))}
                </div>
              </div>
            ))}
          </div>

          {properties.length === 0 && (
            <div className="no-results">
              No se encontraron propiedades con los filtros seleccionados.
            </div>
          )}
        </>
      )}
    </div>
  );
};

export default PropertySearch;
```

---

## ✅ Checklist de Integración

Completa estos pasos para integrar correctamente la API:

- [ ] **Configuración inicial**
  - [ ] Obtener `agency_id` de GHL
  - [ ] Configurar variables de entorno (`.env`)
  - [ ] Crear archivo `config.ts`

- [ ] **Tipos y definiciones**
  - [ ] Crear `types.ts` con interfaces TypeScript
  - [ ] Definir tipos para Property, Location, etc.

- [ ] **Implementación básica**
  - [ ] Implementar fetch a `/api/properties/` (listado básico)
  - [ ] Implementar fetch a `/api/properties/<id>/` (detalle)
  - [ ] Manejar estados de loading y error

- [ ] **Funcionalidades avanzadas**
  - [ ] Implementar búsqueda con filtros (`/api/properties/search/`)
  - [ ] Obtener ubicaciones (`/api/locations/`) para dropdowns
  - [ ] Implementar ordenamiento de resultados

- [ ] **Testing**
  - [ ] Testear con diferentes filtros
  - [ ] Verificar paginación
  - [ ] Testear en diferentes dispositivos

- [ ] **Deploy**
  - [ ] Configurar variables de entorno en producción
  - [ ] Verificar que las peticiones funcionen en producción
  - [ ] Testear desde el dominio final

---

## 🔧 Troubleshooting (Resolución de Problemas)

### ❌ Error: CORS

**Síntoma:**
```
Access to fetch at '...' has been blocked by CORS policy
```

**Solución:**
- La API ya tiene CORS habilitado globalmente
- Verifica que estés haciendo peticiones desde el **navegador** (no desde servidor Node.js)
- Asegúrate de que la URL sea correcta

---

### ❌ Error: No se devuelven propiedades

**Verificaciones:**
1. ¿Incluiste el parámetro `agency_id`?
   ```javascript
   // ❌ MAL
   fetch('/api/properties/')

   // ✅ BIEN
   fetch('/api/properties/?agency_id=ABC123')
   ```

2. ¿El `agency_id` es correcto?
3. ¿La agencia tiene propiedades en estado `"activo"`?
4. ¿Estás usando el endpoint correcto?

---

### ❌ Error: Filtros no funcionan

**Verificaciones:**
1. ¿Estás usando el endpoint `/api/properties/search/`?
   ```javascript
   // ❌ MAL - No soporta filtros
   fetch('/api/properties/?type=Villa')

   // ✅ BIEN - Endpoint con filtros
   fetch('/api/properties/search/?agency_id=ABC&type=Villa')
   ```

2. ¿Los valores de `features` coinciden exactamente?
   - ✅ Correcto: `"Balcón"`, `"Garaje"`, `"Mascotas"`, `"Patio"`
   - ❌ Incorrecto: `"balcon"`, `"garaje"`, `"pets"`

3. ¿Los parámetros están correctamente codificados?
   ```javascript
   const params = new URLSearchParams({
     features: 'Balcón,Garaje' // URLSearchParams codifica automáticamente
   });
   ```

---

### ❌ Error: Respuesta vacía o inesperada

**Verificaciones:**
1. Abre DevTools → Network
2. Verifica que la petición devuelva **200 OK**
3. Revisa el JSON de respuesta
4. Verifica que `data.results` exista (respuesta paginada)

```javascript
const data = await response.json();
console.log(data); // Ver estructura completa

// Respuesta paginada tiene esta estructura:
// { count: 10, next: "...", previous: null, results: [...] }

const properties = data.results || data; // Manejar ambos casos
```

---

## 📞 Soporte

Si tienes problemas con la integración, contacta al equipo técnico con:

1. Tu `agency_id`
2. URL completa de la petición que falla
3. Captura de pantalla del error (DevTools → Network)
4. Código relevante que estás usando

**Ejemplo de reporte:**
```
Agency ID: ABC123
URL: https://web-production-2573f.up.railway.app/api/properties/search/?agency_id=ABC123&type=Villa
Error: Devuelve 0 resultados cuando debería devolver 5
Código: [adjuntar código]
```

---

## 🚀 Próximos Pasos

Después de integrar la API básica:

1. **Optimización**
   - Implementar caché local (localStorage, IndexedDB)
   - Añadir debounce a filtros de búsqueda
   - Lazy loading de imágenes

2. **UX Avanzada**
   - Mapas interactivos con ubicaciones
   - Comparador de propiedades
   - Favoritos guardados localmente

3. **Analytics**
   - Tracking de propiedades más vistas
   - Análisis de filtros más usados
   - Conversión de visitas a contactos

---

## 📚 Recursos Adicionales

- [API_DOCS.md](./API_DOCS.md) - Documentación técnica completa de la API
- [GoHighLevel API](https://highlevel.stoplight.io/) - Documentación oficial de GHL
- Ejemplos en GitHub: *(próximamente)*

---

**Última actualización:** 2025-02-12
**Versión API:** 2.0
