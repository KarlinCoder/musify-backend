from flask import Blueprint, jsonify, request
import requests

song_preview_bp = Blueprint('preview', __name__)


@song_preview_bp.route('/<int:song_id>', methods=['GET'])
def obtener_preview(song_id):
    try:
        # URL para obtener info de la canción por ID (incluye preview)
        url = f"https://api.deezer.com/track/{song_id}" 

        response = requests.get(url)
        response.raise_for_status()  # Lanza error si hay código HTTP != 2xx
        data = response.json()

        preview_url = data.get("preview", "")

        if not preview_url or preview_url == "":
            return jsonify({"error": "No se encontró un preview para esta canción"}), 404

        return jsonify({
            "songId": song_id,
            "preview": preview_url,
            "duration": 30  # Los previews de Deezer duran ~30 segundos
        })

    except requests.exceptions.HTTPError as err:
        if response.status_code == 404:
            return jsonify({"error": "Canción no encontrada", "detalle": str(err)}), 404
        else:
            return jsonify({"error": "Error al obtener el preview", "detalle": str(err)}), 500

    except Exception as e:
        return jsonify({"error": "Ocurrió un problema interno", "detalle": str(e)}), 500