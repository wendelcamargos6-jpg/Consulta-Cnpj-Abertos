import io
import sys
from pathlib import Path
# garantir import do package ao executar pytest a partir de subpaths
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fastapi.testclient import TestClient
from backend.main import app
from services.import_service import ImportService
from pathlib import Path
import openpyxl


client = TestClient(app)


def setup_module(module):
    # Ensure tables and import small fixtures (do not import full base)
    ImportService.create_tables()
    base = Path('data/cache')
    for fname in ['cnaes.csv', 'naturezas.csv', 'municipios.csv', 'empresas.csv', 'estabelecimentos.csv', 'simples.csv']:
        p = base / fname
        if p.exists():
            ImportService.import_file_streaming(p)


def test_health():
    r = client.get('/health')
    assert r.status_code == 200
    data = r.json()
    assert data.get('status') == 'online'


def test_security_headers_are_present_on_healthcheck():
    r = client.get('/health')
    assert r.status_code == 200
    assert r.headers.get('x-content-type-options') == 'nosniff'
    assert r.headers.get('x-frame-options') == 'DENY'


def test_suspicious_paths_are_blocked():
    r = client.get('/static/../README.md')
    assert r.status_code in {400, 404}


def test_search_returns_fixtures():
    body = {'start_date': '2026-07-01', 'end_date': '2026-07-02', 'uf': 'SP', 'municipio': 'Sao Paulo', 'limit': 10}
    r = client.post('/search', json=body)
    assert r.status_code == 200
    j = r.json()
    assert j['success'] is True
    assert len(j['results']) >= 1


def test_search_blocks_more_than_10_days():
    body = {'start_date': '2026-01-01', 'end_date': '2026-02-15', 'limit': 10}
    r = client.post('/search', json=body)
    assert r.status_code == 422


def test_search_respects_uf_filter():
    body = {'start_date': '2026-06-28', 'end_date': '2026-07-01', 'uf': 'RJ', 'limit': 10, 'page':1, 'pageSize':10}
    r = client.post('/search', json=body)
    assert r.status_code == 200
    j = r.json()
    assert any(item['uf'] == 'RJ' for item in j['results'])


def test_search_respects_limit():
    body = {'start_date': '2026-06-28', 'end_date': '2026-07-01', 'limit': 1, 'page':1, 'pageSize':1}
    r = client.post('/search', json=body)
    assert r.status_code == 200
    j = r.json()
    assert len(j['results']) <= 1


def test_export_generates_excel():
    body = {'start_date': '2026-07-01', 'end_date': '2026-07-02', 'uf': 'SP', 'municipio': 'Sao Paulo', 'limit': 10, 'page':1, 'pageSize':10}
    r = client.post('/export', json=body)
    assert r.status_code == 200
    assert r.headers.get('content-type') == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    bio = io.BytesIO(r.content)
    wb = openpyxl.load_workbook(bio)
    assert 'Resultados' in wb.sheetnames


def test_export_excel_get_endpoint_returns_file():
    response = client.get('/export/excel?start_date=2026-07-01&end_date=2026-07-02&uf=SP&municipio=Sao%20Paulo')
    assert response.status_code == 200
    assert 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' in response.headers.get('content-type', '')


def test_export_csv_get_endpoint_returns_file():
    response = client.get('/export/csv?start_date=2026-07-01&end_date=2026-07-02&uf=SP&municipio=Sao%20Paulo')
    assert response.status_code == 200
    assert 'text/csv' in response.headers.get('content-type', '')


def test_search_returns_validation_error_for_invalid_date_format():
    response = client.post('/search', json={'start_date': '01/01/2024', 'end_date': '2024-01-10', 'limit': 10})
    assert response.status_code == 422
    assert 'Data deve estar no formato YYYY-MM-DD' in response.json().get('message', '')


def test_export_returns_friendly_error_when_no_data():
    body = {'start_date': '2000-01-01', 'end_date': '2000-01-02', 'limit': 10}
    r = client.post('/export', json=body)
    assert r.status_code == 404
    j = r.json()
    assert 'Nenhum resultado' in j.get('detail', '')


def test_search_returns_clear_message_when_no_results():
    body = {'start_date': '2000-01-01', 'end_date': '2000-01-02', 'limit': 10}
    r = client.post('/search', json=body)
    assert r.status_code == 200
    j = r.json()
    assert j['success'] is True
    assert 'Nenhum resultado' in j['message']
