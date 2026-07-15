import hashlib
import json
import logging
import re
import time
from pathlib import Path
from config.settings import DOWNLOAD_PATH
from typing import Callable, Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)


class DownloadService:
	BASE_URL = "https://dadosabertos.rfb.gov.br/CNPJ/"
	RAW_DIR = Path(DOWNLOAD_PATH)
	METADATA_PATH = RAW_DIR / "download_metadata.json"
	LINK_PATTERN = re.compile(r'href=["\'](?P<href>[^"\']+\.(?:zip|txt|csv|sha256|sha256sum))["\']', re.IGNORECASE)

	@classmethod
	def ensure_raw_directory(cls) -> None:
		cls.RAW_DIR.mkdir(parents=True, exist_ok=True)

	@classmethod
	def fetch_download_page(cls) -> str:
		request = Request(cls.BASE_URL, headers={"User-Agent": "CNPJ Hunter Pro/5.0"})
		try:
			with urlopen(request, timeout=30) as response:
				content = response.read().decode("utf-8", errors="ignore")
				logger.info("Página de download da base oficial acessada com sucesso.")
				return content
		except (HTTPError, URLError) as exc:
			logger.exception("Falha ao acessar a página de download oficial")
			raise RuntimeError("Não foi possível acessar a base oficial do CNPJ.") from exc

	@classmethod
	def parse_download_links(cls, html: str) -> Dict[str, str]:
		links: Dict[str, str] = {}
		for match in cls.LINK_PATTERN.finditer(html):
			href = match.group("href")
			url = href if href.startswith("http") else urljoin(cls.BASE_URL, href)
			links[Path(urlparse(url).path).name] = url
		return links

	@classmethod
	def list_available_files(cls) -> Dict[str, str]:
		"""Retorna um dicionário {nome: url} dos arquivos disponíveis na página oficial."""
		html = cls.fetch_download_page()
		links = cls.parse_download_links(html)
		return links

	@classmethod
	def download_files(cls, urls: Dict[str, str], progress_callback: Optional[Callable[[str, int, int], None]] = None) -> Dict[str, Path]:
		"""Baixa múltiplos arquivos. `urls` é dict name->url. progress_callback(nome, downloaded, total)."""
		cls.ensure_raw_directory()
		results: Dict[str, Path] = {}
		for name, url in urls.items():
			destination = cls.RAW_DIR / name
			def cb(downloaded, total, _name=name):
				if progress_callback:
					try:
						progress_callback(_name, downloaded, total)
					except Exception:
						logger.exception('Erro no progress callback')

			cls.download_file(url, destination, lambda d, t: cb(d, t))
			results[name] = destination
		return results

	@classmethod
	def find_latest_zip_url(cls) -> Tuple[str, str]:
		html = cls.fetch_download_page()
		links = cls.parse_download_links(html)
		zip_links = {name: url for name, url in links.items() if name.lower().endswith(".zip")}
		if not zip_links:
			logger.error("Nenhum arquivo ZIP encontrado na página oficial de download.")
			raise RuntimeError("Nenhum arquivo ZIP da base oficial foi encontrado.")
		latest_name = sorted(zip_links.keys(), reverse=True)[0]
		logger.info("Arquivo oficial selecionado: %s", latest_name)
		# Return name and url
		return latest_name, zip_links[latest_name]

	@classmethod
	def _get_remote_headers(cls, url: str) -> Dict[str, str]:
		request = Request(url, headers={"User-Agent": "CNPJ Hunter Pro/5.0"}, method="HEAD")
		try:
			with urlopen(request, timeout=20) as response:
				return dict(response.getheaders())
		except Exception:
			return {}

	@classmethod
	def _try_fetch_checksum_url(cls, html_links: Dict[str, str], zip_name: str, zip_url: str) -> Optional[Tuple[str, str]]:
		# Try to find checksum in parsed links
		for suffix in (".sha256", ".sha256.txt", ".sha256sum"):
			candidate = zip_name + suffix
			if candidate in html_links:
				return candidate, html_links[candidate]

		# Try same path + .sha256
		try_path = Path(zip_url).with_suffix(Path(zip_url).suffix + ".sha256")
		return (try_path.name, str(try_path)) if try_path.exists() else None

	@classmethod
	def _fetch_remote_checksum(cls, checksum_url: str) -> Optional[str]:
		try:
			request = Request(checksum_url, headers={"User-Agent": "CNPJ Hunter Pro/5.0"})
			with urlopen(request, timeout=20) as response:
				txt = response.read().decode("utf-8", errors="ignore").strip()
				# common formats: 'SHA256 (file.zip) = <hash>' or '<hash>  filename'
				m = re.search(r"([a-fA-F0-9]{64})", txt)
				if m:
					return m.group(1).lower()
		except Exception:
			logger.debug("Não foi possível obter checksum remoto em %s", checksum_url)
		return None

	@classmethod
	def _compute_sha256(cls, path: Path) -> str:
		h = hashlib.sha256()
		with path.open("rb") as f:
			for chunk in iter(lambda: f.read(8192), b""):
				h.update(chunk)
		return h.hexdigest()

	@classmethod
	def download_file(
		cls,
		url: str,
		destination: Path,
		progress_callback: Optional[Callable[[int, int], None]] = None,
		resume: bool = True,
	) -> Path:
		cls.ensure_raw_directory()
		destination.parent.mkdir(parents=True, exist_ok=True)

		temp_path = destination.with_suffix(destination.suffix + ".part")

		# Determine starting point for resume
		existing = temp_path.stat().st_size if temp_path.exists() else 0
		headers = {"User-Agent": "CNPJ Hunter Pro/5.0"}
		if resume and existing > 0:
			headers["Range"] = f"bytes={existing}-"
			logger.info("Retomando download de %s a partir de %d bytes", destination.name, existing)

		request = Request(url, headers=headers)

		try:
			with urlopen(request, timeout=60) as response:
				status = getattr(response, "status", None)
				# Try to get total size
				content_length = response.getheader("Content-Length") or response.getheader("content-length") or "0"
				try:
					total_size = int(content_length) + (existing if headers.get("Range") else 0)
				except Exception:
					total_size = 0

				mode = "ab" if existing > 0 and status == 206 else "wb"
				downloaded = existing if mode == "ab" else 0

				with temp_path.open(mode) as out_file:
					chunk_size = 64 * 1024
					start_time = time.time()
					while True:
						chunk = response.read(chunk_size)
						if not chunk:
							break
						out_file.write(chunk)
						downloaded += len(chunk)
						if progress_callback:
							progress_callback(downloaded, total_size)
					elapsed = time.time() - start_time

				temp_path.replace(destination)
				logger.info("Download completado: %s (%d bytes) em %.2fs", destination.name, downloaded, elapsed)
				return destination
		except HTTPError as exc:
			# If server doesn't support range and we tried resume, try full download
			if exc.code == 416 and resume and temp_path.exists():
				logger.warning("Range não suportado; reiniciando download completo para %s", destination.name)
				temp_path.unlink(missing_ok=True)
				return cls.download_file(url, destination, progress_callback, resume=False)
			logger.exception("Falha ao baixar %s", url)
			raise RuntimeError(f"Falha ao baixar o arquivo: {url}") from exc
		except URLError as exc:
			logger.exception("Falha de rede ao baixar %s", url)
			raise RuntimeError(f"Falha de rede ao baixar o arquivo: {url}") from exc

	@classmethod
	def validate_file(cls, path: Path, expected_size: Optional[int] = None, expected_sha256: Optional[str] = None) -> bool:
		if not path.exists() or path.stat().st_size == 0:
			logger.error("Arquivo inválido ou vazio: %s", path)
			raise RuntimeError(f"Arquivo inválido ou vazio: {path.name}")

		if expected_size is not None and path.stat().st_size != expected_size:
			logger.warning(
				"Tamanho esperado %s difere do tamanho real %s para %s",
				expected_size,
				path.stat().st_size,
				path.name,
			)

		if expected_sha256 is not None:
			actual = cls._compute_sha256(path)
			if actual.lower() != expected_sha256.lower():
				logger.error("Checksum SHA256 inválido para %s: esperado %s, obtido %s", path.name, expected_sha256, actual)
				raise RuntimeError("Validação SHA256 falhou.")
			logger.info("Checksum SHA256 validado para %s", path.name)

		logger.info("Arquivo validado: %s", path.name)
		return True

	@classmethod
	def save_metadata(cls, metadata: Dict[str, str]) -> None:
		cls.ensure_raw_directory()
		existing = {}
		if cls.METADATA_PATH.exists():
			try:
				existing = json.loads(cls.METADATA_PATH.read_text(encoding="utf-8"))
			except Exception:
				existing = {}
		existing.update(metadata)
		existing["last_checked"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
		cls.METADATA_PATH.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")
		logger.info("Metadados de download salvos em %s", cls.METADATA_PATH)

	@classmethod
	def download_official_base(
		cls,
		file_name: Optional[str] = None,
		progress_callback: Optional[Callable[[int, int], None]] = None,
	) -> Path:
		cls.ensure_raw_directory()

		if file_name:
			download_url = urljoin(cls.BASE_URL, file_name)
			zip_name = Path(download_url).name
		else:
			zip_name, download_url = cls.find_latest_zip_url()

		destination = cls.RAW_DIR / zip_name

		# Parse page links to find checksum if available
		checksum_value = None
		try:
			html = cls.fetch_download_page()
			links = cls.parse_download_links(html)
			checksum_info = cls._try_fetch_checksum_url(links, zip_name, download_url)
			if checksum_info:
				chk_name, chk_url = checksum_info
				logger.info("Tentando obter checksum em %s", chk_url)
				checksum_value = cls._fetch_remote_checksum(chk_url)
		except Exception:
			checksum_value = None

		# If file exists and checksum matches (when available), skip download
		if destination.exists() and destination.stat().st_size > 0:
			logger.info("Arquivo já existe em data/raw: %s", destination.name)
			if checksum_value:
				try:
					cls.validate_file(destination, expected_sha256=checksum_value)
					cls.save_metadata({"url": download_url, "file_name": destination.name, "sha256": checksum_value, "status": "skipped"})
					return destination
				except Exception:
					logger.info("Checksum divergente; rebaixando arquivo: %s", destination.name)
			else:
				cls.save_metadata({"url": download_url, "file_name": destination.name, "status": "exists"})
				return destination

		# Download with resume
		downloaded_path = cls.download_file(download_url, destination, progress_callback, resume=True)

		# Validate
		try:
			# Try to get expected size from headers
			headers = cls._get_remote_headers(download_url)
			expected_size = int(headers.get("Content-Length") or headers.get("content-length") or 0) or None
		except Exception:
			expected_size = None

		cls.validate_file(downloaded_path, expected_size=expected_size, expected_sha256=checksum_value)
		cls.save_metadata({"url": download_url, "file_name": downloaded_path.name, "sha256": checksum_value, "size": downloaded_path.stat().st_size, "status": "downloaded"})
		return downloaded_path

	@classmethod
	def get_latest_version(cls) -> Optional[str]:
		try:
			name, _ = cls.find_latest_zip_url()
			return name
		except Exception:
			return None
