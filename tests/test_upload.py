import io

from docx import Document
from fastapi.testclient import TestClient

from app.api.routes import upload
from app.main import app

client = TestClient(app)


def test_upload_docx(monkeypatch, tmp_path):
    monkeypatch.setattr(upload, "UPLOAD_DIR", tmp_path)
    doc = Document()
    doc.add_paragraph("Hello Bookly")
    f = io.BytesIO()
    doc.save(f)
    f.seek(0)

    files = {"file": ("test.docx", f, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
    resp = client.post("/upload", files=files)
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"
    assert (tmp_path / "test.docx").exists()
