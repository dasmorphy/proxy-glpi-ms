import mimetypes
import os
import uuid

from loguru import logger
from werkzeug.utils import secure_filename

from swagger_server.config.access import access
from swagger_server.exception.custom_error_exception import CustomAPIException

# Utilidades para guardar en disco los documentos adjuntos de una inspección.

ALLOWED_EXTENSIONS = {
    "pdf",
    "png", "jpg", "jpeg", "gif", "webp", "bmp", "heic",
    "doc", "docx", "xls", "xlsx", "ppt", "pptx", "csv", "txt",
}


def get_documents_folder():
    return access()["STORAGE"]["INSPECTION_DOCUMENTS"]


def get_extension(filename):
    return os.path.splitext(filename or "")[1].lower().lstrip(".")


def clean_files(files):
    """Descarta los campos de archivo enviados vacíos desde el front."""
    return [file for file in (files or []) if file and file.filename]


def validate_documents(files):
    invalid = [
        file.filename
        for file in files
        if get_extension(file.filename) not in ALLOWED_EXTENSIONS
    ]
    if invalid:
        raise CustomAPIException(
            f"Tipo de archivo no permitido: {', '.join(invalid)}. "
            f"Extensiones permitidas: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
            400,
        )


def save_document(file, inspection_id):
    """Guarda el archivo y retorna la ruta relativa que se registra en BD."""
    folder = get_documents_folder()
    os.makedirs(folder, exist_ok=True)

    original_name = secure_filename(file.filename) or f"documento.{get_extension(file.filename)}"
    filename = f"{inspection_id}_{uuid.uuid4().hex[:12]}_{original_name}"
    document_path = os.path.join(folder, filename).replace("\\", "/")
    file.save(document_path)
    return document_path


def document_mimetype(filename, declared=None):
    """Tipo MIME por extensión; si no se reconoce se usa el que envió el navegador."""
    guessed, _ = mimetypes.guess_type(filename or "")
    return guessed or declared or "application/octet-stream"


def document_name(document_path):
    """Nombre original del archivo: se guarda como {inspection_id}_{uuid}_{nombre}."""
    filename = (document_path or "").replace("\\", "/").rsplit("/", 1)[-1]
    parts = filename.split("_", 2)
    return parts[2] if len(parts) == 3 else filename


def resolve_document_path(document_path):
    """Ruta absoluta del archivo, solo si existe y está dentro de la carpeta de documentos."""
    folder = os.path.realpath(get_documents_folder())
    full_path = os.path.realpath(document_path or "")
    try:
        inside_folder = os.path.commonpath([folder, full_path]) == folder
    except ValueError:  # rutas en distintas unidades (Windows)
        inside_folder = False
    if not inside_folder or not os.path.isfile(full_path):
        raise CustomAPIException("El archivo del documento no existe en el servidor", 404)
    return full_path


def remove_documents(document_paths):
    """Elimina archivos ya escritos cuando la transacción no se completa."""
    for document_path in document_paths:
        try:
            os.remove(document_path)
        except OSError as exception:
            logger.warning("No se pudo eliminar el documento {}: {}", document_path, str(exception))
