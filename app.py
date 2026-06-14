"""
app.py — Interface web com agente de IA (OpenAI GPT-4o) que consulta
os dados da PNAD Contínua diretamente no MongoDB Atlas.

Qualquer pessoa acessa pelo navegador — sem instalar nada.

Execução local:
    python3 app.py

Deploy (Railway/Render):
    Configura as variáveis de ambiente e aponta para este arquivo.
"""

import json
import logging
import os
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from pymongo import MongoClient, DESCENDING
from openai import OpenAI

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Clientes ───────────────────────────────────────────────────────────────────

openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

MONGO_URI = os.getenv(
    "MONGO_URI",
    f"mongodb+srv://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@cluster0.qok8d3w.mongodb.net/?appName=Cluster0",
)
MONGO_DB = os.getenv("MONGO_DB_NAME", "ibge_pnad")
MONGO_COL = os.getenv("MONGO_COLLECTION", "indicadores")


def get_col():
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=8000)
    return client, client[MONGO_DB][MONGO_COL]


# ── Funções que o agente pode chamar (tools) ───────────────────────────────────

def consultar_indicador(
    variavel: str = None,
    uf_nome: str = None,
    sexo: str = None,
    ano: int = None,
    trimestre: int = None,
    limite: int = 20,
) -> list[dict]:
    """Consulta indicadores com filtros opcionais."""
    filtro: dict[str, Any] = {}
    if variavel:
        if variavel.isdigit():
            filtro["variavel_codigo"] = variavel
        else:
            filtro["variavel_nome"] = {"$regex": variavel, "$options": "i"}
    if uf_nome:
        filtro["uf_nome"] = {"$regex": uf_nome, "$options": "i"}
    if sexo:
        filtro["sexo_nome"] = {"$regex": sexo, "$options": "i"}
    if ano:
        filtro["ano"] = ano
    if trimestre:
        filtro["trimestre"] = trimestre

    client, col = get_col()
    try:
        docs = list(
            col.find(filtro, {"_id": 0, "coletado_em": 0, "data_referencia": 0})
            .sort("periodo", DESCENDING)
            .limit(limite)
        )
        return docs
    finally:
        client.close()


def ultimo_periodo(variavel: str = "desocupação", uf_nome: str = "Pernambuco", sexo: str = None) -> list[dict]:
    """Retorna dados do período mais recente com valor disponível."""
    filtro: dict[str, Any] = {
        "variavel_nome": {"$regex": variavel, "$options": "i"},
        "uf_nome": {"$regex": uf_nome, "$options": "i"},
        "valor": {"$ne": None},
    }
    if sexo:
        filtro["sexo_nome"] = {"$regex": sexo, "$options": "i"}

    client, col = get_col()
    try:
        ultimo = col.find_one(filtro, sort=[("periodo", DESCENDING)])
        if not ultimo:
            return []
        filtro["periodo"] = ultimo["periodo"]
        del filtro["valor"]
        return list(col.find(filtro, {"_id": 0, "coletado_em": 0, "data_referencia": 0}))
    finally:
        client.close()


def listar_periodos(uf_codigo: str = "26", variavel_codigo: str = "4099") -> list[str]:
    """Lista todos os períodos disponíveis."""
    client, col = get_col()
    try:
        return sorted(col.distinct("periodo", {"uf_codigo": uf_codigo, "variavel_codigo": variavel_codigo}))
    finally:
        client.close()


def resumo_uf(uf_nome: str = "Pernambuco", ano: int = None) -> list[dict]:
    """Resumo dos três indicadores para uma UF."""
    filtro: dict[str, Any] = {
        "uf_nome": {"$regex": uf_nome, "$options": "i"},
        "sexo_nome": "Total",
    }
    if ano:
        filtro["ano"] = ano
    client, col = get_col()
    try:
        return list(
            col.find(filtro, {"_id": 0, "coletado_em": 0, "data_referencia": 0})
            .sort([("periodo", DESCENDING), ("variavel_codigo", 1)])
            .limit(60)
        )
    finally:
        client.close()


