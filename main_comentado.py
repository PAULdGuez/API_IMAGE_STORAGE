# Importa FastAPI que es el framework principal para crear la API web
# Importa UploadFile para manejar archivos subidos
# Importa File para definir parámetros de tipo archivo
# Importa Form para manejar datos de formulario
# Importa HTTPException para lanzar errores HTTP personalizados
# Importa WebSocket para manejar conexiones WebSocket en tiempo real
# Importa WebSocketDisconnect para manejar desconexiones de WebSocket
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, WebSocket, WebSocketDisconnect

# Importa CORSMiddleware para configurar políticas de CORS (Cross-Origin Resource Sharing)
# Esto permite que el frontend pueda hacer peticiones al backend desde un origen diferente
from fastapi.middleware.cors import CORSMiddleware

# Importa FileResponse para enviar archivos como respuesta HTTP
from fastapi.responses import FileResponse

# Importa uuid para generar identificadores únicos universales
# Se usa para crear IDs únicos para cada archivo subido
import uuid

# Importa shutil que proporciona operaciones de alto nivel para archivos
# Se usa específicamente para copiar el contenido del archivo subido
import shutil

# Importa Path de pathlib para manejar rutas de archivos de forma orientada a objetos
# Facilita operaciones como crear directorios, verificar existencia, etc.
from pathlib import Path

# Importa os para operaciones del sistema operativo (aunque no se usa directamente aquí)
import os

# Importa List de typing para anotaciones de tipos
# Se usa para indicar que una variable es una lista de un tipo específico
from typing import List

# Crea la instancia principal de la aplicación FastAPI
# Esta instancia es el punto de entrada de toda la API
app = FastAPI()

# Configurar CORS para permitir peticiones desde el frontend
# add_middleware añade un middleware que se ejecuta en cada petición
app.add_middleware(
    CORSMiddleware,  # El middleware de CORS que maneja las cabeceras de origen cruzado
    allow_origins=["http://localhost:3000"],  # Lista de orígenes permitidos (el frontend en puerto 3000)
    allow_credentials=True,  # Permite enviar cookies y credenciales en las peticiones
    allow_methods=["*"],  # Permite todos los métodos HTTP (GET, POST, PUT, DELETE, etc.)
    allow_headers=["*"],  # Permite todas las cabeceras HTTP en las peticiones
)

# Define la ruta del directorio donde se guardarán los archivos subidos
# Path("uploads") crea un objeto Path que representa el directorio "uploads"
UPLOAD_DIR = Path("uploads")

# Crea el directorio "uploads" si no existe
# exist_ok=True evita que lance error si el directorio ya existe
UPLOAD_DIR.mkdir(exist_ok=True)

# Security: Allowed file extensions and max file size
# Define un conjunto (set) de extensiones de archivo permitidas para subida
# Esto previene la subida de archivos potencialmente peligrosos
ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.pdf', '.doc', '.docx', '.xlsx', '.xls', '.txt', '.csv'}

# Define el tamaño máximo de archivo permitido: 10MB
# Se calcula: 10 * 1024 (KB) * 1024 (bytes) = 10,485,760 bytes
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

# Connection Manager for WebSockets
# Define una clase para gestionar las conexiones WebSocket activas
# Esta clase mantiene un registro de todos los clientes conectados
class ConnectionManager:
    # Método constructor que se ejecuta al crear una instancia de la clase
    def __init__(self):
        # Inicializa una lista vacía para almacenar las conexiones WebSocket activas
        # La anotación List[WebSocket] indica que es una lista de objetos WebSocket
        self.active_connections: List[WebSocket] = []

    # Método asíncrono para aceptar una nueva conexión WebSocket
    # async indica que este método es una corutina (se puede pausar y reanudar)
    async def connect(self, websocket: WebSocket):
        # Acepta la conexión WebSocket entrante
        # Esto completa el handshake de WebSocket con el cliente
        await websocket.accept()
        # Añade la conexión a la lista de conexiones activas
        self.active_connections.append(websocket)

    # Método para eliminar una conexión WebSocket de la lista
    # No es async porque remove() es una operación síncrona
    def disconnect(self, websocket: WebSocket):
        # Elimina el websocket específico de la lista de conexiones activas
        self.active_connections.remove(websocket)

    # Método asíncrono para enviar un mensaje a todos los clientes conectados
    # Se usa para notificar a todos cuando hay un nuevo archivo
    async def broadcast(self, message: str):
        # Itera sobre cada conexión activa en la lista
        for connection in self.active_connections:
            # Try-except para manejar errores si una conexión se cerró inesperadamente
            try:
                # Envía el mensaje de texto a la conexión actual
                await connection.send_text(message)
            except Exception:
                # Handle potential errors if connection is closed but not yet removed
                # Si hay un error (conexión cerrada), simplemente continúa con la siguiente
                pass

