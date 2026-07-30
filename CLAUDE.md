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
- WeasyPrint para o PDF do relatório e do painel de gráficos (exige libs de sistema — já no `Dockerfile`)
- openpyxl para ler e gerar a planilha de colaboradores
- ASAAS (httpx) para assinatura mensal e cobrança

## Organização do código

`main.py` concentra as rotas antigas, mas **helpers e leituras foram extraídos** porque um
`APIRouter` não pode importar de `main` (import circular):

| Módulo | Papel |
|---|---|
| `app/web/deps.py` | `templates`, `page_user`, `gestor_page`, `shell_ctx`, datas em SP, impersonation |
| `app/queries.py` | agregados COPSOQ, áreas, campanha, seções do relatório |
| `app/billing.py` | regra de cobrança e **o gate de acesso** (`acesso()`) |
| `app/asaas.py` | client HTTP puro do ASAAS (sem regra de negócio) |
| `app/plans.py`, `app/settings_store.py`, `app/antibot.py` | planos, config em banco, proteção do cadastro |
| `app/routers/{publico,consultor,faturas,admin_billing}.py` | rotas novas, registradas **sem prefixo** |

`main.py` reexporta os nomes antigos (`_page_user = deps.page_user` etc.) para as rotas que
já existiam — a extração não mudou comportamento nenhum.

## Três níveis de acesso

| Papel (`User.role`) | Vê |
|---|---|
| `super_admin` (owner, o Gustavo) | tudo: consultorias e empresas |
| `consultant` | só as empresas com `Company.parent_id` = a consultoria dele |
| `admin` (gestor) | a própria empresa |
| `member` (colaborador) | só `/testes` |

A consultoria **é um tenant** (`Company.kind='consultoria'`), não um User: assim
`Charge.company_id` cobra empresa e consultoria pelo mesmo caminho e a impersonation
existente é reaproveitada. Consultoria não roda avaliação própria — `deps.gestor_page`
redireciona para `/consultor`.

**Impersonation guarda a trilha** (`{"imp": [ids]}` no cookie `tpc_impersonate`), não um id
só. Sem isso, entrar na empresa a partir da consultoria apagaria o caminho de volta.
`POST /impersonate/stop` sobe **um** nível. `auth.pode_impersonar` é revalidado no banco a
cada request: consultor só entra em empresa cujo `parent_id` é a consultoria dele.

## Cadastro público e aprovação

Dois links abertos e permanentes, mais o link de cada consultor:

- `/cadastro-empresa` e `/cadastro-consultor` → fila do owner (`/admin/cadastros`)
- `/cadastro-empresa/{slug_do_consultor}` → fila **daquele consultor** (`/consultor`).
  Essas empresas **não aparecem** na fila do owner e ele é recusado se tentar aprovar.

A conta nasce com `Company.status='pending'` e o gate manda para `/cadastro/analise` até
alguém aprovar. Proteção antibot em `app/antibot.py`, sem serviço externo: rate limit 5/h
por IP, honeypot `website`, desafio matemático assinado com HMAC (tempo mínimo de 3s) e
validação local de CPF/CNPJ.

## Cobrança (ASAAS)

Padrão do `sai-comercial/INSTRUCAO-ASAAS-PARA-OUTRO-PROJETO.md`: header `access_token`
(não Bearer), `User-Agent` obrigatório, CPF/CNPJ só dígitos, `externalReference
company:{id}` em tudo, `billingType="UNDEFINED"` (o cliente escolhe boleto/PIX/cartão na
`invoiceUrl`), webhook idempotente por `(provider, external_id, event_type)` respondendo
**200 sempre**, e reconciliação a cada 30 min como rede de segurança.

**Três formas de cobrança** (`Company.billing_mode`):

- `proprio` — assinatura própria no ASAAS;
- `pelo_consultor` — a consultoria dona paga; a empresa não gera assinatura;
- `isento` — liberado sem cobrança, **nunca bloqueia**.

`billing.ensure_subscription` sai sem fazer nada em `isento` e `pelo_consultor`: a única
porta para começar a cobrar quem está isento é `POST /admin/empresas/{id}/cobranca`, que
troca o `billing_mode` antes de chamar o ASAAS.

**Bloqueio: 7 dias após o vencimento** (`billing.GRACE_DAYS`), em **dois** pontos de
checagem e só:

