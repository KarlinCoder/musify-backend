import os
import shutil
import tempfile
import requests
from io import BytesIO
from flask import Blueprint, jsonify, request, send_file
from deezspot.deezloader import DeeLogin
from mutagen.id3 import ID3, TIT2, TPE1, TALB, TRCK, TYER, APIC
from mutagen.easyid3 import EasyID3

# Directorio temporal para descargas
DOWNLOAD_DIR = './downloads'
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# API base de Deezer
DEEZER_API_SONG = "https://api.deezer.com/track/" 

# Inicialización del cliente Deezer
deezer = DeeLogin(arl='87f304e8bff197c8877dac3ca0a21d0ef6505af952ee392f856c30527508e177c9d0f90af069e248fee50cbe9b200e3962537f4eff8c8ef2d7d564b30c74e06d6c8779c3c0ed002e92792d403ab7522c5c8102ca4dadb319a02e4c8c5729e739')

download_song_bp = Blueprint('download-song', __name__)


def sanitize_filename(name):
    return "".join(c for c in name if c.isalnum() or c in (" ", "-", "_")).strip()


def add_metadata_to_mp3(file_path, track_data, album_data):
    try:
        audio = EasyID3(file_path)
    except:
        audio = EasyID3()

    # Artistas
    contributors = track_data.get("contributors", [])
    artists = [artist["name"] for artist in contributors]
    if not artists:
        artists = [track_data["artist"]["name"]]
    artist_str = ", ".join(artists)

    # Metadatos
    audio["title"] = track_data["title"]
    audio["artist"] = artist_str
    audio["album"] = album_data["title"]
    audio["tracknumber"] = str(track_data["track_position"])
    audio["date"] = album_data["release_date"].split("-")[0]

    try:
        audio.save(file_path)
    except Exception as e:
        print(f"Error saving metadata to file: {e}")

    # Carátula
    id3 = ID3(file_path)
    cover_url = album_data.get("cover_xl") or album_data.get("cover_big")
    if cover_url:
        try:
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
        except Exception as e:
            print(f"Error adding cover art: {e}")


@download_song_bp.route('/', methods=['GET'])
def download_song():
    song_id = request.args.get('song_id')

    if not song_id or not song_id.isdigit():
        return jsonify({
            "status": "error",
            "message": "Se requiere un 'song_id' válido (número)",
            "error": "Invalid song_id"
        }), 400

    try:
        # Obtener datos de la canción desde Deezer
        response = requests.get(f"{DEEZER_API_SONG}{song_id}")
        if response.status_code != 200:
            return jsonify({
                "status": "error",
                "message": "No se pudo obtener información de la canción",
                "error": "Track not found"
            }), 404

        track_data = response.json()
        album_data = track_data.get("album", {})
        artist_data = track_data.get("artist", {})

        # Preparar nombres
        artist_name = artist_data.get("name", "Unknown Artist")
        title = track_data.get("title", "Unknown Title")
        album_title = album_data.get("title", "Unknown Album")
        release_year = album_data.get("release_date", "").split("-")[0] if album_data.get("release_date") else ""

        safe_artist = sanitize_filename(artist_name)
        safe_title = sanitize_filename(title)
        safe_album = sanitize_filename(album_title)

        # Crear directorio temporal único
        temp_dir = tempfile.mkdtemp(dir=DOWNLOAD_DIR)
        output_file = os.path.join(temp_dir, f"{safe_artist} - {safe_title}.mp3")

        # Descargar canción
        track_url = f"https://www.deezer.com/track/{song_id}" 
        deezer.download_trackdee(
            link_track=track_url,
            output_dir=temp_dir,
            quality_download='MP3_128',
            recursive_quality=True,
            recursive_download=False
        )

        # Buscar archivo descargado
        downloaded_file = None
        for root, _, files in os.walk(temp_dir):
            for file in files:
                if file.endswith(".mp3"):
                    downloaded_file = os.path.join(root, file)
                    break
            if downloaded_file:
                break

        if not downloaded_file or os.path.getsize(downloaded_file) == 0:
            shutil.rmtree(temp_dir)
            return jsonify({
                "status": "error",
                "message": "No se pudo descargar la canción o está vacía",
                "error": "Download failed"
            }), 500

        # Añadir metadatos
        add_metadata_to_mp3(downloaded_file, track_data, album_data)

        # Renombrar archivo final
        os.rename(downloaded_file, output_file)

        # Generar URL de descarga (esto depende de cómo esté configurado tu servidor)
        # En Flask puedes servir archivos estáticos desde una ruta específica
        # Aquí asumo que tienes una ruta configurada para servir archivos desde DOWNLOAD_DIR
        download_url = f"/downloads/{os.path.basename(temp_dir)}/{os.path.basename(output_file)}"

        # Configurar headers para descarga directa
        response_headers = {
            "Content-Disposition": f"attachment; filename=\"{os.path.basename(output_file)}\"",
            "Content-Type": "audio/mpeg"
        }

        # Limpiar el archivo temporal después de un tiempo (podrías usar un task scheduler)
        # O implementar un endpoint para limpieza manual

        return jsonify({
            "status": "success",
            "album": album_title,
            "artist": artist_name,
            "delete_url": "",  # Implementar si necesitas borrado manual
            "download_url": download_url,
            "filename": os.path.basename(output_file),
            "message": "Canción descargada con éxito",
            "year": release_year
        }), 200, response_headers

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": "Ocurrió un error al procesar la canción",
            "error": str(e)
        }), 500