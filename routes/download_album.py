import os
import requests
import zipfile
from flask import Blueprint, jsonify, request
from deezspot.deezloader import DeeLogin

# Directorio temporal para descargas
DOWNLOAD_DIR = './downloads'
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# API base de Deezer
DEEZER_API_ALBUM = "https://api.deezer.com/album/"

# Inicialización del cliente Deezer
deezer = DeeLogin(arl='87f304e8bff197c8877dac3ca0a21d0ef6505af952ee392f856c30527508e177c9d0f90af069e248fee50cbe9b200e3962537f4eff8c8ef2d7d564b30c74e06d6c8779c3c0ed002e92792d403ab7522c5c8102ca4dadb319a02e4c8c5729e739')

download_album_bp = Blueprint('download-album', __name__)

def sanitize_filename(name):
    return "".join(c for c in name if c.isalnum() or c in (" ", "-", "_")).strip()

@download_album_bp.route('/', methods=['GET'])
def download_album():
    album_id = request.args.get('album_id')

    if not album_id or not album_id.isdigit():
        return jsonify({"error": "Se requiere un 'album_id' válido (número)"}), 400

    try:
        # Obtener datos del álbum desde Deezer
        response = requests.get(f"{DEEZER_API_ALBUM}{album_id}")
        if response.status_code != 200:
            return jsonify({"error": "No se pudo obtener información del álbum"}), 404

        album_data = response.json()
        artist_name = album_data.get("artist", {}).get("name", "Unknown Artist")
        album_title = album_data.get("title", "Unknown Album")
        release_year = album_data.get("release_date", "").split("-")[0]

        # Crear nombre seguro para el archivo ZIP
        safe_artist = sanitize_filename(artist_name)
        safe_album = sanitize_filename(album_title)
        zip_name = f"{safe_artist} - {safe_album} ({release_year}).zip"
        zip_path = os.path.join(DOWNLOAD_DIR, zip_name)

        # Crear directorio temporal para el álbum
        album_dir = os.path.join(DOWNLOAD_DIR, f"album_{album_id}")
        os.makedirs(album_dir, exist_ok=True)

        # Descargar cada canción del álbum
        tracks = album_data.get("tracks", {}).get("data", [])
        if not tracks:
            return jsonify({"error": "No se encontraron canciones en el álbum"}), 404

        for track in tracks:
            track_id = track.get("id")
            if not track_id:
                continue

            track_url = f"https://www.deezer.com/track/{track_id}"
            deezer.download_trackdee(
                link_track=track_url,
                output_dir=album_dir,
                quality_download='MP3_128',
                recursive_quality=True,
                recursive_download=False
            )

        # Comprimir todas las canciones en un ZIP
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, _, files in os.walk(album_dir):
                for file in files:
                    if file.endswith('.mp3'):
                        file_path = os.path.join(root, file)
                        zipf.write(file_path, os.path.basename(file_path))

        # Subir el ZIP a tmpfiles.org
        with open(zip_path, 'rb') as f:
            response = requests.post(
                "https://tmpfiles.org/api/v1/upload",
                files={"file": (zip_name, f)}
            )

        if response.status_code != 200:
            return jsonify({"error": "Error al subir el archivo a tmpfiles.org"}), 500

        # Obtener URL de descarga (asumiendo que tmpfiles.org devuelve JSON con la URL)
        upload_data = response.json()
        download_url = upload_data.get("url")  # Ajustar según la respuesta real de tmpfiles.org

        # Limpiar archivos temporales
        for root, dirs, files in os.walk(album_dir, topdown=False):
            for name in files:
                os.remove(os.path.join(root, name))
            for name in dirs:
                os.rmdir(os.path.join(root, name))
        os.rmdir(album_dir)
        if os.path.exists(zip_path):
            os.remove(zip_path)

        return jsonify({
            "message": "Álbum descargado y comprimido con éxito",
            "download_url": download_url
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500