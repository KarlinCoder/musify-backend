import os
from flask import Flask, jsonify, send_file, send_from_directory
from flask_cors import CORS
from routes.download import download_song_bp
from routes.download_album import download_album_bp
from functools import wraps
from flask import request, jsonify

app = Flask(__name__)
CORS(app) 

DOWNLOAD_DIR = './downloads'
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

app.register_blueprint(download_song_bp, url_prefix='/download-song')
app.register_blueprint(download_album_bp, url_prefix='/download-album')

@app.route('/downloads/<path:filename>')
def download_file(filename):
    file_path = os.path.join(DOWNLOAD_DIR, filename)
    if not os.path.isfile(file_path):
        return jsonify({"error": "Archivo no encontrado"}), 404
    
    # Forzar descarga con as_attachment=True
    return send_file(file_path, as_attachment=True)

@app.route('/check')
def check():
    return jsonify({"status": "ok"}), 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)), debug=True)