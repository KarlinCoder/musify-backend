# api/routes/album.py o search.py

from flask import Blueprint, jsonify
import requests

album_bp = Blueprint('album', __name__)

@album_bp.route('/<id_album>', methods=['GET'])
def obtener_album_por_id(id_album):
    try:
        # Hacer la solicitud a la API de Deezer
        url = f"https://api.deezer.com/album/{id_album}" 
        response = requests.get(url)
        response.raise_for_status()  # Lanza error si hay código 4xx o 5xx
        album_data = response.json()

        return jsonify(album_data)

    except requests.exceptions.HTTPError as err:
        if response.status_code == 404:
            return jsonify({"error": "Álbum no encontrado"}), 404
        else:
            return jsonify({"error": "Error al obtener datos del álbum", "detalle": str(err)}), 500
    except Exception as e:
        return jsonify({"error": "Ocurrió un problema interno", "detalle": str(e)}), 500