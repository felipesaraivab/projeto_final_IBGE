import logging
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

from config import Config
from extract import Extract
from transform import Transform
from load import Load

logger = logging.getLogger(__name__)


def task_extrair(uf_codigo="26"):
    logger.info("▶ TASK: extrair_dados — UF %s", uf_codigo)
    extractor = Extract(Config())
    raw = extractor.fetch_all(uf_codigo)
    logger.info("✔ Extração concluída — %d variáveis", len(raw))
    return raw


def task_transformar(raw):
    logger.info("▶ TASK: transformar_dados")
    docs = Transform(Config()).normalize_all(raw)
    logger.info("✔ Transformação concluída — %d documentos", len(docs))
    return docs


def task_carregar(docs):
    logger.info("▶ TASK: carregar_dados — %d documentos", len(docs))
    with Load(Config()) as loader:
        metrics = loader.upsert_many(docs)
    logger.info("✔ Carga concluída — inseridos=%d atualizados=%d",
                metrics["inserted"], metrics["modified"])
    return metrics


def ibge_etl_flow(uf_codigo="26"):
    print("\n🚀 Iniciando pipeline IBGE ETL...\n")
    raw = task_extrair(uf_codigo)
    docs = task_transformar(raw)
    metrics = task_carregar(docs)
    print(f"\n✅ Pipeline concluído! inseridos={metrics['inserted']} | "
          f"atualizados={metrics['modified']} | total={metrics['total']}\n")
    return metrics


if __name__ == "__main__":
    ibge_etl_flow("26")