from fastapi import FastAPI, UploadFile, File, Form, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import uuid
import shutil
from pathlib import Path
import os
from typing import List

app = FastAPI()

# Configurar CORS para permitir peticiones desde el frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# Connection Manager for WebSockets
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                # Handle potential errors if connection is closed but not yet removed
                pass

manager = ConnectionManager()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive, maybe wait for messages if needed
            # For this use case, we just need to keep it open to receive broadcasts
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.post("/upload")
async def upload_file(file: UploadFile = File(...), user_id: str = Form(...)):
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")
    
    user_dir = UPLOAD_DIR / user_id
    user_dir.mkdir(exist_ok=True)
    
    file_id = str(uuid.uuid4())
    # Keep original filename but prepend ID to avoid collisions
    safe_filename = f"{file_id}_{file.filename}"
    file_path = user_dir / safe_filename

    with file_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Broadcast new file event
    await manager.broadcast('{"event": "new_file"}')

    return {
        "file_id": file_id,
        "filename": file.filename,
        "user_id": user_id,
        "url": f"http://127.0.0.1:8000/files/{user_id}/{safe_filename}"
    }

@app.get("/files/all")
def list_all_files():
    all_files = []
    # Iterate through all user directories
    if UPLOAD_DIR.exists():
        for user_dir in UPLOAD_DIR.iterdir():
            if user_dir.is_dir():
                user_id = user_dir.name
                for file_path in user_dir.iterdir():
                    if file_path.is_file():
                        all_files.append({
                            "user_id": user_id,
                            "filename": file_path.name.split('_', 1)[1] if '_' in file_path.name else file_path.name,
                            "stored_filename": file_path.name,
                            "url": f"http://127.0.0.1:8000/files/{user_id}/{file_path.name}"
                        })
    return all_files

@app.get("/files/{user_id}")
def list_user_files(user_id: str):
    user_files = []
    user_dir = UPLOAD_DIR / user_id
    
    if user_dir.exists() and user_dir.is_dir():
        for file_path in user_dir.iterdir():
            if file_path.is_file():
                user_files.append({
                    "user_id": user_id,
                    "filename": file_path.name.split('_', 1)[1] if '_' in file_path.name else file_path.name,
                    "stored_filename": file_path.name,
                    "url": f"http://127.0.0.1:8000/files/{user_id}/{file_path.name}"
                })
    return user_files

@app.get("/files/{user_id}/{filename}")
def get_file(user_id: str, filename: str):
    file_path = UPLOAD_DIR / user_id / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path)

