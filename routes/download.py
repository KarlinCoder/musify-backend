import os
import requests
from flask import Blueprint, jsonify, request, send_from_directory
from deezspot.deezloader import DeeLogin
from mutagen.id3 import ID3, TIT2, TPE1, TALB, TRCK, TYER, APIC
from mutagen.easyid3 import EasyID3

# Configuración
DOWNLOAD_DIR = os.path.join(os.getcwd(), 'downloads')
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

DEEZER_API_SONG = "https://api.deezer.com/track/"
deezer = DeeLogin(arl='87f304e8bff197c8877dac3ca0a21d0ef6505af952ee392f856c30527508e177c9d0f90af069e248fee50cbe9b200e3962537f4eff8c8ef2d7d564b30c74e06d6c8779c3c0ed002e92792d403ab7522c5c8102ca4dadb319a02e4c8c5729e739')

download_song_bp = Blueprint('download-song', __name__)

# Ruta para servir archivos descargados
@download_song_bp.route('/downloads/<path:filename>')
def serve_download(filename):
    return send_from_directory(DOWNLOAD_DIR, filename, as_attachment=True)

def sanitize_filename(name):
    return "".join(c for c in name if c.isalnum() or c in (" ", "-", "_")).strip()

def add_metadata_to_mp3(file_path, track_data, album_data):
    try:
        audio = EasyID3(file_path)
    except:
        audio = EasyID3()

    contributors = track_data.get("contributors", [])
    artists = [artist["name"] for artist in contributors]
    if not artists:
        artists = [track_data["artist"]["name"]]
    artist_str = ", ".join(artists)

    audio["title"] = track_data["title"]
    audio["artist"] = artist_str
    audio["album"] = album_data["title"]
    audio["tracknumber"] = str(track_data["track_position"])
    audio["date"] = album_data["release_date"].split("-")[0]

    audio.save(file_path)

    id3 = ID3(file_path)
    cover_url = album_data.get("cover_xl") or album_data.get("cover_big")
    if cover_url:
        try:
            cover_data = requests.get(cover_url).content
            id3.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=cover_data))
            id3.save(v2_version=3)
        except Exception as e:
            print(f"Error adding cover art: {e}")

@download_song_bp.route('/', methods=['GET'])
def download_song():
    song_id = request.args.get('song_id')

    if not song_id or not song_id.isdigit():
        return jsonify({"error": "Se requiere un 'song_id' válido (número)"}), 400

    try:
        # Obtener datos de la canción
        response = requests.get(f"{DEEZER_API_SONG}{song_id}")
        if response.status_code != 200:
            return jsonify({"error": "No se pudo obtener información de la canción"}), 404

        track_data = response.json()
        artist_name = track_data.get("artist", {}).get("name", "Unknown Artist")
        title = track_data.get("title", "Unknown Title")
        safe_artist = sanitize_filename(artist_name)
        safe_title = sanitize_filename(title)
        file_name = f"{safe_artist} - {safe_title}.mp3"
        relative_path = os.path.join(safe_artist, file_name)
        full_path = os.path.join(DOWNLOAD_DIR, relative_path)

        # Crear directorio si no existe
        os.makedirs(os.path.dirname(full_path), exist_ok=True)

        # Descargar canción
        track_url = f"https://www.deezer.com/track/{song_id}"
        deezer.download_trackdee(
            link_track=track_url,
            output_dir=os.path.dirname(full_path),
            quality_download='MP3_128',
            recursive_quality=True,
            recursive_download=False
        )

        # Buscar archivo descargado (puede tener nombre temporal)
        downloaded_file = None
        for file in os.listdir(os.path.dirname(full_path)):
            if file.endswith('.mp3'):
                downloaded_file = os.path.join(os.path.dirname(full_path), file)
                break

        if not downloaded_file:
            return jsonify({"error": "No se encontró el archivo descargado"}), 500

        # Renombrar y añadir metadatos
        os.rename(downloaded_file, full_path)
        add_metadata_to_mp3(full_path, track_data, track_data.get("album", {}))

        # Devolver URL para descargar
        return jsonify({
            "status": "success",
            "download_url": f"/downloads/{relative_path}",
            "filename": file_name,
            "artist": artist_name,
            "title": title,
            "duration": track_data.get("duration", 0),
            "warning": "Este archivo es temporal y se eliminará cuando el servidor se reinicie"
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500