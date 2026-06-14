"""
tests/test_transform.py — Testes unitários para a classe Transform.

Execução:
    pytest tests/ -v
"""

import pytest
from datetime import datetime

from transform import Transform, _parse_valor, _parse_periodo
from config import Config


# ── _parse_valor ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("10.5", 10.5),
    ("10,5", 10.5),
    ("...", None),
    ("-", None),
    ("", None),
    (" ", None),
    ("X", None),
    (None, None),
    ("0.0", 0.0),
])
def test_parse_valor(raw, expected):
    assert _parse_valor(raw) == expected


# ── _parse_periodo ─────────────────────────────────────────────────────────────

def test_parse_periodo_valido():
    result = _parse_periodo("202103")
    assert result["ano"] == 2021
    assert result["trimestre"] == 3
    assert result["periodo_label"] == "3T2021"
    assert isinstance(result["data_referencia"], datetime)
    assert result["data_referencia"].month == 7  # 3T → julho


def test_parse_periodo_invalido():
    result = _parse_periodo("XXXXX")
    assert result["ano"] is None
    assert result["trimestre"] is None


# ── Transform.normalize ────────────────────────────────────────────────────────

# JSON mínimo simulando resposta da API do IBGE
MOCK_API_RESPONSE = [
    {
        "id": "4099",
        "variavel": "Taxa de desocupação",
        "unidade": "%",
        "resultados": [
            {
                "classificacoes": [
                    {
                        "id": "2",
                        "categoria": {"2": "Mulheres"}
                    }
                ],
                "series": [
                    {
                        "localidade": {"id": "26", "nome": "Pernambuco"},
                        "serie": {
                            "202401": "15.2",
                            "202402": "...",
                        }
                    }
                ]
            }
        ]
    }
]


def test_normalize_basic():
    transformer = Transform(Config())
    docs = transformer.normalize(MOCK_API_RESPONSE, "4099")

    assert len(docs) == 2  # dois períodos

    doc_valido = next(d for d in docs if d["periodo"] == "202401")
    assert doc_valido["valor"] == 15.2
    assert doc_valido["uf_codigo"] == "26"
    assert doc_valido["uf_nome"] == "Pernambuco"
    assert doc_valido["variavel_codigo"] == "4099"
    assert doc_valido["sexo_codigo"] == "2"
    assert doc_valido["ano"] == 2024
    assert doc_valido["trimestre"] == 1

    doc_ausente = next(d for d in docs if d["periodo"] == "202402")
    assert doc_ausente["valor"] is None


def test_normalize_upsert_keys_present():
    """Garante que os campos da chave de upsert estão sempre presentes."""
    transformer = Transform(Config())
    docs = transformer.normalize(MOCK_API_RESPONSE, "4099")
    for doc in docs:
        for key in ("variavel_codigo", "uf_codigo", "sexo_codigo", "periodo"):
            assert key in doc, f"Campo '{key}' ausente no documento"


def test_normalize_empty():
    transformer = Transform(Config())
    docs = transformer.normalize([], "4099")
    assert docs == []
