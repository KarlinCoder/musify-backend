import os
import shutil
import tempfile
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

#a5925e3ab97053f14670f20b485fcb51abc817a926d5cd3f93ad62caa21a8cb08914805b0447f3c9625e2a3743039b8d735fa1d1a6dd11f3d77d3172d6291f1f5e0961903b48399edcec0542f7ff422247649d5812b4a2ebc862b64e8132a806

# Inicialización del cliente Deezer
deezer = DeeLogin(arl='81eef20bf87ecee4263e5c2679ad9b3be1c086637408897cc87b70e2397d0ff1cadbfcd01f378b7b42a547681d196c39c0a82c2c6015935a3c6ce3d46bce9126f2ec6d0b80e4c0226617d445cb59987a3f1159bc69896b50cf10f4e2bf3d1537')

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

def add_metadata_to_mp3(file_path, track, album_data, track_number):
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

        # Usamos el track_number pasado como parámetro (basado en el índice del bucle)
        track_num_str = str(track_number)

        # Añadir metadatos básicos
        audio["title"] = track.get("title", "Unknown Title")
        audio["artist"] = artist_str
        audio["album"] = album_data.get("title", "Unknown Album")
        audio["tracknumber"] = track_num_str
        audio["date"] = album_data.get("release_date", "").split("-")[0]

        audio.save(file_path)
        logger.info(f"Metadatos añadidos a {file_path} - Track: {track_num_str}")

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

def upload_to_quax(zip_data, filename):
    try:
        logger.info(f"Subiendo {filename} ({len(zip_data)} bytes) a qu.ax")
        
        if len(zip_data) == 0:
            raise Exception("El archivo ZIP está vacío")
        
        # Crear un objeto BytesIO para el archivo en memoria
        file_obj = BytesIO(zip_data)
        files = {'files[]': (filename, file_obj, 'application/zip')}
        
        response = requests.post(
            "https://qu.ax/upload.php",
            files=files,
            data={'expiry': '30'},
            headers={
                "User-Agent": "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Mobile Safari/537.36",
                "Referer": "https://qu.ax/"
            }
        )
        response.raise_for_status()
        
        json_response = response.json()
        
        # Verificar la estructura de la respuesta
        if not json_response.get('success') or not json_response.get('files') or len(json_response['files']) == 0:
            logger.error(f"Respuesta inesperada de qu.ax: {json_response}")
            raise Exception("La estructura de la respuesta no es la esperada")
        
        # Obtener la URL de descarga
        download_url = json_response['files'][0]['url']
        
        logger.info(f"Subida exitosa a qu.ax. URL: {download_url}")
        return {
            'download_url': download_url,
            'delete_url': ''  # qu.ax no parece proporcionar URL de eliminación
        }
    except Exception as e:
        logger.error(f"Error subiendo a qu.ax: {str(e)}")
        raise

def create_zip_file(folder_path):
    try:
        # Crear un archivo ZIP en memoria
        zip_buffer = BytesIO()
        
        file_count = 0
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, _, files in os.walk(folder_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    # Mantener la estructura de directorios dentro del ZIP
                    arcname = os.path.join(os.path.basename(folder_path), os.path.relpath(file_path, folder_path))
                    zipf.write(file_path, arcname)
                    file_count += 1
                    logger.debug(f"Añadido al ZIP: {file_path} como {arcname}")
        
        if file_count == 0:
            raise Exception("No se encontraron archivos para comprimir")
        
        zip_data = zip_buffer.getvalue()
        logger.info(f"ZIP creado con {file_count} archivos ({len(zip_data)} bytes)")
        
        return zip_data
    except Exception as e:
        logger.error(f"Error creando ZIP: {str(e)}")
        raise

def cleanup_folder(folder_path):
    try:
        logger.info(f"Limpiando carpeta temporal: {folder_path}")
        shutil.rmtree(folder_path)
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

                        # Añadir metadatos - pasamos el índice como número de track
                        logger.info(f"Añadiendo metadatos a {file_path}")
                        add_metadata_to_mp3(file_path, track, album_data, idx)

                        # Renombrar archivo
                        new_file_name = f"{idx:02d}. {sanitize_filename(track['title'])}.mp3"
                        new_file_path = os.path.join(folder_path, new_file_name)
                        os.rename(file_path, new_file_path)
                        downloaded_files.append(new_file_name)
                        logger.info(f"Archivo renombrado a: {new_file_path}")
                        break

        # 3. Crear ZIP con la carpeta completa
        zip_file_name = f"{folder_name}.zip"
        logger.info(f"Creando archivo ZIP: {zip_file_name}")
        zip_data = create_zip_file(folder_path)

        # 4. Subir a qu.ax
        logger.info("Subiendo a qu.ax...")
        upload_response = upload_to_quax(zip_data, zip_file_name)

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