# ── Definição das tools para a OpenAI ─────────────────────────────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "consultar_indicador",
            "description": "Consulta indicadores da PNAD Contínua com filtros opcionais por variável, UF, sexo, ano e trimestre.",
            "parameters": {
                "type": "object",
                "properties": {
                    "variavel": {"type": "string", "description": "Nome parcial ou código da variável (ex: 'desocupação', '4099', 'informalidade')"},
                    "uf_nome": {"type": "string", "description": "Nome da UF (ex: 'Pernambuco', 'São Paulo')"},
                    "sexo": {"type": "string", "description": "'Homens', 'Mulheres' ou 'Total'"},
                    "ano": {"type": "integer", "description": "Ano (ex: 2024)"},
                    "trimestre": {"type": "integer", "description": "Trimestre 1 a 4"},
                    "limite": {"type": "integer", "description": "Máximo de registros (padrão 20)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ultimo_periodo",
            "description": "Retorna os dados do trimestre mais recente disponível para um indicador e UF.",
            "parameters": {
                "type": "object",
                "properties": {
                    "variavel": {"type": "string", "description": "Nome parcial da variável"},
                    "uf_nome": {"type": "string", "description": "Nome da UF"},
                    "sexo": {"type": "string", "description": "'Homens', 'Mulheres' ou 'Total'"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "listar_periodos",
            "description": "Lista todos os períodos disponíveis no banco para uma variável e UF.",
            "parameters": {
                "type": "object",
                "properties": {
                    "uf_codigo": {"type": "string", "description": "Código IBGE da UF (ex: '26' para Pernambuco)"},
                    "variavel_codigo": {"type": "string", "description": "Código da variável (ex: '4099')"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "resumo_uf",
            "description": "Retorna resumo dos três indicadores (desocupação, participação, informalidade) para uma UF.",
            "parameters": {
                "type": "object",
                "properties": {
                    "uf_nome": {"type": "string", "description": "Nome da UF"},
                    "ano": {"type": "integer", "description": "Filtro opcional de ano"},
                },
            },
        },
    },
]

TOOL_MAP = {
    "consultar_indicador": consultar_indicador,
    "ultimo_periodo": ultimo_periodo,
    "listar_periodos": listar_periodos,
    "resumo_uf": resumo_uf,
}

SYSTEM_PROMPT = """Você é um assistente especializado em dados do mercado de trabalho brasileiro, 
com acesso direto ao banco de dados da PNAD Contínua (IBGE) via MongoDB Atlas.

Você pode consultar três indicadores trimestrais para Pernambuco:
- Taxa de desocupação (desemprego)
- Taxa de participação na força de trabalho
- Taxa de informalidade

Os dados estão disponíveis de 2012 até 2025, desagregados por sexo (Homens, Mulheres, Total).

Sempre use as ferramentas disponíveis para buscar dados reais antes de responder.
Apresente os resultados de forma clara, com o período, valor e contexto.
Responda sempre em português."""


# ── FastAPI ────────────────────────────────────────────────────────────────────

app = FastAPI(title="Agente IBGE PNAD")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []


@app.post("/chat")
async def chat(req: ChatRequest):
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(req.history)
    messages.append({"role": "user", "content": req.message})

    # Loop do agente — pode chamar múltiplas tools
    for _ in range(5):
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
        )
        msg = response.choices[0].message

        if msg.tool_calls:
            messages.append(msg)
            for call in msg.tool_calls:
                fn = TOOL_MAP.get(call.function.name)
                args = json.loads(call.function.arguments)
                result = fn(**args) if fn else {"erro": "ferramenta não encontrada"}
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": json.dumps(result, ensure_ascii=False, default=str),
                })
        else:
            return {"response": msg.content, "messages": messages[1:]}

    return {"response": "Não consegui processar a pergunta.", "messages": messages[1:]}


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTML_PAGE


# ── Interface HTML ─────────────────────────────────────────────────────────────

HTML_PAGE = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Agente IBGE PNAD Contínua</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         background: #0f172a; color: #e2e8f0; height: 100vh; display: flex; flex-direction: column; }
  header { background: #1e293b; padding: 16px 24px; border-bottom: 1px solid #334155;
           display: flex; align-items: center; gap: 12px; }
  header h1 { font-size: 18px; font-weight: 600; color: #f1f5f9; }
  header span { font-size: 13px; color: #94a3b8; }
  #chat { flex: 1; overflow-y: auto; padding: 24px; display: flex; flex-direction: column; gap: 16px; }
  .msg { max-width: 75%; padding: 12px 16px; border-radius: 12px; font-size: 14px; line-height: 1.6; }
  .user { align-self: flex-end; background: #3b82f6; color: white; border-bottom-right-radius: 4px; }
  .assistant { align-self: flex-start; background: #1e293b; color: #e2e8f0;
               border: 1px solid #334155; border-bottom-left-radius: 4px; white-space: pre-wrap; }
  .thinking { align-self: flex-start; color: #64748b; font-size: 13px; font-style: italic; }
  #form { padding: 16px 24px; background: #1e293b; border-top: 1px solid #334155;
          display: flex; gap: 12px; }
  #input { flex: 1; background: #0f172a; border: 1px solid #334155; border-radius: 8px;
           padding: 12px 16px; color: #e2e8f0; font-size: 14px; outline: none; }
  #input:focus { border-color: #3b82f6; }
  button { background: #3b82f6; color: white; border: none; border-radius: 8px;
           padding: 12px 20px; font-size: 14px; cursor: pointer; font-weight: 500; }
  button:hover { background: #2563eb; }
  button:disabled { background: #475569; cursor: not-allowed; }
  .suggestions { display: flex; flex-wrap: wrap; gap: 8px; padding: 0 24px 16px; }
  .chip { background: #1e293b; border: 1px solid #334155; border-radius: 20px;
          padding: 6px 14px; font-size: 12px; color: #94a3b8; cursor: pointer; }
  .chip:hover { border-color: #3b82f6; color: #3b82f6; }
</style>
</head>
<body>
<header>
  <div>
    <h1>🤖 Agente IBGE — PNAD Contínua</h1>
    <span>Dados do mercado de trabalho de Pernambuco • 2012–2025</span>
  </div>
</header>
<div id="chat">
  <div class="msg assistant">Olá! Sou um agente de IA com acesso direto aos dados da PNAD Contínua (IBGE) armazenados no MongoDB Atlas.

Posso responder perguntas sobre:
• Taxa de desocupação (desemprego)
• Taxa de participação na força de trabalho
• Taxa de informalidade

Dados disponíveis para Pernambuco, de 2012 a 2025, por sexo e trimestre.

Como posso ajudar?</div>
</div>
<div class="suggestions">
  <div class="chip" onclick="ask(this)">Taxa de desocupação das mulheres no último trimestre</div>
  <div class="chip" onclick="ask(this)">Compare homens e mulheres em 2024</div>
  <div class="chip" onclick="ask(this)">Evolução da informalidade desde 2020</div>
  <div class="chip" onclick="ask(this)">Qual foi o pior trimestre de desemprego?</div>
</div>
<form id="form" onsubmit="send(event)">
  <input id="input" placeholder="Faça uma pergunta sobre os dados da PNAD Contínua..." autocomplete="off" />
  <button type="submit" id="btn">Enviar</button>
</form>
<script>
  let history = [];

  function ask(el) {
    document.getElementById('input').value = el.textContent;
    send(new Event('submit'));
  }

  async function send(e) {
    e.preventDefault();
    const input = document.getElementById('input');
    const btn = document.getElementById('btn');
    const msg = input.value.trim();
    if (!msg) return;

    addMsg(msg, 'user');
    input.value = '';
    btn.disabled = true;

    const thinking = addMsg('Consultando o banco de dados...', 'thinking');

    try {
      const res = await fetch('/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: msg, history }),
      });
      const data = await res.json();
      thinking.remove();
      addMsg(data.response, 'assistant');
      history = data.messages;
    } catch (err) {
      thinking.remove();
      addMsg('Erro ao conectar com o servidor.', 'assistant');
    }
    btn.disabled = false;
    input.focus();
  }

  function addMsg(text, cls) {
    const chat = document.getElementById('chat');
    const div = document.createElement('div');
    div.className = 'msg ' + cls;
    div.textContent = text;
    chat.appendChild(div);
    chat.scrollTop = chat.scrollHeight;
    return div;
  }
</script>
</body>
</html>"""


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False)