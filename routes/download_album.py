# download_album.py

from flask import Blueprint, request, jsonify
import os
import requests
from mutagen.id3 import ID3, APIC, TIT2, TPE1, TALB, TRCK, TDRC
from mutagen.easyid3 import EasyID3
from io import BytesIO
import shutil
import zipfile
import logging
import tempfile

# Configuración
DEEZER_API_ALBUM = "https://api.deezer.com/album/" 
TMPFILES_API = "https://tmpfiles.org/api/v1/upload" 
DOWNLOAD_DIR = tempfile.gettempdir()  # O puedes usar otra carpeta temporal

# Logger básico
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

download_album_bp = Blueprint('download-album', __name__)


def sanitize_filename(name):
    return "".join(c for c in name if c.isalnum() or c in (" ", "-", "_")).strip()


def get_album_metadata(album_id):
    logger.info(f"Obteniendo metadatos del álbum {album_id}")
    response = requests.get(f"{DEEZER_API_ALBUM}{album_id}")
    if response.status_code != 200:
        logger.error(f"Error al obtener metadatos. Status: {response.status_code}")
        raise Exception("Error al obtener metadatos del álbum")
    return response.json()


def add_metadata_to_mp3(file_path, track, album_data, track_number=None):
    try:
        try:
            audio = EasyID3(file_path)
        except Exception:
            audio = EasyID3()

        # Manejar artistas
        contributors = track.get("contributors", [])
        artists = [artist["name"] for artist in contributors] if contributors else [
            track.get("artist", {}).get("name", "Unknown")]
        artist_str = ", ".join(artists)

        # Usar índice del bucle si está disponible
        number = str(track_number) if track_number else str(track.get("track_position", 1))

        # Añadir metadatos básicos
        audio["title"] = track.get("title", "Unknown Title")
        audio["artist"] = artist_str
        audio["album"] = album_data.get("title", "Unknown Album")
        audio["tracknumber"] = number
        audio["date"] = album_data.get("release_date", "").split("-")[0]
        audio.save(file_path)
        logger.info(f"Metadatos básicos añadidos a {file_path}")

        # Añadir portada del álbum
        try:
            id3 = ID3(file_path)
            cover_url = album_data.get("cover_xl") or album_data.get("cover_big")
            if cover_url:
                cover_data = requests.get(cover_url).content
                id3.add(
                    APIC(
                        encoding=3,
                        mime="image/jpeg",
                        type=3,
                        desc="Cover",
                        data=cover_data
                    )
                )
                id3.save(v2_version=3)
                logger.info(f"Portada añadida a {file_path}")
        except Exception as e:
            logger.error(f"Error añadiendo portada: {e}")

    except Exception as e:
        logger.error(f"Error en add_metadata_to_mp3: {str(e)}")
        raise


def create_zip_file(folder_path):
    temp_dir = tempfile.mkdtemp()
    zip_file_name = os.path.basename(folder_path) + ".zip"
    zip_file_path = os.path.join(temp_dir, zip_file_name)

    file_count = 0
    with zipfile.ZipFile(zip_file_path, 'w') as zipf:
        for root, _, files in os.walk(folder_path):
            for file in files:
                if file.endswith(".mp3"):
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, folder_path)
                    zipf.write(file_path, arcname)
                    file_count += 1
                    logger.debug(f"Añadido al ZIP: {file_path}")

    if file_count == 0:
        raise Exception("No se encontraron archivos para comprimir")

    # Leer contenido del ZIP
    with open(zip_file_path, 'rb') as f:
        zip_data = f.read()
    logger.info(f"ZIP creado con {file_count} archivos ({len(zip_data)} bytes)")

    # Limpiar el directorio temporal
    shutil.rmtree(temp_dir)
    return zip_data


def upload_to_tmpfiles(zip_data, filename):
    logger.info(f"Subiendo {filename} ({len(zip_data)} bytes) a tmpfiles.org")
    if len(zip_data) == 0:
        raise Exception("El archivo ZIP está vacío")

    file_obj = BytesIO(zip_data)
    files = {'file': (filename, file_obj, 'application/zip')}
    response = requests.post(TMPFILES_API, files=files)
    response.raise_for_status()
    json_response = response.json()

    if not json_response.get('data') or not json_response['data'].get('url'):
        logger.error(f"Respuesta inesperada de tmpfiles.org: {json_response}")
        raise Exception("La estructura de la respuesta no es la esperada")

    base_url = json_response['data']['url']
    download_url = base_url.replace("https://tmpfiles.org/",  "https://tmpfiles.org/dl/")  + "/" + filename

    return {
        "download_url": download_url,
        "delete_url": json_response.get("data", {}).get("delete_url")
    }


