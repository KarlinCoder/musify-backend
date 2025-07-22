# api/routes/charts.py
from flask import Blueprint, jsonify
import requests

chart_bp = Blueprint('chart', __name__)


@chart_bp.route('/', methods=['GET'])
def obtener_top_global_canciones():
    try:
        # URL del top global de canciones
        url = "https://api.deezer.com/chart/0/tracks" 

        response = requests.get(url)
        response.raise_for_status()  # Lanza error si hay código HTTP != 2xx
        data = response.json()

        return jsonify(data)

    except requests.exceptions.HTTPError as err:
        if response.status_code == 404:
            return jsonify({"error": "No se encontraron datos", "detalle": str(err)}), 404
        else:
            return jsonify({"error": "Error al obtener los datos del chart", "detalle": str(err)}), 500
    except Exception as e:
        return jsonify({"error": "Ocurrió un problema interno", "detalle": str(e)}), 500