import os
import requests
import zipfile
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
DEEZER_API_ALBUM = "https://api.deezer.com/album/"

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

def upload_to_tmpfiles(file_path):
    try:
        with open(file_path, 'rb') as f:
            response = requests.post(
                'https://tmpfiles.org/api/v1/upload',
                files={'file': f}
            )
        
        if response.status_code == 200:
            # La API de tmpfiles.org devuelve un JSON con la URL de descarga
            result = response.json()
            if result.get('status') == 'success':
                return result.get('url')
        return None
    except Exception as e:
        print(f"Error uploading to tmpfiles.org: {e}")
        return None

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
        artist_data = album_data.get("artist", {})
        
        # Preparar nombres
        artist_name = artist_data.get("name", "Unknown Artist")
        album_title = album_data.get("title", "Unknown Album")
        release_year = album_data.get("release_date", "").split("-")[0] if album_data.get("release_date") else ""

        safe_artist = sanitize_filename(artist_name)
        safe_album = sanitize_filename(album_title)
        zip_name = f"{safe_artist} - {safe_album} ({release_year}).zip" if release_year else f"{safe_artist} - {safe_album}.zip"
        
        # Crear directorio para el álbum
        album_dir = os.path.join(DOWNLOAD_DIR, f"{safe_artist} - {safe_album}")
        os.makedirs(album_dir, exist_ok=True)

        # Descargar cada canción del álbum
        tracks = album_data.get("tracks", {}).get("data", [])
        if not tracks:
            return jsonify({"error": "No se encontraron canciones en el álbum"}), 404

        downloaded_files = []
        
        for track in tracks:
            track_id = track.get("id")
            if not track_id:
                continue

            try:
                # Descargar canción
                track_url = f"https://www.deezer.com/track/{track_id}"
                deezer.download_trackdee(
                    link_track=track_url,
                    output_dir=album_dir,
                    quality_download='MP3_128',
                    recursive_quality=True,
                    recursive_download=False
                )

                # Buscar archivo descargado
                downloaded_file = None
                for root, _, files in os.walk(album_dir):
                    for file in files:
                        if file.endswith(".mp3"):
                            downloaded_file = os.path.join(root, file)
                            break
                    if downloaded_file:
                        break

                if not downloaded_file or os.path.getsize(downloaded_file) == 0:
                    print(f"No se pudo descargar la canción {track_id} o está vacía")
                    continue

                # Añadir metadatos
                add_metadata_to_mp3(downloaded_file, track, album_data)

                # Renombrar archivo final
                track_position = str(track.get("track_position", "0")).zfill(2)
                new_file_name = f"{track_position} - {sanitize_filename(track.get('title', 'Unknown Title'))}.mp3"
                new_file_path = os.path.join(album_dir, new_file_name)
                os.rename(downloaded_file, new_file_path)
                
                downloaded_files.append(new_file_path)

            except Exception as e:
                print(f"Error al procesar la canción {track_id}: {str(e)}")
                continue

        if not downloaded_files:
            return jsonify({"error": "No se pudo descargar ninguna canción del álbum"}), 500

        # Crear archivo ZIP
        zip_path = os.path.join(DOWNLOAD_DIR, zip_name)
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file in downloaded_files:
                zipf.write(file, os.path.basename(file))

        # Subir a tmpfiles.org
        download_url = upload_to_tmpfiles(zip_path)
        if not download_url:
            return jsonify({"error": "No se pudo subir el archivo ZIP a tmpfiles.org"}), 500

        # Limpiar archivos temporales
        for file in downloaded_files:
            try:
                os.remove(file)
            except:
                pass
        
        try:
            os.rmdir(album_dir)
            os.remove(zip_path)
        except:
            pass

        return jsonify({
            "message": "Álbum descargado y comprimido exitosamente",
            "download_url": download_url,
            "album": f"{artist_name} - {album_title}",
            "year": release_year,
            "tracks": len(downloaded_files)
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500