# Crea una instancia global del ConnectionManager
# Esta instancia se usa en toda la aplicación para gestionar WebSockets
manager = ConnectionManager()

# Decorador que define un endpoint WebSocket en la ruta "/ws"
# Los clientes se conectarán a ws://127.0.0.1:8000/ws para recibir actualizaciones en tiempo real
@app.websocket("/ws")
# Función asíncrona que maneja cada conexión WebSocket entrante
# Recibe el objeto WebSocket que representa la conexión del cliente
async def websocket_endpoint(websocket: WebSocket):
    # Llama al método connect del manager para aceptar y registrar la conexión
    await manager.connect(websocket)
    # Try-except para manejar la desconexión del cliente
    try:
        # Bucle infinito que mantiene la conexión abierta
        while True:
            # Keep connection alive, maybe wait for messages if needed
            # For this use case, we just need to keep it open to receive broadcasts
            # Espera a recibir un mensaje de texto del cliente
            # Esto mantiene la conexión activa y detecta cuando el cliente se desconecta
            await websocket.receive_text()
    # Captura la excepción cuando el cliente se desconecta
    except WebSocketDisconnect:
        # Elimina la conexión de la lista de conexiones activas
        manager.disconnect(websocket)

# Decorador que define un endpoint POST en la ruta "/upload"
# Este endpoint maneja la subida de archivos
@app.post("/upload")
# Función asíncrona que procesa la subida de archivos
# file: el archivo subido, usando File(...) indica que es un campo requerido
# user_id: el ID del usuario, obtenido de datos de formulario, también requerido
async def upload_file(file: UploadFile = File(...), user_id: str = Form(...)):
    # Verifica que el user_id no esté vacío
    if not user_id:
        # Lanza un error HTTP 400 (Bad Request) si no hay user_id
        raise HTTPException(status_code=400, detail="user_id is required")
    
    # Security: Validate file extension
    # Obtiene la extensión del archivo y la convierte a minúsculas
    # Si no hay filename, usa una cadena vacía
    file_ext = Path(file.filename).suffix.lower() if file.filename else ''
    # Verifica si la extensión está en la lista de extensiones permitidas
    if file_ext not in ALLOWED_EXTENSIONS:
        # Lanza un error HTTP 400 si el tipo de archivo no está permitido
        raise HTTPException(
            status_code=400,  # Código de estado HTTP 400 (Bad Request)
            detail=f"Tipo de archivo no permitido. Extensiones válidas: {', '.join(ALLOWED_EXTENSIONS)}"  # Mensaje de error con las extensiones válidas
        )
    
    # Security: Check file size
    # Mueve el cursor al final del archivo para obtener su tamaño
    # seek(0, 2) significa: mover 0 bytes desde el final (2 = SEEK_END)
    file.file.seek(0, 2)  # Move to end of file
    # Obtiene la posición actual del cursor, que es el tamaño del archivo en bytes
    file_size = file.file.tell()
    # Regresa el cursor al inicio del archivo para poder leerlo después
    file.file.seek(0)  # Reset to beginning
    
    # Verifica si el tamaño del archivo excede el máximo permitido
    if file_size > MAX_FILE_SIZE:
        # Lanza un error HTTP 413 (Payload Too Large) si el archivo es muy grande
        raise HTTPException(
            status_code=413,  # Código de estado HTTP 413 (Payload Too Large)
            detail=f"Archivo muy grande. Tamaño máximo: {MAX_FILE_SIZE // (1024*1024)}MB"  # Convierte bytes a MB para el mensaje
        )
    
    # Crea la ruta del directorio del usuario dentro de UPLOAD_DIR
    # Cada usuario tiene su propia carpeta para sus archivos
    user_dir = UPLOAD_DIR / user_id
    # Crea el directorio del usuario si no existe
    user_dir.mkdir(exist_ok=True)
    
    # Genera un UUID (identificador único universal) para el archivo
    # Esto asegura que cada archivo tenga un ID único
    file_id = str(uuid.uuid4())
    # Keep original filename but prepend ID to avoid collisions
    # Crea un nombre de archivo seguro: UUID + nombre original
    # Esto evita colisiones si dos usuarios suben archivos con el mismo nombre
    safe_filename = f"{file_id}_{file.filename}"
    # Crea la ruta completa donde se guardará el archivo
    file_path = user_dir / safe_filename

    # Abre el archivo de destino en modo escritura binaria ("wb")
    # El context manager (with) asegura que el archivo se cierre correctamente
    with file_path.open("wb") as buffer:
        # Copia el contenido del archivo subido al archivo de destino
        # copyfileobj es eficiente para archivos grandes, copia por chunks
        shutil.copyfileobj(file.file, buffer)

    # Broadcast new file event
    # Notifica a todos los clientes WebSocket conectados que hay un nuevo archivo
    # Envía un JSON con el evento "new_file"
    await manager.broadcast('{"event": "new_file"}')

    # Retorna un diccionario con la información del archivo subido
    # FastAPI automáticamente lo convierte a JSON
    return {
        "file_id": file_id,  # El ID único generado para el archivo
        "filename": file.filename,  # El nombre original del archivo
        "user_id": user_id,  # El ID del usuario que subió el archivo
        "url": f"http://127.0.0.1:8000/files/{user_id}/{safe_filename}"  # La URL para acceder al archivo
    }

