import csv
import io
from typing import List

from openpyxl import Workbook

from models.search import SearchResult


class ExportService:
    @staticmethod
    def create_excel_workbook(rows: List[SearchResult]) -> io.BytesIO:
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Resultados"

        headers = ["cnpj", "nome", "uf", "municipio", "situacao", "data_situacao"]
        sheet.append(headers)

        for row in rows:
            sheet.append([
                row.cnpj,
                row.nome,
                row.uf,
                row.municipio,
                row.situacao,
                row.data_situacao,
            ])

        buffer = io.BytesIO()
        workbook.save(buffer)
        buffer.seek(0)
        return buffer

    @staticmethod
    def create_csv_bytes(rows: List[SearchResult]) -> io.BytesIO:
        output = io.StringIO(newline="")
        writer = csv.writer(output, delimiter=",", quoting=csv.QUOTE_MINIMAL)

        headers = ["cnpj", "nome", "uf", "municipio", "situacao", "data_situacao"]
        writer.writerow(headers)

        for row in rows:
            writer.writerow([
                row.cnpj,
                row.nome,
                row.uf,
                row.municipio,
                row.situacao,
                row.data_situacao,
            ])

        buffer = io.BytesIO()
        buffer.write(output.getvalue().encode("utf-8"))
        buffer.seek(0)
        return buffer
