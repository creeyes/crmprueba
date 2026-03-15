# Changelog - Rama v3 (Sincronización Bidireccional de Propiedades)

Este documento detalla las modificaciones realizadas en el backend de Django (`crmprueba`) para habilitar el guardado y edición de propiedades directamente desde el dashboard de React, manteniendo la integridad de datos con **Go High Level (GHL)**.

## 🚀 Resumen de Cambios
Se ha transformado la API de propiedades (que antes era solo de lectura) en una API transaccional completa que orquesta la creación de registros en GHL y su posterior persistencia en la base de datos local.

---

## 🛠️ Archivos Modificados

### 1. `GHL_Front/views.py`
Se han actualizado las vistas principales para soportar escritura:
- **`PublicPropertyList`**: Se ha implementado el método `POST`.
    - Recibe los datos del formulario de React.
    - Obtiene el token de la agencia y crea un "Placeholder" (registro vacío con ID) en el Custom Object de GHL.
    - Limpia y formatea los datos recibidos mediante helpers.
    - Guarda la propiedad en la base de datos local vinculándola al `ghl_contact_id` generado.
- **`PublicPropertyDetail`**: Se ha cambiado de `RetrieveAPIView` a `RetrieveUpdateAPIView` habilitando el método `PUT`.
    - Sincroniza los cambios realizados en el panel de React directamente hacia el registro correspondiente en GHL.
    - Actualiza los campos locales (`precio`, `habitaciones`, `metros`, `zona`, etc.) instantáneamente.

### 2. `ghl_middleware/utils.py`
Se han añadido funciones de comunicación de bajo nivel con la API de GHL:
- **`ghl_create_property_record`**: Maneja la llamada `POST` a `/objects/{id}/records/` de GHL.
- **`ghl_update_property_record`**: Maneja la llamada `PUT` para actualizar registros existentes en GHL.
- **Sistema de Prevención de Bounce-back**: Se ha integrado `_recent_syncs.add(id)` en las vistas. Esto evita que los webhooks automáticos de GHL generen bucles infinitos al detectar que nosotros mismos fuimos quienes originamos el cambio.

### 3. `ghl_middleware/helpers.py` (Referenciado)
- Se han utilizado los helpers existentes para asegurar que los strings de moneda (`€`, `$`), las preferencias (`si/no`) y los estados se guarden con el formato correcto esperado por los modelos de Django.

---

## 📋 Flujo de Datos
1. **Frontend (React)**: Envía JSON con los datos de la propiedad a `/api/properties/`.
2. **Backend (Django)**: 
    - Valida el `agency_id`.
    - Solicita a GHL la creación del registro.
    - Recibe el `ghl_contact_id` de GHL.
    - Crea la entrada en la DB local de Django.
3. **Resultado**: La propiedad aparece instalada correctamente en GHL y visible en el panel de React inmediatamente después de guardar.

---

## 🛠️ Correcciones Adicionales (Bugfixes)

Tras la implementación inicial, se resolvieron dos incidencias que impedían el correcto funcionamiento:

1. **Importación Faltante en Backend (`NameError`)**:
    - **Archivo:** `GHL_Front/views.py`
    - **Problema:** Un error borró accidentalmente importes necesarios (`json`, `base64`, `hashlib` y el propio `PropiedadPublicaSerializer`).
    - **Solución:** Restauradas las dependencias al principio del fichero.
2. **Error de Tipado en Precios (`TypeError`)**:
    - **Archivos:** `helpers.py` (Backend) y `App.tsx` (Frontend React)
    - **Problema:** La función `clean_currency()` del backend asume por fuerza que recibe un string, empezando con moneda (`€150`). React estaba enviando un número puro (ej. `150`), provocando el error `int object is not subscriptable` en backend.
    - **Solución:** Se ajustó el payload de la función `handleSaveProperty` en el frontend, añadiendo condicionales para envolver el precio (`editForm.price`) como string e insertando una `€` al principio de forma automática antes de hacer la petición `POST`/`PUT`.

---

> [!IMPORTANT]
> Los cambios se han aplicado localmente. Se debe ejecutar un *commit* y *push* desde el panel o CLI de control de versiones para verlos reflejados online en la rama v3.
