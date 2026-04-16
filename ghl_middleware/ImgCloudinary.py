import re
import os
import cloudinary.uploader
import time
from cloudinary.utils import cloudinary_url

def upload_img_model(archivos):
    """
    Recibe una lista de archivos.
    Sube a Cloudinary los ficheros con el nombre base (sin extensión) y devuelve una lista de 'public_id's.
    """
    LIMITE_TAMANO = 10 * 1024 * 1024
    
    for archivo in archivos:
        if getattr(archivo, 'size', 0) > LIMITE_TAMANO:
            print(f"Error: El archivo {getattr(archivo, 'name', 'Desconocido')} supera el límite de 10MB.")
            return []
            
    public_ids = []
    print(f"ARCHIVO: ImgCloudinary.py, LINEA: 22 - Han llegado {len(archivos)} archivos para subir.")
    
    for archivo in archivos:
        try:
            # LIMPIEZA: Quitamos la extensión para evitar duplicados en la URL (ej: .jpg.jpg)
            nombre_base = os.path.splitext(archivo.name)[0]
            
            resultado = cloudinary.uploader.upload(
                archivo,
                resource_type="image",
                folder="pisosImagenes/",
                type="authenticated",
                public_id = nombre_base
            )
            public_ids.append(resultado['public_id'])
            
        except Exception as e:
            print(f"Error subiendo el archivo a Cloudinary: {e}")
            
    print(f"ARCHIVO: ImgCloudinary.py, LINEA: 37 - Subida finalizada. IDs obtenidos (sin extensión): {public_ids}")
    return public_ids

def generar_url_firmada(public_ids, resource_type="image", minutes_valid=10):
    """
    Recibe un string o una lista de public_ids y devuelve sus URLs firmadas.
    """
    if not public_ids:
        return []

    is_single = isinstance(public_ids, str)
    if is_single:
        public_ids = [public_ids]
        
    urls = []
    for pid in public_ids:
        # Por seguridad, si el ID que llega tiene extensión, la limpiamos aquí también
        pid_clean = os.path.splitext(pid)[0]
        try:
            url, options = cloudinary_url(
                pid_clean,
                resource_type=resource_type,
                type="authenticated",
                sign_url=True,
                secure=True,
                expires_at=int(time.time() + (minutes_valid * 60))
            )
            urls.append(url)
        except Exception as e:
            print(f"Error generando URL para {pid_clean}: {e}")
            urls.append(None)
        
    return urls[0] if is_single else urls

def eliminar_recurso_cloudinary(public_ids, resource_type="image"):
    """
    Borra archivos de Cloudinary. Limpia las extensiones por si acaso vienen en la lista.
    """
    if not public_ids:
        return True

    is_single = isinstance(public_ids, str)
    if is_single:
        public_ids = [public_ids]

    todos_eliminados = True
    print(f"ARCHIVO: ImgCloudinary.py, LINEA: 80 - Solicitud de borrado en Cloudinary para IDs: {public_ids}")
    for pid in public_ids:
        pid_clean = os.path.splitext(pid)[0]
        try:
            resultado = cloudinary.uploader.destroy(
                pid_clean, 
                resource_type=resource_type,
                type="authenticated",
                invalidate=True 
            )
            
            if resultado.get('result') == 'ok':
                print(f"ARCHIVO: ImgCloudinary.py, LINEA: 89 - Eliminado con éxito de Cloudinary: {pid_clean}")
            else:
                print(f"ARCHIVO: ImgCloudinary.py, LINEA: 92 - Error en Cloudinary {pid_clean}: {resultado}")
                todos_eliminados = False
                
        except Exception as e:
            print(f"Error al conectar con Cloudinary para borrar {pid_clean}: {e}")
            todos_eliminados = False
            
    return todos_eliminados

def extraer_public_id(url):
    """
    Extrae el publicId de una URL buscando directamente desde la carpeta 'pisosImagenes/'.
    """
    if not url:
        return None
    
    # Buscamos 'pisosImagenes/' y capturamos todo lo que sigue hasta el final o un query param
    match = re.search(r'(pisosImagenes/.*)', url, re.IGNORECASE)
    if match:
        path = match.group(1).split('?')[0] # Limpiar query params (?s=...)
        return os.path.splitext(path)[0]   # Limpiar extensiones (.jpg, etc)
    
    return None