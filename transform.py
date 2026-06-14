"""
etl/transform.py — Classe responsável por normalizar os dados brutos da API IBGE.

Responsabilidades:
- Desaninhar (flatten) o JSON hierárquico retornado pela API
- Converter taxas para float, tratando "...", "-", "" como None
- Enriquecer com metadados (nome legível da variável, sexo, UF)
- Converter o código de período "YYYYTT" em campos separados
- Retornar lista de documentos prontos para carga no MongoDB
"""

import logging
import re
from datetime import datetime
from typing import Any

from config import Config

logger = logging.getLogger(__name__)

# Valores que indicam dado ausente na API do IBGE
_MISSING_VALUES = frozenset({"...", "-", "", " ", "X"})


def _parse_valor(raw: str | None) -> float | None:
    """Converte string de taxa para float; retorna None se ausente."""
    if raw is None or str(raw).strip() in _MISSING_VALUES:
        return None
    try:
        return float(str(raw).replace(",", ".").strip())
    except ValueError:
        logger.debug("Valor não convertível para float: %r", raw)
        return None


def _parse_periodo(periodo: str) -> dict:
    """
    Converte o código de período da API (ex.: '202101') em campos estruturados.

    O IBGE usa o formato YYYYTT onde TT é o trimestre (01–04) para a PNAD Contínua.

    Returns:
        {"periodo": "202101", "ano": 2021, "trimestre": 1,
         "periodo_label": "1T2021", "data_referencia": datetime}
    """
    match = re.fullmatch(r"(\d{4})(\d{2})", periodo)
    if not match:
        return {"periodo": periodo, "ano": None, "trimestre": None,
                "periodo_label": periodo, "data_referencia": None}

    ano = int(match.group(1))
    trimestre = int(match.group(2))

    # Mês do início de cada trimestre (1T→jan, 2T→abr, 3T→jul, 4T→out)
    mes_inicio = {1: 1, 2: 4, 3: 7, 4: 10}.get(trimestre, 1)

    return {
        "periodo": periodo,
        "ano": ano,
        "trimestre": trimestre,
        "periodo_label": f"{trimestre}T{ano}",
        "data_referencia": datetime(ano, mes_inicio, 1),
    }


class Transform:
    """
    Transforma os dados brutos retornados pela API do IBGE em documentos
    normalizados e prontos para persistência.

    Estrutura do JSON da API (simplificada):
    [
      {
        "id": "4099",
        "variavel": "Taxa de desocupação",
        "unidade": "%",
        "resultados": [
          {
            "classificacoes": [
              {
                "id": "2",       # classificação Sexo
                "categoria": {
                  "1": "Homens",
                  "2": "Mulheres",
                  "93": "Total"
                }
              }
            ],
            "series": [
              {
                "localidade": {"id": "26", "nome": "Pernambuco"},
                "serie": {
                  "202101": "10.5",
                  "202102": "11.2",
                  ...
                }
              }
            ]
          }
        ]
      }
    ]
    """

    def __init__(self, config: Config | None = None):
        self.config = config or Config()

    def _extract_sexo_map(self, classificacoes: list[dict]) -> dict[str, str]:
        """Extrai mapa {cod_categoria: nome_sexo} das classificações."""
        for clf in classificacoes:
            if str(clf.get("id")) == "2":  # classificação Sexo
                return clf.get("categoria", {})
        return {}

    def normalize(
        self,
        raw_data: list[dict],
        variavel_codigo: str,
    ) -> list[dict]:
        """
        Normaliza a resposta bruta de UMA variável.

        Args:
            raw_data: JSON retornado pela API para a variável.
            variavel_codigo: Código da variável (ex.: "4099").

        Returns:
            Lista de documentos normalizados.
        """
        docs: list[dict] = []
        variavel_nome = self.config.VARIAVEL_NOMES.get(
            variavel_codigo, f"Variável {variavel_codigo}"
        )

        for item in raw_data:
            unidade = item.get("unidade", "%")

            for resultado in item.get("resultados", []):
                sexo_map = self._extract_sexo_map(
                    resultado.get("classificacoes", [])
                )

                for serie_item in resultado.get("series", []):
                    localidade = serie_item.get("localidade", {})
                    uf_codigo = str(localidade.get("id", ""))
                    uf_nome = localidade.get("nome", "")
                    serie = serie_item.get("serie", {})

                    # A API retorna um bloco "resultado" por categoria de sexo.
                    # O sexo_map deste bloco pode ter 1 ou mais entradas;
                    # criamos um documento para cada período × sexo presente.
                    sexo_items = list(sexo_map.items()) if sexo_map else [("-1", "Não informado")]

                    for periodo_raw, valor_raw in serie.items():
                        periodo_info = _parse_periodo(periodo_raw)
                        valor = _parse_valor(valor_raw)

                        for cod_sexo, nome_sexo in sexo_items:
                            doc = {
                                # --- Chave composta para upsert idempotente ---
                                "variavel_codigo": variavel_codigo,
                                "uf_codigo": uf_codigo,
                                "sexo_codigo": str(cod_sexo),
                                "periodo": periodo_raw,
                                # --- Dados curados ---
                                "variavel_nome": variavel_nome,
                                "uf_nome": uf_nome,
                                "sexo_nome": self.config.SEXO_NOMES.get(
                                    str(cod_sexo), nome_sexo
                                ),
                                "valor": valor,
                                "unidade": unidade,
                                # --- Metadados temporais ---
                                **periodo_info,
                                # --- Metadados de carga ---
                                "coletado_em": datetime.now(tz=None),
                            }
                            docs.append(doc)

        logger.info(
            "Variável %s: %d documentos normalizados.", variavel_codigo, len(docs)
        )
        return docs

    def normalize_all(
        self, raw_by_variavel: dict[str, list[dict]]
    ) -> list[dict]:
        """Normaliza todas as variáveis e retorna lista unificada de documentos."""
        all_docs: list[dict] = []
        for cod, raw in raw_by_variavel.items():
            all_docs.extend(self.normalize(raw, cod))
        return all_docs
