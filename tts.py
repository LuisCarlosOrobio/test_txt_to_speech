import os
import uuid
import subprocess
import json
from fastapi import FastAPI, WebSocket, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import asyncio

app = FastAPI()

# Serve static files
app.mount("/static", StaticFiles(directory="static"), name="static")

AUDIO_FOLDER = "temporary_audio_files"
if not os.path.exists(AUDIO_FOLDER):
    os.makedirs(AUDIO_FOLDER)

active_websockets = {}

@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: int):
    await websocket.accept()
    active_websockets[client_id] = websocket
    try:
        while True:
            data = await websocket.receive_json()
            audio_file = await process_json_and_generate_audio(data)
            await send_audio_file(active_websockets[client_id], audio_file)
    except Exception as e:
        print(f"Error: {e}")
    finally:
        del active_websockets[client_id]

async def process_json_and_generate_audio(data):
    piper_input = json.dumps(data)
    piper_command = ["piper", "--json-input"]
    output_file = os.path.join(AUDIO_FOLDER, f"{uuid.uuid4()}.wav")
    data['output_file'] = output_file

    with subprocess.Popen(piper_command, stdin=subprocess.PIPE, stdout=subprocess.PIPE) as process:
        process.stdin.write(piper_input.encode())
        process.stdin.close()
        await process.wait()

    return output_file

async def send_audio_file(websocket: WebSocket, file_path):
    with open(file_path, 'rb') as f:
        audio_data = f.read()
    await websocket.send_bytes(audio_data)

@app.get("/audio/{filename}")
async def serve_audio(filename: str):
    file_path = os.path.join(AUDIO_FOLDER, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path)

# Serve index.html for the root URL
@app.get("/")
async def read_root():
    return FileResponse('static/index.html')

# Periodic cleanup of old audio files
async def cleanup_old_audio_files():
    now = time.time()
    for file in os.listdir(AUDIO_FOLDER):
        file_path = os.path.join(AUDIO_FOLDER, file)
        if os.stat(file_path).st_mtime < now - 3600:  # 1 hour
            try:
                os.remove(file_path)
            except Exception as e:
                print(f"Failed to delete {file_path}: {e}")

# Run the cleanup every hour
@app.on_event("startup")
async def start_cleanup_task():
    while True:
        await asyncio.sleep(3600)  # Wait for 1 hour
        await cleanup_old_audio_files()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

