"""
etl/extract.py — Classe responsável por consumir a API do IBGE.
Busca dados de TODAS as UFs do Brasil.
"""

import logging
from typing import Any

import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)

from config import Config

logger = logging.getLogger(__name__)


class IBGEExtractError(Exception):
    """Exceção customizada para erros de extração."""


class Extract:
    """
    Extrai dados da API PNAD Contínua do IBGE (Tabela 4093).
    Coleta todas as UFs do Brasil em uma única chamada por variável.
    """

    def __init__(self, config: Config | None = None):
        self.config = config or Config()
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})

    def _build_url(self, variavel: str) -> str:
        base = self.config.IBGE_BASE_URL
        tabela = self.config.IBGE_TABELA
        periodos = self.config.IBGE_PERIODOS
        return f"{base}/agregados/{tabela}/periodos/{periodos}/variaveis/{variavel}"

    @retry(
        retry=retry_if_exception_type((requests.Timeout, requests.ConnectionError)),
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    def _get(self, url: str, params: dict) -> Any:
        try:
            response = self.session.get(url, params=params, timeout=60)
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise IBGEExtractError(
                f"Erro HTTP {exc.response.status_code} em {url}"
            ) from exc
        try:
            return response.json()
        except ValueError as exc:
            raise IBGEExtractError(
                f"Resposta não é JSON válido: {response.text[:200]}"
            ) from exc

    def fetch_variable(self, variavel: str) -> list[dict]:
        """Busca dados de uma variável para TODAS as UFs do Brasil."""
        url = self._build_url(variavel)
        params = {"localidades": "N3"}
        logger.info("Extraindo variável %s — todas as UFs", variavel)
        data = self._get(url, params)
        if not isinstance(data, list) or len(data) == 0:
            raise IBGEExtractError(
                f"Resposta inesperada para variável {variavel}: {str(data)[:200]}"
            )
        return data

    def fetch_all(self) -> dict[str, list[dict]]:
        """Busca todas as variáveis para todas as UFs."""
        results: dict[str, list[dict]] = {}
        for variavel in self.config.IBGE_VARIAVEIS:
            variavel = variavel.strip()
            try:
                results[variavel] = self.fetch_variable(variavel)
            except IBGEExtractError as exc:
                logger.error("Falha ao extrair variável %s: %s", variavel, exc)
        return results