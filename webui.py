import json
import os
import sys
import logging
import asyncio
import threading
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

import uvicorn

from LGTV.scan import LGTVScan
from LGTV.remote import LGTVRemote
from LGTV.auth import LGTVAuth
from LGTV.cursor import LGTVCursor
from LGTV import find_config, write_config

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="LGTV WebOS Remote UI")

# Ensure static and templates directories exist
os.makedirs("static", exist_ok=True)
os.makedirs("templates", exist_ok=True)

app.mount("/static", StaticFiles(directory="static"), name="static")

def get_config():
    try:
        filename = find_config()
        if os.path.isfile(filename):
            with open(filename, "r") as f:
                return json.load(f), filename
    except Exception as e:
        logger.error(f"Error loading config: {e}")
    return {}, None

class CommandRequest(BaseModel):
    tv_name: str
    command: str
    args: Optional[Dict[str, Any]] = None

class AuthRequest(BaseModel):
    tv_name: str
    host: str

class RemoveTVRequest(BaseModel):
    tv_name: str

@app.get("/", response_class=HTMLResponse)
def read_root():
    with open("templates/index.html", "r") as f:
        return f.read()

@app.get("/api/config")
def api_get_config():
    config, _ = get_config()
    # Filter out _default if we just want a list of TVs
    tvs = {k: v for k, v in config.items() if k != "_default"}
    default_tv = config.get("_default")
    return {"tvs": tvs, "default": default_tv}

@app.post("/api/scan")
def api_scan():
    try:
        results = LGTVScan()
        return {"count": len(results), "list": results}
    except Exception as e:
        logger.error(f"Scan error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/auth")
def api_auth(req: AuthRequest):
    config, filename = get_config()
    if not filename:
        raise HTTPException(status_code=500, detail="Cannot find config file")

    try:
        logger.info(f"Authenticating with {req.tv_name} at {req.host} using SSL")
        ws = LGTVAuth(req.tv_name, req.host, ssl=True)
        ws.connect()
        # run_forever blocks, so we should run it in a separate thread or just let it finish.
        # auth typically needs pairing confirmed on the TV.
        # ws4py client run_forever blocks until connection closes.

        # We give the user 30 seconds to confirm on the TV
        timer = threading.Timer(30.0, ws.close)
        timer.start()

        ws.run_forever()
        timer.cancel()

        config[req.tv_name] = ws.serialise()
        if "_default" not in config:
            config["_default"] = req.tv_name

        write_config(filename, config)
        return {"status": "success", "message": f"Successfully authenticated and saved config for {req.tv_name}"}
    except Exception as e:
        logger.error(f"Auth error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/remove_tv")
def api_remove_tv(req: RemoveTVRequest):
    config, filename = get_config()
    if not filename:
        raise HTTPException(status_code=500, detail="Cannot find config file")

    if req.tv_name in config:
        del config[req.tv_name]
        # Update default if needed
        if config.get("_default") == req.tv_name:
            remaining_tvs = [k for k in config.keys() if k != "_default"]
            if remaining_tvs:
                config["_default"] = remaining_tvs[0]
            else:
                del config["_default"]

        write_config(filename, config)
        return {"status": "success", "message": f"Successfully removed {req.tv_name}"}
    else:
        raise HTTPException(status_code=404, detail=f"TV '{req.tv_name}' not found in config")

@app.post("/api/command")
def api_command(req: CommandRequest):
    config, filename = get_config()
    if req.tv_name not in config:
        raise HTTPException(status_code=404, detail=f"TV '{req.tv_name}' not found in config")

    tv_config = config[req.tv_name]

    # We will gather the response
    command_response = None

    def callback(res):
        nonlocal command_response
        command_response = res
        logger.info(f"Callback response: {res}")

    try:
        kwargs = req.args or {}

        if req.command == "sendButton":
            cursor = LGTVCursor(req.tv_name, **tv_config, ssl=True)
            cursor.connect()
            # args should be a list for sendButton
            button_args = kwargs.get("buttons", [])
            cursor.execute(button_args)
            return {"status": "success", "command": req.command}

        ws = LGTVRemote(req.tv_name, **tv_config, ssl=True)

        if req.command == "on":
            ws.on()
            return {"status": "success", "command": req.command}

        # We check if the command takes a callback
        import inspect
        if hasattr(ws, req.command):
            method = getattr(ws, req.command)
            sig = inspect.signature(method)
            if 'callback' in sig.parameters:
                def close_callback(res):
                    nonlocal command_response
                    command_response = res
                    logger.info(f"Custom callback response: {res}")
                    ws.close()
                kwargs['callback'] = close_callback

        ws.connect()
        ws.execute(req.command, kwargs)

        timer = threading.Timer(5.0, ws.close)
        timer.start()

        ws.run_forever()
        timer.cancel()

        return {"status": "success", "command": req.command, "response": command_response}

    except Exception as e:
        logger.error(f"Command error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/dashboard")
def api_dashboard(tv_name: str):
    config, filename = get_config()
    if tv_name not in config:
        raise HTTPException(status_code=404, detail=f"TV '{tv_name}' not found")

    tv_config = config[tv_name]

    # We want to get: volume, current app, mute status, power state.
    # We will do this by executing multiple commands sequentially.
    # However, running multiple commands with LGTVRemote might be tricky if it closes connection.
    # Actually LGTVRemote executes all commands in the queue before closing IF we don't close.
    # So we queue them up and collect responses.

    dashboard_data = {}

    def handle_audio(res):
        if "payload" in res:
            dashboard_data["audio"] = res["payload"]

    def handle_app(res):
        if "payload" in res:
            dashboard_data["app"] = res["payload"]

    try:
        ws = LGTVRemote(tv_name, **tv_config, ssl=True)
        ws.connect()

        expected_responses = 2
        received_responses = 0

        def handle_audio_close(res):
            nonlocal received_responses
            handle_audio(res)
            received_responses += 1
            if received_responses == expected_responses:
                ws.close()

        def handle_app_close(res):
            nonlocal received_responses
            handle_app(res)
            received_responses += 1
            if received_responses == expected_responses:
                ws.close()

        ws.execute("audioStatus", {"callback": handle_audio_close})
        ws.execute("getForegroundAppInfo", {"callback": handle_app_close})

        timer = threading.Timer(3.0, ws.close)
        timer.start()

        ws.run_forever()
        timer.cancel()

        return {"status": "success", "data": dashboard_data}
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
