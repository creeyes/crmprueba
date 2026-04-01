import cloudinary.uploader
import time
from cloudinary.utils import cloudinary_url

def upload_img_model(archivos):
    """
    Recibe una lista de archivos.
    Comprueba que ninguno supere los 10MB. Si alguno lo supera, 
    imprime un mensaje y devuelve una lista vacía.
    Sube a Cloudinary los ficheros y devuelve una lista de 'public_id's.
    """
    LIMITE_TAMANO = 10 * 1024 * 1024
    
    # Comprobación de tamaños
    for archivo in archivos:
        if getattr(archivo, 'size', 0) > LIMITE_TAMANO:
            print(f"Error: El archivo {getattr(archivo, 'name', 'Desconocido')} supera el límite de 10MB.")
            return []
            
    public_ids = []
    
    for archivo in archivos:
        try:
            resultado = cloudinary.uploader.upload(
                archivo,
                resource_type="image",
                folder="pisosImagenes/",
                type="authenticated",
                public_id = archivo.name # Opcional: mantener el nombre original
            )
            public_ids.append(resultado['public_id'])
            
        except Exception as e:
            print(f"Error subiendo el archivo a Cloudinary: {e}")
            
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
        try:
            url, options = cloudinary_url(
                pid,
                resource_type=resource_type,
                type="authenticated",
                sign_url=True,
                secure=True,
                expires_at=int(time.time() + (minutes_valid * 60))
            )
            urls.append(url)
        except Exception as e:
            print(f"Error generando URL para {pid}: {e}")
            urls.append(None)
        
    return urls[0] if is_single else urls

def eliminar_recurso_cloudinary(public_ids, resource_type="image"):
    """
    Borra archivos de Cloudinary iterando sobre una lista de public_id.
    """
    if not public_ids:
        return True

    is_single = isinstance(public_ids, str)
    if is_single:
        public_ids = [public_ids]

    todos_eliminados = True
    for pid in public_ids:
        try:
            resultado = cloudinary.uploader.destroy(
                pid, 
                resource_type=resource_type,
                invalidate=True 
            )
            
            if resultado.get('result') == 'ok':
                print(f"Eliminado con éxito de Cloudinary: {pid}")
            else:
                print(f"No se encontró el recurso o error al eliminar {pid}: {resultado}")
                todos_eliminados = False
                
        except Exception as e:
            print(f"Error al conectar con Cloudinary para borrar {pid}: {e}")
            todos_eliminados = False
            
    return todos_eliminados