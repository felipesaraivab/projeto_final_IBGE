"""
config.py — Configurações centralizadas via variáveis de ambiente.
Nunca coloque credenciais hardcoded aqui.
"""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # --- MongoDB ---
    DB_USER: str = os.getenv("DB_USER", "")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "")
    MONGO_URI: str = os.getenv(
        "MONGO_URI",
        f"mongodb+srv://{DB_USER}:{DB_PASSWORD}@cluster0.qok8d3w.mongodb.net/?appName=Cluster0",
    )
    MONGO_DB_NAME: str = os.getenv("MONGO_DB_NAME", "ibge_pnad")
    MONGO_COLLECTION: str = os.getenv("MONGO_COLLECTION", "indicadores")

    # --- API IBGE ---
    IBGE_BASE_URL: str = os.getenv(
        "IBGE_BASE_URL", "https://servicodados.ibge.gov.br/api/v3"
    )
    IBGE_TABELA: str = os.getenv("IBGE_TABELA", "4093")
    IBGE_PERIODOS: str = os.getenv("IBGE_PERIODOS", "201201-202504")

    # Variáveis: 4099=desocupação, 4098=participação, 4101=informalidade
    IBGE_VARIAVEIS: list[str] = os.getenv(
        "IBGE_VARIAVEIS", "4099,4098,4101"
    ).split(",")

    # --- Servidor MCP ---
    MCP_HOST: str = os.getenv("MCP_HOST", "0.0.0.0")
    MCP_PORT: int = int(os.getenv("MCP_PORT", "8000"))

    # --- Mapeamentos legíveis ---
    VARIAVEL_NOMES: dict[str, str] = {
        "4099": "Taxa de desocupação",
        "4098": "Taxa de participação na força de trabalho",
        "4101": "Taxa de informalidade",
    }

    # Classificações de sexo retornadas pela API
    SEXO_NOMES: dict[str, str] = {
        "1": "Homens",
        "2": "Mulheres",
        "0": "Total",
    }
