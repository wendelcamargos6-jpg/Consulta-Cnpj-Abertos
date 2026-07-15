import csv
import logging
import zipfile
import json
import tempfile
import os
import time
from pathlib import Path
from config.settings import DOWNLOAD_PATH
from typing import List, Dict, Optional

from services.database_service import DatabaseService

logger = logging.getLogger(__name__)


class ImportService:
	RAW_DIR = Path(DOWNLOAD_PATH)
	EXTRACTED_DIR = RAW_DIR / "extracted"
	METADATA_PATH = RAW_DIR / "import_metadata.json"
	BATCH_SIZE = 100000

	@classmethod
	def ensure_directories(cls) -> None:
		cls.RAW_DIR.mkdir(parents=True, exist_ok=True)
		cls.EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)

	@classmethod
	def load_metadata(cls) -> Dict:
		if cls.METADATA_PATH.exists():
			try:
				return json.loads(cls.METADATA_PATH.read_text(encoding="utf-8"))
			except Exception:
				logger.exception("Metadata inválida, recriando.")
		return {"files": {}, "last_updated": None}

	@classmethod
	def save_metadata(cls, meta: Dict) -> None:
		meta["last_updated"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
		cls.METADATA_PATH.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

	@classmethod
	def list_raw_files(cls) -> List[Path]:
		cls.ensure_directories()
		files = [p for p in sorted(cls.RAW_DIR.iterdir()) if p.suffix.lower() in {".zip", ".txt", ".csv"}]
		files.extend([p for p in sorted(cls.EXTRACTED_DIR.iterdir()) if p.suffix.lower() in {".txt", ".csv"}])
		return files

	@classmethod
	def extract_zip(cls, archive_path: Path) -> List[Path]:
		logger.info("Extraindo arquivo ZIP: %s", archive_path.name)
		if not zipfile.is_zipfile(archive_path):
			raise RuntimeError(f"Arquivo ZIP inválido: {archive_path.name}")

		extracted_files = []
		with zipfile.ZipFile(archive_path, "r") as archive:
			archive.extractall(cls.EXTRACTED_DIR)
			for member in archive.namelist():
				extracted_path = cls.EXTRACTED_DIR / member
				if extracted_path.suffix.lower() in {".txt", ".csv"}:
					extracted_files.append(extracted_path)
		logger.info("Extração concluída: %s", archive_path.name)
		return extracted_files

	@classmethod
	def detect_delimiter(cls, sample_path: Path) -> str:
		try:
			with sample_path.open("r", encoding="latin-1", errors="ignore") as sample_file:
				sample = "".join([next(sample_file) for _ in range(5)])
			dialect = csv.Sniffer().sniff(sample, delimiters=";,|")
			logger.info("Delimitador detectado para %s: %s", sample_path.name, dialect.delimiter)
			return dialect.delimiter
		except Exception:
			logger.warning("Não foi possível detectar delimitador para %s; usando ponto e vírgula.", sample_path.name)
			return ";"

	@classmethod
	def detect_file_type(cls, path: Path) -> str:
		name = path.name.lower()
		if "empresa" in name or "empresas" in name:
			return "empresas"
		if "estabele" in name or "estabelecimentos" in name:
			return "estabelecimentos"
		if "simples" in name or "sn" in name:
			return "simples"
		if "cnae" in name:
			return "cnaes"
		if "natureza" in name:
			return "naturezas"
		if "municipio" in name or "municipios" in name or "municipio" in name:
			return "municipios"

		# Fallback: inspect header for known columns
		try:
			with path.open("r", encoding="latin-1", errors="ignore") as f:
				header = next(f)
				h = header.lower()
				if "razao" in h or ("nome" in h and "cnpj" in h):
					return "empresas"
				if "logradouro" in h or ("cep" in h and "cnpj" in h):
					return "estabelecimentos"
				if "cnae" in h and ("cod" in h or "codigo" in h):
					return "cnaes"
		except Exception:
			pass
		return "unknown"

	@classmethod
	def create_tables(cls) -> None:
		"""Cria todas as tabelas necessárias no DuckDB (idempotente)."""
		with DatabaseService.get_connection() as conn:
			# Empresas
			conn.execute(
				"""
				CREATE TABLE IF NOT EXISTS empresas (
					cnpj TEXT,
					razao_social TEXT,
					nome_fantasia TEXT,
					natureza_juridica TEXT,
					capital_social DOUBLE,
					data_constituicao DATE,
					situacao_cadastral TEXT,
					data_situacao DATE,
					uf TEXT,
					municipio TEXT,
					bairro TEXT,
					endereco TEXT,
					numero TEXT,
					complemento TEXT,
					cep TEXT,
					telefone TEXT,
					email TEXT,
					website TEXT,
					cnae_principal TEXT,
					cnae_descricao TEXT,
					porte TEXT,
					matriz BOOLEAN,
					filial BOOLEAN,
					ultima_atualizacao DATE
				)
				"""
			)

			# Estabelecimentos
			conn.execute(
				"""
				CREATE TABLE IF NOT EXISTS estabelecimentos (
					cnpj TEXT,
					cnpj_basico TEXT,
					razao_social TEXT,
					nome_fantasia TEXT,
					endereco TEXT,
					numero TEXT,
					complemento TEXT,
					bairro TEXT,
					municipio TEXT,
					uf TEXT,
					cep TEXT,
					telefone TEXT,
					email TEXT,
					atividade_principal TEXT,
					natureza_juridica TEXT,
					situacao_cadastral TEXT,
					data_situacao DATE
				)
				"""
			)

			# Simples Nacional
			conn.execute(
				"""
				CREATE TABLE IF NOT EXISTS simples (
					cnpj TEXT,
					adesao_simples TEXT,
					data_adesao DATE,
					data_renuncia DATE,
					opcao_simples TEXT
				)
				"""
			)

			# CNAEs
			conn.execute(
				"""
				CREATE TABLE IF NOT EXISTS cnaes (
					codigo TEXT,
					descricao TEXT
				)
				"""
			)

			# Naturezas
			conn.execute(
				"""
				CREATE TABLE IF NOT EXISTS naturezas (
					codigo TEXT,
					descricao TEXT
				)
				"""
			)

			# Municipios
			conn.execute(
				"""
				CREATE TABLE IF NOT EXISTS municipios (
					codigo_ibge TEXT,
					nome TEXT,
					uf TEXT
				)
				"""
			)

			logger.info("Tabelas criadas/validadas no DuckDB.")

	@classmethod
	def import_file_streaming(cls, file_path: Path, batch_size: int = None) -> Dict:
		"""Importa um arquivo em streaming, processando por lotes e atualizando metadata para retomada.

		Retorna um relatório com contagem, tempo e erros (se houver).
		"""
		batch_size = batch_size or cls.BATCH_SIZE
		meta = cls.load_metadata()
		file_meta = meta.setdefault("files", {}).get(file_path.name, {})
		if file_meta.get("processed"):
			logger.info("Arquivo %s já processado; pulando.", file_path.name)
			return {"skipped": True}

		file_type = cls.detect_file_type(file_path)
		logger.info("Tipo detectado para %s: %s", file_path.name, file_type)

		# Map file_type to table
		table_map = {
			"empresas": "empresas",
			"estabelecimentos": "estabelecimentos",
			"simples": "simples",
			"cnaes": "cnaes",
			"naturezas": "naturezas",
			"municipios": "municipios",
		}
		table = table_map.get(file_type)
		if not table:
			logger.warning("Tipo de arquivo desconhecido para importacao: %s", file_path.name)
			return {"error": "unknown_type"}

		start_time = time.time()
		rows_imported = 0
		errors = []

		# Resume position
		last_row = file_meta.get("last_row", 0)

		delimiter = cls.detect_delimiter(file_path)

		with file_path.open("r", encoding="latin-1", errors="ignore") as fh:
			reader = csv.reader(fh, delimiter=delimiter)
			# Read header to determine columns
			try:
				header = [c.strip() for c in next(reader)]
			except StopIteration:
				logger.warning("Arquivo vazio: %s", file_path.name)
				return {"file": file_path.name, "rows": 0, "time_s": 0.0, "errors": []}

			columns = header

			# Skip data rows up to last_row
			for _ in range(last_row):
				try:
					next(reader)
				except StopIteration:
					break

			batch = []
			with DatabaseService.get_connection() as conn:
				for row_idx, row in enumerate(reader, start=last_row + 1):
					batch.append(row)
					if len(batch) >= batch_size:
						# write batch to temp CSV and COPY
						try:
							with tempfile.NamedTemporaryFile(mode='w', delete=False, encoding='utf-8', newline='') as tf:
								w = csv.writer(tf, delimiter=';')
								for r in batch:
									w.writerow(r)
								tmpname = tf.name
							conn.execute('BEGIN TRANSACTION')
							cols = ','.join(columns)
							copy_q = f"COPY {table}({cols}) FROM '{tmpname}' (DELIMITER ';', HEADER FALSE)"
							conn.execute(copy_q)
							conn.execute('COMMIT')
							rows_imported += len(batch)
							file_meta['last_row'] = row_idx
							file_meta['rows_imported'] = file_meta.get('rows_imported', 0) + len(batch)
							meta['files'][file_path.name] = file_meta
							cls.save_metadata(meta)
						except Exception as exc:
							conn.execute('ROLLBACK')
							logger.exception('Erro importando batch do arquivo %s', file_path.name)
							errors.append(str(exc))
						finally:
							try:
								os.unlink(tmpname)
							except Exception:
								pass
						batch = []

				# remaining batch
				if batch:
					try:
						with tempfile.NamedTemporaryFile(mode='w', delete=False, encoding='utf-8', newline='') as tf:
							w = csv.writer(tf, delimiter=';')
							for r in batch:
								w.writerow(r)
							tmpname = tf.name
						conn.execute('BEGIN TRANSACTION')
						cols = ','.join(columns)
						copy_q = f"COPY {table}({cols}) FROM '{tmpname}' (DELIMITER ';', HEADER FALSE)"
						conn.execute(copy_q)
						conn.execute('COMMIT')
						rows_imported += len(batch)
						file_meta['last_row'] = row_idx
						file_meta['rows_imported'] = file_meta.get('rows_imported', 0) + len(batch)
						meta['files'][file_path.name] = file_meta
						cls.save_metadata(meta)
					except Exception as exc:
						conn.execute('ROLLBACK')
						logger.exception('Erro importando ultimo batch do arquivo %s', file_path.name)
						errors.append(str(exc))
					finally:
						try:
							os.unlink(tmpname)
						except Exception:
							pass

		elapsed = time.time() - start_time
		file_meta['processed'] = len(errors) == 0
		file_meta['time_s'] = elapsed
		file_meta['errors'] = errors
		meta['files'][file_path.name] = file_meta
		cls.save_metadata(meta)

		logger.info('Importacao concluida para %s: %d linhas, tempo %.2fs, erros %d', file_path.name, rows_imported, elapsed, len(errors))
		return {"file": file_path.name, "rows": rows_imported, "time_s": elapsed, "errors": errors}

