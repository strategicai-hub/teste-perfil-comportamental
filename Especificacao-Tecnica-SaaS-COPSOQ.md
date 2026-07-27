# Especificação Técnica — SaaS de Avaliação de Riscos Psicossociais (NR-1)

**Projeto:** SAI · Solução NR-1
**Instrumento:** COPSOQ II — Versão Longa (119 questões; adaptação PT de Silva et al., 2011)
**Público deste documento:** desenvolvedor(a) responsável pela sistematização do SaaS
**Anexo obrigatório:** `copsoq-config.json` (dados, faixas, templates e biblioteca de ações — machine-readable)
**Versão:** 1.0

> Este documento consolida os três módulos já prototipados (Base Científica, Dashboard de Análises e Plano de Ação) em uma especificação implementável. É **stack-agnóstico**: descreve modelo de dados, regras de negócio, lógica de IA e saídas. O time pode implementar em qualquer linguagem/framework.

---

## 0. Visão geral

O sistema recebe as respostas de um questionário COPSOQ II, calcula escores por dimensão, classifica o risco e gera três saídas encadeadas:

1. **Base Científica** — conteúdo institucional/estático que dá validade legal ao método (não depende dos dados do cliente).
2. **Dashboard de Análises** — panorama dos resultados + devolutivas por dimensão + análise aprofundada por item macro, com textos padrão nuançados por IA conforme o percentual.
3. **Plano de Ação** — registros de ação gerados automaticamente (dimensão + faixa → medida da biblioteca), com responsáveis, prazos, indicadores e cronograma/Gantt.

**Fluxo macro:**

```
CSV/respostas → [1] Pontuação → [2] Classificação → [3] Devolutivas (IA) → [4] Plano de Ação (IA) → [5] Relatórios/Exports
```

---

## 1. Modelo de dados

Entidades principais (chaves e tipos essenciais; ver JSON schemas abaixo).

| Entidade | Descrição |
|---|---|
| `Instrumento` | Metadados do COPSOQ II (119 questões, escala 1–5). |
| `Questao` | Cada item do questionário; pertence a uma `Dimensao`; pode ser `reversa`. |
| `Dimensao` | 35 dimensões; tem `direcao` (`demanda` \| `recurso`) e pertence a um `ItemMacro`. |
| `ItemMacro` | 8 blocos que agrupam as dimensões (ordem fixa de exibição). |
| `Respondente` | Colaborador; atributos de recorte: `setor`, `cargo`, `empresa`. |
| `Resposta` | Valor 1–5 de um respondente para uma questão. |
| `ResultadoDimensao` | Escore 0–100 agregado + `faixa` + `direcao`. |
| `ResultadoItemMacro` | Classificação do bloco (pior faixa) + focos de risco. |
| `Devolutiva` | Texto padrão + texto nuançado por IA, por dimensão e por item macro. |
| `RegistroAcao` | Item do plano de ação (5W2H). |
| `Cronograma` | Tarefas com início/duração para o Gantt. |

### 1.1 JSON Schemas (resumo)

```json
// ResultadoDimensao
{
  "dimensaoId": "ritmo",
  "nome": "Ritmo de trabalho",
  "direcao": "demanda",              // demanda | recurso
  "escore": 60,                      // 0-100
  "faixa": "atencao",                // favoravel | atencao | risco_alto
  "pressaoRisco": 60,                // ver 2.4
  "gapRiscoAlto": 7,                 // ver 2.4
  "n": 10                            // respondentes considerados
}
```

```json
// RegistroAcao (saída do gerador de plano)
{
  "ordem": 1,
  "fator": "Ritmo de trabalho",
  "dimensaoId": "ritmo",
  "itemMacro": "Exigências laborais",
  "escore": 60,
  "faixa": "atencao",
  "riscoIdentificado": "Ritmo intenso e picos de demanda mal distribuídos...",
  "medidaControle": "Revisar metas e dimensionamento; regular banco de horas...",
  "tipo": "Controle administrativo (fonte)",
  "nivel": "Primário",              // Primário | Secundário | Terciário
  "responsavel": "Gestão + RH",
  "prazoDias": 90,
  "indicador": "Índice de carga percebida; horas extras por setor",
  "origemTexto": "template|ia"      // rastreabilidade
}
```

O restante das estruturas (dimensões, faixas, templates, biblioteca de ações) está em `copsoq-config.json` — **importar como fonte única de verdade**.

---

## 2. Regras de codificação (núcleo do sistema)