1. `deps.page_user` — todas as páginas logadas. `allow_blocked=True` apenas em
   `/pagamento`, `/faturas*` e `/cadastro/analise`;
2. `_invite_ctx` em `main.py` — cobre as 3 páginas `/nr1/*` e as 3 rotas `/api/nr1/*`.

`billing.acesso()` **nunca chama o ASAAS** (só lê o banco) e curto-circuita para
`super_admin` — gateway fora do ar ou erro de cobrança não pode trancar a administração.

Token/ambiente do ASAAS ficam em `AppSetting` (tela `/admin/integracoes`) e **vencem o
`.env`** — dá para testar em sandbox e virar para produção sem redeploy.

> `replicas: 1` no compose é requisito: a reconciliação e o rate limit vivem em memória
> do processo.

## Fluxo da avaliação NR-1

1. **`/empresa/avaliacao`** (na UI: **"Envio Convite"**) — o gestor baixa a planilha modelo em
   `/empresa/avaliacao/modelo.xlsx` ou sobe a dele (`Nome`, `E-mail`, `Área`; `.xlsx` ou `.csv`)
   e define a **data de fim**. A data de início é carimbada no envio. Áreas novas são criadas sozinhas.
   - Se o cabeçalho não permite identificar as 3 colunas, cai no **wizard de mapeamento**
     (`empresa_avaliacao_mapear.html`) em vez de recusar o arquivo. `invites.py` está dividido
     em `ler_grade` → `sugerir_mapa` → `mapear_e_validar` justamente para isso.
2. Cada colaborador recebe um **link único sem senha** (`/nr1/{invite_token}`) e responde direto.
   O `Lead` fica com `user_id = NULL` e `campaign_id` preenchido.
3. Faltou alguém? `POST /empresa/avaliacao/adicionar` (uma pessoa) ou `/adicionar-lote` (lista
   colada) adiciona à campanha aberta. Quem já está convidado é ignorado — ninguém recebe dois links.
4. **Barra de progresso** = respondidos ÷ **quem recebeu** (`enviado_em` sem `erro_envio`).
   Cobrar resposta de quem nunca recebeu o link não mede nada.
5. **`POST /empresa/avaliacao/reengajar`** manda um e-mail próprio de lembrete
   (`mailer.send_reengagement_email`) para quem recebeu e não respondeu. Carimba
   `CampaignInvite.reengajado_em` **antes** de enviar, para nunca disparar em dobro.
   > A rota antiga `/reenviar` é só um alias. Ela **zerava `enviado_em`**, destruindo a base do
   > percentual de adesão — foi por isso que `reengajado_em` existe como coluna separada.
6. **`/empresa/resultados?aba=grafico`** — painel que se atualiza conforme as respostas chegam,
   com chips de recorte por área e download em `/empresa/graficos.pdf`.
7. Passada a data de fim, o teste para de aceitar respostas e a **aba Relatório** é liberada,
   com os mesmos chips por área e download em `/empresa/relatorio.pdf`.
   > Na tela o chip **filtra**; o PDF sai sempre **completo** (geral + todas as áreas) — é o
   > artefato de arquivo e auditoria.

Recortes com menos de `MIN_RESPONDENTES` (3) não são exibidos, para preservar o anonimato.

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

> `seed_super_admin()` reescreve a senha do super admin **a cada boot** a partir do env — não
> replicar esse padrão para consultor/empresa, e aprovar cadastro nunca toca em senha.
> `migrate_company_managers()` também roda a cada boot e reescreve `password_hash`: por isso ela
> ignora tenant fora do status `ativo`, e os cadastros novos gravam `manager_email=""`.

## Migrações

Não há Alembic: `init_db()` faz `create_all` + `ALTER TABLE ADD COLUMN` do que falta
(`_migrate_*_columns`). **O backfill é parte inseparável da migração** — sem o
`UPDATE companies SET status='ativo'`, o default `pending` prenderia todos os clientes atuais
em "cadastro em análise" no primeiro deploy. Empresas pré-existentes viram `billing_mode='isento'`
de propósito: ninguém passa a ser cobrado por efeito colateral do deploy.

Cuidados do SQLite: `ADD COLUMN` não aceita `UNIQUE` nem default não-constante (uniques novas
vêm do `create_all`), e dinheiro é sempre `Integer` em centavos — nunca `Float`.

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
