import os
import zipfile
import requests
from io import BytesIO
from flask import Blueprint, jsonify, request, send_file
from deezspot.deezloader import DeeLogin
from mutagen.id3 import ID3, APIC
from mutagen.easyid3 import EasyID3

# Directorios temporales
DOWNLOAD_DIR = './downloads'
ZIP_TEMP_DIR = './temp_albums'
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(ZIP_TEMP_DIR, exist_ok=True)

# URLs y credenciales
DEEZER_API_ALBUM = "https://api.deezer.com/album/" 
DEEZER_API_SONG = "https://api.deezer.com/track/" 
TMPFILES_UPLOAD_URL = "https://tmpfiles.org/api/v1/upload" 

# Inicialización del cliente Deezer
deezer = DeeLogin(arl='87f304e8bff197c8877dac3ca0a21d0ef6505af952ee392f856c30527508e177c9d0f90af069e248fee50cbe9b200e3962537f4eff8c8ef2d7d564b30c74e06d6c8779c3c0ed002e92792d403ab7522c5c8102ca4dadb319a02e4c8c5729e739')

download_album_bp = Blueprint('download-album', __name__)


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

    try:
        audio.save(file_path)
    except Exception as e:
        print(f"Error saving metadata to file: {e}")

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


def download_single_song(song_id, output_dir):
    response = requests.get(f"{DEEZER_API_SONG}{song_id}")
    if response.status_code != 200:
        raise Exception(f"No se pudo obtener información de la canción {song_id}")

    track_data = response.json()
    album_data = track_data.get("album", {})
    artist_data = track_data.get("artist", {})

    # Preparar nombres
    artist_name = artist_data.get("name", "Unknown Artist")
    title = track_data.get("title", "Unknown Title")

    safe_artist = sanitize_filename(artist_name)
    safe_title = sanitize_filename(title)

    song_output_dir = os.path.join(output_dir, f"{safe_artist} - {safe_title}")
    os.makedirs(song_output_dir, exist_ok=True)

    track_url = f"https://www.deezer.com/track/{song_id}" 
    deezer.download_trackdee(
        link_track=track_url,
        output_dir=song_output_dir,
        quality_download='MP3_128',
        recursive_quality=True,
        recursive_download=False
    )

    downloaded_file = None
    for root, _, files in os.walk(song_output_dir):
        for file in files:
            if file.endswith(".mp3"):
                downloaded_file = os.path.join(root, file)
                break
        if downloaded_file:
            break

    if not downloaded_file or os.path.getsize(downloaded_file) == 0:
        raise Exception(f"No se pudo descargar o está vacía la canción {song_id}")

    add_metadata_to_mp3(downloaded_file, track_data, album_data)

    new_file_name = f"{safe_artist} - {safe_title}.mp3"
    new_file_path = os.path.join(output_dir, new_file_name)
    os.rename(downloaded_file, new_file_path)

    # Limpiar directorio temporal de la canción
    for root, dirs, files in os.walk(song_output_dir, topdown=False):
        for name in files:
            os.remove(os.path.join(root, name))
        for name in dirs:
            os.rmdir(os.path.join(root, name))
    os.rmdir(song_output_dir)

    return new_file_path


@download_album_bp.route('/album', methods=['GET'])
def download_album():
    album_id = request.args.get('album_id')

    if not album_id or not album_id.isdigit():
        return jsonify({"error": "Se requiere un 'album_id' válido (número)"}), 400

    try:
        # Obtener info del álbum
        album_response = requests.get(f"{DEEZER_API_ALBUM}{album_id}")
        if album_response.status_code != 200:
            return jsonify({"error": "No se pudo obtener información del álbum"}), 404

        album_data = album_response.json()
        tracks = album_data.get("tracks", {}).get("data", [])

        if not tracks:
            return jsonify({"error": "Este álbum no tiene canciones disponibles"}), 404

        artist_name = album_data.get("artist", {}).get("name", "Unknown Artist")
        album_title = album_data.get("title", "Unknown Album")
        release_year = album_data.get("release_date", "").split("-")[0] or "Unknown Year"

        safe_artist = sanitize_filename(artist_name)
        safe_album = sanitize_filename(album_title)
        zip_dir = os.path.join(ZIP_TEMP_DIR, f"{safe_artist} - {safe_album} ({release_year})")
        os.makedirs(zip_dir, exist_ok=True)

        mp3_files = []

        for track in tracks:
            song_id = track.get("id")
            print(f"Descargando canción {song_id}...")
            mp3_path = download_single_song(song_id, zip_dir)
            mp3_files.append(mp3_path)

        # Crear ZIP
        zip_filename = f"{safe_artist} - {safe_album} ({release_year}).zip"
        zip_filepath = os.path.join(ZIP_TEMP_DIR, zip_filename)

        with zipfile.ZipFile(zip_filepath, 'w') as zipf:
            for file in mp3_files:
                zipf.write(file, arcname=os.path.basename(file))

        # Cargar ZIP a tmpfiles.org
        with open(zip_filepath, "rb") as f:
            files = {"file": f}
            upload_response = requests.post(TMPFILES_UPLOAD_URL, files=files)

        if upload_response.status_code != 200:
            return jsonify({"error": "No se pudo subir el archivo ZIP temporalmente"}), 500

        upload_data = upload_response.json()
        file_url = upload_data.get("url").replace("https://tmpfiles.org/",  "https://") 

        # Limpiar archivos temporales
        for file in mp3_files + [zip_filepath]:
            if os.path.exists(file):
                os.remove(file)

        return jsonify({
            "album_zip_url": file_url
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500