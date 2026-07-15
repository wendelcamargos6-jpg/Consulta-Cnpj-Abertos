from datetime import date
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator
from pydantic import ConfigDict


def to_camel_case(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(word.capitalize() for word in parts[1:])


class SearchResult(BaseModel):
    cnpj: str
    nome: str
    uf: str
    municipio: str
    situacao: str
    data_situacao: str


class SearchRequest(BaseModel):
    start_date: Optional[str] = Field(None, alias="startDate")
    end_date: Optional[str] = Field(None, alias="endDate")
    uf: Optional[str] = None
    municipio: Optional[str] = None
    bairro: Optional[str] = None
    cep: Optional[str] = None
    cnae: Optional[str] = None
    natureza: Optional[str] = None
    situacao: Optional[str] = None
    porte: Optional[str] = None
    capital_min: Optional[float] = Field(None, alias="capitalMin")
    capital_max: Optional[float] = Field(None, alias="capitalMax")
    empresa_matriz: bool = Field(False, alias="empresaMatriz")
    empresa_filial: bool = Field(False, alias="empresaFilial")
    only_phone: bool = Field(False, alias="onlyPhone")
    only_email: bool = Field(False, alias="onlyEmail")
    only_website: bool = Field(False, alias="onlyWebsite")
    limit: Optional[int] = Field(100, alias="limit")
    page: Optional[int] = Field(1, alias="page")
    page_size: Optional[int] = Field(10, alias="pageSize")

    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel_case, extra="ignore")

    @field_validator("start_date", "end_date", mode="before")
    @classmethod
    def strip_date(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return value.strip()

    @field_validator(
        "start_date",
        "end_date",
        mode="before",
    )
    @classmethod
    def validate_date_format(cls, value: Optional[str]) -> Optional[str]:
        if value is None or value == "":
            return value
        try:
            date.fromisoformat(value)
        except ValueError:
            raise ValueError("Data deve estar no formato YYYY-MM-DD")
        return value

    @field_validator(
        "uf",
        "municipio",
        "bairro",
        "cep",
        "cnae",
        "natureza",
        "situacao",
        "porte",
        mode="before",
    )
    @classmethod
    def normalize_strings(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        return normalized if normalized != "" else None

    @field_validator("capital_min", "capital_max", mode="before")
    @classmethod
    def normalize_numbers(cls, value: Optional[Any]) -> Optional[float]:
        if value in (None, ""):
            return None
        return float(value)

    @field_validator("limit", mode="before")
    @classmethod
    def normalize_limit(cls, value: Optional[Any]) -> Optional[int]:
        if value in (None, ""):
            return None
        return int(value)


class SearchResponse(BaseModel):
    success: bool
    message: str
    filters: Dict[str, Any]
    results: List[Any] = []
    # Pagination
    total_count: Optional[int] = 0
    total_pages: Optional[int] = 0
    current_page: Optional[int] = 1
    has_next: Optional[bool] = False
    has_previous: Optional[bool] = False
