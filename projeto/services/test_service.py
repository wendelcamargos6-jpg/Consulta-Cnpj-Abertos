import logging
import time
from pathlib import Path
from typing import Dict, List, Optional

from services.download_service import DownloadService
from services.import_service import ImportService
from services.database_service import DatabaseService
from services.export_service import ExportService
from services.search_service import SearchService
from config.settings import DOWNLOAD_PATH
from pathlib import Path
import io
import time
import os

logger = logging.getLogger(__name__)


class TestService:
    """Rota e rotina para executar o TEST MODE — baixa poucos arquivos, importa e reporta métricas."""

    @classmethod
    def select_test_files(cls, html: str) -> Dict[str, str]:
        links = DownloadService.parse_download_links(html)
        names = {k.lower(): v for k, v in links.items()}

        def pick(matchers: List[str]) -> Optional[str]:
            for name, url in names.items():
                for m in matchers:
                    if m in name:
                        return url
            return None

        empresa_url = pick(["empresas", "empresa", "estabelecimentos—empresas", "empres" ])
        estabelecimento_url = pick(["estabelecimentos", "estabelec", "estab"]) or pick(["estabelecimentos_estab"])
        simples_url = pick(["simples", "sn", "simplesnacional"]) or pick(["simples_nacional"])

        return {
            "empresa": empresa_url,
            "estabelecimento": estabelecimento_url,
            "simples": simples_url,
        }

    @classmethod
    def check_local_test_files(cls) -> Dict[str, bool]:
        """Verifica presença local dos arquivos de teste detectados na página oficial."""
        result = {"empresa": False, "estabelecimento": False, "simples": False}
        try:
            html = DownloadService.fetch_download_page()
            candidates = cls.select_test_files(html)
            for k, url in candidates.items():
                if not url:
                    result[k] = False
                    continue
                p = Path(DOWNLOAD_PATH) / Path(url).name
                result[k] = p.exists() and p.stat().st_size > 0
        except Exception:
            # If page fetch failed, try to detect any local known filenames
            raw = Path(DOWNLOAD_PATH)
            for k in result.keys():
                found = any(raw.glob(f"*{k}*"))
                result[k] = found
        return result

    @classmethod
    def run_pipeline(cls, allow_download: bool = False, progress_callback=None) -> Dict[str, object]:
        """Executa o pipeline de teste conforme fluxo solicitado.

        Se `allow_download` for False, apenas verifica existência local e retorna lista de arquivos faltantes.
        """
        report = {
            "download": {"needed": [], "performed": False, "time_s": 0},
            "import": {"performed": False, "time_s": 0, "counts": {}},
            "indexing": {"performed": False, "time_s": 0},
            "search": {"performed": False},
            "export": {"performed": False, "path": None},
        }

        DatabaseService.initialize_database()

        html = DownloadService.fetch_download_page()
        candidates = cls.select_test_files(html)

        # Check local files
        missing = []
        for key, url in candidates.items():
            if not url:
                missing.append(key)
                continue
            path = Path(DOWNLOAD_PATH) / Path(url).name
            if not path.exists() or path.stat().st_size == 0:
                missing.append(Path(url).name)

        if missing and not allow_download:
            report['download']['needed'] = missing
            report['status'] = 'missing_files'
            return report

        # Perform downloads if allowed
        download_start = time.time()
        downloaded_paths = []
        if allow_download:
            for key, url in candidates.items():
                if not url:
                    continue
                dst = Path(DOWNLOAD_PATH) / Path(url).name
                if dst.exists() and dst.stat().st_size > 0:
                    downloaded_paths.append(dst)
                    continue
                DownloadService.download_file(url, dst, progress_callback)
                downloaded_paths.append(dst)
            report['download']['performed'] = True
        report['download']['time_s'] = time.time() - download_start

        # Extract zips and import
        ImportService.ensure_directories()
        extracted_files = []
        for p in Path(DOWNLOAD_PATH).iterdir():
            if p.suffix.lower() == '.zip':
                try:
                    files = ImportService.extract_zip(p)
                    extracted_files.extend(files)
                except Exception:
                    logger.exception('Erro extraindo %s', p)

        # If no extracted files, try to import any txt/csv in raw dir
        for p in Path(DOWNLOAD_PATH).glob('*.txt'):
            extracted_files.append(p)
        for p in Path(DOWNLOAD_PATH).glob('*.csv'):
            extracted_files.append(p)

        import_start = time.time()
        imported_counts = {}
        with DatabaseService.get_connection() as conn:
            conn.execute('BEGIN TRANSACTION')
            try:
                for f in extracted_files:
                    before = conn.execute('SELECT COUNT(*) FROM company_data').fetchone()[0]
                    ImportService.import_file(conn, f)
                    after = conn.execute('SELECT COUNT(*) FROM company_data').fetchone()[0]
                    imported_counts[f.name] = after - before
                conn.execute('COMMIT')
                report['import']['performed'] = True
            except Exception:
                conn.execute('ROLLBACK')
                logger.exception('Falha na importação em pipeline')
                raise
        report['import']['time_s'] = time.time() - import_start
        report['import']['counts'] = imported_counts

        # Create indexes and measure time
        idx_start = time.time()
        with DatabaseService.get_connection() as conn:
            try:
                conn.execute('CREATE INDEX IF NOT EXISTS idx_company_data_data_constituicao ON company_data(data_constituicao);')
                conn.execute('CREATE INDEX IF NOT EXISTS idx_company_data_uf ON company_data(uf);')
                conn.execute('CREATE INDEX IF NOT EXISTS idx_company_data_municipio ON company_data(municipio);')
                conn.execute('CREATE INDEX IF NOT EXISTS idx_company_data_cnae_principal ON company_data(cnae_principal);')
                conn.execute('CREATE INDEX IF NOT EXISTS idx_company_data_natureza_juridica ON company_data(natureza_juridica);')
                conn.execute('CREATE INDEX IF NOT EXISTS idx_company_data_situacao_cadastral ON company_data(situacao_cadastral);')
                report['indexing']['performed'] = True
            except Exception:
                logger.exception('Falha criando índices no pipeline')
                raise
        report['indexing']['time_s'] = time.time() - idx_start

        # Execute a test search (use existing SearchService)
        try:
            sample = SearchService.search(start_date='2026-01-01', end_date='2026-01-02', uf=None, municipio=None)
            report['search']['performed'] = True
            report['search']['sample_rows'] = len(sample)
        except Exception:
            logger.exception('Falha na pesquisa de teste')

        # Export sample to Excel
        try:
            export_time_start = time.time()
            excel_buf = ExportService.create_excel_workbook(sample)
            exports_dir = Path(__file__).resolve().parent.parent / 'exports'
            exports_dir.mkdir(parents=True, exist_ok=True)
            out_name = f'test_pipeline_{int(time.time())}.xlsx'
            out_path = exports_dir / out_name
            with out_path.open('wb') as f:
                f.write(excel_buf.getvalue())
            report['export']['performed'] = True
            report['export']['path'] = str(out_path)
            report['export']['time_s'] = time.time() - export_time_start
        except Exception:
            logger.exception('Falha exportando Excel de teste')

        report['status'] = 'ok'
        report['total_time_s'] = time.time() - start_time

        return report

    @classmethod
    def run_test(cls, progress_callback=None) -> Dict[str, object]:
        start_time = time.time()
        DatabaseService.initialize_database()
        html = DownloadService.fetch_download_page()
        candidates = cls.select_test_files(html)

        downloaded = {}
        download_times = {}

        for key in ("empresa", "estabelecimento", "simples"):
            url = candidates.get(key)
            if not url:
                logger.warning("Arquivo de teste para %s não encontrado.", key)
                continue
            name = Path(url).name
            dst = DownloadService.RAW_DIR / name
            t0 = time.time()
            try:
                DownloadService.download_file(url, dst, progress_callback)
                download_times[key] = time.time() - t0
                downloaded[key] = str(dst)
                logger.info("Download de teste concluído: %s", dst)
            except Exception as exc:
                logger.exception("Falha no download de teste %s: %s", key, exc)

        # Extract any zips
        ImportService.ensure_directories()
        extracted = []
        for p in DownloadService.RAW_DIR.iterdir():
            if p.suffix.lower() == ".zip":
                try:
                    files = ImportService.extract_zip(p)
                    extracted.extend(files)
                except Exception:
                    logger.exception("Falha ao extrair %s", p)

        # Import into DuckDB using import_service.import_file
        imported_counts = {}
        import_start = time.time()
        with DatabaseService.get_connection() as conn:
            conn.execute("BEGIN TRANSACTION")
            try:
                for f in extracted:
                    try:
                        before = conn.execute("SELECT COUNT(*) FROM company_data").fetchone()[0]
                        ImportService.import_file(conn, f)
                        after = conn.execute("SELECT COUNT(*) FROM company_data").fetchone()[0]
                        imported_counts[f.name] = after - before
                    except Exception:
                        logger.exception("Erro ao importar arquivo %s", f)
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        import_time = time.time() - import_start

        # Create indexes (idempotent)
        with DatabaseService.get_connection() as conn:
            try:
                conn.execute("CREATE INDEX IF NOT EXISTS idx_company_data_data_constituicao ON company_data(data_constituicao);")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_company_data_uf ON company_data(uf);")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_company_data_municipio ON company_data(municipio);")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_company_data_cnae_principal ON company_data(cnae_principal);")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_company_data_natureza_juridica ON company_data(natureza_juridica);")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_company_data_situacao_cadastral ON company_data(situacao_cadastral);")
            except Exception:
                logger.exception("Falha ao criar índices de teste")

        # Gather stats
        with DatabaseService.get_connection() as conn:
            try:
                total_companies = conn.execute("SELECT COUNT(*) FROM company_data").fetchone()[0]
            except Exception:
                total_companies = 0
            try:
                active_companies = conn.execute("SELECT COUNT(*) FROM company_data WHERE situacao_cadastral LIKE 'Ativa' OR situacao_cadastral LIKE 'ATIVA'").fetchone()[0]
            except Exception:
                active_companies = 0

        total_time = time.time() - start_time

        return {
            "downloaded": downloaded,
            "download_times": download_times,
            "imported_counts": imported_counts,
            "import_time_s": import_time,
            "total_time_s": total_time,
            "total_companies": total_companies,
            "active_companies": active_companies,
        }
