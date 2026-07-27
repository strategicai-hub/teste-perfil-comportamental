"""Base de conhecimento do COPSOQ II — textos do relatório NR-1.

Transcrição do documento "BASE DE CONHECIMENTO PARA IA DE ANÁLISE DE RELATÓRIO
COPSOQ II" (34 indicadores). Cada entrada traz:

- `numero`     — numeração do indicador no documento (None quando redigido aqui);
- `definicao`  — o parágrafo explicativo exibido abaixo do nome no relatório;
- `textos`     — o texto de status por faixa do semáforo (verde/amarelo/vermelho);
- `acao`       — "Prioridade de Ação Recomendada" (insumo da FASE 2, plano de ação);
- `impacto_negativo` / `impacto_positivo` — colunas de impacto do documento
  (também reservadas para a FASE 2).

As chaves são as mesmas de `structure.SUBDIMENSIONS`, então o relatório é montado
por consulta direta — sem LLM. A ordem de exibição vem de SUBDIMENSIONS, não deste
dicionário.

Cobertura: o documento descreve 34 indicadores e o instrumento implementado tem 35
subescalas. A subescala `stress` ("Estresse") não consta do documento e foi redigida
seguindo o mesmo padrão dos demais — está marcada com `"fonte": "redigido"`.
"""

# Rótulo exibido na linha STATUS do relatório, por faixa do semáforo.
STATUS_LABEL: dict[str, str] = {
    "verde": "FAVORÁVEL",
    "amarelo": "ATENÇÃO",
    "vermelho": "RISCO ALTO",
}

# Natureza do indicador, exibida abaixo do nome no painel gráfico.
DIRECAO_LABEL: dict[str, str] = {
    "risco": "demanda — maior é pior",
    "recurso": "recurso — maior é melhor",
}


