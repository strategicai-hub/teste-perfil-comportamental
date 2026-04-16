# Teste de Perfil Comportamental

Aplicação web que substitui a página Wix com captação estruturada de leads, teste de 30 perguntas em wizard interativo e chat de análise com IA (Gemini 2.5 Pro).

## Características

- **Fluxo de 3 etapas** sem quebra de navegação:
  1. Captura de lead (nome, e-mail, WhatsApp, profissão, origem)
  2. Wizard de 30 perguntas com 4 arquétipos (Tubarão, Lobo, Águia, Gato)
  3. Resultado com análise de IA embarcada
  
- **Links pessoais duráveis**: usuários podem retornar via `/r/{token}` para rever resultado e continuar a conversa
- **Notificações automáticas**: e-mail de resultado ao lead + WhatsApp para follow-up comercial
- **Persistência**: leads e histórico de chat salvos em SQLite em volume Docker

## Stack

- **Backend**: FastAPI (Python 3.11) + SQLAlchemy + SQLite
- **Frontend**: HTML5 + Alpine.js + Tailwind CSS (CDN)
- **LLM**: Gemini 2.5 Pro com streaming SSE
- **Persistência de leads**: Google Sheets via gspread
- **E-mail**: SMTP (Google Workspace)
- **Notificações**: UAZAPI (WhatsApp)

## URLs

- **Aplicação**: https://teste.strategicai.com.br/perfil-comportamental
- **Link de retorno**: https://teste.strategicai.com.br/perfil-comportamental/r/{token}

## Desenvolvimento Local

### Requisitos

- Python 3.11+
- pip + venv

### Setup

```bash
python -m venv .venv
source .venv/bin/activate   # Linux/Mac
# ou
.venv\Scripts\activate       # Windows

pip install -r requirements.txt
cp .env.example .env         # preencher variáveis
mkdir -p data
```

### Rodar localmente

```bash
DATABASE_URL=sqlite:///./data/app.db uvicorn app.main:app --reload
```

Acesso em http://localhost:8000/

## Variáveis de Ambiente

Copie `.env.example` para `.env` e preencha:

- `GEMINI_API_KEY`: chave da API Gemini
- `GOOGLE_CREDENTIALS_JSON`: JSON da service account (Google Sheets)
- `GOOGLE_SHEET_ID`: ID da planilha de leads
- `SMTP_*`: credenciais de SMTP
- `UAZAPI_*`: credenciais de WhatsApp
- `ALERT_PHONE`: número para notificações

## Docker

```bash
docker build -t teste-perfil-comportamental:latest .
docker run -p 8000:8000 --env-file .env teste-perfil-comportamental:latest
```

## Deploy no Portainer

Veja `CLAUDE.md` para instruções de deploy via Portainer + Docker Swarm.

## Estrutura

```
app/
├── main.py          # FastAPI routes
├── db.py            # SQLAlchemy models
├── questions.py     # 30 perguntas e arquétipos
├── scoring.py       # Cálculo de percentuais
├── gemini.py        # Cliente Gemini 2.5 Pro
├── sheets.py        # Google Sheets integration
├── mailer.py        # SMTP email delivery
├── notifier.py      # UAZAPI WhatsApp
└── prompts/
    └── analista.txt # System prompt do analista
static/
├── index.html       # SPA
├── app.js           # Alpine.js logic
└── style.css        # Custom styles
assets/
├── tubarao.png
├── lobo.png
├── aguia.png
└── gato.png
```

## Licença

Proprietary — Strategic AI
