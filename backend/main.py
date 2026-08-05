"""API do Chatbot de Livros.

Expõe endpoints REST que usam a API da OpenRouter para conversar sobre
livros e gerar resumos de obras.
"""

import os

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.1-8b-instruct:free")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

SYSTEM_PROMPT = (
     "Você é um chatbot especializado em livros. Conversa sobre livros, dá "
    "dicas de leitura personalizadas e ajuda o usuário a descobrir novas "
    "obras. Responda sempre em português do Brasil, de forma amigável e "
    "objetiva."
)


def build_messages(extra_messages: list[dict]) -> list[dict]:
    """Monta a lista de mensagens enviada ao modelo, prefixada com o system prompt."""
    return [{"role": "system", "content": SYSTEM_PROMPT}, *extra_messages]


app = FastAPI(
    title="Chatbot de Livros",
    description=(
        "API que conversa sobre livros e gera resumos de obras usando um "
        "modelo de linguagem via OpenRouter."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class Message(BaseModel):
    """Uma mensagem trocada entre usuário e assistente."""

    role: str = Field(..., description="Quem enviou a mensagem: 'user' ou 'assistant'.")
    content: str = Field(..., description="Texto da mensagem.")


class ChatRequest(BaseModel):
    """Corpo da requisição do endpoint /chat."""

    message: str = Field(..., description="Mensagem enviada pelo usuário.")
    history: list[Message] = Field(
        default_factory=list,
        description="Histórico da conversa, do mais antigo para o mais recente.",
    )


class ChatResponse(BaseModel):
    """Resposta do endpoint /chat."""

    reply: str = Field(..., description="Resposta gerada pelo assistente.")


class ResumoRequest(BaseModel):
    """Corpo da requisição do endpoint /resumo."""

    titulo: str = Field(..., description="Título do livro a ser resumido.")
    autor: str | None = Field(default=None, description="Autor do livro (opcional).")


class ResumoResponse(BaseModel):
    """Resposta do endpoint /resumo."""

    resumo: str = Field(..., description="Resumo gerado do livro.")


async def call_openrouter(messages: list[dict]) -> str:
    """Envia as mensagens para a OpenRouter e retorna o texto da resposta.

    Args:
        messages: Lista de mensagens no formato role/content esperado pela
            API de chat completions.

    Raises:
        HTTPException: 500 se a chave da API não estiver configurada;
            502 se a OpenRouter não puder ser contatada ou retornar erro.
    """
    if not OPENROUTER_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="OPENROUTER_API_KEY não configurada no .env",
        )

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {"model": OPENROUTER_MODEL, "messages": messages}

    async with httpx.AsyncClient(timeout=60) as client:
        try:
            response = await client.post(OPENROUTER_URL, headers=headers, json=payload)
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=502, detail=f"Erro ao conectar ao OpenRouter: {exc}"
            ) from exc

    if response.status_code != 200:
        raise HTTPException(status_code=502, detail=f"OpenRouter retornou erro: {response.text}")

    data = response.json()
    return data["choices"][0]["message"]["content"]


@app.post("/chat", response_model=ChatResponse, summary="Conversar com o chatbot", tags=["Chat"])
async def chat(request: ChatRequest):
    """Envia a mensagem do usuário, junto do histórico, para o modelo e retorna a resposta."""
    extra_messages = [{"role": m.role, "content": m.content} for m in request.history]
    extra_messages.append({"role": "user", "content": request.message})
    messages = build_messages(extra_messages)

    reply = await call_openrouter(messages)
    return ChatResponse(reply=reply)


@app.post(
    "/resumo", response_model=ResumoResponse, summary="Gerar resumo de um livro", tags=["Chat"]
)
async def resumo(request: ResumoRequest):
    """Gera um resumo do livro informado: sinopse, temas e público-alvo."""
    referencia = request.titulo
    if request.autor:
        referencia += f" de {request.autor}"

    prompt = (
        f"Faça um resumo do livro '{referencia}'. Inclua: sinopse, temas "
        "principais e para qual tipo de leitor o livro é indicado. Se não "
        "conhecer a obra, diga isso claramente em vez de inventar."
    )
    messages = build_messages([{"role": "user", "content": prompt}])

    texto = await call_openrouter(messages)
    return ResumoResponse(resumo=texto)


@app.get("/", summary="Verificar status da API", tags=["Status"])
async def health():
    """Health check simples usado para confirmar que a API está no ar."""
    return {"status": "ok"}
