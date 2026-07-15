from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)


def test_homepage_simplified_search_flow():
    response = client.get('/')
    assert response.status_code == 200

    html = response.text
    assert 'Data Inicial' in html
    assert 'Data Final' in html
    assert 'Pesquisar' in html
    assert 'Exportar Excel' in html
    assert 'Base oficial' in html
    assert 'menos de 5 segundos' in html.lower()
    assert 'Aguardando pesquisa' in html
    assert 'resultados em menos de 5 segundos' in html.lower()
    assert 'Configurações' not in html
    assert 'Logs' not in html
