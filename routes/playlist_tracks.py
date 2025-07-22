# routes/playlist_tracks.py
from flask import Blueprint, request, jsonify
import requests

playlist_tracks_bp = Blueprint('playlist-tracks', __name__)

@playlist_tracks_bp.route('/<int:playlist_id>', methods=['GET'])
def obtener_tracks_playlist(playlist_id):
    # URL de la API de Deezer para obtener las canciones de una playlist
    url = f"https://api.deezer.com/playlist/{playlist_id}"

    try:
        response = requests.get(url)
        response.raise_for_status()  # Lanza error si hay status code != 200
        tracks = response.json()
        return jsonify(tracks)

    except requests.exceptions.RequestException as e:
        return jsonify({
            "error": "Error al conectar con la API de Deezer",
            "detalle": str(e),
            "url_usada": response.request.url if response else url
        }), 500