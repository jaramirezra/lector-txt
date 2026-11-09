"""Pruebas de la API: subida, desbloqueo, render y exportación."""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from app import create_app


def make_client(tmp_path: Path, **overrides):
    config = {
        "TESTING": True,
        "JOBS_DIR": str(tmp_path / "jobs"),
        "MAX_FILE_MB": 30,
        "MAX_PAGES": 300,
        "JOB_TTL": 3600,
        "MAX_ATTEMPTS": 5,
        "RENDER_DPI": 72,
    }
    config.update(overrides)
    app = create_app(config)
    return app.test_client()


def upload(client, data: bytes, filename: str):
    return client.post(
        "/api/jobs",
        data={"file": (io.BytesIO(data), filename)},
        content_type="multipart/form-data",
    )


def test_upload_export_and_page_render(tmp_path: Path, sample_pdf_bytes: bytes):
    client = make_client(tmp_path)
    response = upload(client, sample_pdf_bytes, "informe.pdf")

    assert response.status_code == 201
    payload = response.get_json()
    assert payload["status"] == "ready"
    assert payload["kind"] == "pdf"
    assert payload["page_count"] == 3
    assert payload["blocks"]

    job_id = payload["job_id"]

    image = client.get(f"/api/jobs/{job_id}/pages/1.png")
    assert image.status_code == 200
    assert image.mimetype == "image/png"
    assert image.data.startswith(b"\x89PNG")

    included = [
        block["id"]
        for block in payload["blocks"]
        if not block["suggested"]
    ]
    exported = client.post(
        f"/api/jobs/{job_id}/export",
        json={"included": included},
    )

    assert exported.status_code == 200
    assert exported.mimetype == "text/plain"
    text = exported.data.decode("utf-8")
    assert "Contenido de la pagina 1." in text
    assert "Informe confidencial" not in text
    assert "Pagina 1 de 3" not in text
    assert "informe.txt" in exported.headers["Content-Disposition"]


def test_password_flow(tmp_path: Path, encrypted_pdf_bytes: bytes):
    client = make_client(tmp_path)
    response = upload(client, encrypted_pdf_bytes, "cifrado.pdf")

    assert response.status_code == 202
    payload = response.get_json()
    assert payload["status"] == "locked"
    assert payload["attempts_left"] == 5
    job_id = payload["job_id"]

    locked_page = client.get(f"/api/jobs/{job_id}/pages/1.png")
    assert locked_page.status_code == 423

    wrong = client.post(f"/api/jobs/{job_id}/unlock", json={"password": "mala"})
    assert wrong.status_code == 401
    assert wrong.get_json()["attempts_left"] == 4

    correct = client.post(f"/api/jobs/{job_id}/unlock", json={"password": "clave"})
    assert correct.status_code == 200
    unlocked = correct.get_json()
    assert unlocked["status"] == "ready"
    assert unlocked["encryption"]["level"] == "user"
    assert unlocked["blocks"]

    image = client.get(f"/api/jobs/{job_id}/pages/1.png")
    assert image.status_code == 200


def test_password_lockout(tmp_path: Path, encrypted_pdf_bytes: bytes):
    client = make_client(tmp_path, MAX_ATTEMPTS=2)
    payload = upload(client, encrypted_pdf_bytes, "cifrado.pdf").get_json()
    job_id = payload["job_id"]

    first = client.post(f"/api/jobs/{job_id}/unlock", json={"password": "mala"})
    assert first.status_code == 401
    assert first.get_json()["attempts_left"] == 1

    second = client.post(f"/api/jobs/{job_id}/unlock", json={"password": "mala"})
    assert second.status_code == 410

    gone = client.post(f"/api/jobs/{job_id}/unlock", json={"password": "clave"})
    assert gone.status_code == 404


def test_owner_only_pdf_warning(tmp_path: Path, owner_only_pdf_bytes: bytes):
    client = make_client(tmp_path)
    response = upload(client, owner_only_pdf_bytes, "permisos.pdf")

    assert response.status_code == 201
    payload = response.get_json()
    assert payload["status"] == "ready"
    assert payload["encryption"]["level"] == "owner"
    assert payload["encryption"]["can_copy"] is False
    assert payload["warnings"]


def test_encrypted_docx(tmp_path: Path, encrypted_docx_bytes: bytes):
    client = make_client(tmp_path)
    response = upload(client, encrypted_docx_bytes, "cifrado.docx")

    assert response.status_code == 202
    job_id = response.get_json()["job_id"]

    unlocked = client.post(f"/api/jobs/{job_id}/unlock", json={"password": "clave"})
    assert unlocked.status_code == 200
    payload = unlocked.get_json()
    assert payload["kind"] == "docx"
    assert payload["preview_html"]
    assert any(block["text"] == "Titulo del documento" for block in payload["blocks"])


def test_export_manual_override_with_crlf_and_bom(tmp_path: Path, sample_pdf_bytes: bytes):
    client = make_client(tmp_path)
    payload = upload(client, sample_pdf_bytes, "informe.pdf").get_json()
    job_id = payload["job_id"]

    exported = client.post(
        f"/api/jobs/{job_id}/export",
        json={
            "included": [],
            "text_override": "Linea uno\nLinea dos",
            "options": {"newline": "crlf", "encoding": "utf-8-sig"},
        },
    )

    assert exported.status_code == 200
    assert exported.data.startswith(b"\xef\xbb\xbf")
    assert b"Linea uno\r\nLinea dos\r\n" in exported.data


def test_unsupported_and_delete(tmp_path: Path, sample_pdf_bytes: bytes):
    client = make_client(tmp_path)

    rejected = upload(client, b"no soy un documento", "nota.txt")
    assert rejected.status_code == 415

    payload = upload(client, sample_pdf_bytes, "informe.pdf").get_json()
    job_id = payload["job_id"]
    assert client.delete(f"/api/jobs/{job_id}").status_code == 204
    assert client.get(f"/api/jobs/{job_id}/pages/1.png").status_code == 404


def test_health(tmp_path: Path):
    client = make_client(tmp_path)
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.get_json()["status"] == "ok"
