"""
mcp/server.py — Servidor MCP para consulta aos indicadores da PNAD Contínua.

Permite que clientes de IA (ex.: Claude Desktop) consultem os dados curados
diretamente no MongoDB Atlas via linguagem natural.

Ferramentas disponíveis:
  - consultar_indicador: filtra por variável, UF, sexo e/ou período
  - listar_periodos: retorna os períodos disponíveis no banco
  - ultimo_periodo: retorna a medição mais recente para um indicador

Como executar:
    python -m mcp.server          # SSE (para Claude Desktop)
    python mcp/server.py          # direto

Exemplo de pergunta:
    "Qual a taxa de desocupação das mulheres em Pernambuco no último trimestre?"
"""

import logging
from typing import Any

from mcp.server.fastmcp import FastMCP
from pymongo import MongoClient, DESCENDING

from config import Config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Instância do servidor MCP ──────────────────────────────────────────────────
mcp = FastMCP(
    name="ibge-pnad-server",
    instructions=(
        "Você tem acesso a indicadores trimestrais da PNAD Contínua (IBGE) "
        "armazenados no MongoDB Atlas. "
        "Use as ferramentas disponíveis para responder perguntas sobre "
        "taxa de desocupação, participação na força de trabalho e informalidade "
        "por UF, sexo e período."
    ),
)

config = Config()


def _get_collection():
    """Retorna a collection do MongoDB (sem manter conexão persistente)."""
    client = MongoClient(config.MONGO_URI, serverSelectionTimeoutMS=8_000)
    db = client[config.MONGO_DB_NAME]
    return client, db[config.MONGO_COLLECTION]


# ── Ferramentas MCP ────────────────────────────────────────────────────────────

@mcp.tool()
def consultar_indicador(
    variavel: str | None = None,
    uf_nome: str | None = None,
    uf_codigo: str | None = None,
    sexo: str | None = None,
    periodo: str | None = None,
    ano: int | None = None,
    trimestre: int | None = None,
    limite: int = 20,
) -> list[dict]:
    """
    Consulta indicadores da PNAD Contínua com filtros opcionais.

    Args:
        variavel: Nome parcial ou código da variável
                  (ex.: "desocupação", "4099", "informalidade")
        uf_nome:  Nome da UF (ex.: "Pernambuco", "São Paulo")
        uf_codigo: Código IBGE da UF (ex.: "26")
        sexo:     "Homens", "Mulheres" ou "Total"
        periodo:  Código exato do período (ex.: "202401")
        ano:      Ano (ex.: 2024)
        trimestre: Trimestre 1-4
        limite:   Máximo de registros retornados (padrão 20)

    Returns:
        Lista de documentos com os campos principais.
    """
    filtro: dict[str, Any] = {}

    if variavel:
        # Aceita código numérico ou nome parcial
        if variavel.isdigit():
            filtro["variavel_codigo"] = variavel
        else:
            filtro["variavel_nome"] = {"$regex": variavel, "$options": "i"}

    if uf_codigo:
        filtro["uf_codigo"] = uf_codigo
    elif uf_nome:
        filtro["uf_nome"] = {"$regex": uf_nome, "$options": "i"}

    if sexo:
        filtro["sexo_nome"] = {"$regex": sexo, "$options": "i"}

    if periodo:
        filtro["periodo"] = periodo

    if ano:
        filtro["ano"] = ano

    if trimestre:
        filtro["trimestre"] = trimestre

    client, col = _get_collection()
    try:
        cursor = (
            col.find(filtro, {"_id": 0, "coletado_em": 0, "data_referencia": 0})
            .sort("periodo", DESCENDING)
            .limit(limite)
        )
        return list(cursor)
    finally:
        client.close()


@mcp.tool()
def ultimo_periodo(
    variavel: str = "desocupação",
    uf_nome: str = "Pernambuco",
    sexo: str | None = None,
) -> list[dict]:
    """
    Retorna os dados do período mais recente disponível para um indicador e UF.

    Args:
        variavel: Nome parcial ou código da variável
        uf_nome:  Nome da UF
        sexo:     Filtro opcional de sexo ("Homens", "Mulheres", "Total")

    Returns:
        Lista de documentos do último trimestre disponível.
    """
    client, col = _get_collection()
    try:
        filtro: dict[str, Any] = {
            "variavel_nome": {"$regex": variavel, "$options": "i"},
            "uf_nome": {"$regex": uf_nome, "$options": "i"},
        }
        if sexo:
            filtro["sexo_nome"] = {"$regex": sexo, "$options": "i"}

        # Descobre o período mais recente
        ultimo = col.find_one(filtro, sort=[("periodo", DESCENDING)])
        if not ultimo:
            return []

        filtro["periodo"] = ultimo["periodo"]
        cursor = col.find(filtro, {"_id": 0, "coletado_em": 0, "data_referencia": 0})
        return list(cursor)
    finally:
        client.close()


@mcp.tool()
def listar_periodos(
    uf_codigo: str = "26",
    variavel_codigo: str = "4099",
) -> list[str]:
    """
    Lista todos os períodos disponíveis no banco para uma variável e UF.

    Args:
        uf_codigo:       Código IBGE da UF (padrão "26" = Pernambuco)
        variavel_codigo: Código da variável (padrão "4099" = desocupação)

    Returns:
        Lista de períodos ordenados crescentemente (ex.: ["201201", "201202", ...])
    """
    client, col = _get_collection()
    try:
        periodos = col.distinct(
            "periodo",
            {"uf_codigo": uf_codigo, "variavel_codigo": variavel_codigo},
        )
        return sorted(periodos)
    finally:
        client.close()


@mcp.tool()
def resumo_uf(uf_nome: str = "Pernambuco", ano: int | None = None) -> list[dict]:
    """
    Retorna um resumo dos três indicadores para uma UF, agrupado por período.

    Args:
        uf_nome: Nome da UF
        ano:     Filtro opcional de ano

    Returns:
        Lista de documentos ordenados por período decrescente.
    """
    filtro: dict[str, Any] = {
        "uf_nome": {"$regex": uf_nome, "$options": "i"},
        "sexo_nome": "Total",
    }
    if ano:
        filtro["ano"] = ano

    client, col = _get_collection()
    try:
        cursor = (
            col.find(filtro, {"_id": 0, "coletado_em": 0, "data_referencia": 0})
            .sort([("periodo", DESCENDING), ("variavel_codigo", 1)])
            .limit(60)
        )
        return list(cursor)
    finally:
        client.close()


# ── Entrypoint ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Modo SSE para integração com Claude Desktop
    mcp.run(transport="sse")
