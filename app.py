"""Aplicación web local: documentos a TXT con recorte visual."""

from __future__ import annotations

import io
import os
import secrets
import tempfile
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request, send_file
from werkzeug.exceptions import HTTPException

from lector import __version__
from lector.extract import analyze, sniff_kind
from lector.export import ExportOptions, build_text
from lector.jobs import Job, JobNotFound, JobStore, TooLargeError
from lector.models import count_words
from lector.pdf import render_pdf_page
from lector.security import DocumentError, LockedDocument, WrongPassword


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _public_job(job: Job) -> dict:
    payload = {
        "job_id": job.id,
        "status": job.status,
        "kind": job.kind,
        "filename": job.filename,
        "page_count": job.page_count,
        "encryption": job.encryption,
        "warnings": job.warnings,
    }
    if job.status == "ready":
        words = sum(count_words(block.text) for block in job.blocks)
        payload.update(
            {
                "pages": [page.to_dict() for page in job.pages],
                "blocks": [block.to_dict() for block in job.blocks],
                "preview_html": job.preview_html,
                "stats": {"blocks": len(job.blocks), "words": words},
            }
        )
    else:
        payload["attempts_left"] = job.attempts_left
    return payload


def _error(message: str, code: str, status: int, **extra):
    return jsonify({"error": code, "message": message, **extra}), status


