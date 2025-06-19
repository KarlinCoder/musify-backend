import requests

def upload_to_tmpfiles(file_path):
    url = "https://tmpfiles.org/api/v1/upload" 
    with open(file_path, "rb") as file:
        files = {"file": file}
        response = requests.post(url, files=files)

        if response.status_code == 200:
            data = response.json()
            # El enlace se encuentra en data['data']['url']
            return data['data']['url'].replace("https://tmpfiles.org/",  "https://tmpfiles.org/dl/") 
        else:
            raise Exception(f"Error al subir el archivo: {response.text}")

# Ejemplo de uso
if __name__ == "__main__":
    archivo = "./archivo.txt"  # Cambia esto por la ruta real
    enlace = upload_to_tmpfiles(archivo)
    print("Archivo subido. Enlace:", enlace)