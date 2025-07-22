# api/routes/search.py
from flask import Blueprint, request, jsonify
import requests

search_bp = Blueprint('search', __name__)

@search_bp.route('/', methods=['GET'])
def buscar_en_deezer():
    # Obtener el término de búsqueda desde los parámetros de la URL
    query = request.args.get('q')
    search_type = request.args.get('type', default='all')  # 'artist', 'track', 'album' o 'all'

    if not query:
        return jsonify({"error": "Falta el término de búsqueda 'q'"}), 400

    # URL base de la API de Deezer
    base_url = "https://api.deezer.com/search" 

    # Mapeo de tipos de búsqueda
    valid_types = ['artist', 'track', 'album']
    if search_type in valid_types:
        url = f"{base_url}/{search_type}"
    else:
        url = base_url  # Búsqueda general (all)

    # Realizar la solicitud a la API de Deezer con límite de 30 resultados
    try:
        params = {
            'q': query,
            'limit': 70  # Aquí se establece el límite a 30 resultados
        }

        response = requests.get(url, params=params)
        response.raise_for_status()
        resultados = response.json()

        return jsonify(resultados)
        

    except requests.exceptions.RequestException as e:
        return jsonify({"error": "Error al conectar con la API de Deezer", "detalle": str(e)}), 500