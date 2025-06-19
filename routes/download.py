import os
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
deezer = DeeLogin(arl='10fa24c551e734b466e54a4415ca0a00712efaf47064f7fee8acd843f6e4bb2e94d82ac842988fc81072af4a65ad781ba419c11c3175b17339b1d5e0f90ae80a603292b3648c68992df6f2eecfcfc9dd2bc8bb965f1a6f8e7be4ea62480fa500')

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
        return jsonify({"error": "Se requiere un 'song_id' válido (número)"}), 400

    try:
        # Obtener datos de la canción desde Deezer
        response = requests.get(f"{DEEZER_API_SONG}{song_id}")
        if response.status_code != 200:
            return jsonify({"error": "No se pudo obtener información de la canción"}), 404

        track_data = response.json()
        album_data = track_data.get("album", {})
        artist_data = track_data.get("artist", {})

        # Preparar nombres
        artist_name = artist_data.get("name", "Unknown Artist")
        title = track_data.get("title", "Unknown Title")

        safe_artist = sanitize_filename(artist_name)
        safe_title = sanitize_filename(title)

        output_dir = os.path.join(DOWNLOAD_DIR, f"{safe_artist} - {safe_title}")
        os.makedirs(output_dir, exist_ok=True)

        # Descargar canción
        track_url = f"https://www.deezer.com/track/{song_id}" 
        deezer.download_trackdee(
            link_track=track_url,
            output_dir=output_dir,
            quality_download='MP3_128',
            recursive_quality=True,
            recursive_download=False
        )

        # Buscar archivo descargado
        downloaded_file = None
        for root, _, files in os.walk(output_dir):
            for file in files:
                if file.endswith(".mp3"):
                    downloaded_file = os.path.join(root, file)
                    break
            if downloaded_file:
                break

        if not downloaded_file or os.path.getsize(downloaded_file) == 0:
            return jsonify({"error": "No se pudo descargar la canción o está vacía"}), 500

        # Añadir metadatos
        add_metadata_to_mp3(downloaded_file, track_data, album_data)

        # Renombrar archivo final
        new_file_name = f"{safe_artist} - {safe_title}.mp3"
        new_file_path = os.path.join(output_dir, new_file_name)
        os.rename(downloaded_file, new_file_path)

        # Cargar archivo en memoria
        mp3_buffer = BytesIO()
        with open(new_file_path, "rb") as f:
            mp3_buffer.write(f.read())
        mp3_buffer.seek(0)

        # Limpiar carpeta temporal
        for root, dirs, files in os.walk(output_dir, topdown=False):
            for name in files:
                os.remove(os.path.join(root, name))
            for name in dirs:
                os.rmdir(os.path.join(root, name))
        os.rmdir(output_dir)

        # Enviar archivo como descarga directa
        return send_file(
            mp3_buffer,
            mimetype='audio/mpeg',
            as_attachment=True,
            download_name=new_file_name
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500