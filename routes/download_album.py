import os
import shutil
import tempfile
import requests
import zipfile
import threading
from io import BytesIO
from flask import Blueprint, jsonify, request
from deezspot.deezloader import DeeLogin
from mutagen.id3 import ID3, TIT2, TPE1, TALB, TRCK, TYER, APIC
from mutagen.easyid3 import EasyID3
import logging
import time

# Configura logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DOWNLOAD_DIR = './downloads'
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

DEEZER_API_ALBUM = "https://api.deezer.com/album/"
TMPFILES_API = "https://tmpfiles.org/api/v1/upload"

deezer = DeeLogin(arl='87f304e8bff197c8877dac3ca0a21d0ef6505af952ee392f856c30527508e177c9d0f90af069e248fee50cbe9b200e3962537f4eff8c8ef2d7d564b30c74e06d6c8779c3c0ed002e92792d403ab7522c5c8102ca4dadb319a02e4c8c5729e739')

download_album_bp = Blueprint('download-album', __name__)

# Variable global para el progreso
download_progress = {
    'status': 'waiting',
    'message': '',
    'completed': 0,
    'total': 0
}

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

def download_track(track, idx, folder_path, album_data):
    """Función para descargar y procesar una pista en un hilo separado"""
    global download_progress
    
    try:
        song_id = track["id"]
        track_url = f"https://www.deezer.com/track/{song_id}"
        logger.info(f"[{idx}] Iniciando descarga: {track.get('title')}")
        
        # Actualizar progreso
        download_progress['message'] = f"Descargando {idx}/{download_progress['total']}: {track.get('title')}"
        
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
                if file.endswith(".mp3"):
                    file_path = os.path.join(root, file)
                    
                    if os.path.getsize(file_path) == 0:
                        logger.warning(f"Archivo vacío, eliminando: {file_path}")
                        os.remove(file_path)
                        continue
                    
                    # Añadir metadatos
                    logger.info(f"Añadiendo metadatos a {file_path}")
                    add_metadata_to_mp3(file_path, track, album_data, idx)
                    
                    # Renombrar archivo
                    new_file_name = f"{idx:02d}. {sanitize_filename(track['title'])}.mp3"
                    new_file_path = os.path.join(folder_path, new_file_name)
                    os.rename(file_path, new_file_path)
                    logger.info(f"Archivo renombrado a: {new_file_path}")
                    
                    # Actualizar progreso
                    download_progress['completed'] += 1
                    download_progress['message'] = f"Procesado {download_progress['completed']}/{download_progress['total']}: {track.get('title')}"
                    break
    except Exception as e:
        logger.error(f"Error en track {idx}: {str(e)}")
        download_progress['message'] = f"Error en track {idx}: {str(e)}"

@download_album_bp.route('/progress')
def progress():
    """Endpoint para verificar el progreso"""
    return jsonify(download_progress)

@download_album_bp.route('/', methods=['GET'])
def download_album():
    global download_progress
    
    album_id = request.args.get('album_id')
    logger.info(f"Iniciando descarga para album_id: {album_id}")

    if not album_id or not album_id.isdigit():
        logger.error("ID de álbum inválido")
        return jsonify({"error": "Se requiere un ID de álbum válido (número)"}), 400

    # Respuesta inmediata para que el navegador no se quede esperando
    response = jsonify({
        "status": "processing",
        "message": "Descargando album completo en proceso con multihilos...",
        "progress_url": "/progress"
    })
    
    # Iniciar el proceso en segundo plano
    def background_task():
        global download_progress
        
        try:
            # 1. Obtener metadatos del álbum
            download_progress = {
                'status': 'downloading',
                'message': 'Obteniendo metadatos del álbum...',
                'completed': 0,
                'total': 0
            }
            
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

            # 2. Descargar pistas en paralelo
            tracks = album_data.get("tracks", {}).get("data", [])
            if not tracks:
                download_progress['status'] = 'error'
                download_progress['message'] = 'Álbum no tiene pistas disponibles'
                logger.error("Álbum no tiene pistas disponibles")
                return

            download_progress['total'] = len(tracks)
            download_progress['message'] = f"Iniciando descarga de {len(tracks)} pistas..."
            logger.info(f"Descargando {len(tracks)} pistas en paralelo...")

            threads = []
            for idx, track in enumerate(tracks, start=1):
                thread = threading.Thread(
                    target=download_track,
                    args=(track, idx, folder_path, album_data)
                )
                thread.start()
                threads.append(thread)
                time.sleep(0.1)  # Pequeña pausa para evitar saturación

            # Esperar a que todos los hilos terminen
            for thread in threads:
                thread.join()

            # 3. Crear ZIP con la carpeta completa
            download_progress['message'] = "Creando archivo ZIP..."
            zip_file_name = f"{folder_name}.zip"
            logger.info(f"Creando archivo ZIP: {zip_file_name}")
            zip_data = create_zip_file(folder_path)

            # 4. Subir a qu.ax
            download_progress['message'] = "Subiendo a qu.ax..."
            logger.info("Subiendo a qu.ax...")
            upload_response = upload_to_quax(zip_data, zip_file_name)

            # 5. Limpiar
            cleanup_folder(folder_path)

            # 6. Actualizar estado final
            download_progress['status'] = 'completed'
            download_progress['message'] = 'Proceso completado exitosamente'
            download_progress['download_url'] = upload_response['download_url']
            logger.info("Proceso completado exitosamente")

        except Exception as e:
            logger.error(f"Error procesando álbum: {str(e)}", exc_info=True)
            download_progress['status'] = 'error'
            download_progress['message'] = f"Error: {str(e)}"

    # Iniciar el hilo de fondo
    threading.Thread(target=background_task).start()
    
    return response
