"""
etl/extract.py — Classe responsável por consumir a API do IBGE.

Responsabilidades:
- Montar a URL correta para cada variável / localidade / período
- Tratar erros HTTP, timeouts e respostas inválidas
- Implementar retry automático com back-off exponencial (tenacity)
- Retornar o JSON bruto sem nenhuma transformação
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

    A URL segue o padrão:
        /api/v3/agregados/{tabela}/periodos/{periodos}/variaveis/{variavel}
        ?localidades=N3[{uf_codigo}]&classificacao={classificacao}

    Referência: https://servicodados.ibge.gov.br/api/docs/agregados
    """

    # Classificação 2 = Sexo (código da classificação na Tabela 4093)
    _CLASSIFICACAO_SEXO = "2[1,2,93]"  # 1=Homens, 2=Mulheres, 93=Total

    def __init__(self, config: Config | None = None):
        self.config = config or Config()
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})

    def _build_url(self, variavel: str) -> str:
        """Monta a URL da API para uma variável específica."""
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
        """Executa o GET com retry automático em caso de falha de rede."""
        try:
            response = self.session.get(url, params=params, timeout=30)
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

    def fetch_variable(
        self,
        variavel: str,
        uf_codigo: str = "26",  # 26 = Pernambuco (padrão do projeto)
    ) -> list[dict]:
        """
        Busca os dados de uma variável para uma UF específica, desagregados por sexo.

        Args:
            variavel: Código da variável IBGE (ex.: "4099")
            uf_codigo: Código IBGE da UF (ex.: "26" para PE)

        Returns:
            Lista de objetos JSON retornados pela API.
        """
        url = self._build_url(variavel)
        params = {
            "localidades": f"N3[{uf_codigo}]",
        }
        logger.info(
            "Extraindo variável %s — UF %s | url=%s params=%s",
            variavel,
            uf_codigo,
            url,
            params,
        )
        data = self._get(url, params)
        if not isinstance(data, list) or len(data) == 0:
            raise IBGEExtractError(
                f"Resposta inesperada para variável {variavel}: {str(data)[:200]}"
            )
        return data

    def fetch_all(self, uf_codigo: str = "26") -> dict[str, list[dict]]:
        """
        Busca todas as variáveis configuradas para uma UF.

        Returns:
            Dicionário {cod_variavel: dados_brutos}
        """
        results: dict[str, list[dict]] = {}
        for variavel in self.config.IBGE_VARIAVEIS:
            variavel = variavel.strip()
            try:
                results[variavel] = self.fetch_variable(variavel, uf_codigo)
            except IBGEExtractError as exc:
                logger.error("Falha ao extrair variável %s: %s", variavel, exc)
                # Continua com as outras variáveis
        return results
