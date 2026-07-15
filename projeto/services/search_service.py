from typing import List, Optional, Tuple
from services.database_service import DatabaseService
from config.settings import MAX_RESULTS

from models.search import SearchResult


class SearchService:
    @staticmethod
    def search(start_date: str, end_date: str, uf: Optional[str] = None, municipio: Optional[str] = None, cnae: Optional[str] = None, limit: Optional[int] = 100, page: int = 1, page_size: int = 10) -> Tuple[List[SearchResult], int]:
        """Consulta real no DuckDB aplicando filtros básicos e retornando lista de SearchResult.

        Filtros suportados: intervalo de data (`empresas.data_situacao`), `uf`, `municipio`, `cnae` (cnae_principal), `limit`.
        """
        sql = [
            "SELECT e.cnpj AS cnpj, e.razao_social AS nome, e.uf AS uf, e.municipio AS municipio, e.situacao_cadastral AS situacao, e.data_situacao AS data_situacao",
            "FROM empresas e",
            "LEFT JOIN estabelecimentos est ON e.cnpj = est.cnpj",
            "LEFT JOIN cnaes c ON e.cnae_principal::TEXT = c.codigo",
            "LEFT JOIN naturezas n ON e.natureza_juridica::TEXT = n.codigo",
        ]

        where = []
        params: List = []

        if start_date:
            where.append("e.data_situacao >= ?")
            params.append(start_date)
        if end_date:
            where.append("e.data_situacao <= ?")
            params.append(end_date)
        if uf:
            where.append("e.uf = ?")
            params.append(uf)
        if municipio:
            where.append("e.municipio = ?")
            params.append(municipio)
        if cnae:
            where.append("e.cnae_principal = ?")
            params.append(cnae)

        if where:
            sql.append("WHERE " + " AND ".join(where))

        sql.append("GROUP BY e.cnpj, e.razao_social, e.uf, e.municipio, e.situacao_cadastral, e.data_situacao")
        # Count total distinct empresas matching filters
        count_sql = [
            "SELECT COUNT(DISTINCT e.cnpj) FROM empresas e",
        ]
        # Build where for count similarly
        count_where = []
        count_params = []
        if start_date:
            count_where.append("e.data_situacao >= ?")
            count_params.append(start_date)
        if end_date:
            count_where.append("e.data_situacao <= ?")
            count_params.append(end_date)
        if uf:
            count_where.append("e.uf = ?")
            count_params.append(uf)
        if municipio:
            count_where.append("e.municipio = ?")
            count_params.append(municipio)
        if cnae:
            count_where.append("e.cnae_principal = ?")
            count_params.append(cnae)
        if count_where:
            count_sql.append("WHERE " + " AND ".join(count_where))

        count_query = "\n".join(count_sql)

        # Apply ordering and pagination
        sql.append("ORDER BY e.data_situacao DESC")
        # Cap limit to MAX_RESULTS
        if limit is None:
            limit = page_size
        limit = min(int(limit), MAX_RESULTS)

        offset = max(0, (int(page) - 1) * int(page_size))
        sql.append(f"LIMIT {int(page_size)} OFFSET {int(offset)}")

        query = "\n".join(sql)

        results: List[SearchResult] = []
        total_count = 0
        with DatabaseService.get_connection() as conn:
            try:
                # total distinct cnpj
                total_count = conn.execute(count_query, count_params).fetchone()[0]
            except Exception:
                total_count = 0
            try:
                rows = conn.execute(query, params).fetchall()
            except Exception:
                rows = []

        # enforce overall cap
        total_count_capped = min(total_count, MAX_RESULTS)

        for r in rows:
            results.append(
                SearchResult(
                    cnpj=r[0],
                    nome=r[1] or "",
                    uf=r[2] or "",
                    municipio=r[3] or "",
                    situacao=r[4] or "",
                    data_situacao=str(r[5]) if r[5] is not None else "",
                )
            )

        return results, int(total_count_capped)
