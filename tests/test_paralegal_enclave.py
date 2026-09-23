from pathlib import Path

from fastapi.testclient import TestClient

from freyja.paralegal_app import app


def _blank_pdf(path: Path) -> None:
    path.write_bytes(
        b"%PDF-1.4\n"
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 72 72] >> endobj\n"
        b"trailer << /Root 1 0 R >>\n%%EOF\n"
    )


def test_paralegal_page_is_available() -> None:
    client = TestClient(app)
    response = client.get("/paralegal")
    assert response.status_code == 200
    assert "Paralegal Enclave" in response.text
    assert "/paralegal/api/extractions.csv" in response.text


def test_matter_folder_scan_and_csv_export(tmp_path, monkeypatch) -> None:
    import freyja.paralegal_enclave as enclave

    monkeypatch.setattr(enclave, "DATA_DIR", tmp_path)
    monkeypatch.setattr(enclave, "MATTERS_DIR", tmp_path / "matters")
    monkeypatch.setattr(enclave, "DB_FILE", tmp_path / "financial_extractions.sqlite3")
    monkeypatch.setattr(enclave, "EXPORT_FILE", tmp_path / "financial_extractions.csv")
    monkeypatch.setattr(enclave, "_extract_pdf_pages", lambda path: (1, [(1, "Please pay invoice total $1,234.56 by check.")]))

    client = TestClient(app)
    created = client.post("/paralegal/api/matters", json={"name": "Beth Case 101"})
    assert created.status_code == 200
    slug = created.json()["slug"]

    pdf_path = tmp_path / "sample.pdf"
    _blank_pdf(pdf_path)
    uploaded = client.put(
        f"/paralegal/api/matters/{slug}/documents/sample.pdf",
        content=pdf_path.read_bytes(),
    )
    assert uploaded.status_code == 200
    assert uploaded.json()["scan"]["processed"] == 1

    extractions = client.get("/paralegal/api/extractions").json()["extractions"]
    assert extractions[0]["matter_slug"] == slug
    assert extractions[0]["amount_text"] == "$1,234.56"
    assert extractions[0]["page_text_start"] > 0
    assert extractions[0]["page_text_end"] > extractions[0]["page_text_start"]
    assert "$1,234.56" in extractions[0]["text_anchor"]
    assert extractions[0]["source_link"].startswith(f"/paralegal/api/matters/{slug}/documents/")
    assert "extraction_id=" in extractions[0]["source_link"]

    csv_response = client.get("/paralegal/api/extractions.csv")
    assert csv_response.status_code == 200
    assert "amount_text" in csv_response.text
    assert "text_anchor" in csv_response.text
    assert "$1,234.56" in csv_response.text
    assert (tmp_path / "financial_extractions.csv").exists()
    assert "$1,234.56" in (tmp_path / "financial_extractions.csv").read_text(encoding="utf-8")

    status = client.get("/paralegal/api/status").json()
    assert status["document_count"] == 1
    assert status["extraction_count"] == 1
    assert status["matter_root"] == str(tmp_path / "matters")
    assert status["excel_readable_file"] == str(tmp_path / "financial_extractions.csv")
    assert "ocr_available" in status


def test_paralegal_page_loads_when_connector_auth_is_enabled(monkeypatch) -> None:
    import freyja.main as main

    monkeypatch.setattr(main.settings, "freyja_connector_token", "secret")
    client = TestClient(app)
    response = client.get("/paralegal")
    assert response.status_code == 200


def test_paralegal_auto_scan_starts_with_app_lifespan(tmp_path, monkeypatch) -> None:
    import freyja.paralegal_enclave as enclave

    monkeypatch.setattr(enclave, "DATA_DIR", tmp_path)
    monkeypatch.setattr(enclave, "MATTERS_DIR", tmp_path / "matters")
    monkeypatch.setattr(enclave, "DB_FILE", tmp_path / "financial_extractions.sqlite3")
    monkeypatch.setattr(enclave, "EXPORT_FILE", tmp_path / "financial_extractions.csv")

    with TestClient(app) as client:
        status = client.get("/paralegal/api/status").json()
        assert status["auto_scan_running"] is True
        assert status["scan_interval_seconds"] == 10


def test_status_scan_detects_pdf_dropped_directly_into_matter_folder(tmp_path, monkeypatch) -> None:
    import freyja.paralegal_enclave as enclave

    monkeypatch.setattr(enclave, "DATA_DIR", tmp_path)
    monkeypatch.setattr(enclave, "MATTERS_DIR", tmp_path / "matters")
    monkeypatch.setattr(enclave, "DB_FILE", tmp_path / "financial_extractions.sqlite3")
    monkeypatch.setattr(enclave, "EXPORT_FILE", tmp_path / "financial_extractions.csv")
    monkeypatch.setattr(enclave, "_extract_pdf_pages", lambda path: (1, [(1, "Settlement payment was $9,876.54 on receipt.")]))

    client = TestClient(app)
    created = client.post("/paralegal/api/matters", json={"name": "Dropped File Matter"}).json()
    dropped_pdf = tmp_path / "matters" / created["slug"] / "bank-statement.pdf"
    second_pdf = tmp_path / "matters" / created["slug"] / "invoice.pdf"
    _blank_pdf(dropped_pdf)
    _blank_pdf(second_pdf)

    status = client.get("/paralegal/api/status").json()
    assert status["scan"]["processed"] == 2

    extractions = client.get("/paralegal/api/extractions").json()["extractions"]
    assert {row["filename"] for row in extractions} == {"bank-statement.pdf", "invoice.pdf"}
    assert {row["amount_text"] for row in extractions} == {"$9,876.54"}
