import os
from flask import Flask, jsonify, send_file, send_from_directory
from flask_cors import CORS
from routes.download import download_song_bp
from routes.download_album import download_album_bp
from functools import wraps
from flask import request, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address




API_KEY = os.getenv("FLASK_API_KEY", "default-secret-key")  # Mejor usar variable de entorno

def require_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        provided_key = request.headers.get('X-API-Key')
        if provided_key and provided_key == API_KEY:
            return f(*args, **kwargs)
        return jsonify({"error": "Acceso denegado"}), 401
    return decorated

app = Flask(__name__)
CORS(app, origins=["https://musifydl.vercel.app"]) 

limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["50 per hour"]
)

DOWNLOAD_DIR = './downloads'
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

app.register_blueprint(download_song_bp, url_prefix='/download-song')
app.register_blueprint(download_album_bp, url_prefix='/download-album')

@app.route('/downloads/<path:filename>')
def download_file(filename):
    file_path = os.path.join(DOWNLOAD_DIR, filename)
    if not os.path.isfile(file_path):
        return jsonify({"error": "Archivo no encontrado"}), 404
    return send_file(file_path)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)), debug=True)