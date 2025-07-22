# api/routes/album.py o search.py

from flask import Blueprint, jsonify
import requests

artist_bp = Blueprint('artist', __name__)

@artist_bp.route('/<id_artista>', methods=['GET'])
def obtener_album_por_id(id_artista):
    try:
        # Hacer la solicitud a la API de Deezer
        url = f"https://api.deezer.com/artist/{id_artista}" 
        response = requests.get(url)
        response.raise_for_status()  # Lanza error si hay código 4xx o 5xx
        album_data = response.json()

        return jsonify(album_data)

    except requests.exceptions.HTTPError as err:
        if response.status_code == 404:
            return jsonify({"error": "Artista no encontrado"}), 404
        else:
            return jsonify({"error": "Error al obtener datos del artista", "detalle": str(err)}), 500
    except Exception as e:
        return jsonify({"error": "Ocurrió un problema interno", "detalle": str(e)}), 500
    
@artist_bp.route('/<id_artista>/top', methods=['GET'])  # Corregí "id_artisat" a "id_artista"
def obtener_top_canciones_artista(id_artista):
    try:
        url = f"https://api.deezer.com/artist/{id_artista}/top?limit=10"
        response = requests.get(url)
        response.raise_for_status()
        top_songs_data = response.json()
        return jsonify(top_songs_data)
    except requests.exceptions.HTTPError as err:
        if response.status_code == 404:
            return jsonify({"error": "Artista no encontrado"}), 404
        else:
            return jsonify({"error": "Error al obtener el top de canciones del artista", "detalle": str(err)}), 500
    except Exception as e:
        return jsonify({"error": "Ocurrió un problema interno", "detalle": str(e)}), 500