> Estas regras são o coração do produto. Implementar como funções puras e testáveis.

### 2.1 Cálculo do escore (0–100)

1. Para cada questão, converter a resposta Likert (1–5) para 0–100: `valor = (likert - 1) / 4 * 100` → (1→0, 2→25, 3→50, 4→75, 5→100).
2. **Itens reversos:** inverter antes de agregar: `valor = 100 - valor`. A lista de itens reversos segue o **manual oficial do COPSOQ II** (não está codificada neste protótipo — ver observação em `meta` do JSON).
3. Escore da dimensão = média dos valores das suas questões (ignorando respostas ausentes), arredondado para inteiro.

### 2.2 Direção da dimensão

Cada dimensão é `demanda` ou `recurso` (ver `copsoq-config.json`). **A direção determina a cor**, não o número cru.

### 2.3 Faixas (classificação por tercis)

```
banda(escore, direcao):
  nivel = "baixo" se escore<=33; "medio" se escore<=66; senão "alto"
  se direcao == "demanda":  baixo→favoravel, medio→atencao, alto→risco_alto
  se direcao == "recurso":  alto→favoravel,  medio→atencao, baixo→risco_alto
```

### 2.4 Priorização (pressão de risco e gap)

- `pressaoRisco = escore` se `demanda`, senão `100 - escore`. (0–100; maior = mais preocupante — usar para ordenar.)
- `gapRiscoAlto` (quanto falta para virar risco alto) = `67 - escore` (demanda) ou `escore - 33` (recurso), quando em `atencao`.

### 2.5 Classificação do item macro

`faixaMacro = pior faixa entre as dimensões do bloco` (risco_alto > atencao > favoravel). Focos = dimensões do bloco com faixa ≠ favoravel, ordenadas por `pressaoRisco` desc (exibir top 3).

### 2.6 Privacidade (NR-1 / dado sensível)

Nenhum recorte (setor/cargo/área) com **menos de 5 respondentes** deve ser exibido individualmente. Abaixo do limite, agregar ao "Geral" ou suprimir. Configurável em `privacidade.minRespondentesPorRecorte`.

---

## 3. Módulo 1 — Base Científica

Conteúdo **estático/institucional** (independe dos dados do cliente). Renderizar como página/seção fixa e como export PDF. Estrutura já definida (ver PDF `Base-Cientifica-SAI-NR1.pdf`): apresentação, marco normativo (NR-1, ISO 45003, OMS/OIT), fundamentação teórica (Karasek, Siegrist, JD-R, HSE), instrumento COPSOQ II, método de pontuação e referências.

**Implementação:** CMS simples ou markdown versionado. Deve permitir atualização de datas normativas sem deploy.

---

## 4. Módulo 2 — Dashboard de Análises

### 4.1 Seção "Panorama de resultados"
Lista as 35 dimensões agrupadas pelos 8 itens macro. Cada linha: nome, barra (largura = escore; cor = faixa), escore, selo de faixa. Marcadores de tercil em 33% e 66%.

### 4.2 Devolutiva por dimensão
Para cada dimensão, exibir o **texto padrão** de `templatesDevolutiva[direcao][faixa]` com `{nome}`/`{escore}` substituídos. Campo **editável** pelo analista. Guardar `textoPadrao` e `textoFinal` separadamente.

### 4.3 Análise aprofundada por item macro
Para cada um dos 8 blocos (na ordem de `itensMacro`): chips das dimensões (nome: escore, colorido), a **devolutiva do bloco** (aponta os focos calculados em 2.5) e um **campo de texto livre** ("análise aprofundada") para o conteúdo redigido/IA.

### 4.4 Lógica de nuance por IA
A IA reescreve o texto padrão ajustando **ênfase e intensidade conforme o `escore` exato** (ex.: 60 e 66 são ambos "Atenção", mas o 66 recebe tom mais urgente). Especificação do prompt em §6.

---

## 5. Módulo 3 — Plano de Ação

### 5.1 Geração automática de registros
Para cada dimensão com faixa `atencao` ou `risco_alto` (priorizadas por `pressaoRisco`):

```
para cada dimensao priorizada:
  base = bibliotecaAcoes[dimensaoId] ou bibliotecaAcoes["_default"]
  registro = {
    fator, dimensaoId, itemMacro, escore, faixa,
    riscoIdentificado: <template ou IA>,
    medidaControle: base.medida,
    tipo: base.tipo, nivel: base.nivel,
    responsavel: base.responsavelSugerido,
    prazoDias: base.prazoDias,
    indicador: base.indicador
  }
```

