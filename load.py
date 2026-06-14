"""
etl/load.py — Classe responsável por persistir os documentos no MongoDB Atlas.

Responsabilidades:
- Conectar ao cluster MongoDB Atlas via URI segura
- Garantir carga idempotente via upsert (update_one com upsert=True)
- Chave de upsert: {variavel_codigo, uf_codigo, sexo_codigo, periodo}
- Criar índice composto na primeira execução para garantir unicidade e performance
- Retornar métricas de carga (inseridos, atualizados)
"""

import logging
from typing import Any

from pymongo import MongoClient, UpdateOne, ASCENDING
from pymongo.collection import Collection
from pymongo.errors import BulkWriteError, ConnectionFailure

from config import Config

logger = logging.getLogger(__name__)

# Campos que identificam unicamente um registro (chave do upsert)
_UPSERT_KEYS = ("variavel_codigo", "uf_codigo", "sexo_codigo", "periodo")


class Load:
    """
    Carrega documentos curados no MongoDB Atlas com garantia de idempotência.

    Modelagem dos documentos:
        Cada documento representa UMA medição trimestral de UM indicador,
        para UMA UF e UM grupo de sexo. Isso facilita:
        - consultas por qualquer combinação de filtros
        - atualização pontual sem re-inserir toda a série
        - agregações temporais nativas do MongoDB

    Índice criado automaticamente:
        {variavel_codigo, uf_codigo, sexo_codigo, periodo} — único
    """

    def __init__(self, config: Config | None = None):
        self.config = config or Config()
        self._client: MongoClient | None = None
        self._collection: Collection | None = None

    def connect(self) -> None:
        """Abre a conexão com o MongoDB Atlas."""
        try:
            self._client = MongoClient(self.config.MONGO_URI, serverSelectionTimeoutMS=10_000)
            # Força a resolução do servidor (detecta erros de auth antecipadamente)
            self._client.admin.command("ping")
            db = self._client[self.config.MONGO_DB_NAME]
            self._collection = db[self.config.MONGO_COLLECTION]
            self._ensure_index()
            logger.info(
                "Conectado ao MongoDB Atlas — db=%s col=%s",
                self.config.MONGO_DB_NAME,
                self.config.MONGO_COLLECTION,
            )
        except ConnectionFailure as exc:
            raise RuntimeError(f"Falha ao conectar ao MongoDB: {exc}") from exc

    def _ensure_index(self) -> None:
        """Cria o índice único composto caso ainda não exista."""
        index_fields = [(k, ASCENDING) for k in _UPSERT_KEYS]
        self._collection.create_index(index_fields, unique=True, background=True)
        logger.debug("Índice único garantido: %s", _UPSERT_KEYS)

    def _build_filter(self, doc: dict) -> dict:
        """Retorna o filtro de upsert com os campos-chave do documento."""
        return {k: doc[k] for k in _UPSERT_KEYS}

    def upsert_many(self, docs: list[dict]) -> dict[str, int]:
        """
        Realiza upsert em lote usando BulkWrite.

        Para cada documento:
        - Se já existir (mesma chave composta) → atualiza os campos
        - Se não existir → insere

        Returns:
            {"inserted": N, "modified": M, "total": T}
        """
        if not docs:
            logger.warning("Nenhum documento para carregar.")
            return {"inserted": 0, "modified": 0, "total": 0}

        if self._collection is None:
            raise RuntimeError("Chame connect() antes de upsert_many().")

        operations = [
            UpdateOne(
                filter=self._build_filter(doc),
                update={"$set": doc},
                upsert=True,
            )
            for doc in docs
        ]

        try:
            result = self._collection.bulk_write(operations, ordered=False)
        except BulkWriteError as exc:
            logger.error("Erro em bulk_write: %s", exc.details)
            raise

        metrics = {
            "inserted": result.upserted_count,
            "modified": result.modified_count,
            "total": len(docs),
        }
        logger.info(
            "Carga concluída — inseridos=%d atualizados=%d total=%d",
            metrics["inserted"],
            metrics["modified"],
            metrics["total"],
        )
        return metrics

    def close(self) -> None:
        """Fecha a conexão com o MongoDB."""
        if self._client:
            self._client.close()
            logger.info("Conexão MongoDB encerrada.")

    # --- Context manager para uso com `with` ---
    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.close()
