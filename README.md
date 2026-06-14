# 📊 IBGE PNAD Contínua — Pipeline ETL de Indicadores do Mercado de Trabalho

> Projeto de Engenharia de Dados — CESAR School · GP2 · 2025

**Integrantes:** Felipe Saraiva · Anna Clara · Lucas Barros · Renan Carvalho · Fabiana Lima

---

## 🎯 Objetivo

Construir uma solução completa de Engenharia de Dados para coletar, tratar, armazenar, orquestrar e consultar indicadores da **PNAD Contínua (IBGE)**, com foco em Pernambuco.

Os três indicadores coletados são:

| Código | Indicador |
|--------|-----------|
| 4099 | Taxa de desocupação |
| 4098 | Taxa de participação na força de trabalho |
| 4101 | Taxa de informalidade |

Os dados são desagregados por **variável**, **UF**, **sexo** (Homens / Mulheres / Total) e **período** (trimestre).

---

## 🗂️ Estrutura do Repositório

```
ibge-etl/
├── src/
│   ├── config.py          # Configurações centralizadas (lê .env)
│   ├── etl/
│   │   ├── extract.py     # Classe Extract — consome a API do IBGE
│   │   ├── transform.py   # Classe Transform — normaliza o JSON
│   │   └── load.py        # Classe Load — persiste no MongoDB Atlas
│   └── mcp/
│       └── server.py      # Servidor MCP para consultas por IA
├── tests/
│   ├── conftest.py
│   └── test_transform.py  # Testes unitários da transformação
├── pipeline.py            # Flow Prefect (orquestração)
├── requirements.txt
├── .env.example
└── README.md
```

---

## 🏗️ Arquitetura da Solução

```
┌─────────────────────────────────────────────────────────────────┐
│                        Prefect Flow                             │
│                                                                 │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────────┐   │
│  │   Extract    │──▶│  Transform   │──▶│      Load        │   │
│  │              │   │              │   │                  │   │
│  │ API IBGE     │   │ Flatten JSON │   │ Upsert MongoDB   │   │
│  │ + retry      │   │ parse tipos  │   │ Atlas (idempot.) │   │
│  │ + validação  │   │ metadados    │   │                  │   │
│  └──────────────┘   └──────────────┘   └──────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                                │
                    ┌───────────▼───────────┐
                    │    MongoDB Atlas       │
                    │  db: ibge_pnad        │
                    │  col: indicadores     │
                    └───────────┬───────────┘
                                │
                    ┌───────────▼───────────┐
                    │    Servidor MCP        │
                    │  (FastMCP / SSE)      │
                    │  consultas por IA     │
                    └───────────────────────┘
```

---

## ⚙️ Instalação

### 1. Pré-requisitos

