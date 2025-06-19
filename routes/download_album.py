# routes/download_album.py

import os
import requests
import zipfile
from io import BytesIO
from flask import Blueprint, jsonify, request
from deezspot.deezloader import DeeLogin
from mutagen.id3 import ID3, TIT2, TPE1, TALB, TRCK, TYER, APIC
from mutagen.easyid3 import EasyID3
import logging

# Configura logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DOWNLOAD_DIR = './downloads'
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

DEEZER_API_ALBUM = "https://api.deezer.com/album/"
TMPFILES_API = "https://tmpfiles.org/api/v1/upload"

deezer = DeeLogin(arl='87f304e8bff197c8877dac3ca0a21d0ef6505af952ee392f856c30527508e177c9d0f90af069e248fee50cbe9b200e3962537f4eff8c8ef2d7d564b30c74e06d6c8779c3c0ed002e92792d403ab7522c5c8102ca4dadb319a02e4c8c5729e739')

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

def add_metadata_to_mp3(file_path, track, album_data):
    try:
        try:
            audio = EasyID3(file_path)
        except:
            audio = EasyID3()
            audio.save(file_path)
            audio = EasyID3(file_path)

        # Manejar artistas
        contributors = track.get("contributors", [])
        artists = [artist["name"] for artist in contributors] if contributors else [track.get("artist", {}).get("name", "Unknown")]
        artist_str = ", ".join(artists)

        # Manejar número de pista (track_position o TRACK_NUMBER)
        track_number = str(track.get("track_position", track.get("TRACK_NUMBER", 1)))

        # Añadir metadatos básicos
        audio["title"] = track.get("title", "Unknown Title")
        audio["artist"] = artist_str
        audio["album"] = album_data.get("title", "Unknown Album")
        audio["tracknumber"] = track_number
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

def upload_to_tmpfiles(zip_data, filename):
    try:
        logger.info(f"Subiendo {filename} ({len(zip_data)} bytes) a tmpfiles.org")
        
        if len(zip_data) == 0:
            raise Exception("El archivo ZIP está vacío")
        
        files = {'file': (filename, zip_data, 'application/zip')}
        
        response = requests.post(TMPFILES_API, files=files)
        response.raise_for_status()
        
        json_response = response.json()
        
        if not json_response.get('url'):
            raise Exception("La API no devolvió una URL de descarga válida")
        
        logger.info("Subida exitosa a tmpfiles.org")
        return {
            'download_url': json_response['url'],
            'delete_url': json_response.get('delete_url', '')
        }
    except Exception as e:
        logger.error(f"Error subiendo a tmpfiles.org: {str(e)}")
        raise

def create_zip_file(folder_path):
    try:
        memory_zip = BytesIO()
        file_count = 0
        
        with zipfile.ZipFile(memory_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, _, files in os.walk(folder_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, folder_path)
                    zipf.write(file_path, arcname)
                    file_count += 1
                    logger.debug(f"Añadido al ZIP: {file_path}")
        
        if file_count == 0:
            raise Exception("No se encontraron archivos para comprimir")
        
        memory_zip.seek(0)
        zip_data = memory_zip.getvalue()
        
        logger.info(f"ZIP creado con {file_count} archivos ({len(zip_data)} bytes)")
        return zip_data
    except Exception as e:
        logger.error(f"Error creando ZIP: {str(e)}")
        raise

def cleanup_folder(folder_path):
    try:
        logger.info(f"Limpiando carpeta temporal: {folder_path}")
        for root, dirs, files in os.walk(folder_path, topdown=False):
            for name in files:
                os.remove(os.path.join(root, name))
            for name in dirs:
                os.rmdir(os.path.join(root, name))
        os.rmdir(folder_path)
        logger.info("Limpieza completada")
    except Exception as e:
        logger.error(f"Error limpiando carpeta: {str(e)}")
        raise

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
            track_url = f"https://www.deezer.com/track/{song_id}"
            logger.info(f"[{idx}/{len(tracks)}] Procesando: {track.get('title')}")

            # Descargar pista
            deezer.download_trackdee(
                link_track=track_url,
                output_dir=folder_path,
                quality_download='MP3_128',
                recursive_quality=True,
                recursive_download=False
            )

            # Procesar archivo descargado
            for root, _, files in os.walk(folder_path):
                for file in files:
                    if file.endswith(".mp3") and file not in downloaded_files:
                        file_path = os.path.join(root, file)

                        if os.path.getsize(file_path) == 0:
                            logger.warning(f"Archivo vacío, eliminando: {file_path}")
                            os.remove(file_path)
                            continue

                        # Añadir metadatos
                        logger.info(f"Añadiendo metadatos a {file_path}")
                        add_metadata_to_mp3(file_path, track, album_data)

                        # Renombrar archivo
                        new_file_name = f"{idx:02d}. {sanitize_filename(artist_name)} - {sanitize_filename(track['title'])}.mp3"
                        new_file_path = os.path.join(folder_path, new_file_name)
                        os.rename(file_path, new_file_path)
                        downloaded_files.append(new_file_name)
                        logger.info(f"Archivo renombrado a: {new_file_path}")
                        break

        # 3. Crear ZIP
        zip_file_name = f"{safe_artist} - {safe_album} ({release_year}).zip"
        logger.info(f"Creando archivo ZIP: {zip_file_name}")
        zip_data = create_zip_file(folder_path)

        # 4. Subir a tmpfiles.org
        logger.info("Subiendo a tmpfiles.org...")
        upload_response = upload_to_tmpfiles(zip_data, zip_file_name)
        
        # 5. Limpiar
        cleanup_folder(folder_path)

        # 6. Respuesta exitosa
        logger.info("Proceso completado exitosamente")
        return jsonify({
            "status": "success",
            "download_url": upload_response['download_url'],
            "delete_url": upload_response.get('delete_url', ''),
            "filename": zip_file_name,
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