from flask import Blueprint, jsonify
import requests

artist_discography_bp = Blueprint('artist-discography', __name__)

@artist_discography_bp.route('/<int:artist_id>/albums', methods=['GET'])
def obtener_albumes_y_singles(artist_id):
    try:
        # URLs para obtener álbumes y singles del artista
        albums_url = f"https://api.deezer.com/artist/{artist_id}/albums?limit=999"
        singles_url = f"https://api.deezer.com/artist/{artist_id}/singles?limit=999" 

        # Hacer las dos peticiones en paralelo
        albums_response = requests.get(albums_url)
        singles_response = requests.get(singles_url)

        # Lanzar error si alguna falla
        albums_response.raise_for_status()
        singles_response.raise_for_status()

        # Parsear JSON
        albums_data = albums_response.json()
        singles_data = singles_response.json()

        return jsonify({
            "albums": albums_data.get("data", []),
            "singles": singles_data.get("data", [])
        })

    except requests.exceptions.HTTPError as err:
        if "404" in str(err):
            return jsonify({"error": "Artista o datos no encontrados"}), 404
        else:
            return jsonify({
                "error": "Error al obtener datos del artista",
                "detalle": str(err)
            }), 500

    except Exception as e:
        return jsonify({
            "error": "Ocurrió un problema interno",
            "detalle": str(e)
        }), 500