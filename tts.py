from fastapi import FastAPI, WebSocket, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os
import uuid
import json
import asyncio
import time

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
            if audio_file:  # Check if file was successfully created
                await send_audio_file(active_websockets[client_id], audio_file)
    except Exception as e:
        print(f"Error: {e}")
    finally:
        del active_websockets[client_id]

async def process_json_and_generate_audio(data):
    model = "/root/piper-voices/en/en_US/lessac/medium/en_US-lessac-medium.onnx"
    piper_input = json.dumps(data)
    print(f"Input data for piper: {piper_input}")  # Log input data

    piper_command = ["piper", "--json-input", "--model", model, "--use-cuda"]
    output_file = os.path.join(AUDIO_FOLDER, f"{uuid.uuid4()}.wav")
    data['output_file'] = output_file

    process = await asyncio.create_subprocess_exec(
        *piper_command,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    process.stdin.write(piper_input.encode())
    await process.stdin.drain()
    process.stdin.close()

    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        print(f"piper command failed with return code {process.returncode}")
        print(f"Standard Output: {stdout.decode()}")
        print(f"Standard Error: {stderr.decode()}")
        return None

    if not os.path.exists(output_file):
        print(f"Expected audio file was not created: {output_file}")
        return None

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

@app.get("/")
async def read_root():
    return FileResponse('static/index.html')

async def cleanup_old_audio_files():
    now = time.time()
    for file in os.listdir(AUDIO_FOLDER):
        file_path = os.path.join(AUDIO_FOLDER, file)
        if os.stat(file_path).st_mtime < now - 3600:  # 1 hour
            try:
                os.remove(file_path)
            except Exception as e:
                print(f"Failed to delete {file_path}: {e}")

@app.on_event("startup")
async def on_startup():
    asyncio.create_task(run_periodic_cleanup())

@app.on_event("shutdown")
async def on_shutdown():
    pass  # No specific shutdown logic required

async def run_periodic_cleanup():
    while True:
        await asyncio.sleep(3600)  # Wait for 1 hour
        await cleanup_old_audio_files()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