# Decorador que define un endpoint GET en la ruta "/files/all"
# Este endpoint lista todos los archivos de todos los usuarios
@app.get("/files/all")
# Función síncrona (no async) que retorna la lista de todos los archivos
def list_all_files():
    # Inicializa una lista vacía para almacenar la información de los archivos
    all_files = []
    # Iterate through all user directories
    # Verifica si el directorio de uploads existe
    if UPLOAD_DIR.exists():
        # Itera sobre cada elemento (subdirectorio de usuario) en UPLOAD_DIR
        for user_dir in UPLOAD_DIR.iterdir():
            # Verifica que el elemento sea un directorio (no un archivo suelto)
            if user_dir.is_dir():
                # Obtiene el nombre del directorio, que es el user_id
                user_id = user_dir.name
                # Itera sobre cada archivo dentro del directorio del usuario
                for file_path in user_dir.iterdir():
                    # Verifica que el elemento sea un archivo (no un subdirectorio)
                    if file_path.is_file():
                        # Añade un diccionario con la información del archivo a la lista
                        all_files.append({
                            "user_id": user_id,  # El ID del usuario propietario
                            # Extrae el nombre original del archivo (después del primer "_")
                            # Si no tiene "_", usa el nombre completo
                            "filename": file_path.name.split('_', 1)[1] if '_' in file_path.name else file_path.name,
                            "stored_filename": file_path.name,  # El nombre almacenado (con UUID)
                            "url": f"http://127.0.0.1:8000/files/{user_id}/{file_path.name}"  # URL de acceso
                        })
    # Retorna la lista de todos los archivos encontrados
    return all_files

# Decorador que define un endpoint GET con parámetro dinámico {user_id}
# Este endpoint lista los archivos de un usuario específico
@app.get("/files/{user_id}")
# Función que recibe el user_id como parámetro de ruta
def list_user_files(user_id: str):
    # Inicializa una lista vacía para los archivos del usuario
    user_files = []
    # Construye la ruta al directorio del usuario
    user_dir = UPLOAD_DIR / user_id
    
    # Verifica que el directorio exista y sea un directorio (no un archivo)
    if user_dir.exists() and user_dir.is_dir():
        # Itera sobre cada archivo en el directorio del usuario
        for file_path in user_dir.iterdir():
            # Verifica que sea un archivo
            if file_path.is_file():
                # Añade la información del archivo a la lista
                user_files.append({
                    "user_id": user_id,  # El ID del usuario
                    # Extrae el nombre original quitando el UUID del prefijo
                    "filename": file_path.name.split('_', 1)[1] if '_' in file_path.name else file_path.name,
                    "stored_filename": file_path.name,  # Nombre con UUID
                    "url": f"http://127.0.0.1:8000/files/{user_id}/{file_path.name}"  # URL de descarga
                })
    # Retorna la lista de archivos del usuario
    return user_files

# Decorador que define un endpoint GET para descargar un archivo específico
# {user_id} y {filename} son parámetros dinámicos de la ruta
@app.get("/files/{user_id}/{filename}")
# Función que permite descargar un archivo específico
def get_file(user_id: str, filename: str):
    # Construye la ruta completa al archivo y la resuelve a una ruta absoluta
    # resolve() convierte rutas relativas a absolutas y normaliza la ruta
    file_path = (UPLOAD_DIR / user_id / filename).resolve()
    
    # Security: Prevent path traversal attacks
    # Verifica que la ruta resuelta esté dentro del directorio de uploads
    # Esto previene ataques donde alguien intenta acceder a ../ para salir del directorio
    if not str(file_path).startswith(str(UPLOAD_DIR.resolve())):
        # Lanza un error HTTP 403 (Forbidden) si se detecta un intento de path traversal
        raise HTTPException(status_code=403, detail="Acceso denegado")
    
    # Verifica si el archivo existe en el sistema de archivos
    if not file_path.exists():
        # Lanza un error HTTP 404 (Not Found) si el archivo no existe
        raise HTTPException(status_code=404, detail="File not found")
    # Retorna el archivo como respuesta HTTP
    # FileResponse se encarga de establecer las cabeceras correctas y enviar el archivo
    return FileResponse(file_path)
