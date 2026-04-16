# Teste de Perfil Comportamental — Instruções do projeto

Aplicação web que substitui a página Wix `strategicai.com.br/teste-perfil-comportamental` com captação estruturada de leads, teste de 30 perguntas em wizard e chat de análise com Gemini 2.5 Pro.

## Stack

- FastAPI (Python 3.11) + SQLAlchemy + SQLite em volume persistente
- Frontend single-page com Alpine.js + Tailwind (CDN)
- Gemini 2.5 Pro (`google-generativeai`) para o chat do analista
- Google Sheets (gspread) para view de leads do Gustavo
- SMTP (Google Workspace) para envio do resultado ao lead
- UAZAPI para notificação WhatsApp ao Gustavo

## URL pública

`https://teste.strategicai.com.br/perfil-comportamental`

Traefik faz `StripPrefix` para `/perfil-comportamental`, então o FastAPI serve tudo a partir de `/` internamente.

## Regra obrigatória: commit, push e deploy

**Antes de qualquer operação de commit, push ou redeploy, SEMPRE perguntar:**

> "Quer que eu faça commit, push e redeploy agora?"

Aguardar confirmação explícita antes de executar.

Isso inclui:
- `git commit`
- `git push`
- Redeploy via Portainer (force-update do serviço Swarm)
- Build de imagem Docker com `nocache=true`

## Deploy

O processo de redeploy deste projeto é sempre:
1. Criar o tarball: `tar -czf /tmp/build-context.tar.gz --exclude='.git' --exclude='node_modules' --exclude='.env' --exclude='data' .`
2. Build via Portainer API (endpoint `<ID_ENDPOINT>`, tag `ghcr.io/strategicai-hub/teste-perfil-comportamental:latest`)
3. Force-update do serviço Swarm (`<SERVICE_ID>`) com o spec completo incrementando `ForceUpdate`
4. Verificar HTTP 200 em `https://teste.strategicai.com.br/perfil-comportamental/`
5. Verificar se os containers estão rodando via `docker service ps <SERVICE_ID>` ou Portainer API
   - Se algum container estiver com estado diferente de `running`, ler os logs (`docker service logs <SERVICE_ID> --tail 50`) e corrigir o erro antes de encerrar.

Credenciais necessárias estão em `.env` na raiz do projeto (nunca commitado).

## Checklist pré-primeiro-deploy

1. Criar registro A `teste.strategicai.com.br` → IP do host Portainer (91.98.64.92)
2. Configurar SPF/DKIM do domínio (Google Workspace gera os registros TXT)
3. Criar planilha Google e compartilhá-la com a service account → salvar `GOOGLE_SHEET_ID`
4. Obter `GEMINI_API_KEY` no AI Studio
5. Criar imagem inicial no GHCR (`ghcr.io/strategicai-hub/teste-perfil-comportamental:latest`)
6. Preencher todas as variáveis em `.env`
7. Deploy da stack via Portainer apontando para `docker-compose.yml` deste repo

## Rodar local

```bash
python -m venv .venv
source .venv/bin/activate   # ou .venv/Scripts/activate no Windows
pip install -r requirements.txt
cp .env.example .env  # preencher as variáveis
mkdir -p data
DATABASE_URL=sqlite:///./data/app.db uvicorn app.main:app --reload
```

Acessar `http://localhost:8000/`.

## Tom e idioma

- Responder sempre em português brasileiro.
- Respostas curtas e diretas.
- Não usar emojis a menos que solicitado.
