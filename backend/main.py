import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

import httpx
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.1-8b-instruct:free")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
APP_ENV = os.getenv("APP_ENV", "development")
APP_SECRET_KEY = os.getenv("APP_SECRET_KEY", "development-only-change-me")
DATABASE_PATH = Path(os.getenv("DATABASE_PATH", "data/chatbot.db"))
TOKEN_TTL_SECONDS = int(os.getenv("TOKEN_TTL_SECONDS", "604800"))
PASSWORD_HASH_ITERATIONS = int(os.getenv("PASSWORD_HASH_ITERATIONS", "600000"))

SYSTEM_PROMPT = (
    "Você é um chatbot especializado em livros. Conversa sobre livros, dá "
    "dicas de leitura personalizadas e ajuda o usuário a descobrir novas "
    "obras. Responda sempre em português do Brasil, de forma amigável e objetiva."
)

if APP_ENV == "production" and APP_SECRET_KEY == "development-only-change-me":
    raise RuntimeError("APP_SECRET_KEY deve ser configurada em produção")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def database():
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def init_database() -> None:
    with database() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                mode TEXT NOT NULL CHECK(mode IN ('chat', 'resumo')),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_conversations_user_updated
                ON conversations(user_id, updated_at DESC);
            CREATE INDEX IF NOT EXISTS idx_messages_conversation
                ON messages(conversation_id, id);
            """
        )


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt, PASSWORD_HASH_ITERATIONS
    )
    return f"pbkdf2_sha256${PASSWORD_HASH_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, iterations, salt, expected = stored.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt), int(iterations)
        )
        return hmac.compare_digest(digest.hex(), expected)
    except (ValueError, TypeError):
        return False


def encode_token(user_id: int) -> str:
    payload = json.dumps(
        {"sub": user_id, "exp": int(time.time()) + TOKEN_TTL_SECONDS},
        separators=(",", ":"),
    ).encode()
    encoded = base64.urlsafe_b64encode(payload).rstrip(b"=")
    signature = hmac.new(APP_SECRET_KEY.encode(), encoded, hashlib.sha256).digest()
    return f"{encoded.decode()}.{base64.urlsafe_b64encode(signature).rstrip(b'=').decode()}"


def decode_token(token: str) -> int:
    try:
        encoded, supplied_signature = token.split(".", 1)
        expected = hmac.new(APP_SECRET_KEY.encode(), encoded.encode(), hashlib.sha256).digest()
        supplied = base64.urlsafe_b64decode(supplied_signature + "=" * (-len(supplied_signature) % 4))
        if not hmac.compare_digest(expected, supplied):
            raise ValueError
        payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
        if payload["exp"] < time.time():
            raise ValueError
        return int(payload["sub"])
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=401, detail="Sessão inválida ou expirada") from exc


async def current_user(authorization: Annotated[str | None, Header()] = None) -> sqlite3.Row:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Faça login para continuar")
    user_id = decode_token(authorization.removeprefix("Bearer ").strip())
    with database() as connection:
        user = connection.execute(
            "SELECT id, name, email, created_at FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    if not user:
        raise HTTPException(status_code=401, detail="Usuário não encontrado")
    return user


def build_messages(extra_messages: list[dict]) -> list[dict]:
    return [{"role": "system", "content": SYSTEM_PROMPT}, *extra_messages]


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_database()
    yield


app = FastAPI(title="Entrelinhas API", version="2.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


class AuthRequest(BaseModel):
    email: str
    password: str = Field(min_length=8, max_length=128)


class RegisterRequest(AuthRequest):
    name: str = Field(min_length=2, max_length=80)


class UserResponse(BaseModel):
    id: int
    name: str
    email: str


class AuthResponse(BaseModel):
    token: str
    user: UserResponse


class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=10_000)
    conversation_id: int | None = None


class ChatResponse(BaseModel):
    reply: str
    conversation_id: int


class ResumoRequest(BaseModel):
    titulo: str = Field(min_length=1, max_length=300)
    autor: str | None = Field(default=None, max_length=200)
    conversation_id: int | None = None


class ResumoResponse(BaseModel):
    resumo: str
    conversation_id: int


def serialize_user(user: sqlite3.Row) -> dict:
    return {"id": user["id"], "name": user["name"], "email": user["email"]}


def create_conversation(user_id: int, mode: str, title: str) -> int:
    now = utc_now()
    with database() as connection:
        cursor = connection.execute(
            "INSERT INTO conversations (user_id, title, mode, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, title[:80], mode, now, now),
        )
        return int(cursor.lastrowid)


def assert_conversation(conversation_id: int, user_id: int) -> sqlite3.Row:
    with database() as connection:
        conversation = connection.execute(
            "SELECT * FROM conversations WHERE id = ? AND user_id = ?",
            (conversation_id, user_id),
        ).fetchone()
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversa não encontrada")
    return conversation


def save_message(conversation_id: int, role: str, content: str) -> None:
    now = utc_now()
    with database() as connection:
        connection.execute(
            "INSERT INTO messages (conversation_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (conversation_id, role, content, now),
        )
        connection.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?", (now, conversation_id)
        )


def conversation_messages(conversation_id: int) -> list[dict]:
    with database() as connection:
        rows = connection.execute(
            "SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY id",
            (conversation_id,),
        ).fetchall()
    return [{"role": row["role"], "content": row["content"]} for row in rows]


async def call_openrouter(messages: list[dict]) -> str:
    if not OPENROUTER_API_KEY:
        raise HTTPException(status_code=500, detail="OPENROUTER_API_KEY não configurada no .env")
    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": OPENROUTER_MODEL, "messages": messages}
    async with httpx.AsyncClient(timeout=60) as client:
        try:
            response = await client.post(OPENROUTER_URL, headers=headers, json=payload)
        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail=f"Erro ao conectar ao OpenRouter: {exc}") from exc
    if response.status_code != 200:
        raise HTTPException(status_code=502, detail=f"OpenRouter retornou erro: {response.text}")
    return response.json()["choices"][0]["message"]["content"]


@app.post("/auth/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(request: RegisterRequest):
    email = request.email.strip().lower()
    if "@" not in email:
        raise HTTPException(status_code=422, detail="Informe um e-mail válido")
    with database() as connection:
        try:
            cursor = connection.execute(
                "INSERT INTO users (name, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
                (request.name.strip(), email, hash_password(request.password), utc_now()),
            )
            user_id = int(cursor.lastrowid)
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=409, detail="Este e-mail já está cadastrado") from exc
        user = connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return {"token": encode_token(user_id), "user": serialize_user(user)}


@app.post("/auth/login", response_model=AuthResponse)
async def login(request: AuthRequest):
    with database() as connection:
        user = connection.execute(
            "SELECT * FROM users WHERE email = ?", (request.email.strip().lower(),)
        ).fetchone()
    if not user or not verify_password(request.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="E-mail ou senha incorretos")
    return {"token": encode_token(user["id"]), "user": serialize_user(user)}


@app.get("/auth/me", response_model=UserResponse)
async def me(user: Annotated[sqlite3.Row, Depends(current_user)]):
    return serialize_user(user)


@app.get("/conversations")
async def list_conversations(user: Annotated[sqlite3.Row, Depends(current_user)]):
    with database() as connection:
        rows = connection.execute(
            "SELECT id, title, mode, created_at, updated_at FROM conversations "
            "WHERE user_id = ? ORDER BY updated_at DESC",
            (user["id"],),
        ).fetchall()
    return [dict(row) for row in rows]


@app.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: int, user: Annotated[sqlite3.Row, Depends(current_user)]):
    conversation = assert_conversation(conversation_id, user["id"])
    return {**dict(conversation), "messages": conversation_messages(conversation_id)}


@app.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(conversation_id: int, user: Annotated[sqlite3.Row, Depends(current_user)]):
    assert_conversation(conversation_id, user["id"])
    with database() as connection:
        connection.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, user: Annotated[sqlite3.Row, Depends(current_user)]):
    conversation_id = request.conversation_id
    if conversation_id is None:
        conversation_id = create_conversation(user["id"], "chat", request.message)
    else:
        conversation = assert_conversation(conversation_id, user["id"])
        if conversation["mode"] != "chat":
            raise HTTPException(status_code=409, detail="Esta conversa é um resumo")
    history = conversation_messages(conversation_id)
    messages = build_messages([*history, {"role": "user", "content": request.message}])
    reply = await call_openrouter(messages)
    save_message(conversation_id, "user", request.message)
    save_message(conversation_id, "assistant", reply)
    return {"reply": reply, "conversation_id": conversation_id}


@app.post("/resumo", response_model=ResumoResponse)
async def resumo(request: ResumoRequest, user: Annotated[sqlite3.Row, Depends(current_user)]):
    referencia = request.titulo.strip()
    if request.autor:
        referencia += f" de {request.autor.strip()}"
    conversation_id = request.conversation_id
    if conversation_id is None:
        conversation_id = create_conversation(user["id"], "resumo", f"Resumo: {referencia}")
    else:
        conversation = assert_conversation(conversation_id, user["id"])
        if conversation["mode"] != "resumo":
            raise HTTPException(status_code=409, detail="Esta conversa não é de resumos")
    user_message = f"Resuma “{referencia}”"
    prompt = (
        f"Faça um resumo do livro '{referencia}'. Inclua: sinopse, temas principais e para qual "
        "tipo de leitor o livro é indicado. Se não conhecer a obra, diga isso claramente."
    )
    texto = await call_openrouter(build_messages([{"role": "user", "content": prompt}]))
    save_message(conversation_id, "user", user_message)
    save_message(conversation_id, "assistant", texto)
    return {"resumo": texto, "conversation_id": conversation_id}


@app.get("/")
async def health():
    return {"status": "ok"}
