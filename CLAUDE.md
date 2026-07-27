# Teste de Perfil Comportamental — Instruções do projeto

Aplicação web que substitui a página Wix `strategicai.com.br/teste-perfil-comportamental` com captação estruturada de leads, teste de 30 perguntas em wizard e chat de análise com Gemini 2.5 Pro.

Hoje o teste ativo é o **COPSOQ II (NR-1 — riscos psicossociais)**, com 119 itens, 35 subescalas e 8 itens macro.

## Stack

- FastAPI (Python 3.11) + SQLAlchemy + SQLite em volume persistente
- Frontend single-page com Alpine.js + Tailwind (CDN)
- Gemini 2.5 Pro (`google-generativeai`) para o chat do analista
- Google Sheets (gspread) para view de leads do Gustavo
- SMTP (Google Workspace) para envio do resultado ao lead e dos convites da NR-1
- UAZAPI para notificação WhatsApp ao Gustavo
- WeasyPrint para o PDF do relatório (exige libs de sistema — já no `Dockerfile`)
- openpyxl para ler a planilha de colaboradores

## Fluxo da avaliação NR-1

1. **`/empresa/avaliacao`** — o gestor sobe uma planilha (`Nome`, `E-mail`, `Área`; `.xlsx` ou `.csv`)
   e define a **data de fim**. A data de início é carimbada no envio. Áreas novas são criadas sozinhas.
2. Cada colaborador recebe um **link único sem senha** (`/nr1/{invite_token}`) e responde direto.
   O `Lead` fica com `user_id = NULL` e `campaign_id` preenchido.
3. **`/empresa/resultados?aba=grafico`** — painel que se atualiza conforme as respostas chegam.
4. Passada a data de fim, o teste para de aceitar respostas e a **aba Relatório** é liberada,
   com consolidado geral + por área e download em `/empresa/relatorio.pdf`.

> A campanha não tem job de encerramento: está aberta enquanto `datetime.utcnow() < Campaign.fim`.

### Relatório é determinístico — não usa LLM

Os textos vêm de `app/copsoq/knowledge.py`, transcrição da "BASE DE CONHECIMENTO PARA IA DE
ANÁLISE DE RELATÓRIO COPSOQ II" (34 indicadores × definição + 3 status). A subescala `stress`
não consta do documento e foi redigida no mesmo padrão (marcada com `"fonte": "redigido"`).
`app/copsoq/report.py` só cruza esses textos com o resultado de `scoring.aggregate()`.

O Gemini segue existindo apenas no chat do resultado individual.

### Fase 2 — plano de ação (ainda sem tela)

Já estão prontos e testáveis: `KNOWLEDGE[...]["acao"|"impacto_negativo"|"impacto_positivo"]`,
`report.build_action_plan()` (registros 5W2H) e `report.correlacoes()` (análise cruzada da §5
da base). Falta apenas a interface e o export.

## Dados de demonstração

```bash
python -m scripts.seed_demo --listar
python -m scripts.seed_demo --empresa-slug <slug>
```

Cria 10 respondentes em 3 áreas com respostas desenhadas para o agregado cobrir os três status
(favorável, atenção e risco alto). Idempotente: apaga os anteriores (`@demo.local`) antes.
Em produção, rodar dentro do container (`docker exec ... python -m scripts.seed_demo ...`).

## URL pública

`https://teste.strategicai.com.br/`

Traefik roteia só pelo Host (sem PathPrefix nem StripPrefix); o FastAPI serve tudo a partir de `/` e `BASE_PATH` fica vazio. Links antigos com o prefixo `/perfil-comportamental/*` recebem redirect 301 para a raiz (rota `legacy_prefix_redirect` em `app/main.py`).

O super admin entra pela própria tela de login da raiz: e-mail `atendimento@strategicai.com.br` (`SUPER_ADMIN_EMAIL`) + `SUPER_ADMIN_PASSWORD` → vai para `/admin`. Não existe mais página `/admin/login`.

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
4. Verificar HTTP 200 em `https://teste.strategicai.com.br/`
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
