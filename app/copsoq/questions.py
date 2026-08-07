"""Os 119 itens do COPSOQ II adaptados para o português brasileiro.

`QUESTIONS` é a versão longa (119 itens); `QUESTIONS_CURTA` é a versão curta
(41 itens), um recorte da mesma lista — ver `structure.SHORT_ORDER`.

Cada item tem: id ("q1".."q119"), n (número no PDF), prompt, scale (escala de
resposta) e secao (linha de contexto exibida acima do enunciado, quando houver).
As opções (valor "1".."5" + rótulo) são derivadas da escala.
"""

from .structure import SCALES, SHORT_ORDER


def _options(scale_key: str) -> list[dict]:
    scale = SCALES[scale_key]
    opts = [{"value": str(i + 1), "label": label} for i, label in enumerate(scale["labels"])]
    if scale.get("display_desc"):
        opts = list(reversed(opts))
    return opts


# (n, prompt, scale, secao)
_RAW: list[tuple[int, str, str, str]] = [
    (1, "Sua carga de trabalho se acumula por ser mal distribuída?", "freq", ""),
    (2, "Com que frequência você fica sem tempo para concluir todas as suas tarefas?", "freq", ""),
    (3, "Você precisa fazer horas extras?", "freq", ""),
    (4, "Você precisa trabalhar muito rápido?", "freq", ""),
    (5, "Seu trabalho exige atenção constante?", "freq", ""),
    (6, "Seu trabalho exige que você seja bom(boa) em propor novas ideias?", "freq", ""),
    (7, "Seu trabalho exige que você tome decisões difíceis?", "freq", ""),
    (8, "Seu trabalho o(a) coloca em situações emocionalmente perturbadoras?", "freq", ""),
    (9, "Seu trabalho exige muito de você emocionalmente?", "freq", ""),
    (10, "Você se sente emocionalmente envolvido(a) com o seu trabalho?", "freq", ""),
    (11, "Seu trabalho exige que você não manifeste a sua opinião?", "freq", ""),
    (12, "Seu trabalho exige que você esconda os seus sentimentos?", "freq", ""),
    (13, "Você precisa tratar todas as pessoas de forma igual, mesmo quando não concorda com isso?", "freq", ""),
    (14, "Você precisa ser simpático(a) com todos, mesmo sentindo que isso não é retribuído?", "freq", ""),
    (15, "Você tem grande influência sobre o seu trabalho?", "freq", ""),
    (16, "Você participa da escolha das pessoas com quem trabalha?", "freq", ""),
    (17, "Você pode influenciar a quantidade de trabalho que lhe é atribuída?", "freq", ""),
    (18, "Você tem alguma influência sobre o tipo de tarefas que realiza?", "freq", ""),
    (19, "Seu trabalho exige que você tenha iniciativa?", "freq", ""),
    (20, "Seu trabalho permite que você aprenda coisas novas?", "freq", ""),
    (21, "Seu trabalho permite que você use as suas habilidades ou competências?", "freq", ""),
    (22, "Seu trabalho é variado?", "freq", ""),
    (23, "Você é informado(a) com antecedência sobre decisões importantes, mudanças ou planos para o futuro?", "freq", ""),
    (24, "Você recebe todas as informações de que precisa para fazer bem o seu trabalho?", "freq", ""),
    (25, "Seu trabalho tem objetivos claros?", "freq", ""),
    (26, "Você sabe exatamente quais são as suas responsabilidades?", "freq", ""),
    (27, "Você sabe exatamente o que esperam de você?", "freq", ""),
    (28, "Seu trabalho é reconhecido e valorizado pela direção?", "freq", ""),
    (29, "Existem boas perspectivas no seu emprego?", "freq", ""),
    (30, "A direção do seu local de trabalho o(a) respeita?", "freq", ""),
    (31, "Você é tratado(a) de forma justa no seu local de trabalho?", "freq", ""),
    (32, "Você faz coisas no trabalho que uns aprovam e outros não?", "freq", ""),
    (33, "No seu trabalho, são feitas exigências contraditórias a você?", "freq", ""),
    (34, "Às vezes você precisa fazer coisas que deveriam ser feitas de outra maneira?", "freq", ""),
    (35, "Às vezes você precisa fazer coisas que considera desnecessárias?", "freq", ""),
    (36, "Com que frequência você tem ajuda e apoio dos seus colegas de trabalho?", "freq", ""),
    (37, "Com que frequência os seus colegas se dispõem a ouvir os seus problemas de trabalho?", "freq", ""),
    (38, "Com que frequência os seus colegas conversam com você sobre o seu desempenho?", "freq", ""),
    (39, "Com que frequência o seu superior imediato conversa com você sobre como o seu trabalho está indo?", "freq", ""),
    (40, "Com que frequência você tem ajuda e apoio do seu superior imediato?", "freq", ""),
    (41, "Com que frequência o seu superior imediato conversa com você sobre o seu desempenho?", "freq", ""),
    (42, "Existe um bom ambiente entre você e os seus colegas?", "freq", ""),
    (43, "Existe boa cooperação entre os colegas de trabalho?", "freq", ""),
    (44, "No seu local de trabalho, você se sente parte de uma equipe?", "freq", ""),
    (45, "Oferece boas oportunidades de desenvolvimento às pessoas e à equipe?", "freq", "Sobre a sua liderança direta:"),
    (46, "Dá prioridade à satisfação no trabalho?", "freq", "Sobre a sua liderança direta:"),
    (47, "É boa no planejamento do trabalho?", "freq", "Sobre a sua liderança direta:"),
    (48, "É boa na resolução de conflitos?", "freq", "Sobre a sua liderança direta:"),
    (49, "Os funcionários escondem informações uns dos outros?", "freq", "Sobre o seu local de trabalho como um todo:"),
    (50, "Os funcionários escondem informações da direção?", "freq", "Sobre o seu local de trabalho como um todo:"),
    (51, "Os funcionários confiam uns nos outros, de modo geral?", "freq", "Sobre o seu local de trabalho como um todo:"),
    (52, "A direção confia que os funcionários fazem um bom trabalho?", "freq", "Sobre o seu local de trabalho como um todo:"),
    (53, "Você confia nas informações que recebe da direção?", "freq", "Sobre o seu local de trabalho como um todo:"),
    (54, "A direção esconde informações dos funcionários?", "freq", "Sobre o seu local de trabalho como um todo:"),
    (55, "Os conflitos são resolvidos de forma justa?", "freq", "Sobre o seu local de trabalho como um todo:"),
    (56, "Os funcionários são valorizados quando fazem um bom trabalho?", "freq", "Sobre o seu local de trabalho como um todo:"),
    (57, "As sugestões dos funcionários são levadas a sério pela direção?", "freq", "Sobre o seu local de trabalho como um todo:"),
    (58, "O trabalho é distribuído de forma igual entre os funcionários?", "freq", "Sobre o seu local de trabalho como um todo:"),
    (59, "Homens e mulheres são tratados da mesma forma?", "freq", "Sobre o seu local de trabalho como um todo:"),
    (60, "Há espaço para funcionários de diferentes raças e religiões?", "freq", "Sobre o seu local de trabalho como um todo:"),
    (61, "Há espaço para funcionários com doenças ou deficiências?", "freq", "Sobre o seu local de trabalho como um todo:"),
    (62, "Há espaço para funcionários mais velhos?", "freq", "Sobre o seu local de trabalho como um todo:"),
    (63, "Seu trabalho tem significado para você?", "intensidade", ""),
    (64, "Você sente que o seu trabalho é importante?", "intensidade", ""),
    (65, "Você se sente motivado(a) e envolvido(a) com o seu trabalho?", "intensidade", ""),
    (66, "Você gosta de falar com outras pessoas sobre o seu local de trabalho?", "intensidade", ""),
    (67, "Você sente que os problemas do seu local de trabalho também são seus?", "intensidade", ""),
    (68, "Seu local de trabalho tem grande importância pessoal para você?", "intensidade", ""),
    (69, "Suas perspectivas de carreira", "satisfacao", "O quanto você está satisfeito(a) com:"),
    (70, "As condições físicas do seu local de trabalho", "satisfacao", "O quanto você está satisfeito(a) com:"),
    (71, "A forma como as suas capacidades são aproveitadas", "satisfacao", "O quanto você está satisfeito(a) com:"),
    (72, "O seu trabalho, de forma geral", "satisfacao", "O quanto você está satisfeito(a) com:"),
    (73, "Ficar desempregado(a)", "intensidade", "O quanto você se preocupa com:"),
    (74, "Que uma nova tecnologia torne você dispensável", "intensidade", "O quanto você se preocupa com:"),
    (75, "Ter dificuldade para conseguir outro emprego, caso ficasse desempregado(a)", "intensidade", "O quanto você se preocupa com:"),
    (76, "Ser transferido(a) para outro local de trabalho contra a sua vontade", "intensidade", "O quanto você se preocupa com:"),
    (77, "De forma geral, como você considera a sua saúde?", "saude", ""),
    (78, "Exige tanta energia que acaba afetando negativamente a sua vida pessoal?", "intensidade", "O quanto o seu trabalho:"),
    (79, "Exige tanto tempo que acaba afetando negativamente a sua vida pessoal?", "intensidade", "O quanto o seu trabalho:"),
    (80, "Faz com que a sua família e amigos digam que você trabalha demais?", "intensidade", "O quanto o seu trabalho:"),
    (81, "Exige tanta energia que acaba afetando negativamente o seu trabalho?", "intensidade", "O quanto a sua vida pessoal:"),
    (82, "Exige tanto tempo que acaba afetando negativamente o seu trabalho?", "intensidade", "O quanto a sua vida pessoal:"),
    (83, "Teve dificuldade para adormecer?", "freq", "Nas últimas 4 semanas, com que frequência você:"),
    (84, "Dormiu mal e de forma agitada?", "freq", "Nas últimas 4 semanas, com que frequência você:"),
    (85, "Acordou cedo demais e não conseguiu voltar a dormir?", "freq", "Nas últimas 4 semanas, com que frequência você:"),
    (86, "Acordou várias vezes à noite e teve dificuldade para voltar a dormir?", "freq", "Nas últimas 4 semanas, com que frequência você:"),
    (87, "Sentiu-se cansado(a)?", "freq", "Nas últimas 4 semanas, com que frequência você:"),
    (88, "Sentiu-se esgotado(a)?", "freq", "Nas últimas 4 semanas, com que frequência você:"),
    (89, "Sentiu-se fisicamente exausto(a)?", "freq", "Nas últimas 4 semanas, com que frequência você:"),
    (90, "Sentiu-se emocionalmente exausto(a)?", "freq", "Nas últimas 4 semanas, com que frequência você:"),
    (91, "Teve dificuldade para relaxar?", "freq", "Nas últimas 4 semanas, com que frequência você:"),
    (92, "Sentiu-se irritado(a)?", "freq", "Nas últimas 4 semanas, com que frequência você:"),
    (93, "Sentiu-se tenso(a)?", "freq", "Nas últimas 4 semanas, com que frequência você:"),
    (94, "Sentiu-se ansioso(a)?", "freq", "Nas últimas 4 semanas, com que frequência você:"),
    (95, "Sentiu-se triste?", "freq", "Nas últimas 4 semanas, com que frequência você:"),
    (96, "Sentiu falta de autoconfiança?", "freq", "Nas últimas 4 semanas, com que frequência você:"),
    (97, "Sentiu peso na consciência ou culpa?", "freq", "Nas últimas 4 semanas, com que frequência você:"),
    (98, "Sentiu falta de interesse pelas coisas do dia a dia?", "freq", "Nas últimas 4 semanas, com que frequência você:"),
    (99, "Teve dores de barriga?", "freq", "Nas últimas 4 semanas, com que frequência você:"),
    (100, "Sentiu aperto ou dor no peito?", "freq", "Nas últimas 4 semanas, com que frequência você:"),
    (101, "Teve dores de cabeça?", "freq", "Nas últimas 4 semanas, com que frequência você:"),
    (102, "Teve palpitações (coração acelerado)?", "freq", "Nas últimas 4 semanas, com que frequência você:"),
    (103, "Sentiu tensão em vários músculos?", "freq", "Nas últimas 4 semanas, com que frequência você:"),
    (104, "Teve dificuldade para se concentrar?", "freq", "Nas últimas 4 semanas, com que frequência você:"),
    (105, "Teve dificuldade para tomar decisões?", "freq", "Nas últimas 4 semanas, com que frequência você:"),
    (106, "Teve dificuldade para lembrar de coisas?", "freq", "Nas últimas 4 semanas, com que frequência você:"),
    (107, "Teve dificuldade para pensar com clareza?", "freq", "Nas últimas 4 semanas, com que frequência você:"),
    (108, "Sou sempre capaz de resolver problemas, se me esforçar o suficiente.", "concordancia", "O quanto você concorda com cada afirmação:"),
    (109, "Mesmo que as pessoas atrapalhem, encontro um jeito de conseguir o que quero.", "concordancia", "O quanto você concorda com cada afirmação:"),
    (110, "É fácil para mim seguir os meus planos e atingir os meus objetivos.", "concordancia", "O quanto você concorda com cada afirmação:"),
    (111, "Sinto-me confiante para lidar com acontecimentos inesperados.", "concordancia", "O quanto você concorda com cada afirmação:"),
    (112, "Quando tenho um problema, geralmente encontro várias formas de resolvê-lo.", "concordancia", "O quanto você concorda com cada afirmação:"),
    (113, "Aconteça o que acontecer, costumo encontrar solução para os meus problemas.", "concordancia", "O quanto você concorda com cada afirmação:"),
    (114, "Envolveu-se em conflitos ou discussões?", "freq", "Nos últimos 12 meses, no trabalho, com que frequência você:"),
    (115, "Foi alvo de fofocas ou calúnias?", "freq", "Nos últimos 12 meses, no trabalho, com que frequência você:"),
    (116, "Foi alvo de insultos ou provocações verbais?", "freq", "Nos últimos 12 meses, no trabalho, com que frequência você:"),
    (117, "Foi exposto(a) a assédio sexual indesejado?", "freq", "Nos últimos 12 meses, no trabalho, com que frequência você:"),
    (118, "Foi exposto(a) a ameaças de violência?", "freq", "Nos últimos 12 meses, no trabalho, com que frequência você:"),
    (119, "Foi exposto(a) a violência física?", "freq", "Nos últimos 12 meses, no trabalho, com que frequência você:"),
]

QUESTIONS: list[dict] = [
    {
        "id": f"q{n}",
        "n": n,
        "prompt": prompt,
        "scale": scale,
        "secao": secao,
        "options": _options(scale),
    }
    for (n, prompt, scale, secao) in _RAW
]

QUESTION_IDS: list[str] = [q["id"] for q in QUESTIONS]

# --- Versão curta (41 itens) -------------------------------------------------
# Mesmos enunciados, mesmas escalas e os MESMOS ids ("q1", "q4", ...) da versão
# longa — só muda quais perguntas são feitas e em que ordem. Manter os ids é o
# que deixa a resposta de uma versão comparável com a da outra.
_BY_N = {q["n"]: q for q in QUESTIONS}

QUESTIONS_CURTA: list[dict] = [_BY_N[n] for n in SHORT_ORDER]
QUESTION_IDS_CURTA: list[str] = [q["id"] for q in QUESTIONS_CURTA]