def create_app(config: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.json.sort_keys = False

    max_file_mb = _env_int("LECTOR_MAX_FILE_MB", 30)
    app.config.update(
        MAX_CONTENT_LENGTH=(max_file_mb + 2) * 1024 * 1024,
        MAX_FILE_MB=max_file_mb,
        MAX_PAGES=_env_int("LECTOR_MAX_PAGES", 300),
        JOB_TTL=_env_int("LECTOR_JOB_TTL", 3600),
        MAX_ATTEMPTS=_env_int("LECTOR_MAX_PASSWORD_ATTEMPTS", 5),
        RENDER_DPI=_env_int("LECTOR_RENDER_DPI", 120),
        JOBS_DIR=os.environ.get("LECTOR_JOBS_DIR")
        or str(Path(tempfile.gettempdir()) / "lector-txt-jobs"),
    )
    if config:
        app.config.update(config)
    if "MAX_CONTENT_LENGTH" not in (config or {}):
        app.config["MAX_CONTENT_LENGTH"] = (app.config["MAX_FILE_MB"] + 2) * 1024 * 1024

    store = JobStore(
        base_dir=app.config["JOBS_DIR"],
        ttl_seconds=app.config["JOB_TTL"],
        max_file_mb=app.config["MAX_FILE_MB"],
        max_attempts=app.config["MAX_ATTEMPTS"],
    )
    app.extensions["jobs"] = store

    def get_job(job_id: str) -> Job | None:
        try:
            return store.get(job_id)
        except JobNotFound:
            return None

    @app.before_request
    def _purge_expired() -> None:
        store.purge_expired()

    @app.after_request
    def _security_headers(response: Response) -> Response:
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Frame-Options", "DENY")
        if response.mimetype == "text/html":
            response.headers.setdefault("Cache-Control", "no-store")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self'; "
            "script-src 'self'; connect-src 'self'; object-src 'none'; "
            "base-uri 'none'; form-action 'self'; frame-ancestors 'none'",
        )
        return response

    @app.get("/")
    def index():
        return render_template(
            "index.html",
            max_file_mb=app.config["MAX_FILE_MB"],
            max_pages=app.config["MAX_PAGES"],
            version=__version__,
        )

    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok", "app": "lector-txt", "version": __version__})

    @app.post("/api/jobs")
    def create_job():
        uploaded = request.files.get("file")
        if uploaded is None or not uploaded.filename:
            return _error("Selecciona un archivo PDF o DOCX.", "missing_file", 400)

        data = uploaded.read()
        if not data:
            return _error("El archivo está vacío.", "empty_file", 400)

        kind = sniff_kind(data, uploaded.filename)
        if kind is None:
            return _error(
                "El archivo no parece un PDF o DOCX válido.",
                "unsupported_type",
                415,
            )

        try:
            job = store.create(uploaded.filename, data, kind)
        except TooLargeError as exc:
            return _error(exc.message, "file_too_large", 413)

        try:
            analysis = analyze(
                job.path,
                kind,
                password=None,
                max_pages=app.config["MAX_PAGES"],
            )
        except LockedDocument as exc:
            job.status = "locked"
            job.encryption = exc.info
            job.page_count = exc.page_count
            response = jsonify(_public_job(job))
            response.status_code = 202
            response.headers["Cache-Control"] = "no-store"
            return response
        except DocumentError as exc:
            store.delete(job.id)
            return _error(exc.message, exc.code, exc.status)
        except Exception:
            store.delete(job.id)
            raise

        job.status = "ready"
        job.page_count = analysis.page_count
        job.pages = analysis.pages
        job.blocks = analysis.blocks
        job.warnings = analysis.warnings
        job.preview_html = analysis.preview_html
        if analysis.encryption is not None:
            job.encryption = analysis.encryption

        response = jsonify(_public_job(job))
        response.status_code = 201
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.post("/api/jobs/<job_id>/unlock")
    def unlock(job_id: str):
        job = get_job(job_id)
        if job is None:
            return _error("El documento ya no está disponible. Vuelve a subirlo.", "job_not_found", 404)
        if job.status == "ready":
            response = jsonify(_public_job(job))
            response.headers["Cache-Control"] = "no-store"
            return response
        if job.attempts_left <= 0:
            store.delete(job.id)
            return _error("Se agotaron los intentos. Sube el documento de nuevo.", "locked_out", 410)

        body = request.get_json(silent=True) or {}
        password = body.get("password")
        if not isinstance(password, str):
            return _error("Introduce la contraseña del documento.", "missing_password", 400)
        if len(password) > 1024:
            return _error("La contraseña es demasiado larga.", "invalid_password", 400)

        try:
            analysis = analyze(
                job.path,
                job.kind,
                password=password,
                max_pages=app.config["MAX_PAGES"],
            )
        except (WrongPassword, LockedDocument):
            job.attempts_left -= 1
            if job.attempts_left <= 0:
                store.delete(job.id)
                return _error(
                    "Se agotaron los intentos. Sube el documento de nuevo.",
                    "locked_out",
                    410,
                )
            response = jsonify(
                {
                    "error": "invalid_password",
                    "message": "Contraseña incorrecta.",
                    "attempts_left": job.attempts_left,
                }
            )
            response.status_code = 401
            response.headers["Cache-Control"] = "no-store"
            return response
        except DocumentError as exc:
            return _error(exc.message, exc.code, exc.status)
        except Exception as exc:
            # No registramos el mensaje de la excepción para no arriesgar que
            # aparezca la contraseña en los registros.
            app.logger.warning("Fallo al desbloquear el documento (%s)", type(exc).__name__)
            return _error("No se pudo abrir el documento con esa contraseña.", "unlock_failed", 422)

        job.password = password
        job.status = "ready"
        job.page_count = analysis.page_count
        job.pages = analysis.pages
        job.blocks = analysis.blocks
        job.warnings = analysis.warnings
        job.preview_html = analysis.preview_html
        if analysis.encryption is not None:
            job.encryption = analysis.encryption

        response = jsonify(_public_job(job))
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/jobs/<job_id>/pages/<int:number>.png")
    def page_image(job_id: str, number: int):
        job = get_job(job_id)
        if job is None:
            return _error("El documento ya no está disponible.", "job_not_found", 404)
        if job.status != "ready":
            return _error("El documento está bloqueado.", "job_locked", 423)
        if job.kind != "pdf" or not 1 <= number <= job.page_count:
            return _error("Página no encontrada.", "page_not_found", 404)

        cache_path = job.directory / f"page-{number}.png"
        if not cache_path.exists():
            try:
                png = render_pdf_page(
                    job.path,
                    job.password,
                    number,
                    dpi=app.config["RENDER_DPI"],
                )
            except WrongPassword:
                return _error("No se pudo desbloquear el documento.", "job_locked", 423)
            except DocumentError as exc:
                return _error(exc.message, exc.code, exc.status)
            temporary = job.directory / f"page-{number}-{secrets.token_hex(4)}.tmp"
            temporary.write_bytes(png)
            temporary.replace(cache_path)

        response = send_file(
            cache_path,
            mimetype="image/png",
            conditional=True,
            max_age=3600,
        )
        response.cache_control.private = True
        return response

    @app.post("/api/jobs/<job_id>/export")
    def export_job(job_id: str):
        job = get_job(job_id)
        if job is None:
            return _error("El documento ya no está disponible.", "job_not_found", 404)
        if job.status != "ready":
            return _error("Desbloquea el documento antes de exportarlo.", "job_locked", 423)

        body = request.get_json(silent=True) or {}
        included = body.get("included")
        if included is None:
            included_ids = {block.id for block in job.blocks}
        elif isinstance(included, list):
            included_ids = {str(block_id) for block_id in included}
        else:
            return _error("Lista de bloques no válida.", "invalid_request", 400)

        edits_raw = body.get("edits") or {}
        if not isinstance(edits_raw, dict):
            return _error("Ediciones no válidas.", "invalid_request", 400)
        edits = {str(key): str(value) for key, value in edits_raw.items()}

        override = body.get("text_override")
        if override is not None and not isinstance(override, str):
            return _error("Texto final no válido.", "invalid_request", 400)

        options = ExportOptions.from_dict(body.get("options"))
        text = build_text(
            job.blocks,
            included_ids,
            edits=edits,
            options=options,
            text_override=override,
        )

        filename = f"{Path(job.filename).stem or 'documento'}.txt"
        buffer = io.BytesIO(options.encode(text))
        response = send_file(
            buffer,
            mimetype="text/plain",
            as_attachment=True,
            download_name=filename,
        )
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.delete("/api/jobs/<job_id>")
    def delete_job(job_id: str):
        store.delete(job_id)
        return "", 204

    @app.errorhandler(413)
    def too_large(_exc):
        return _error(
            f"El archivo supera el límite de {app.config['MAX_FILE_MB']} MB.",
            "file_too_large",
            413,
        )

    @app.errorhandler(Exception)
    def unhandled(exc):
        if isinstance(exc, HTTPException):
            return exc
        app.logger.exception("Error no controlado")
        if request.path.startswith("/api/"):
            return _error("Error interno al procesar el documento.", "internal_error", 500)
        raise exc

    return app


app = create_app()


if __name__ == "__main__":
    host = os.environ.get("LECTOR_HOST", "127.0.0.1")
    port = _env_int("LECTOR_PORT", 8000)
    debug = os.environ.get("LECTOR_DEBUG", "").lower() in {"1", "true", "yes"}
    app.run(host=host, port=port, debug=debug, threaded=True)
