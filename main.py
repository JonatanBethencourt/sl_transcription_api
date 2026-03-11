
from fastapi import FastAPI, UploadFile, File
import subprocess
import sys
import os
import uuid
from pathlib import Path

app = FastAPI()

UPLOAD_DIR = Path("/tmp/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

@app.post("/run-script")
async def run_script(file: UploadFile = File(...)):
    try:
        # Save uploaded file
        temp_filename = f"{uuid.uuid4()}_{file.filename}"
        temp_path = UPLOAD_DIR / temp_filename

        with temp_path.open("wb") as f:
            f.write(await file.read())

        # Pass this path to processor.py
        os.environ["INPUT_DOCX_PATH"] = str(temp_path)

        # Run your existing script
        result = subprocess.run(
            [sys.executable, "processor.py"],
            capture_output=True,
            text=True
        )

        # Delete file
        try:
            temp_path.unlink()
        except:
            pass

        return {
            "status": "completed",
            "stdout": result.stdout,
            "stderr": result.stderr
        }

    except Exception as e:
        return {"status": "error", "message": str(e)}