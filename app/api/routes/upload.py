from fastapi import APIRouter, UploadFile, File, HTTPException
import shutil
import os
from pathlib import Path
from typing import Dict

router = APIRouter()

UPLOAD_DIR = Path(os.getenv("UPLOADS_DIR", "uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@router.post("/upload")
async def upload_document(file: UploadFile = File(...)) -> Dict[str, str]:
    # Validate file type
    filename = Path(file.filename)
    if filename.suffix.lower() not in (".docx",):
        raise HTTPException(status_code=400, detail="Only .docx files are supported")

    dest = UPLOAD_DIR / filename.name
    try:
        with dest.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    finally:
        file.file.close()

    return {"status": "success", "filename": str(dest)}