def cleanup_folder(folder_path):
    logger.info(f"Limpiando carpeta temporal: {folder_path}")
    for root, dirs, files in os.walk(folder_path, topdown=False):
        for name in files:
            os.remove(os.path.join(root, name))
        for name in dirs:
            os.rmdir(os.path.join(root, name))
    os.rmdir(folder_path)
    logger.info("Limpieza completada")


@download_album_bp.route('/', methods=['GET'])
def download_album():
    album_id = request.args.get('album_id')
    logger.info(f"Iniciando descarga para album_id: {album_id}")

    if not album_id or not album_id.isdigit():
        logger.error("ID de álbum inválido")
        return jsonify({"error": "Se requiere un ID de álbum válido (número)"}), 400

    try:
        # 1. Obtener metadatos del álbum
        album_data = get_album_metadata(album_id)
        logger.info(f"Álbum: {album_data.get('title')} - Artista: {album_data.get('artist', {}).get('name')}")

        artist_name = album_data["artist"]["name"]
        album_title = album_data["title"]
        release_year = album_data["release_date"].split("-")[0]

        # Crear nombre de carpeta seguro
        safe_artist = sanitize_filename(artist_name)
        safe_album = sanitize_filename(album_title)
        folder_name = f"{safe_artist} - {safe_album} ({release_year})"
        folder_path = os.path.join(DOWNLOAD_DIR, folder_name)
        os.makedirs(folder_path, exist_ok=True)
        logger.info(f"Carpeta de descarga: {folder_path}")

        # 2. Descargar pistas
        tracks = album_data.get("tracks", {}).get("data", [])
        if not tracks:
            logger.error("Álbum no tiene pistas disponibles")
            return jsonify({"error": "Este álbum no tiene pistas disponibles"}), 400

        logger.info(f"Descargando {len(tracks)} pistas...")
        downloaded_files = []

        for idx, track in enumerate(tracks, start=1):
            song_id = track["id"]
            song_title = track["title"]

            # Descargar canción
            download_link = track.get("preview")
            if not download_link:
                logger.warning(f"Pista {song_title} no tiene link de descarga")
                continue

            logger.info(f"Descargando pista {idx}: {song_title}")
            response = requests.get(download_link)
            if response.status_code != 200:
                logger.warning(f"No se pudo descargar {song_title}")
                continue

            # Guardar archivo temporal
            file_path = os.path.join(folder_path, f"{song_id}.mp3")
            with open(file_path, "wb") as f:
                f.write(response.content)

            # Añadir metadatos
            logger.info(f"Añadiendo metadatos a {file_path}")
            add_metadata_to_mp3(file_path, track, album_data, idx)

            # Renombrar archivo
            new_file_name = f"{idx:02d}. {sanitize_filename(artist_name)} - {sanitize_filename(track['title'])}.mp3"
            new_file_path = os.path.join(folder_path, new_file_name)
            os.rename(file_path, new_file_path)
            downloaded_files.append(new_file_name)

        if not downloaded_files:
            logger.error("No se descargó ninguna pista")
            return jsonify({"error": "No se descargó ninguna pista del álbum"}), 400

        # 3. Crear ZIP
        zip_data = create_zip_file(folder_path)

        # 4. Subir a tmpfiles.org
        logger.info("Subiendo a tmpfiles.org...")
        upload_response = upload_to_tmpfiles(zip_data, f"{folder_name}.zip")

        # 5. Limpiar
        cleanup_folder(folder_path)

        # 6. Devolver respuesta
        logger.info("Proceso completado exitosamente")
        return jsonify({
            "status": "success",
            "download_url": upload_response['download_url'],
            "delete_url": upload_response.get('delete_url', ''),
            "filename": f"{folder_name}.zip",
            "album": album_title,
            "artist": artist_name,
            "year": release_year,
            "message": "Álbum descargado y comprimido con éxito"
        })

    except Exception as e:
        logger.error(f"Error procesando álbum: {str(e)}", exc_info=True)
        return jsonify({
            "error": str(e),
            "message": "Ocurrió un error al procesar el álbum"
        }), 500