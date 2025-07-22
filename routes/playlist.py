# api/routes/playlist.py
from flask import Blueprint, request, jsonify
import requests

playlist_bp = Blueprint('playlist', __name__)

@playlist_bp.route('/', methods=['GET'])
def buscar_playlist():
    # Obtener el término de búsqueda desde los parámetros de la URL
    query = request.args.get('q')

    if not query:
        return jsonify({"error": "Falta el término de búsqueda 'q'"}), 400

    # URL de la API de Deezer para buscar playlists
    url = "https://api.deezer.com/search/playlist"

    # Realizar la solicitud a la API de Deezer con límite de 30 resultados
    try:
        params = {
            'q': query,
            'limit': 50  # Aquí se establece el límite a 30 resultados
        }

        response = requests.get(url, params=params)
        response.raise_for_status()
        resultados = response.json()

        return jsonify(resultados)

    except requests.exceptions.RequestException as e:
        return jsonify({"error": "Error al conectar con la API de Deezer", "detalle": str(e)}), 500