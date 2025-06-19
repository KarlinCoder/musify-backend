import os
import uuid
import requests
import zipfile
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor
from tempfile import NamedTemporaryFile
from flask import Blueprint, jsonify, request
from deezspot.deezloader import DeeLogin
from mutagen.id3 import ID3, TIT2, TPE1, TALB, TYER, APIC
from mutagen.easyid3 import EasyID3

DOWNLOAD_DIR = './downloads'
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

DEEZER_API_ALBUM = "https://api.deezer.com/album/"    
TMPFILES_UPLOAD_URL = "https://tmpfiles.org/api/v1/upload" 

deezer = DeeLogin(arl='87f304e8bff197c8877dac3ca0a21d0ef6505af952ee392f856c30527508e177c9d0f90af069e248fee50cbe9b200e3962537f4eff8c8ef2d7d564b30c74e06d6c8779c3c0ed002e92792d403ab7522c5c8102ca4dadb319a02e4c8c5729e739')

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


def download_single_track(deezer_instance, folder_path, track, album_data):
    try:
        song_id = track["id"]
        track_url = f"https://www.deezer.com/track/{song_id}"    

        deezer_instance.download_trackdee(
            link_track=track_url,
            output_dir=folder_path,
            quality_download='MP3_128',
            recursive_quality=True,
            recursive_download=False
        )

        # Buscar el archivo recién descargado
        for root, _, files in os.walk(folder_path):
            for file in files:
                if file.endswith(".mp3"):
                    file_path = os.path.join(root, file)

                    if os.path.getsize(file_path) == 0:
                        os.remove(file_path)
                        return None

                    idx = track.get("index", 1)
                    new_file_name = f"{idx:02d}. {sanitize_filename(track['artist']['name'])} - {sanitize_filename(track['title'])}.mp3"
                    new_file_path = os.path.join(folder_path, new_file_name)
                    try:
                        add_metadata_to_mp3(file_path, track, album_data)
                    except Exception as e:
                        print(f"Error adding metadata: {e}")
                    os.rename(file_path, new_file_path)
                    return new_file_name

    except Exception as e:
        print(f"Error downloading track {track['id']}: {e}")
        return None


@download_album_bp.route('/', methods=['GET'])
def download_album():
    album_id = request.args.get('album_id')

    if not album_id or not album_id.isdigit():
        return jsonify({"error": "Se requiere un 'album_id' válido (número)"}), 400

    try:
        album_data = get_album_metadata(album_id)

        artist_name = album_data["artist"]["name"]
        album_title = album_data["title"]
        release_year = album_data["release_date"].split("-")[0]

        safe_artist = sanitize_filename(artist_name)
        safe_album = sanitize_filename(album_title)
        session_id = str(uuid.uuid4())
        session_folder = os.path.join(DOWNLOAD_DIR, session_id)
        folder_name = f"{safe_artist} - {safe_album} ({release_year})"
        folder_path = os.path.join(session_folder, folder_name)

        os.makedirs(folder_path, exist_ok=True)

        tracks = album_data.get("tracks", {}).get("data", [])
        if not tracks:
            return jsonify({"error": "Este álbum no tiene canciones disponibles"}), 400

        downloaded_files = []

        # Asignamos índice manualmente
        for idx, track in enumerate(tracks, start=1):
            track["index"] = idx

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = []
            for track in tracks:
                future = executor.submit(download_single_track, deezer, folder_path, track, album_data)
                futures.append(future)

            for future in futures:
                result = future.result()
                if result:
                    downloaded_files.append(result)

        if not downloaded_files:
            return jsonify({"error": "No se pudo descargar ninguna canción del álbum"}), 500

        # Crear ZIP en memoria
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w') as zipf:
            for root, _, files in os.walk(folder_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, folder_path)
                    zipf.write(file_path, arcname)

        zip_buffer.seek(0)

        # Guardar el ZIP en un archivo temporal
        with NamedTemporaryFile(delete=False, suffix=".zip") as tmp_zip:
            tmp_zip.write(zip_buffer.getvalue())
            tmp_zip_path = tmp_zip.name

        # Subir a tmpfiles.org
        with open(tmp_zip_path, "rb") as f:
            files = {"file": ("album.zip", f)}
            response = requests.post(TMPFILES_UPLOAD_URL, files=files)

        os.remove(tmp_zip_path)  # Limpiar el archivo temporal local

        if response.status_code != 200:
            return jsonify({
                "error": "Fallo al subir el archivo a tmpfiles.org",
                "response": response.text
            }), 500

        response_json = response.json()
        file_url = response_json.get("url", "").replace("https://tmpfiles.org/",  "http://tmpfiles.org/dl/")

        # Limpiar carpeta temporal
        for root, dirs, files in os.walk(session_folder, topdown=False):
            for name in files:
                os.remove(os.path.join(root, name))
            for name in dirs:
                os.rmdir(os.path.join(root, name))
        os.rmdir(session_folder)

        return jsonify({
            "download_url": file_url
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500