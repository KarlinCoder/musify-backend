import os
from flask import Flask, jsonify, send_file
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from routes.download import download_song_bp
from routes.download_album import download_album_bp
from routes.search import search_bp
from routes.album import album_bp
from routes.artist import artist_bp
from routes.charts import chart_bp
from routes.artist_discography import artist_discography_bp
from routes.song_preview import song_preview_bp
from routes.playlist import playlist_bp 
from routes.playlist_tracks import playlist_tracks_bp

app = Flask(__name__)
CORS(app)

# Configuración del Rate Limiter
limiter = Limiter(
    app=app,
    key_func=get_remote_address,  # Limita por dirección IP
    default_limits=["200 per hour", "50 per minute"]  # Límites globales
)

# Límites específicos para rutas que consumen más recursos
limiter.limit("120 per hour")(download_song_bp)
limiter.limit("50 per hour")(download_album_bp)
limiter.limit("120 per hour")(playlist_tracks_bp)

# Directorio de descargas
DOWNLOAD_DIR = './downloads'
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Registro de blueprints con sus prefijos
app.register_blueprint(download_song_bp, url_prefix='/download-song')
app.register_blueprint(download_album_bp, url_prefix='/download-album')
app.register_blueprint(search_bp, url_prefix="/search")
app.register_blueprint(album_bp, url_prefix="/album")
app.register_blueprint(artist_bp, url_prefix="/artist")
app.register_blueprint(chart_bp, url_prefix='/chart')
app.register_blueprint(artist_discography_bp, url_prefix='/artist-discography')
app.register_blueprint(song_preview_bp, url_prefix='/song-preview')
app.register_blueprint(playlist_bp, url_prefix='/playlist')  
app.register_blueprint(playlist_tracks_bp, url_prefix='/playlist-tracks')

@app.route('/downloads/<path:filename>')
@limiter.limit("50 per hour")  # Límite específico para descargas
def download_file(filename):
    file_path = os.path.join(DOWNLOAD_DIR, filename)
    if not os.path.isfile(file_path):
        return jsonify({"error": "Archivo no encontrado"}), 404
    
    return send_file(file_path, as_attachment=True)

@app.route('/check')
def check():
    return jsonify({"status": "ok"}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)), debug=True)