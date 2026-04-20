# GHL_Front API Documentation

**Base URL (Producción):** `https://web-production-2573f.up.railway.app/api/`

Esta es la documentación técnica de la API REST de GHL_Front para propiedades inmobiliarias.

---

## 📋 Endpoints Disponibles

### 1. Listar Propiedades (Básico)

**GET** `/properties/`

Devuelve un listado paginado de todas las propiedades activas de una agencia.

**Parámetros requeridos:**
- `agency_id` (string): ID de la agencia GHL (Location ID)

**Parámetros opcionales:**
- `page` (number): Número de página (default: 1)
- `page_size` (number): Resultados por página (default: 20, max: 100)

**Ejemplo:**
```
GET /api/properties/?agency_id=WpWPYfkF9tMdy8HV4UHM&page=1&page_size=20
```

**Respuesta:**
```json
{
  "count": 42,
  "next": "https://web-production-2573f.up.railway.app/api/properties/?agency_id=WpWPYfkF9tMdy8HV4UHM&page=2",
  "previous": null,
  "results": [
    {
      "id": 1,
      "ghl_id": "contact_abc123",
      "title": "Oportunidad en Gràcia, Barcelona",
      "price": 450000,
      "location": "Gràcia",
      "beds": 3,
      "sqm": 85,
      "type": "Apartment",
      "image": "https://example.com/image1.jpg",
      "images": ["https://example.com/image1.jpg", "https://example.com/image2.jpg"],
      "features": ["Balcón", "Garaje"],
      "description": "Excelente Apartment en Gràcia con 85m² y 3 habitaciones. Contáctanos para visitar."
    }
  ]
}
```

---

### 2. Buscar Propiedades (Con Filtros) ⭐ NUEVO

**GET** `/properties/search/`

Endpoint avanzado con filtros para búsqueda de propiedades.

**Parámetros requeridos:**
- `agency_id` (string): ID de la agencia GHL

**Parámetros opcionales (filtros):**

| Parámetro | Tipo | Descripción | Valores posibles |
|-----------|------|-------------|------------------|
| `type` | string | Tipo de propiedad | `Villa`, `Apartment`, `Studio` |
| `location` | string | Nombre de la zona | Ej: `"Gràcia"`, `"Sarrià"` |
| `min_price` | number | Precio mínimo | Cualquier número |
| `max_price` | number | Precio máximo | Cualquier número |
| `beds` | number | Número exacto de habitaciones | 0, 1, 2, 3, 4, 5+ |
| `min_sqm` | number | Metros cuadrados mínimos | Cualquier número |
| `features` | string | Características (separadas por coma) | `Balcón`, `Garaje`, `Mascotas`, `Patio` |
| `ordering` | string | Campo de ordenamiento | `precio`, `-precio`, `habitaciones`, `-habitaciones` |

**Lógica de filtro `type`:**
- `Villa`: Propiedades con más de 4 habitaciones
- `Apartment`: Propiedades con 1 a 4 habitaciones
- `Studio`: Propiedades con 0 habitaciones

**Ejemplos:**

Búsqueda simple:
```
GET /api/properties/search/?agency_id=ABC123&type=Apartment
```

Búsqueda con múltiples filtros:
```
GET /api/properties/search/?agency_id=ABC123&type=Apartment&location=Gràcia&min_price=200000&max_price=500000&features=Balcón,Garaje&ordering=-precio
```

**Respuesta:** Igual formato que el endpoint básico (paginado).

---

### 3. Detalle de Propiedad

**GET** `/properties/<ghl_contact_id>/`

Devuelve los detalles de una propiedad específica.

**Parámetros de URL:**
- `ghl_contact_id` (string): ID del contacto de GHL (ID de la propiedad)

**Parámetros opcionales:**
- `agency_id` (string): ID de la agencia (recomendado para seguridad)

**Ejemplo:**
```
GET /api/properties/contact_abc123/?agency_id=ABC123
```

**Respuesta:**
```json
{
  "id": 1,
  "ghl_id": "contact_abc123",
  "title": "Oportunidad en Gràcia, Barcelona",
  "price": 450000,
  "location": "Gràcia",
  "beds": 3,
  "sqm": 85,
  "type": "Apartment",
  "image": "https://example.com/image1.jpg",
  "images": ["https://example.com/image1.jpg", "https://example.com/image2.jpg"],
  "features": ["Balcón", "Garaje"],
  "description": "Excelente Apartment en Gràcia con 85m² y 3 habitaciones. Contáctanos para visitar."
}
```