- Python 3.11+
- Conta no [MongoDB Atlas](https://www.mongodb.com/atlas) com cluster ativo
- (Opcional) Conta no [Prefect Cloud](https://app.prefect.cloud) para visualização

### 2. Clone o repositório

```bash
git clone https://github.com/felipesaraivab/desocupacao-IBGE.git
cd desocupacao-IBGE
```

### 3. Crie e ative o ambiente virtual

```bash
python3 -m venv .venv
source .venv/bin/activate   # macOS / Linux
# .venv\Scripts\activate    # Windows
```

### 4. Instale as dependências

```bash
pip3 install -r requirements.txt
```

### 5. Configure as variáveis de ambiente

```bash
cp .env.example .env
# Edite o .env com suas credenciais reais
```

> ⚠️ **Nunca** faça commit do arquivo `.env`. Ele já está no `.gitignore`.

---

## 🚀 Como Executar o ETL

### Execução direta (sem Prefect)

```bash
python3 pipeline.py
```

### Execução via Prefect CLI

```bash
# Autentique-se no Prefect (opcional para UI)
prefect cloud login

# Execute o flow
prefect run pipeline.py
```

---

## ⏰ Como Executar o Prefect com Agendamento

```bash
# Agenda execução diária às 6h
prefect deployment build pipeline.py:ibge_etl_flow \
    --name producao \
    --cron "0 6 * * *"

prefect deployment apply ibge_etl_flow-deployment.yaml
prefect agent start --work-queue default
```

---

## 🤖 Como Executar o Servidor MCP

```bash
python3 -m src.mcp.server
# ou
python3 src/mcp/server.py
```

O servidor inicia em modo SSE (Server-Sent Events), compatível com **Claude Desktop**.

### Configurar no Claude Desktop

Adicione em `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "ibge-pnad": {
      "command": "python3",
      "args": ["-m", "src.mcp.server"],
      "cwd": "/caminho/para/desocupacao-IBGE"
    }
  }
}
```

### Exemplos de perguntas ao MCP

- *"Qual a taxa de desocupação das mulheres em Pernambuco no último trimestre?"*
- *"Compare a informalidade entre homens e mulheres em 2023."*
- *"Quais os períodos disponíveis para a taxa de participação?"*

---

## 🗄️ Modelagem no MongoDB Atlas

### Por que um documento por medição?

Cada documento representa **uma medição trimestral** de **um indicador**, para **uma UF** e **um grupo de sexo**. Essa modelagem garante:

- Consultas eficientes por qualquer combinação de filtros
- Atualizações pontuais sem re-processar a série inteira
- Suporte nativo a agregações temporais do MongoDB

### Estrutura do documento

```json
{
  "variavel_codigo": "4099",
  "variavel_nome": "Taxa de desocupação",
  "uf_codigo": "26",
  "uf_nome": "Pernambuco",
  "sexo_codigo": "2",
  "sexo_nome": "Mulheres",
  "periodo": "202401",
  "periodo_label": "1T2024",
  "ano": 2024,
  "trimestre": 1,
  "data_referencia": "2024-01-01T00:00:00Z",
  "valor": 16.8,
  "unidade": "%",
  "coletado_em": "2025-05-10T14:32:00Z"
}
```

### Índice único (chave de upsert)

```
{ variavel_codigo: 1, uf_codigo: 1, sexo_codigo: 1, periodo: 1 }  ← unique
```

Esse índice garante que re-execuções do pipeline **nunca dupliquem dados**.

---

## 🧪 Executar os Testes

```bash
pytest tests/ -v
```

---

## 🔌 Fonte dos Dados

- **API:** IBGE — PNAD Contínua (Tabela 4093)
- **URL base:** `https://servicodados.ibge.gov.br/api/v3/agregados/4093`
- **Períodos:** 2012T1 a 2025T1 (201201–202504)
- **Variáveis:** 4099, 4098, 4101
- **Desagregação:** N3 (UF) × Classificação 2 (Sexo)
- **Documentação:** https://servicodados.ibge.gov.br/api/docs/agregados

---

## 🧩 Descrição das Classes

| Classe | Arquivo | Responsabilidade |
|--------|---------|-----------------|
| `Extract` | `src/etl/extract.py` | Consome a API do IBGE com retry automático (tenacity) |
| `Transform` | `src/etl/transform.py` | Normaliza JSON, converte tipos, trata ausências |
| `Load` | `src/etl/load.py` | Persiste no MongoDB via upsert em lote (BulkWrite) |
| FastMCP server | `src/mcp/server.py` | Expõe ferramentas de consulta para clientes de IA |

---

## 📈 Evidências de Execução

As evidências (screenshots do Prefect UI, outputs do terminal, consultas MCP) estão na pasta `evidencias/`.

---

## 🚧 Dificuldades e Melhorias Futuras

**Dificuldades encontradas:**
- Estrutura hierárquica do JSON da API exigiu flatten cuidadoso para separar sexo × período
- Cluster MongoDB pausado durante desenvolvimento — resolvido reativando no Atlas Console
- Permissões de push no repositório forked — resolvido via pull request

**Melhorias futuras (pontuação extra):**
- Implementar arquitetura medalhão (Bronze → Silver → Gold) com coleções separadas
- Ampliar para todas as UFs do Brasil (não só Pernambuco)
- Dashboard interativo com Streamlit consumindo o MongoDB
- Alertas automáticos via Prefect quando a taxa de desocupação superar threshold