A **hierarquia de controles** (eliminar > substituir > administrativo > treinamento) e os **níveis de intervenção** (Primário/Secundário/Terciário da ISO 45003) já vêm marcados na biblioteca. Todo registro cujo fator seja Médio/Alto/Crítico **deve** compor o inventário do PGR.

### 5.2 Cronograma físico + Gantt
Cada `RegistroAcao` gera uma tarefa com `inicioMes` e `duracaoMeses` (derivados de `prazoDias` e da priorização). Renderizar Gantt horizontal (timeline de 6 meses padrão). Incluir marco de **reavaliação COPSOQ** ao final (fecha o ciclo PDCA). Ver `Plano-de-Acao-Modelo-COPSOQ.pdf`.

---

## 6. Camada de IA — especificação de prompt

**Entrada (variáveis):** `nome`, `escore`, `direcao`, `faixa`, `itemMacro`, `pressaoRisco`, `gapRiscoAlto`, `textoPadrao`, e (opcional) indicadores operacionais reais.

**Regras do prompt:**
- Reescrever `textoPadrao` mantendo o significado técnico e o enquadramento NR-1.
- Modular a intensidade pelo `escore`: quanto mais próximo do limite de risco alto (menor `gapRiscoAlto`), mais assertivo o texto.
- Não inventar dados; usar apenas escore/faixa fornecidos.
- Saída em PT-BR, tom técnico-profissional, 2–4 frases (devolutiva) ou parágrafo (análise aprofundada).

**Determinismo/custo:** cachear a saída por (`dimensaoId`, `escore`) — mesma entrada, mesmo texto. Permitir override manual (o texto editado pelo analista sempre prevalece).

---

## 7. Pipeline de processamento

```
1. Ingerir respostas (CSV/form) → validar schema (colunas Nome,Cargo,Setor,Empresa,Q1..Q119)
2. Pontuar por questão (2.1) → aplicar reversos → agregar por dimensão
3. Classificar faixas (2.3) + calcular pressão/gap (2.4)
4. Consolidar itens macro (2.5) + aplicar privacidade (2.6)
5. Gerar devolutivas (templates → IA §6)
6. Gerar plano de ação (5.1) + cronograma (5.2)
7. Renderizar dashboard + exports (PDF/HTML)
```

Formato de ingestão de referência: `COPSOQ_Modelo_Versao_Longa_SETOR.csv` (colunas `Nome;Cargo;Setor;Empresa;Q1..Q119`, separador `;`).

---

## 8. Saídas e exports

| Saída | Formato | Observação |
|---|---|---|
| Dashboard interativo | HTML/SPA | Filtro por item macro; campos editáveis; barras animadas. |
| Relatório de análise | PDF | Panorama + análise por item macro (ver `Analise-Teste-Psicossocial-COPSOQ.pdf`). |
| Plano de ação | PDF | Cards 5W2H + Gantt (landscape). |
| Base científica | PDF | Anexo técnico fixo. |
| Dados | JSON/CSV | Exportar resultados por dimensão/macro para o PGR. |

**Identidade visual (padrão do produto):** teal `#0e7c72` / `#17a89a`; semáforo verde `#1f9d57`, âmbar `#c9860f`, vermelho `#d23b3f`; badges numerados; tags amarelas.

---

## 9. Regras de negócio e casos de borda

- **Respostas ausentes:** ignorar na média da dimensão; se >50% ausente, marcar dimensão como "sem dados".
- **Dimensão com 1 questão** (ex.: autoeficácia, saúde geral): média = a própria questão.
- **Empate de faixa no item macro:** vale a pior.
- **Recorte < 5 respondentes:** suprimir (2.6).
- **Texto editado pelo analista:** nunca sobrescrever com IA sem confirmação.
- **Itens reversos:** obrigatório validar contra o manual COPSOQ II antes de produção (impacto direto na direção/cor).

---

## 10. Anexos

- **Anexo A —** `copsoq-config.json`: dimensões, direções, itens macro, faixas, templates de devolutiva e biblioteca de ações. **Fonte única de verdade.**
- **Anexo B —** PDFs de referência dos três módulos (Base Científica, Análise, Plano de Ação) como especificação visual.

**Referências normativas:** NR-1 (GRO/PGR); ISO 45003:2021; OMS/OIT (2022); COPSOQ II (Kristensen, 2005; adaptação Silva et al., 2011).