---

### 4. Ubicaciones Disponibles ⭐ NUEVO

**GET** `/locations/`

Devuelve todas las ubicaciones (zonas) únicas que tienen propiedades activas para una agencia.

**Parámetros requeridos:**
- `agency_id` (string): ID de la agencia GHL

**Uso:** Para popular dropdowns de filtros de ubicación en el frontend.

**Ejemplo:**
```
GET /api/locations/?agency_id=ABC123
```

**Respuesta:**
```json
{
  "count": 5,
  "locations": [
    {
      "zona": "Gràcia",
      "municipio": "Barcelona",
      "provincia": "Barcelona"
    },
    {
      "zona": "Sarrià",
      "municipio": "Barcelona",
      "provincia": "Barcelona"
    },
    {
      "zona": "Eixample",
      "municipio": "Barcelona",
      "provincia": "Barcelona"
    }
  ]
}
```

---

## 📦 Formato de Datos

### Objeto Property (Propiedad)

```typescript
interface Property {
  id: number;              // ID numérico de Django (id_django)
  ghl_id: string;          // ghl_contact_id (ID del contacto en GHL)
  title: string;           // Título generado automáticamente
  price: number;           // Precio sin decimales (EUR)
  location: string;        // Nombre de la zona
  beds: number;            // Número de habitaciones
  sqm: number;             // Metros cuadrados
  type: string;            // "Villa" | "Apartment" | "Studio"
  image: string;           // URL de la primera imagen (o placeholder)
  images: string[];        // Array de URLs de todas las imágenes
  features: string[];      // ["Balcón", "Garaje", "Mascotas", "Patio"]
  description: string;     // Descripción generada automáticamente
}
```

### Objeto Location (Ubicación)

```typescript
interface Location {
  zona: string;            // Nombre de la zona (ej: "Gràcia")
  municipio: string;       // Nombre del municipio (ej: "Barcelona")
  provincia: string;       // Nombre de la provincia (ej: "Barcelona")
}
```

---

## 🔐 Autenticación y Seguridad

- **Sin autenticación requerida**: Todos los endpoints son públicos
- **CORS habilitado**: La API acepta peticiones desde cualquier origen
- **Filtrado por agencia**: Siempre se debe pasar `agency_id` para aislar datos entre agencias
- **Solo propiedades activas**: Solo se devuelven propiedades con `estado='activo'`

---

## 📄 Paginación

Todos los endpoints de listado (`/properties/` y `/properties/search/`) están paginados.

**Parámetros:**
- `page`: Número de página (default: 1)
- `page_size`: Tamaño de página (default: 20, max: 100)

**Respuesta paginada:**
```json
{
  "count": 150,           // Total de resultados
  "next": "URL...",       // URL de la siguiente página (null si no hay más)
  "previous": "URL...",   // URL de la página anterior (null si es la primera)
  "results": [...]        // Array de propiedades
}
```

---

## ⚠️ Códigos de Error

| Código | Descripción |
|--------|-------------|
| 200 | OK - Petición exitosa |
| 400 | Bad Request - Parámetro `agency_id` faltante o inválido |
| 404 | Not Found - Propiedad no encontrada |
| 500 | Internal Server Error - Error del servidor |

**Ejemplo de error:**
```json
{
  "error": "agency_id es requerido"
}
```

---

## 🔍 Optimizaciones

- **N+1 queries resueltas**: Uso de `select_related` para evitar consultas múltiples
- **Índices de base de datos**: Índices compuestos en campos frecuentemente filtrados
- **Paginación**: Evita devolver todos los datos de golpe
- **Filtrado en base de datos**: Los filtros se aplican a nivel de SQL, no en Python

---

## 📞 Soporte Técnico

Para reportar problemas o solicitar ayuda:
- Incluir `agency_id` y URL de la petición
- Captura de pantalla del error (DevTools → Network)
- Descripción del comportamiento esperado vs actual

---

## 📝 Changelog

### v2.0 (2025-02-12)
- ✅ Agregado endpoint `/api/properties/search/` con filtros avanzados
- ✅ Agregado endpoint `/api/locations/` para obtener ubicaciones disponibles
- ✅ Soporte para filtros: type, location, price, beds, sqm, features, ordering

### v1.0 (Inicial)
- ✅ Endpoint `/api/properties/` para listar propiedades
- ✅ Endpoint `/api/properties/<id>/` para detalle de propiedad
- ✅ Paginación básica
- ✅ Serialización de propiedades
