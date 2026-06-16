import os
from fastapi.testclient import TestClient
from app.main import app
import io


client = TestClient(app)


def test_upload_docx():
    # Create a minimal docx in memory
    from docx import Document
    doc = Document()
    doc.add_paragraph("Hello Bookly")
    f = io.BytesIO()
    doc.save(f)
    f.seek(0)

    files = {"file": ("test.docx", f, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
    resp = client.post("/upload", files=files)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