KNOWLEDGE: dict[str, dict] = {
    # =====================================================================
    # ÁREA 1 — EXIGÊNCIAS LABORAIS
    # =====================================================================
    "exigencias_quantitativas": {
        "numero": 1,
        "definicao": (
            "Refere-se ao volume de trabalho versus tempo disponível. Avalia a presença de "
            "sobrecarga, horas extras e erros por pressa. A NR-1 exige uma carga sustentável "
            "para evitar o esgotamento."
        ),
        "textos": {
            "verde": (
                "Parabéns. O resultado indica equilíbrio na carga de trabalho. Este indicador "
                "demanda menor prioridade no seu plano de ação, sendo um ponto positivo da sua "
                "cultura de trabalho."
            ),
            "amarelo": (
                "Há percepção de desequilíbrio no volume de tarefas. A recomendação é dar atenção "
                "a este critério no plano de ação, pois ele está fora do padrão ideal exigido pela "
                "NR-1."
            ),
            "vermelho": (
                "Prioridade crítica! Dê total atenção a este ponto no plano de ação para evitar "
                "sobrecarga grave e riscos operacionais. Hoje ele é um ponto frágil da sua gestão e "
                "merece sua máxima atenção."
            ),
        },
        "acao": "Revisão de dimensionamento do quadro (headcount), redesenho de processos e prazos.",
        "impacto_negativo": "Sobrecarga, horas extras excessivas, erros operacionais por pressa, propensão ao Burnout.",
        "impacto_positivo": "Carga de trabalho equilibrada, ritmo sustentável, cumprimento de prazos sem desgaste.",
    },
    "ritmo_trabalho": {
        "numero": 2,
        "definicao": (
            "Avalia a velocidade e a pressão temporal contínua na execução das tarefas. Um ritmo "
            "acelerado gera fadiga e acidentes, enquanto a NR-1 pede cadência previsível e pausas."
        ),
        "textos": {
            "verde": (
                "Excelente resultado. Sua equipe trabalha em um ritmo saudável e sustentável. Este "
                "item não exige esforço imediato e demonstra um bom equilíbrio operacional."
            ),
            "amarelo": (
                "Identificamos pontos de aceleração excessiva na rotina. Vale dar atenção a este "
                "indicador no plano de ação para evitar que o cansaço acumulado vire um problema maior."
            ),
            "vermelho": (
                "Ponto de alerta urgente. A pressão por velocidade está no limite e pode gerar "
                "adoecimento ou falhas graves. Coloque este tema como prioridade máxima no seu plano "
                "de ação."
            ),
        },
        "acao": "Introdução de pausas ergonômicas e controle do fluxo contínuo de demandas.",
        "impacto_negativo": "Fadiga mental instantânea, perda de atenção, microacidentes de trabalho, estresse crônico.",
        "impacto_positivo": "Ritmo previsível, pausas regulamentares respeitadas, ausência de urgência contínua.",
    },
    "exigencias_cognitivas": {
        "numero": 3,
        "definicao": (
            "Mede a necessidade de concentração constante, decisões rápidas e alta complexidade "
            "mental. O objetivo na NR-1 é prevenir a exaustão por fadiga decisória."
        ),
        "textos": {
            "verde": (
                "Muito bom. A exigência mental exigida está alinhada com a capacidade da equipe. É um "
                "indicador de menor prioridade, mostrando maturidade nos processos."
            ),
            "amarelo": (
                "Há sinais de desgaste mental em alguns momentos. Recomendamos incluir este ponto com "
                "atenção moderada no plano de ação para alinhar expectativas e capacitação."
            ),
            "vermelho": (
                "Sua equipe está no limite da exaustão cognitiva. Trate este indicador como prioridade "
                "total no plano de ação, pois a sobrecarga mental afeta direto a tomada de decisão."
            ),
        },
        "acao": "Treinamento, automação de processos repetitivos e distribuição de tarefas complexas.",
        "impacto_negativo": "Sobrecarga cognitiva, exaustão mental ao final do dia, indecisão por fadiga (decision fatigue).",
        "impacto_positivo": "Tarefas compatíveis com a capacitação técnica, alta clareza de processamento.",
    },
    "exigencias_emocionais": {
        "numero": 4,
        "definicao": (
            "Avalia o desgaste provocado pelo contato com situações de tensão, conflitos ou "
            "atendimento ao público. Exige ambiente seguro para evitar esgotamento afetivo."
        ),
        "textos": {
            "verde": (
                "Parabéns pelo cuidado. A carga emocional das funções está bem gerida e sob controle, "
                "tornando este um ponto forte da sua cultura e de menor prioridade de ação."
            ),
            "amarelo": (
                "Notamos pequenos focos de desgaste emocional no dia a dia. É importante dar atenção a "
                "isso no plano de ação para proteger a saúde mental do time."
            ),
            "vermelho": (
                "Alerta vermelho para o bem-estar da equipe. O desgaste emocional está elevado e exige "
                "sua intervenção imediata no plano de ação para estancar o adoecimento."
            ),
        },
        "acao": "Suporte psicológico, treinamento de resiliência e rodízio de funções críticas.",
        "impacto_negativo": "Desgaste psicológico, esgotamento emocional, absenteísmo e apatia funcional.",
        "impacto_positivo": "Ambiente emocionalmente seguro, capacidade de distanciamento saudável do problema.",
    },
    "esconder_emocoes": {
        "numero": 5,
        "definicao": (
            "Avalia quando o colaborador precisa engolir frustrações ou simular comportamentos no "
            "ambiente profissional. A NR-1 busca promover relacionamentos autênticos e transparentes."
        ),
        "textos": {
            "verde": (
                "Ótimo indicador. Sua empresa cultiva um ambiente transparente onde as pessoas podem se "
                "expressar. É uma fortaleza do seu clima e de menor prioridade técnica."
            ),
            "amarelo": (
                "Existe uma percepção de que é preciso reprimir sentimentos para manter a harmonia. Vale "
                "dar atenção a isso no plano de ação para fortalecer a segurança psicológica."
            ),
            "vermelho": (
                "Ponto crítico na sua cultura. A obrigação de conter frustrações gera estresse somático "
                "silencioso. Coloque este item como prioridade no seu plano de ação."
            ),
        },
        "acao": "Canais abertos de escuta, cultura de feedback sem punição e apoio à liderança.",
        "impacto_negativo": "Dissonância emotiva, estresse somático, sentimento de falsidade e insatisfação profunda.",
        "impacto_positivo": "Liberdade de expressão profissional, ambiente transparente e psicologicamente seguro.",
    },

    # =====================================================================
    # ÁREA 2 — ORGANIZAÇÃO E CONTEÚDO DO TRABALHO
    # =====================================================================
    "influencia_trabalho": {
        "numero": 6,
        "definicao": (
            "Mede a margem de autonomia e poder de decisão sobre a própria rotina. Dar espaço de "
            "atuação é um dos principais fatores de proteção exigidos na NR-1."
        ),
        "textos": {
            "verde": (
                "Parabéns! Sua empresa concede boa autonomia e espaço para a equipe atuar. Mantenha essa "
                "prática; este indicador é uma fortaleza e de menor prioridade de ação."
            ),
            "amarelo": (
                "A equipe sente certa rigidez e falta de voz nas decisões. Recomendamos dar atenção no "
                "plano de ação para descentralizar a gestão e incentivar a autonomia."
            ),
            "vermelho": (
                "Alerta de microgestão. A falta de autonomia está sufocando as pessoas e gerando "
                "desmotivação. Coloque este ponto como prioridade urgente no plano de ação."
            ),
        },
        "acao": "Implementação de gestão por resultados e delegação progressiva de autonomia.",
        "impacto_negativo": "Sensação de microgestão, desmotivação, falta de iniciativa e passividade.",
        "impacto_positivo": "Alta autonomia, sentimento de dono, proatividade e capacidade de inovação.",
    },
    "possibilidades_desenvolvimento": {
        "numero": 7,
        "definicao": (
            "Avalia se as pessoas enxergam espaço para aprender e evoluir profissionalmente na função. "
            "O crescimento contínuo previne a estagnação e a perda de talentos."
        ),
        "textos": {
            "verde": (
                "Excelente. Seu time sente que está crescendo e aprendendo na empresa. Este indicador "
                "demanda menor prioridade no plano de ação, sendo um atrativo de retenção."
            ),
            "amarelo": (
                "Há uma sensação de limitação no aprendizado. Recomendamos dar atenção a isso no plano de "
                "ação para criar caminhos mais claros de capacitação e evolução."
            ),
            "vermelho": (
                "Ponto cego importante. A sensação de estagnação é alta e pode gerar rotatividade e "
                "desinteresse. Coloque este item como prioridade na sua pauta de ação."
            ),
        },
        "acao": "Criação de PDI (Plano de Desenvolvimento Individual) e trilhas de capacitação.",
        "impacto_negativo": "Estagnação, obsolescência profissional, alta rotatividade (turnover) de talentos.",
        "impacto_positivo": "Sensação de crescimento contínuo, retenção de talentos e engajamento elevado.",
    },
    "variacao_trabalho": {
        "numero": 8,
        "definicao": (
            "Mede a diversidade das tarefas para combater a rotina repetitiva. Tarefas muito monótonas "
            "aumentam o tédio e o risco de acidentes por desatenção."
        ),
        "textos": {
            "verde": (
                "Muito bom. A rotina é dinâmica e estimulante para o time. Este é um indicador positivo e "
                "de menor prioridade para o seu plano de ação imediato."
            ),
            "amarelo": (
                "Notamos que a repetitividade está gerando tédio em alguns setores. Vale dar atenção no "
                "plano de ação para diversificar as rotinas e reenergizar as entregas."
            ),
            "vermelho": (
                "Monotonia crítica. A falta de variação está desligando o foco dos colaboradores. Dê total "
                "atenção a este ponto no plano de ação para evitar falhas graves."
            ),
        },
        "acao": "Enriquecimento do cargo e job rotation entre equipes.",
        "impacto_negativo": "Monotonia, tédio operacional, falta de atenção gerando erros repetitivos.",
        "impacto_positivo": "Trabalho dinâmico, motivador e estimulante.",
    },
    "significado_trabalho": {
        "numero": 9,
        "definicao": (
            "Mede o quanto o colaborador entende o valor e o propósito do que faz. Compreender o impacto "
            "do próprio trabalho alimenta o engajamento e a saúde mental."
        ),
        "textos": {
            "verde": (
                "Parabéns! Sua equipe vê sentido e orgulho no que produz. Este indicador é um pilar da sua "
                "cultura e demanda menor prioridade técnica no plano de ação."
            ),
            "amarelo": (
                "Algumas pessoas parecem executar tarefas no \"piloto automático\", sem ver o impacto do que "
                "fazem. Dê atenção no plano de ação para resgatar esse propósito."
            ),
            "vermelho": (
                "Desconexão preocupante. O time não enxerga valor no trabalho realizado, gerando apatia. "
                "Trate este tema como prioridade máxima no seu plano de ação."
            ),
        },
        "acao": "Campanhas de comunicação interna reforçando o impacto direto do trabalho no cliente final.",
        "impacto_negativo": "Alienação do trabalho, execução \"no automático\", falta de comprometimento.",
        "impacto_positivo": "Orgulho do pertencimento, alinhamento de valores com a empresa e alto eNPS.",
    },
    "compromisso_local": {
        "numero": 10,
        "definicao": (
            "Avalia o sentimento de pertencimento, lealdade e orgulho de fazer parte da organização. É a "
            "métrica que mede a força da sua marca empregadora interna."
        ),
        "textos": {
            "verde": (
                "Excelente resultado. A vestir a camisa é uma realidade no seu time. Este indicador "
                "demonstra alta fidelidade e demanda menor prioridade no plano de ação."
            ),
            "amarelo": (
                "O sentimento de conexão com a empresa deu uma esfriada. A recomendação é dar atenção no "
                "plano de ação para reaproximar o colaborador da cultura do negócio."
            ),
            "vermelho": (
                "Desengajamento crítico. O vínculo com a empresa está rompido em níveis preocupantes. Dê "
                "total atenção a este ponto frágil na construção do seu plano de ação."
            ),
        },
        "acao": "Ações de fortalecimento de cultura, employer branding e melhoria do clima.",
        "impacto_negativo": "Baixa lealdade, imagem negativa da empresa, saída precoce de colaboradores.",
        "impacto_positivo": "Forte cultura organizacional, defensores da marca (brand advocates).",
    },

    # =====================================================================
    # ÁREA 3 — RELAÇÕES SOCIAIS E LIDERANÇA
    # =====================================================================
    "previsibilidade": {
        "numero": 11,
        "definicao": (
            "Mede a transparência na comunicação e a antecipação de mudanças operacionais. A "
            "previsibilidade reduz a ansiedade e evita a \"rádio corredor\"."
        ),
        "textos": {
            "verde": (
                "Parabéns! Sua comunicação interna é transparente e gera segurança. Este indicador é uma "
                "fortaleza e exige menor prioridade no seu plano de ação."
            ),
            "amarelo": (
                "A falta de avisos prévios sobre mudanças está gerando incertezas pontuais. Recomendamos "
                "dar atenção no plano de ação para alinhar melhor os fluxos de informação."
            ),
            "vermelho": (
                "Ponto cego de gestão. A falta de transparência e planejamento na mudança está gerando "
                "ansiedade e boatos. Dê total atenção a este ponto prioritário no seu plano de ação."
            ),
        },
        "acao": "Comunicação transparente e cadência estruturada de alinhamentos estratégicos.",
        "impacto_negativo": "Ansiedade generalizada, rumores/fofocas (rádio corredor), resistência a mudanças.",
        "impacto_positivo": "Sensação de segurança, adaptação rápida a cenários e confiança na gestão.",
    },
    "clareza_papel": {
        "numero": 12,
        "definicao": (
            "Avalia se cada pessoa sabe exatamente o que se espera dela, suas metas e responsabilidades. "
            "A clareza evita o retrabalho e o estresse por cobranças indevidas."
        ),
        "textos": {
            "verde": (
                "Muito bom. Todo mundo sabe exatamente o seu papel e onde quer chegar. Este item demonstra "
                "excelente organização e demanda menor prioridade no plano de ação."
            ),
            "amarelo": (
                "Notamos dúvidas e sobreposição de tarefas em algumas áreas. Vale dar atenção a este ponto "
                "no plano de ação para delimitar melhor as responsabilidades."
            ),
            "vermelho": (
                "Confusão operacional. A falta de clareza gera cobranças desalinhadas e frustração, e os "
                "colaboradores podem não saber o que se espera deles. Trate este ponto como prioridade "
                "urgente na tratativa do plano de ação."
            ),
        },
        "acao": "Mapeamento e atualização de descrições de cargo (JDs) e matrizes RACI.",
        "impacto_negativo": "Retrabalho, sobreposição de tarefas, desperdício de tempo e ineficiência.",
        "impacto_positivo": "Alta produtividade, alinhamento de expectativas e autonomia assertiva.",
    },
    "recompensas_reconhecimento": {
        "numero": 13,
        "definicao": (
            "Avalia a percepção de valorização moral, financeira e profissional pelo esforço dedicado. O "
            "reconhecimento é um pilar vital de motivação e retenção."
        ),
        "textos": {
            "verde": (
                "Parabéns! A equipe se sente genuinamente valorizada pelo trabalho que entrega. É uma "
                "grande qualidade da sua liderança e demanda menor prioridade de ação."
            ),
            "amarelo": (
                "Existe uma sensação de que o esforço individual nem sempre é notado. Recomendamos dar "
                "atenção a isso no plano de ação para fortalecer o reconhecimento diário."
            ),
            "vermelho": (
                "Sentimento agudo de injustiça e invisibilidade. A falta de valorização está minando o "
                "clima. Dê total atenção a este ponto como prioridade no plano de ação."
            ),
        },
        "acao": "Programas formais de reconhecimento, elogios públicos e meritocracia clara.",
        "impacto_negativo": "Sentimento de injustiça, desengajamento, baixo esforço discricionário.",
        "impacto_positivo": "Motivação elevada, empenho contínuo e sentimento de justiça.",
    },
    "conflitos_papel": {
        "numero": 14,
        "definicao": (
            "Avalia a presença de ordens contraditórias ou orientações divergentes de diferentes "
            "gestores, o que gera paralisia e estresse no colaborador."
        ),
        "textos": {
            "verde": (
                "Ótimo trabalho. O alinhamento entre a gestão é claro e as orientações não se cruzam. Este "
                "indicador é favorável e demanda menor prioridade de intervenção."
            ),
            "amarelo": (
                "Ocorrem episódios de ordens conflitantes em alguns setores. A recomendação é dar atenção "
                "no plano de ação para alinhar as vozes de comando da liderança."
            ),
            "vermelho": (
                "Sinal de fumaça na governança. As pessoas recebem ordens opostas e não sabem a quem "
                "atender. Coloque este item como prioridade absoluta no plano de ação."
            ),
        },
        "acao": "Alinhamento de governança entre lideranças e unificação de comando técnico.",
        "impacto_negativo": "Estresse de mediação, paralisia operacional, frustração por metas antagônicas.",
        "impacto_positivo": "Alinhamento entre gestores, direcionamento único e prioridades claras.",
    },
    "apoio_colegas": {
        "numero": 15,
        "definicao": (
            "Mede o espírito de equipe, a empatia e a ajuda mútua entre os pares no dia a dia. A "
            "cooperação horizontal é um forte escudo contra o estresse."
        ),
        "textos": {
            "verde": (
                "Parabéns. Sua equipe é unida e se apoia nos momentos de aperto. Este clima colaborativo é "
                "uma fortaleza e exige menor prioridade no seu plano de ação."
            ),
            "amarelo": (
                "Identificamos posturas mais individualistas em certas áreas. Vale a pena dar atenção no "
                "plano de ação para cultivar dinâmicas de maior cooperação entre pares."
            ),
            "vermelho": (
                "Clima de ilhas e rivalidade. A falta de ajuda mútua está isolando as pessoas e criando "
                "silos. Dê total atenção a este ponto frágil na construção do seu plano de ação."
            ),
        },
        "acao": "Atividades de integração (team building) e dinâmicas de colaboração.",
        "impacto_negativo": "Isolamento, clima competitivo nocivo, baixo espírito de equipe.",
        "impacto_positivo": "Forte sinergia, colaboração em momentos de crise, bom clima interno.",
    },
    "apoio_superiores": {
        "numero": 16,
        "definicao": (
            "Mede a postura da liderança direta em estar disponível para orientar, ouvir e ajudar a "
            "resolver problemas operacionais e humanos da equipe."
        ),
        "textos": {
            "verde": (
                "Excelente. A liderança é presente e parceira do time no dia a dia. Este indicador mostra "
                "segurança psicológica e demanda menor prioridade no plano de ação."
            ),
            "amarelo": (
                "A equipe sente a liderança um pouco distante na hora de resolver abacaxis. Dê atenção a "
                "este critério no plano de ação para capacitar seus líderes."
            ),
            "vermelho": (
                "Sensação de desamparo. A liderança é vista como ausente ou inacessível em momentos "
                "críticos. Trate este tema como prioridade máxima no plano de ação."
            ),
        },
        "acao": "Capacitação de líderes em comunicação empática e liderança humanizada.",
        "impacto_negativo": "Sensação de desamparo, medo da liderança, isolamento técnico.",
        "impacto_positivo": "Liderança servidora, alta resolução de problemas operacionais e segurança.",
    },
    "comunidade_social": {
        "numero": 17,
        "definicao": (
            "Avalia o clima comunitário, o respeito mútuo e a qualidade das relações humanas dentro do "
            "ambiente corporativo de forma geral."
        ),
        "textos": {
            "verde": (
                "Muito bom! O ambiente é leve, amigável e acolhedor. Este clima saudável protege a saúde "
                "mental e demanda menor prioridade técnica no plano de ação."
            ),
            "amarelo": (
                "O clima interpessoal está frio ou pontuado por pequenos atritos. A recomendação é dar "
                "atenção no plano de ação para reforçar a convivência respeitosa."
            ),
            "vermelho": (
                "Ambiência hostil e pesada. A convivência social está desgastada e gerando mal-estar "
                "contínuo. Coloque este ponto como prioridade urgente no plano de ação."
            ),
        },
        "acao": "Promoção de espaços de convivência e celebração de conquistas coletivas.",
        "impacto_negativo": "Relações estritamente transacionais, frieza, falta de cumplicidade profissional.",
        "impacto_positivo": "Ambiente agradável, baixas taxas de conflito interpessoal, alto companheirismo.",
    },
    "qualidade_lideranca": {
        "numero": 18,
        "definicao": (
            "Mede a capacidade dos gestores de planejar o trabalho, mediar conflitos, dar feedback e "
            "conduzir a equipe com firmeza e empatia."
        ),
        "textos": {
            "verde": (
                "Parabéns! Sua liderança demonstra maturidade e ótima capacidade de gestão. É um motor de "
                "engajamento e exige menor prioridade de correção no plano de ação."
            ),
            "amarelo": (
                "Notamos falhas pontuais de gestão que geram ruídos na rotina. Vale dar atenção no plano "
                "de ação para lapidar as competências da liderança."
            ),
            "vermelho": (
                "Fragilidade na gestão. Lideranças despreparadas estão prejudicando a operação e o clima. "
                "Dê total atenção a este ponto prioritário no seu plano de ação."
            ),
        },
        "acao": "Desenvolvimento contínuo do pipeline de liderança e mentoria executiva.",
        "impacto_negativo": "Liderança tóxica ou omissa, decisões erráticas, perda de autoridade.",
        "impacto_positivo": "Liderança inspiradora, equipes de alta performance, clareza na execução.",
    },

    # =====================================================================
    # ÁREA 4 — INTERFACE TRABALHO–INDIVÍDUO
    # =====================================================================
    "satisfacao_trabalho": {
        "numero": 19,
        "definicao": (
            "Avalia o contentamento geral do colaborador com o conjunto do seu emprego: rotina, "
            "condições, ambiente e tratamento recebido."
        ),
        "textos": {
            "verde": (
                "Ótimo resultado! A equipe se declara feliz e satisfeita com o ambiente de trabalho. É um "
                "ponto forte que demanda menor prioridade de ação."
            ),
            "amarelo": (
                "Existe um descontentamento silencioso que precisa ser ouvido. Recomendamos dar atenção a "
                "este item no plano de ação para evitar que a insatisfação cresça."
            ),
            "vermelho": (
                "Alerta de descontentamento generalizado. A insatisfação está alta e coloca em risco a "
                "produtividade e a permanência do time. Trate como prioridade no plano de ação."
            ),
        },
        "acao": "Pesquisas qualitativas complementares para sanar pontos de insatisfação.",
        "impacto_negativo": "Absenteísmo, turnover iminente, postura passiva-agressiva.",
        "impacto_positivo": "Alta dedicação, recomendação da empresa como bom lugar para trabalhar.",
    },
    "inseguranca_laboral": {
        "numero": 20,
        "definicao": (
            "Mede o medo constante de demissão, perda do cargo ou reestruturações desfavoráveis. A "
            "insegurança crônica destrói o foco e a inovação."
        ),
        "textos": {
            "verde": (
                "Parabéns. O time se sente seguro e confiante no seu espaço dentro da empresa. É um pilar "
                "de estabilidade emocional e de menor prioridade de ação."
            ),
            "amarelo": (
                "Há receios pontuais sobre o futuro das funções ou estabilidade no setor. Vale dar atenção "
                "a isso no plano de ação para reforçar a comunicação de futuro."
            ),
            "vermelho": (
                "Clima de apreensão constante. A equipe trabalha com medo da demissão, paralisando a "
                "inovação. Coloque este ponto como prioridade urgente no plano de ação."
            ),
        },
        "acao": "Comunicação transparente sobre a saúde do negócio e planos de carreira.",
        "impacto_negativo": "Ansiedade contínua, ocultação de erros, perda de foco nas entregas.",
        "impacto_positivo": "Estabilidade percebida, foco em inovação e aprendizado sem medo de falhar.",
    },
    "conflito_trabalho_familia": {
        "numero": 21,
        "definicao": (
            "Avalia o quanto a rotina profissional invade a vida pessoal e familiar do colaborador "
            "(mensagens fora do horário, horas extras, preocupações levadas para casa)."
        ),
        "textos": {
            "verde": (
                "Excelente equilíbrio. As pessoas conseguem desligar do trabalho e aproveitar a vida "
                "pessoal. É um indicador de menor prioridade e alta saúde cultural."
            ),
            "amarelo": (
                "As demandas profissionais estão começando a invadir o tempo de descanso do time. "
                "Recomendamos dar atenção no plano de ação para estabelecer limites claros."
            ),
            "vermelho": (
                "Invasão grave do trabalho na vida familiar. A sobrecarga está afetando o lar das pessoas. "
                "Dê total atenção a este indicador crítico no seu plano de ação."
            ),
        },
        "acao": "Políticas de desconexão do trabalho (sem mensagens fora do expediente), flexibilidade.",
        "impacto_negativo": "Exaustão, sobrecarga de papéis, conflitos familiares, desgaste psicológico.",
        "impacto_positivo": "Equilíbrio saudável, separação clara entre vida profissional e pessoal.",
    },
    "conflito_familia_trabalho": {
        "numero": 22,
        "definicao": (
            "Mede o quanto problemas e pressões do âmbito familiar impactam a concentração e o desempenho "
            "no ambiente de trabalho."
        ),
        "textos": {
            "verde": (
                "Muito bom. As pessoas conseguem gerenciar seus desafios pessoais sem comprometer a "
                "jornada. Indicador de menor prioridade no seu plano de ação."
            ),
            "amarelo": (
                "Questões pessoais estão afetando o foco de alguns colaboradores. Vale dar atenção no "
                "plano de ação para oferecer suporte ou flexibilidade pontual."
            ),
            "vermelho": (
                "Alto impacto de problemas pessoais na rotina de trabalho. É hora de agir com empatia: "
                "coloque este item como prioridade e avalie programas de apoio ao colaborador."
            ),
        },
        "acao": "Programas de assistência ao colaborador (EAP — suporte psicológico, jurídico e financeiro).",
        "impacto_negativo": "Queda de produtividade, falta de concentração, atrasos frequentes.",
        "impacto_positivo": "Tranquilidade pessoal permitindo foco total nas entregas durante a jornada.",
    },

    # =====================================================================
    # ÁREA 5 — VALORES NO LOCAL DE TRABALHO
    # =====================================================================
    "confianca_horizontal": {
        "numero": 23,
        "definicao": (
            "Mede o grau de certeza de que os pares são honestos, éticos e comprometidos uns com os "
            "outros na realização das entregas."
        ),
        "textos": {
            "verde": (
                "Parabéns! A relação entre colegas é pautada pela confiança e respeito técnico. Este é um "
                "atrativo cultural forte e de menor prioridade de ação."
            ),
            "amarelo": (
                "Existe certa desconfiança sobre o empenho de alguns colegas. A recomendação é dar atenção "
                "no plano de ação para alinhar as entregas entre os times."
            ),
            "vermelho": (
                "Ruptura de confiança entre pares. O clima de desconfiança atrasa processos e gera "
                "atritos. Trate este ponto como prioridade máxima no seu plano de ação."
            ),
        },
        "acao": "Dinâmicas de alinhamento de expectativas e cooperação interdisciplinar.",
        "impacto_negativo": "Desconfiança, checagem dupla de trabalho, atritos velados.",
        "impacto_positivo": "Agilidade no fluxo de trabalho, delegação segura entre pares.",
    },
    "confianca_vertical": {
        "numero": 24,
        "definicao": (
            "Avalia a credibilidade que a diretoria e a liderança executiva possuem perante a equipe "
            "quanto à palavra, promessas e decisões tomadas."
        ),
        "textos": {
            "verde": (
                "Excelente! A liderança transmite firmeza, ética e cumpre o que promete. Essa relação de "
                "confiança é exemplar e demanda menor prioridade de ação."
            ),
            "amarelo": (
                "O time começa a questionar algumas decisões da alta gestão. Vale dar atenção no plano de "
                "ação para aproximar a diretoria da base e esclarecer rumos."
            ),
            "vermelho": (
                "Crise severa de credibilidade na gestão. Quando a equipe deixa de confiar na direção, o "
                "engajamento desmorona. Dê total atenção a isso no plano de ação."
            ),
        },
        "acao": "Práticas de governança transparente, cumprimento de promessas da gestão.",
        "impacto_negativo": "Ceticismo quanto a anúncios da empresa, desmotivação e ceticismo institucional.",
        "impacto_positivo": "Alinhamento total aos direcionamentos estratégicos, alta lealdade.",
    },
    "justica_respeito": {
        "numero": 25,
        "definicao": (
            "Mede a percepção de imparcialidade na distribuição de tarefas, reconhecimento, meritocracia "
            "e ausência de favoritos dentro da organização."
        ),
        "textos": {
            "verde": (
                "Parabéns! As pessoas sentem que a empresa é justa e trata todos com igualdade. É uma "
                "grande virtude ética e de menor prioridade para correções."
            ),
            "amarelo": (
                "Há percepção de privilégios ou critérios não muito claros em promoções e tarefas. Dê "
                "atenção no plano de ação para deixar as regras mais transparentes."
            ),
            "vermelho": (
                "Sentimento generalizado de injustiça. A sensação de favoritismo destrói o clima "
                "organizacional. Coloque este item como prioridade na sua pauta de ação."
            ),
        },
        "acao": "Padronização de critérios de promoção, avaliação de desempenho transparente.",
        "impacto_negativo": "Sensação de favoritismo, injustiça, ressentimento organizacional.",
        "impacto_positivo": "Meritocracia percebida, tratamento equânime para todos.",
    },
    "inclusao_social": {
        "numero": 26,
        "definicao": (
            "Avalia o respeito às diferenças de gênero, raça e diversidade, bem como o compromisso ético "
            "e social da empresa com seus colaboradores e a comunidade."
        ),
        "textos": {
            "verde": (
                "Muito bom! Sua cultura valoriza a diversidade e atua com forte responsabilidade social. "
                "Este indicador demanda menor prioridade, sendo motivo de orgulho."
            ),
            "amarelo": (
                "Suas práticas inclusivas ainda estão tímidas ou pouco divulgadas. Recomendamos dar "
                "atenção no plano de ação para amadurecer a pauta de diversidade."
            ),
            "vermelho": (
                "Percepção de um ambiente excludente ou desalinhado com a ética moderna. Trate este "
                "indicador com prioridade no plano de ação para proteger o clima e a marca."
            ),
        },
        "acao": "Comitê de Diversidade e treinamentos de vieses inconscientes.",
        "impacto_negativo": "Alienação de minorias, risco de imagem/ESG, clima discriminatório.",
        "impacto_positivo": "Diversidade de ideias, forte atração de talentos modernos, orgulho ético.",
    },

    # =====================================================================
    # ÁREA 6 — SAÚDE E BEM-ESTAR
    # =====================================================================
    "saude_geral": {
        "numero": 27,
        "definicao": (
            "Mede a percepção direta do trabalhador sobre a sua própria vitalidade, saúde física e "
            "mental. É o indicador termômetro do seu time."
        ),
        "textos": {
            "verde": (
                "Parabéns! Sua equipe relata boa saúde e disposição no dia a dia. Este é um resultado "
                "excelente e demanda menor prioridade imediata no plano de ação."
            ),
            "amarelo": (
                "O time apresenta sinais de cansaço e queda de energia vital. A recomendação é dar atenção "
                "a este item no plano de ação com medidas preventivas de saúde."
            ),
            "vermelho": (
                "Sinal de alerta na saúde coletiva! A equipe se sente debilitada e sem energia. Coloque a "
                "preservação da saúde como prioridade urgente no plano de ação."
            ),
        },
        "acao": "Campanhas de medicina preventiva e estilo de vida saudável.",
        "impacto_negativo": "Risco iminente de afastamento médico (INSS), baixo rendimento vital.",
        "impacto_positivo": "Alta vitalidade, disposição física, engajamento e disposição funcional.",
    },
    "problemas_sono": {
        "numero": 28,
        "definicao": (
            "Avalia a ocorrência de insônia ou dificuldades para desligar a mente do trabalho à noite. O "
            "sono ruim prejudica a atenção, a saúde e a segurança."
        ),
        "textos": {
            "verde": (
                "Excelente. O time consegue descansar bem à noite e recuperar as energias. Este indicador "
                "favorável exige menor prioridade técnica no plano de ação."
            ),
            "amarelo": (
                "Relatos de insônia por preocupação com o trabalho começaram a surgir. Dê atenção a este "
                "ponto no plano de ação antes que afete a produtividade."
            ),
            "vermelho": (
                "Risco elevado de noites mal dormidas por conta do estresse do trabalho. Isso antecede "
                "acidentes e demissões. Trate como prioridade máxima no plano de ação."
            ),
        },
        "acao": "Ações de higiene do sono, limitação de contatos corporativos noturnos.",
        "impacto_negativo": "Déficit de atenção, irritabilidade, riscos de acidentes graves no trabalho.",
        "impacto_positivo": "Recuperação energética adequada, lucidez na tomada de decisão.",
    },
    "burnout": {
        "numero": 29,
        "definicao": (
            "Mede o nível de exaustão física, mental e cinismo funcional resultantes do estresse crônico "
            "acumulado. Um dos pontos mais fiscalizados pela NR-1."
        ),
        "textos": {
            "verde": (
                "Parabéns! Sua empresa mantém os índices de esgotamento sob controle. Mantenha essa "
                "vigilância; este indicador é de menor prioridade de intervenção."
            ),
            "amarelo": (
                "Há colaboradores apresentando sinais claros de fadiga crônica. Recomendamos dar atenção "
                "imediata no plano de ação para redistribuir cargas e acolher o time."
            ),
            "vermelho": (
                "PARE TUDO AGORA! Níveis críticos de esgotamento detectados. O risco de colapso de saúde é "
                "iminente. Este ponto deve ser a PRIORIDADE ABSOLUTA do seu plano de ação."
            ),
        },
        "acao": "Intervenção urgente: redesenho imediato de carga/ritmo e acolhimento clínico.",
        "impacto_negativo": "Colapso mental, afastamentos longos, contágio do clima negativo na equipe.",
        "impacto_positivo": "Energia preservada, entusiasmo e resiliência saudável.",
    },
    # A subescala "Estresse" existe no instrumento (itens 91-94) mas NÃO consta do
    # documento da base de conhecimento (que cobre 34 indicadores). Definição e textos
    # abaixo foram redigidos seguindo o mesmo padrão dos demais.
    "stress": {
        "numero": None,
        "fonte": "redigido",
        "definicao": (
            "Mede o nível de tensão, irritabilidade e nervosismo percebido no dia a dia de trabalho. É o "
            "estágio que antecede os sintomas físicos e o esgotamento, e por isso funciona como alerta "
            "precoce exigido pela NR-1."
        ),
        "textos": {
            "verde": (
                "Parabéns! O nível de tensão da equipe está sob controle e dentro do saudável. Este "
                "indicador é de menor prioridade e mostra um ambiente equilibrado."
            ),
            "amarelo": (
                "Há sinais de tensão e irritabilidade acumuladas na rotina. Recomendamos dar atenção a "
                "este item no plano de ação antes que evolua para sintomas físicos ou esgotamento."
            ),
            "vermelho": (
                "Nível crítico de estresse percebido. A tensão constante já compromete o bem-estar e o "
                "desempenho do time. Trate este ponto como prioridade máxima no plano de ação."
            ),
        },
        "acao": "Redução de fatores de pressão na fonte, pausas estruturadas e canal de apoio psicológico.",
        "impacto_negativo": "Irritabilidade, conflitos interpessoais, evolução para sintomas somáticos e burnout.",
        "impacto_positivo": "Serenidade na rotina, boa tolerância à pressão e clima interpessoal estável.",
    },
    "sintomas_depressivos": {
        "numero": 30,
        "definicao": (
            "Avalia o surgimento de tristeza persistente, apatia e desânimo ligados à rotina e às "
            "condições vividas no ambiente corporativo."
        ),
        "textos": {
            "verde": (
                "Muito bom. A equipe demonstra ânimo, disposição e visão positiva do ambiente. Este "
                "indicador demanda menor prioridade de atenção no plano de ação."
            ),
            "amarelo": (
                "Notamos sinais de desânimo e apatia em algumas pessoas. Vale a pena dar atenção no plano "
                "de ação para oferecer escuta e acolhimento preventivo."
            ),
            "vermelho": (
                "Alerta de saúde mental. A apatia e o desânimo estão afetando a vida das pessoas. Dê total "
                "atenção a este ponto prioritário na construção do seu plano de ação."
            ),
        },
        "acao": "Encaminhamento para assistência psicológica e adequação de rotina.",
        "impacto_negativo": "Desconexão, queda drástica na produtividade, isolamento social.",
        "impacto_positivo": "Disposição, ânimo, visão otimista do futuro e engajamento.",
    },
    "stress_somatico": {
        "numero": 31,
        "definicao": (
            "Mede o surgimento de dores físicas, tensão muscular ou desconfortos gástricos causados pelo "
            "nível de tensão no trabalho."
        ),
        "textos": {
            "verde": (
                "Parabéns! Sua equipe não relata dores ou sintomas físicos associados ao trabalho. Este é "
                "um resultado saudável e de menor prioridade de ação."
            ),
            "amarelo": (
                "O estresse começou a \"falar\" através do corpo (dores de cabeça, tensões). Recomendamos "
                "dar atenção a isso no plano de ação para evitar afastamentos."
            ),
            "vermelho": (
                "O corpo do seu time está pedindo socorro. Altas queixas físicas ligadas ao estresse. "
                "Coloque a ergonomia e a pausa como prioridades urgentes no plano de ação."
            ),
        },
        "acao": "Ações conjugadas de ergonomia, pausas e programas de redução de ansiedade.",
        "impacto_negativo": "Consultas médicas frequentes, absenteísmo presencial ou presenteísmo.",
        "impacto_positivo": "Ausência de dores fisiológicas associadas ao trabalho.",
    },
    "stress_cognitivo": {
        "numero": 32,
        "definicao": (
            "Avalia lapsos de memória, falhas de concentração e raciocínio lento resultantes da "
            "sobrecarga mental contínua na função."
        ),
        "textos": {
            "verde": (
                "Excelente! O foco, a memória e o raciocínio da equipe estão afiados. Este item favorável "
                "demanda menor prioridade no plano de ação."
            ),
            "amarelo": (
                "Identificamos lapsos de atenção e esquecimentos por conta da correria. Dê atenção a este "
                "critério no plano de ação para reduzir o multitasking."
            ),
            "vermelho": (
                "Exaustão mental afetando a memória e o foco. A probabilidade de erros graves e acidentes "
                "é alta. Trate este tema como prioridade total no plano de ação."
            ),
        },
        "acao": "Redução da fragmentação do trabalho (multitasking), foco em prioridades.",
        "impacto_negativo": "Erros em tarefas simples, esquecimentos operacionais, lentidão.",
        "impacto_positivo": "Clareza mental, rapidez no raciocínio e alta precisão funcional.",
    },

    # =====================================================================
    # ÁREA 7 — PERSONALIDADE / AUTOEFICÁCIA
    # =====================================================================
    "autoeficacia": {
        "numero": 33,
        "definicao": (
            "Mede o quanto o colaborador acredita na sua própria capacidade de superar desafios, "
            "resolver problemas complexos e entregar bons resultados."
        ),
        "textos": {
            "verde": (
                "Parabéns! Seu time é confiante, proativo e seguro de sua competência técnica. Este "
                "indicador é uma fortaleza e de menor prioridade técnica de ação."
            ),
            "amarelo": (
                "Há uma sensação temporária de insegurança técnica em alguns desafios. Recomendamos dar "
                "atenção no plano de ação reforçando treinamentos e feedbacks."
            ),
            "vermelho": (
                "Baixa crença na própria capacidade. A equipe se sente incapaz de responder às demandas, "
                "gerando paralisia. Dê total atenção a este ponto no seu plano de ação."
            ),
        },
        "acao": "Treinamentos práticos de capacitação e feedbacks construtivos frequentes.",
        "impacto_negativo": "Sentimento de incapacidade, dependência excessiva de validação, paralisia.",
        "impacto_positivo": "Altíssimo poder de realização, resiliência perante erros, proatividade.",
    },

    # =====================================================================
    # ÁREA 8 — COMPORTAMENTOS OFENSIVOS
    # =====================================================================
    "comportamentos_ofensivos": {
        "numero": 34,
        "definicao": (
            "Avalia o relato de agressões verbais, assédio moral/sexual, discriminação ou atitudes "
            "intimidadoras no ambiente de trabalho."
        ),
        "textos": {
            "verde": (
                "Parabéns! Seu ambiente é seguro, respeitoso e livre de condutas ofensivas. Mantenha essa "
                "postura ética; este item é de menor prioridade de correção."
            ),
            "amarelo": (
                "Ocorreram episódios pontuais de conduta inadequada que exigem postura firme. "
                "Recomendamos dar atenção no plano de ação e reforçar o código de ética."
            ),
            "vermelho": (
                "TOLERÂNCIA ZERO! Relatos graves de comportamentos ofensivos ou assédio. Este é um índice "
                "que tem que estar no topo das medidas corretivas. Trate este ponto como emergência no "
                "seu plano de ação, acionando medidas corretivas imediatas."
            ),
        },
        "acao": "Ação imediata: acionamento do canal de denúncias, investigação e sanções.",
        "impacto_negativo": "CRÍTICO: risco trabalhista grave, destruição imediata do clima, adoecimento em massa.",
        "impacto_positivo": "Ambiente ético, seguro, pautado pelo respeito e conformidade legal.",
    },
}


def get(key: str) -> dict:
    """Entrada da base de conhecimento para uma subescala (dict vazio se ausente)."""
    return KNOWLEDGE.get(key, {})


def texto_status(key: str, nivel: str | None) -> str:
    """Texto de devolutiva do indicador na faixa informada."""
    if not nivel:
        return ""
    return (KNOWLEDGE.get(key, {}).get("textos") or {}).get(nivel, "")
