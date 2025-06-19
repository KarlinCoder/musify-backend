
# routes/download_album.py

import os
import uuid
import requests
import zipfile
from io import BytesIO
from flask import Blueprint, jsonify, request, send_file, send_from_directory
from deezspot.deezloader import DeeLogin
from mutagen.id3 import ID3, TIT2, TPE1, TALB, TRCK, TYER, APIC
from mutagen.easyid3 import EasyID3

DOWNLOAD_DIR = './downloads'
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

DEEZER_API_ALBUM = "https://api.deezer.com/album/"   

deezer = DeeLogin(arl='ce07a9bdbb677f70fec97b4682998f513ac3dcacd9fc843f2e0ef71efd90667b314ce91cbcccd86f331d945606b29b26222b1828d4c81a054dce4d2516176efdce68a8139dbeb5e34bb379ba62eed5811904008b1279f3156dc0c4f60ecbd61d')

download_album_bp = Blueprint('download-album', __name__)


def sanitize_filename(name):
    return "".join(c for c in name if c.isalnum() or c in (" ", "-", "_")).strip()


def get_album_metadata(album_id):
    response = requests.get(f"{DEEZER_API_ALBUM}{album_id}")
    if response.status_code != 200:
        raise Exception("Error fetching album metadata")
    return response.json()


def add_metadata_to_mp3(file_path, track, album_data):
    try:
        audio = EasyID3(file_path)
    except:
        audio = EasyID3()

    contributors = track.get("contributors", [])
    artists = [artist["name"] for artist in contributors]
    if not artists:
        artists = [track["artist"]["name"]]
    artist_str = ", ".join(artists)

    audio["title"] = track["title"]
    audio["artist"] = artist_str
    audio["album"] = album_data["title"]
    audio["tracknumber"] = str(track["track_position"])
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


@download_album_bp.route('/', methods=['GET'])
def download_album():
    album_id = request.args.get('album_id')

    if not album_id or not album_id.isdigit():
        return jsonify({"error": "Se requiere un 'album_id' válido (número)"}), 400

    try:
        # Obtener metadatos del álbum
        album_data = get_album_metadata(album_id)

        artist_name = album_data["artist"]["name"]
        album_title = album_data["title"]
        release_year = album_data["release_date"].split("-")[0]

        safe_artist = sanitize_filename(artist_name)
        safe_album = sanitize_filename(album_title)
        folder_name = f"{safe_artist} - {safe_album} ({release_year})"
        folder_path = os.path.join(DOWNLOAD_DIR, folder_name)
        os.makedirs(folder_path, exist_ok=True)

        tracks = album_data.get("tracks", {}).get("data", [])
        if not tracks:
            return jsonify({"error": "Este álbum no tiene canciones disponibles"}), 400

        downloaded_files = []

        for idx, track in enumerate(tracks, start=1):
            song_id = track["id"]
            track_url = f"https://www.deezer.com/track/{song_id}"   

            deezer.download_trackdee(
                link_track=track_url,
                output_dir=folder_path,
                quality_download='MP3_128',
                recursive_quality=True,
                recursive_download=False
            )

            for root, _, files in os.walk(folder_path):
                for file in files:
                    if file.endswith(".mp3") and file not in downloaded_files:
                        file_path = os.path.join(root, file)

                        if os.path.getsize(file_path) == 0:
                            os.remove(file_path)
                            continue

                        try:
                            add_metadata_to_mp3(file_path, track, album_data)
                        except Exception as e:
                            print(f"Error adding metadata: {e}")

                        new_file_name = f"{idx:02d}. {sanitize_filename(artist_name)} - {sanitize_filename(track['title'])}.mp3"
                        new_file_path = os.path.join(folder_path, new_file_name)
                        os.rename(file_path, new_file_path)
                        downloaded_files.append(new_file_name)
                        break

        # Crear ZIP en memoria
        memory_zip = BytesIO()
        with zipfile.ZipFile(memory_zip, 'w') as zipf:
            for root, _, files in os.walk(folder_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, folder_path)
                    zipf.write(file_path, arcname)

        memory_zip.seek(0)

        # Limpiar carpeta temporal
        for root, dirs, files in os.walk(folder_path, topdown=False):
            for name in files:
                os.remove(os.path.join(root, name))
            for name in dirs:
                os.rmdir(os.path.join(root, name))
        os.rmdir(folder_path)

        zip_file_name = f"{safe_artist} - {safe_album} ({release_year}).zip"

        # Devolver archivo ZIP desde memoria
        return send_file(
            memory_zip,
            mimetype='application/zip',
            as_attachment=True,
            download_name=zip_file_name
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# Esta ruta ya no es necesaria si usamos send_file directamente
# Pero puedes dejarla por compatibilidad o quitarla
@download_album_bp.route('/download/<filename>')
def serve_zip(filename):
    full_path = os.path.join(DOWNLOAD_DIR, filename)
    if not os.path.exists(full_path):
        return jsonify({"error": "Archivo no encontrado"}), 404
    return send_from_directory(DOWNLOAD_DIR, filename, as_attachment=True)