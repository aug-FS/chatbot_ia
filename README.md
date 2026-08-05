# Entrelinhas

Chatbot literário com inteligência artificial para conversar sobre livros, recomendar leituras e gerar resumos. Cada pessoa possui uma conta e uma biblioteca privada com o histórico de suas conversas.

## Funcionalidades

- Cadastro e login por e-mail e senha
- Senhas protegidas com PBKDF2-SHA256 e salt individual
- Sessão por token assinado e com expiração
- Conversas com contexto via OpenRouter
- Resumos com sinopse, temas e público indicado
- Histórico separado por usuário
- Reabertura e exclusão de conversas
- Interface responsiva em português
- Documentação interativa da API

## Arquitetura

```text
Navegador (React + Vite)
        │ HTTP + Bearer token
        ▼
API (FastAPI)
   ├── SQLite: usuários, conversas e mensagens
   └── OpenRouter: geração das respostas
```

O frontend nunca recebe a chave da OpenRouter. Ela permanece somente no backend. O banco SQLite é criado automaticamente em `data/chatbot.db` e não é versionado.

## Requisitos

- Python 3.10 ou superior
- Node.js 20 ou superior
- npm 10 ou superior
- Uma chave da [OpenRouter](https://openrouter.ai/keys)

## Configuração local

Na raiz do projeto:

```bash
cp .env.example .env
```

Preencha `OPENROUTER_API_KEY` e gere um segredo de sessão:

```bash
openssl rand -hex 32
```

Copie o resultado para `APP_SECRET_KEY`. Nunca envie o `.env` ao Git; ele já está no `.gitignore`.

### Backend

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt -r backend/requirements-dev.txt
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

Se o Ubuntu informar que `ensurepip` não está disponível:

```bash
sudo apt install python3-venv
```

API: <http://127.0.0.1:8000>  
Swagger: <http://127.0.0.1:8000/docs>

### Frontend

Em outro terminal:

```bash
cd frontend
npm ci
npm run dev
```

Interface: <http://127.0.0.1:5173>

Durante o desenvolvimento, o Vite encaminha `/api` para a porta `8000`. Por isso não é necessário colocar a URL do backend no `.env` do frontend.

## Variáveis de ambiente

| Variável | Obrigatória | Padrão | Finalidade |
|---|---:|---|---|
| `OPENROUTER_API_KEY` | Sim | — | Autentica chamadas à OpenRouter |
| `OPENROUTER_MODEL` | Não | Llama 3.1 8B gratuito | Modelo usado pelo chatbot |
| `APP_ENV` | Em produção | `development` | Use `production` na publicação |
| `APP_SECRET_KEY` | Em produção | somente desenvolvimento | Assina as sessões; use valor aleatório |
| `TOKEN_TTL_SECONDS` | Não | `604800` | Duração da sessão, em segundos (7 dias) |
| `PASSWORD_HASH_ITERATIONS` | Não | `600000` | Custo do PBKDF2; não reduza em produção |
| `DATABASE_PATH` | Não | `data/chatbot.db` | Caminho do banco SQLite |
| `CORS_ORIGINS` | Em produção | URLs locais | Origens permitidas, separadas por vírgula |
| `VITE_API_URL` | Em produção | `/api` | URL pública da API usada no build do frontend |

Variáveis iniciadas por `VITE_` são públicas no navegador. Nunca coloque segredos nelas.

## Banco de dados

O schema é criado no primeiro start e possui:

- `users`: nome, e-mail único e hash da senha
- `conversations`: título, modo, proprietário e datas
- `messages`: mensagens ordenadas de usuário e assistente

Todas as consultas de histórico verificam o usuário autenticado. A exclusão de um usuário remove suas conversas e mensagens por cascata.

Para fazer backup local, pare o backend e copie o arquivo indicado por `DATABASE_PATH`. Em produção, monte esse caminho em um volume persistente.

## API principal

| Método | Rota | Autenticação | Descrição |
|---|---|---:|---|
| `POST` | `/auth/register` | Não | Cria uma conta |
| `POST` | `/auth/login` | Não | Inicia uma sessão |
| `GET` | `/auth/me` | Sim | Retorna a pessoa autenticada |
| `GET` | `/conversations` | Sim | Lista seu histórico |
| `GET` | `/conversations/{id}` | Sim | Abre uma conversa |
| `DELETE` | `/conversations/{id}` | Sim | Exclui uma conversa |
| `POST` | `/chat` | Sim | Conversa com contexto e persiste a resposta |
| `POST` | `/resumo` | Sim | Gera e persiste um resumo |
| `GET` | `/` | Não | Health check |

## Testes e build

```bash
pytest backend/tests -q
cd frontend && npm run build
```

## Caminho simples para produção

Para a primeira versão, a opção mais simples é:

1. publicar o frontend estático na Vercel, Netlify ou Cloudflare Pages;
2. publicar o FastAPI no Railway, Render ou Fly.io;
3. anexar um volume persistente ao backend e apontar `DATABASE_PATH` para ele;
4. definir `APP_ENV=production`, um `APP_SECRET_KEY` forte, a chave OpenRouter e `CORS_ORIGINS` com o domínio real;
5. gerar o frontend com `VITE_API_URL=https://api.seudominio.com`.

Com SQLite, execute apenas uma instância do backend. Isso é adequado para o lançamento inicial e baixo volume. Quando precisar de múltiplas instâncias, alta disponibilidade ou mais concorrência, migre a persistência para PostgreSQL antes de escalar horizontalmente.

Comando de produção do backend:

```bash
uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}
```

Build do frontend:

```bash
cd frontend
npm ci
npm run build
```

Publique o conteúdo de `frontend/dist` no provedor estático.

## Segurança

- Não versione `.env`, bancos, tokens ou chaves.
- Use HTTPS em produção.
- Troque `APP_SECRET_KEY` se houver suspeita de vazamento; sessões atuais serão invalidadas.
- Restrinja `CORS_ORIGINS` ao domínio do frontend.
- Faça backups regulares do volume do banco.
- Para uma aplicação pública, adicione recuperação de senha, confirmação de e-mail e limitação de tentativas de login.

## Estrutura

```text
chatbot_ia/
├── backend/
│   ├── main.py
│   ├── requirements.txt
│   └── tests/
├── frontend/
│   ├── src/
│   ├── package.json
│   └── vite.config.ts
├── .env.example
├── .gitignore
└── README.md
```
