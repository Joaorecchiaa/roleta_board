"""
Config e mapeamentos da ARENA.

Os valores marcados com "CONFIRMAR" são heurísticas/placeholders que precisam
ser validados com dados reais da conta (rode `python3 arena.py discover-fields`
e me mande o resultado pra eu ajustar isto aqui).

MIGRAÇÃO CRN (22/10) — app.py agora busca Pipedrive e calcula regra de
negócio via crn_bridge.py + a biblioteca crn (crn.base.*/crn.regras.*), não
mais por este arquivo nem por colaboradores.py/pipedrive_client.py (que
continuam existindo, intactos, só não são mais importados por app.py — não
apague, podem estar em uso em outro painel sincronizado manualmente com
este). Os blocos abaixo que ficaram SEM USO no app.py (mas não foram
apagados daqui, pra não quebrar nada que ainda os leia) estão marcados
"RETIRADO 22/10" no comentário de cada um: CLOSERS_DO_MES/DONOS_VALIDOS_
EXTRA/eh_closer_do_mes/deve_pontuar_como_closer (ainda USADO, só que agora
só pro ajuste CLOSERS_SEM_PONTUACAO — ver app.py), PIPELINE_IDS_CAMPANHA/
eh_pipeline_campanha, FILTER_ID_*, QUALIFICADOR_FIELD_KEY/QUALIFICADOR_
LABELS (RETIRADO — crn resolve isso via Pipedrive ao vivo, opcoes_campo).
As variáveis de ambiente continuam as MESMAS (regra 1 da migração):
PIPEDRIVE_API_TOKEN, PLANILHA_URL. A biblioteca crn só lê PIPEDRIVE_TOKEN —
crn_bridge.py mapeia PIPEDRIVE_API_TOKEN pra ela automaticamente, sem
precisar trocar nome na Vercel.
"""

import os
from dotenv import load_dotenv

load_dotenv()

PIPEDRIVE_API_TOKEN = os.getenv("PIPEDRIVE_API_TOKEN", "")
PIPEDRIVE_DOMAIN = os.getenv("PIPEDRIVE_DOMAIN", "boardacademy")

# Link único que baixa a planilha de colaboradores INTEIRA (todas as abas,
# incluindo "Colaboradores" e "Metas") — o João preferiu colar no .env em
# vez de mandar o link aqui no chat. Veja .env.example pra instruções de
# como montar esse link.
PLANILHA_URL = os.getenv("PLANILHA_URL", "")
BASE_URL_V1 = f"https://{PIPEDRIVE_DOMAIN}.pipedrive.com/api/v1"
BASE_URL_V2 = f"https://{PIPEDRIVE_DOMAIN}.pipedrive.com/api/v2"

# ---------------------------------------------------------------------------
# Filtros SALVOS no Pipedrive (criados pelo João, 04/09) — REATIVADOS em
# 23/10 pra contornar um bug real da própria CRN: crn.base.pipedrive.
# atividades_do_periodo ordena por due_date decrescente SEM limite superior
# de data e só para quando acha uma atividade anterior ao início do
# período — numa conta com muita atividade futura agendada (comum aqui),
# isso varre a conta inteira antes de chegar no período pedido e estoura
# o limite de 200 páginas da própria CRN (RuntimeError "Busca passou de
# 200 páginas"). Reportar esse bug pro mantenedor da CRN é tarefa à parte
# (devería ser filtro server-side com due_date máximo, ou v1 com
# start_date/end_date) — ISSO AQUI não reimplementa regra nenhuma da CRN,
# só troca a FONTE da lista de atividades por um filtro salvo do Pipedrive
# (GET, igual de sempre), e o código continua repassando o resultado pras
# mesmas funções oficiais (rules.eventos_validados_crn → M6,
# fr2_agendamentos_dia.agendamentos → FR2).
#
# 23/10 — o João removeu a condição de FUNIL (antes "funil da campanha")
# do filtro 1671347 no Pipedrive, porque a regra M6 da CRN não filtra por
# funil (confirmado lendo o código: SDR pode agendar pra closer de
# QUALQUER funil) — manter o funil no filtro reintroduzia essa restrição
# escondida. FILTER_ID_ATIVIDADES_AGENDADAS_HOJE (1671344) ainda precisa
# da MESMA edição (tirar funil) antes de entrar em uso — ver app.py.
FILTER_ID_ATIVIDADES_REALIZADAS_HOJE = 1671343  # due_date=hoje, concluído, negócio não vazio, tipo Reunião/No Show/Reagendamento — SEM USO (eventos_validados_mes já cobre "hoje")
FILTER_ID_ATIVIDADES_AGENDADAS_HOJE = 1671344  # data adicionada=hoje, negócio não vazio, tipo Reunião/No Show/Reagendamento — AINDA COM funil da campanha, falta o João remover
FILTER_ID_GANHO_HOJE = 1671341  # negócio ganho em=hoje, valor != 0, funil da campanha — SEM USO (deals_won_hoje já filtra em Python)
# due_date=este mês, concluído, negócio não vazio, tipo Reunião/No Show/
# Reagendamento (client-side descarta o que não é "reuniao"), SEM funil
# (removido 23/10). Só serve pro MÊS ATUAL ("este mês" é relativo ao
# calendário no Pipedrive) — pra qualquer outro mês selecionado no painel,
# o código volta a usar crn_pd.atividades_do_periodo (ver _calcular_dados
# em app.py) — igual o painel antigo já fazia.
#
# CORRIGIDO 07/10 — o filtro TINHA também a condição "negócio 'Reunião
# Válida?'=Sim" salva no próprio Pipedrive. Isso excluía, ANTES de qualquer
# código Python rodar, todo negócio com o campo ainda vazio. O João
# removeu essa condição do filtro salvo no Pipedrive — quem decide
# Sim/Não/vazio é só a regra M6 da CRN (deals_validados), como já devia
# ser. Não mexer nesse filtro de novo pra reintroduzir essa condição.
FILTER_ID_ATIVIDADES_REALIZADAS_MES = 1671347

# ---------------------------------------------------------------------------
# Tipos de atividade que funcionam como "Desfecho da reunião" (docx seção 2).
# ALINHADO com "logica_classificacao_reunioes.md" (a lógica já usada em
# produção no meetings-dashboard) — só estes 3 tipos importam, e só quando a
# atividade tem deal_id preenchido:
ACTIVITY_TYPE_MEETING = "meeting"       # "Reunião" (id 2)
ACTIVITY_TYPE_NO_SHOW = "no_show"       # "No Show" (id 14)
ACTIVITY_TYPES_RESCHEDULE = {"reagendamento"}  # "Reagendamento" (id 13)
# Os outros tipos parecidos que existem na conta ("reagendado" id 26,
# "reuniao_nao_realizada" id 15, "reuniao_fora_de_sla" id 16) NÃO fazem parte
# da lógica de classificação estabelecida — ficam de fora, por ora.

# ---------------------------------------------------------------------------
# Campo "Reunião Válida?" do NEGÓCIO — critério oficial de reunião VALIDADA
# (não é o mesmo que "Feita"; é um refinamento dela). Documentado em
# logica_classificacao_reunioes.md seção 4. Só fica preenchido quando o
# negócio entra na etapa "Negociação"; critério é "Sim" ESTRITO (branco não
# conta).
REUNIAO_VALIDA_FIELD_KEY = "7299bf170c5deab9b4fd8c2275f55faf51984dea"
REUNIAO_VALIDA_LABELS = {411: "Sim", 412: "Não", 481: "No Show"}

TIPO_REUNIAO_FIELD_KEY = "8c55d15897cd6564b77fd2ec7497ebe8753a46e4"  # varchar
DATA_REUNIAO_FIELD_KEY = "a731ea7683581f52f7241e7321fbcb82a301fa45"  # date
HORA_REUNIAO_FIELD_KEY = "46b0fa98c14c1f63ea56b1fa0102627923e7137d"  # time

# ---------------------------------------------------------------------------
# Restrição extra pra "reunião validada" (seção 4 do documento): além do
# campo = "Sim" (ou vazio, ver rules.is_reuniao_validada), o Proprietário do
# negócio precisa ser um Closer do mês. Fonte hoje: tabela de closers do
# docx da ARENA (nomes como aparecem lá — CONFIRMAR se batem exatamente com
# o nome completo no Pipedrive, senão essa checagem falha silenciosamente).
CLOSERS_DO_MES = {
    "Maia", "Perim", "Natália Ferreira", "Mayara", "Lucas",
    "Vander", "Alessandra", "Natália Vaz", "Camila", "Francisco",
}
# Antes havia uma exceção "OU Denise Mussolin" em rules.py (is_reuniao_
# validada, nomes_donos_nao_reconhecidos, compute_closer_scores) e em
# app.py (_vendas_do_dia) tratando ela como closer válida mesmo fora de
# CLOSERS_DO_MES. João confirmou (02/09) que ela não faz mais parte dos 3
# funis ORIGINAIS da campanha (Sniper/Elite/Olympus) — a exceção foi
# REMOVIDA de todo lugar que checava esse nome NAQUELA rodada.
#
# 02/09 (mesmo dia, rodada seguinte): o funil NAVIGATOR foi incluído na
# campanha, e nele a Denise Mussolin volta a ser Closer de verdade — João
# confirmou que uma reunião do Alisson Santos não estava contando porque o
# dono do negócio (Denise) não era reconhecida. A exceção volta, mas agora
# ESCOPADA: só conta como Closer do mês pra negócio do funil Navigator —
# em Sniper/Elite/Olympus ela continua de fora. Ver eh_closer_do_mes.
#
# 02/09 (rodada seguinte ainda no mesmo dia): João ajustou de novo — a
# Denise NÃO deve aparecer no Ranking Closer nem pontuar como Closer (nem
# pódio de vendas, nem bônus de confirmação), só serve como "dono válido"
# pra destravar o crédito do SDR que agendou pra ela. Ou seja: ela some de
# CLOSERS_SEM_PONTUACAO (Closer que valida reunião mas nunca pontua/aparece
# no Ranking Closer), mas eh_closer_do_mes continua True pra ela no
# Navigator — é exatamente essa distinção que libera a reunião pro SDR sem
# dar ponto pra ela.
DENISE_MUSSOLIN_NOME = "Denise Mussolin"

# Gustavo Fabro (pedido do João, 06/10 no BOARD 5ANOS): ele é Closer de
# verdade, mas do squad/funil ELITE — não do OLYMPUS, que é o único Closer
# que esse painel mostra. Está cadastrado como "Head" na planilha de
# colaboradores. Mesma ideia da Denise acima: precisa ser reconhecido como
# "dono válido" (eh_closer_do_mes) pra destravar a validação de reunião do
# SDR que agenda pra ele, mas SEM contar como venda de Closer nem aparecer
# em nenhuma tabela/meta de Closer do painel (que é só Olympus) — diferente
# da Denise, essa exceção aqui não depende de pipeline específico (ver
# DONOS_VALIDOS_EXTRA, checado em eh_closer_do_mes).
#
# IMPORTANTE: como o papel dele na planilha continua "Head" (não mexemos
# nisso), ele nunca entra em CLOSERS_DO_MES (que é reconstruído em tempo de
# execução a partir de quem tem papel "closer" — ver app.py), nem em
# nomes_closer — por isso já fica de fora de toda tabela/meta de Closer
# automaticamente, sem precisar do CLOSERS_SEM_PONTUACAO abaixo pra isso.
# Ele entra em CLOSERS_SEM_PONTUACAO mesmo assim, por garantia/consistência
# com o padrão da Denise, caso algum dia o papel dele mude pra "closer" na
# planilha sem essa exceção ser removida daqui.
GUSTAVO_FABRO_NOME = "Gustavo Fabro"

# Thais Montalvão e Fernanda Alves (pedido do João, 08/10 no BOARD 5ANOS):
# mesmo mecanismo exato do Gustavo Fabro acima — quando uma reunião
# agendada por um SDR é marcada 'Reunião Válida?'='Sim' e o negócio está
# com uma delas como Proprietário (dono do negócio = "closer" da
# reunião), isso precisa 'destravar' a validação pra contar na meta de
# reuniões do SDR (eh_closer_do_mes passa a reconhecer as duas como
# 'dono válido', em qualquer pipeline). Confirmado com o João (via
# AskUserQuestion): elas só destravam a meta do SDR — não pontuam nem
# aparecem em nenhuma tabela/ranking de Closer do painel (por isso
# também entram em CLOSERS_SEM_PONTUACAO, igual Gustavo/Denise). Se o
# papel delas na planilha de Colaboradores for "closer", isso sozinho já
# as poria nas tabelas de Closer (nomes_closer vem do papel, não daqui)
# — nesse caso, avisar o João antes de mudar qualquer coisa aqui, porque
# a intenção combinada foi "só destravam, não pontuam".
THAIS_MONTALVAO_NOME = "Thais Montalvão"
FERNANDA_ALVES_NOME = "Fernanda Alves"
CLOSERS_SEM_PONTUACAO = {
    DENISE_MUSSOLIN_NOME, GUSTAVO_FABRO_NOME,
    THAIS_MONTALVAO_NOME, FERNANDA_ALVES_NOME,
}
DONOS_VALIDOS_EXTRA = {GUSTAVO_FABRO_NOME, THAIS_MONTALVAO_NOME, FERNANDA_ALVES_NOME}

# CORRIGIDO 09/10 (pedido do João) — a reunião validar pro SDR (acima) é
# uma coisa; o VALOR da venda entrar na meta financeira do time Olympus é
# outra, checada em separado (app.py::realizado_olympus, que normalmente
# só soma negócio de dono cadastrado na planilha de Colaboradores deste
# mês com subárea MGM + cargo financeiro). João confirmou: enquanto a
# Thais e a Fernanda não estiverem cadastradas assim na planilha, a venda
# delas AINDA PRECISA contar na meta financeira do Olympus — MAS só
# quando o negócio for do funil OLYMPUS especificamente (PIPELINE_IDS
# ["OLYMPUS"]), não qualquer funil da campanha ("a reunião não depende do
# funil, mas a venda sim"). Set separado de DONOS_VALIDOS_EXTRA de
# propósito: aquele também tem o Gustavo Fabro, que é do squad ELITE —
# ele nunca deve contar na meta financeira do Olympus.
DONOS_VALIDOS_EXTRA_FINANCEIRO_OLYMPUS = {THAIS_MONTALVAO_NOME, FERNANDA_ALVES_NOME}


def deve_pontuar_como_closer(nome_completo):
    """False pra quem é 'dono válido' (eh_closer_do_mes) só pra efeito de
    destravar a validação da reunião pro SDR, mas não deve receber ponto de
    Closer nem aparecer no Ranking Closer/Vendas do dia/Alvo do dia (ver
    CLOSERS_SEM_PONTUACAO, comentário em DENISE_MUSSOLIN_NOME). Todo
    chamador que for CREDITAR ponto de Closer (pódio de vendas, bônus de
    confirmação) ou listar alguém como Closer numa tela deve checar isso
    ALÉM de eh_closer_do_mes."""
    if not nome_completo:
        return True
    alvo = _sem_acentos(nome_completo).lower()
    return alvo not in {_sem_acentos(n).lower() for n in CLOSERS_SEM_PONTUACAO}


def _sem_acentos(s):
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def eh_closer_do_mes(nome_completo, pipeline_id=None):
    """Confere se `nome_completo` (como vem cadastrado no Pipedrive, ex:
    'Willian Maia', 'Francisco Martins') corresponde a um dos nomes/apelidos
    da tabela de Closers do docx (CLOSERS_DO_MES, que só tem nomes
    parciais/curtos — ex: 'Maia', 'Francisco'). Faz o match por PALAVRA
    INTEIRA (case/acento-insensitive) dentro do nome completo, em vez de
    comparação exata — a comparação exata falhava silenciosamente pra quase
    todo mundo, porque 'Maia' != 'Willian Maia'.

    Caso especial: 'Natália Ferreira' e 'Natália Vaz' já têm duas palavras
    no config (pra distinguir as duas Natálias que existem), então essas
    duas são comparadas como frase, não palavra a palavra.

    Segundo caso especial (02/09): Denise Mussolin conta como Closer do mês
    SÓ quando `pipeline_id` é o do Navigator (ver comentário em
    DENISE_MUSSOLIN_NOME) — por isso todo chamador que já tem o negócio em
    mãos deve passar deal.get('pipeline_id') aqui. Quando pipeline_id não é
    informado (None), essa exceção não se aplica — mantém o comportamento
    antigo (só CLOSERS_DO_MES) pros chamadores que ainda não repassam o
    negócio.

    Terceiro caso especial (06/10, BOARD 5ANOS): quem está em
    DONOS_VALIDOS_EXTRA (hoje só Gustavo Fabro) conta como Closer do mês
    SEMPRE, qualquer pipeline — ele é Closer de verdade, só não aparece nas
    tabelas de Closer do painel porque o papel dele na planilha continua
    "Head" (ver comentário em GUSTAVO_FABRO_NOME)."""
    if not nome_completo:
        return False
    alvo = _sem_acentos(nome_completo).lower()
    alvo_palavras = set(alvo.split())
    for candidato in CLOSERS_DO_MES:
        c = _sem_acentos(candidato).lower()
        if " " in c:
            if c in alvo:
                return True
        elif c in alvo_palavras:
            return True
    for candidato in DONOS_VALIDOS_EXTRA:
        c = _sem_acentos(candidato).lower()
        if c in alvo or c in alvo_palavras:
            return True
    if pipeline_id is not None and int(pipeline_id) == PIPELINE_IDS["NAVIGATOR"]:
        if alvo == _sem_acentos(DENISE_MUSSOLIN_NOME).lower():
            return True
    return False

# ---------------------------------------------------------------------------
# Exclusões e casos especiais (seção 6 do documento) — mesmas constantes já
# usadas no meetings-dashboard, reaproveitadas na ARENA:
MATHEUS_PAZ_CREATOR_ID = 14326654  # integração de IA; exclui só do lado Closer
SDR_EXCLUIDOS = {
    # Priscila Ribeiro e Thiago Santos: João confirmou (31/08) que não são
    # dos funis da campanha (Sniper/Elite/Olympus) — mesmo aparecendo como
    # "SDR" na planilha de colaboradores, não devem contar ponto nem
    # aparecer em nenhum painel da ARENA (Ranking, Alvo do dia, etc.).
    "Priscila Ribeiro",
    "Thiago Santos",
    # Mylena Oliveira: investigado via `arena.py investigate` (28/08) — o
    # volume alto dela (343 pts, 60+ "validada") vem de sessões recorrentes
    # em horário fixo (14:30/17:00/13:00/22:00 repetidos quase todo dia),
    # aparentando onboarding/aula em grupo, não agendamento comercial 1:1.
    # João confirmou: não é o tipo de trabalho que a ARENA quer premiar no
    # Ranking SDR, mesmo quando a atividade está vinculada a negócio real.
    "Mylena Oliveira",
    # Raphaela Moutinho e Denise Mussolin: João confirmou (02/09) que
    # também não fazem mais parte dos 3 funis da campanha (Sniper/Elite/
    # Olympus) — mesmo padrão de Priscila/Thiago/Mylena acima: fora de
    # qualquer painel da ARENA. Denise também deixou de ser exceção
    # especial no lado Closer (ver comentário em DENISE_MUSSOLIN_NOME).
    "Raphaela Moutinho",
    DENISE_MUSSOLIN_NOME,
    # Matheus Paz: é a integração de IA (MATHEUS_PAZ_CREATOR_ID acima) —
    # aquela constante só filtra ele do lado Closer (quem criou a atividade
    # "de verdade"); esta entrada aqui é o que impede o nome dele de
    # aparecer como SDR quando ele acaba sendo a única atividade do grupo
    # (fallback de _criador_da_reuniao).
    "Matheus Paz",
    # Marlon Silva SAIU daqui em 07/10 (pedido do João, BOARD 5ANOS) — ele
    # tinha entrado em 02/09 (ARENA) porque "não é SDR, não deve participar
    # do Ranking SDR nem de nenhum painel". Isso continua verdade, mas
    # agora a reunião validada DELE (e da Stephanie Nascimento, que nunca
    # esteve aqui) precisa contar na Meta do time SNIPER (reunioes_
    # validadas_no_mes/atingimento), só sem aparecer em nenhum painel
    # individual de SDR (Detalhamento do dia, Destaque do dia, Destaque
    # contínuo) — exatamente como já acontece no painel grande. Manter ele
    # (e a Stephanie) de fora dos painéis individuais agora é feito via
    # LIDERANCAS_FIXAS (ver abaixo, usado em app.py pra tirar os dois de
    # nomes_sdr/destaque contínuo), não mais via exclusão total daqui —
    # porque exclusão total também bloqueava a reunião de contar pra
    # QUALQUER lugar, inclusive a meta do funil, que é exatamente o que o
    # João pediu pra parar de acontecer.
}
# Exceção TEMPORÁRIA (pedido do João, 03/09): Toryell Moura começou hoje no
# time de SDR e está em rampagem — a meta diária dela é bem menor que a dos
# outros (ritmo de rampagem), então não seria justo ela virar "1º SDR a bater
# a Meta do dia" (destaque no topo do painel) só por bater uma meta muito mais
# fácil. Ela continua aparecendo normalmente no Detalhamento (Validadas/
# Agendadas/meta mensal) — só é pulada na escolha de quem fica em destaque
# como 1º do dia (ver _primeiro_sdr_bateu_meta em app.py). O João vai avisar
# uma data específica pra remover essa exceção e voltar ao normal pra ela;
# até lá, é só tirar o nome dela deste conjunto quando ele pedir.
SDRS_SEM_DESTAQUE_DIA = {
    "Toryell Moura",
}

# ---------------------------------------------------------------------------
# Exclusão manual de colaboradores que JÁ SAÍRAM do time mas continuam
# aparecendo na planilha (pedido do João, 28/09) — ele não pode simplesmente
# apagar a linha delas na planilha porque o mês ainda não fechou (perderia o
# histórico de "mês de referência" dos dias em que elas trabalharam), mas
# elas não devem mais aparecer em NENHUM painel da ARENA a partir de agora.
#
# Diferente de SDR_EXCLUIDOS (que é sobre gente que nunca devia contar
# ponto, por não ser dos funis certos da campanha) — aqui é sobre gente que
# SAIU DA EMPRESA/TIME no meio do mês, mesmo continuando cadastrada na
# planilha. Funciona pra SDR OU Closer (é aplicado direto em cima da lista
# pessoas_do_mes inteira, em app.py::_calcular_dados, ANTES de qualquer
# outro filtro/lista derivar dela — Closers do mês, SDRs do mês, Atingimento
# por squad, Metas etc. — então basta um lugar só pra cascatear em tudo).
#
# Cuidado ao adicionar alguém aqui que é (ou foi) Closer: qualquer negócio
# no Pipedrive que ainda estiver com ela como Proprietário deixa de ser
# reconhecido como "dono válido" (config.eh_closer_do_mes) — isso também
# destrava/bloqueia a validação de reuniões de SDRs vinculadas a esses
# negócios (mesmo mecanismo do caso do Head cobrindo reunião, visto em
# 24/09). Se isso derrubar pontos de SDR que não deveriam cair, o ajuste
# certo é reatribuir o Proprietário do negócio no Pipedrive pra outro
# Closer ativo, não mexer aqui.
#
# Basta colocar o nome EXATO como aparece na planilha/Pipedrive — a
# comparação já ignora acento/maiúscula/espaço extra (mesma normalização
# usada em SDR_EXCLUIDOS). Remover o nome daqui quando não precisar mais.
COLABORADORES_REMOVIDOS_MANUALMENTE = {
    "Natália Ferreira",
    "Camila Cardoso",
}

# Líderes (Team Leader/Head) que PODEM validar reunião pra conta própria
# (owner_id/creator de uma atividade, dentro da subárea Sniper na planilha)
# mas não são SDR de cota — CORRIGIDO 07/10 (pedido do João, BOARD 5ANOS):
# a reunião validada delas conta na Meta do time SNIPER (reunioes_validadas_
# no_mes), mas elas não devem aparecer em nenhum painel INDIVIDUAL de SDR
# (Detalhamento do dia, Destaque do dia, Destaque contínuo). Em
# Detalhamento/Destaque do dia isso já acontece sozinho (esses painéis só
# iteram nomes_sdr, que é por papel=="sdr" — líder tem papel diferente); em
# Destaque contínuo precisa de um filtro explícito (ver app.py,
# validadas_mes_por_sdr) porque esse painel soma QUALQUER nome que validou
# reunião, sem filtrar por papel. Mylena Oliveira continua em SDR_EXCLUIDOS
# (motivo totalmente diferente, ver comentário lá) — fica nesta lista só
# por já estar cadastrada como líder na planilha, sem efeito prático extra
# (SDR_EXCLUIDOS já bloqueia ela de tudo, inclusive da meta do funil).
LIDERANCAS_FIXAS = {
    "Mylena Oliveira": "Team Leader",
    "Stephanie Nascimento": "Team Leader",
    "Marlon Silva": "Head",
}

# Exceção mais estreita que LIDERANCAS_FIXAS acima — CORRIGIDO 07/10 (pedido
# do João: "coloque uma exceção para a Stephanie e para o Marlon que os dois
# agendam mas não estão com o cargo de SDR"): das 3 pessoas em
# LIDERANCAS_FIXAS, só Stephanie Nascimento e Marlon Silva agendam reunião
# na prática (cargo de líder na planilha, mas função de SDR no dia a dia) —
# Mylena Oliveira NÃO entra aqui (ela já está em SDR_EXCLUIDOS, por motivo
# totalmente diferente, não relacionado a cargo). Usado só pra decidir quem
# conta na META do time Sniper (meta_reunioes_sniper/meta_financeira_sniper
# em app.py) além dos SDRs de cota de verdade — continua exigindo que a
# pessoa esteja na subárea Sniper na planilha deste mês (nomes_sniper), só
# dispensa a exigência de papel=="sdr" pra essas duas.
LIDERES_QUE_AGENDAM_COMO_SDR = {
    "Stephanie Nascimento",
    "Marlon Silva",
}


# Pipedrive devolve tudo em UTC; Brasília = UTC-3. Aplicado antes de calcular
# dia da semana / mês da reunião (devido/due_date pode virar o dia em UTC
# perto da meia-noite e mudar o mês do resultado se não ajustar).
AJUSTE_FUSO_HORAS = -3

# ---------------------------------------------------------------------------
# Forma de pagamento -> fator multiplicador (docx seção 3/4).
# NÃO existe um campo único "Forma de pagamento" com essas 5 opções prontas.
# Amostra real (26/08/2026, sample-deals) mostrou que "Método de Pagamento"
# (texto livre) e a lista suspensa "QUANTIDADE DE PARCELAS?" quase sempre
# vêm em branco. O João indicou usar em vez disso o campo NUMÉRICO
# "Quantidade de Parcelas" (double, provavelmente vindo do gateway/Guru),
# que tende a estar mais confiável preenchido.
METODO_PAGAMENTO_FIELD_KEY = "830b176d25451ccd93c113a75c34e8ff7566c2ec"
VENDA_PARCELADA_FIELD_KEY = "bb8f93736a719e61d9d826f52dbc25925d4d5e79"
QTD_PARCELAS_FIELD_KEY = "03d29a5e9a11838dc311a0ce85e19d32d6999fb4"  # enum antigo, mantido de reserva
QTD_PARCELAS_NUMERO_FIELD_KEY = "b0626ed5e620e171e6a5992586d3d56fa2e80347"  # double

# Campo "Multiplicador" do negócio — receita já com o fator de forma de
# pagamento aplicado (calculado fora do Pipedrive, por automação/gateway).
# Usado SÓ pro Atingimento por squad (Elite/Olympus), pedido do João 03/09
# — é um número pronto pra somar, diferente de payment_multiplier() acima
# (que RECALCULA o fator a partir da quantidade de parcelas pro desempate
# do pódio de vendas).
MULTIPLICADOR_FIELD_KEY = "7e0e43c2734751f77be292a72527f638a850ad50"

# Campo "Qualificador" do negócio (dropdown, aponta o SDR que originou a
# venda) — pedido do João 06/10: usar pro Atingimento FINANCEIRO do Sniper,
# mesmo critério já em produção no painel grande de métricas da empresa
# (handoff-painel-board-academy.md, "a forma real e certa de pegar o
# dado"). Diferente do Proprietário/dono do negócio (que é o Closer que
# fechou) — aqui é quem QUALIFICOU a venda, i.e. o SDR.
QUALIFICADOR_FIELD_KEY = "a6f13cc27c8d041f3af4091283ce0d4fe0913875"

# Mapa id-da-opção -> nome, pro campo Qualificador acima. CORRIGIDO 07/10
# (bug real em produção, achado pelo João — "subiu mas zerou a meta
# financeira de todos"): a API v2 do Pipedrive devolve esse campo (dropdown)
# como só o ID BRUTO da opção (int), não como {'id':..,'label':'Fulano'} —
# sem esse mapa não dá pra saber o nome, e a 1ª tentativa de correção
# (tratar ID bruto como "não identificado") zerava o financeiro de todo
# mundo, porque TODOS os negócios vêm assim, não só o caso raro do
# "Guilherme Oliveira" (ver rules.qualificador_do_negocio). Mesmo padrão já
# usado em REUNIAO_VALIDA_LABELS acima. Lista completa das opções do campo
# (puxada direto do Pipedrive em 07/10) — atualizar aqui se alguém novo for
# cadastrado como opção nova do dropdown.
QUALIFICADOR_LABELS = {
    1307: "Ailton Mariano", 1141: "Alex Lima", 1484: "Alisson Santos",
    787: "Amanda Torres", 958: "Ana Gomes", 965: "Beatriz Lage",
    558: "Bruna Góes", 559: "Bruna Santana", 649: "Bruna Sena",
    970: "Bruno Gomes", 844: "Bruno Santos", 1472: "Carolina Matos",
    797: "Christoffer Reis", 966: "Cristiane Martins", 645: "Cynthia Freitas",
    1405: "Cíntia Oliveira", 1270: "Daniela Silva", 1271: "Danilo Viegas",
    1480: "Debora Matos", 1272: "Diego Lima", 974: "Diego Reátegui",
    951: "Douglas Diel", 967: "Elaine Alencar", 953: "Eloá Maurêncio",
    1273: "Erika Pires", 1275: "Fabio Perim", 971: "Felippe Santos",
    1174: "Fernando Junior", 954: "Flaviana Silveira", 1274: "Fábio Melo",
    1473: "Gabriel Oliveira", 952: "Gabriela Souza Coimbra",
    964: "Gabrielle Barros", 473: "Mickaelly Machado", 483: "Mylena Oliveira",
    513: "Laryssa Reis", 554: "Letícia Bagini", 639: "Giovanna Souza",
    651: "João Paiva", 791: "Marlon Silva", 831: "Luca Bueno",
    832: "Jeane Vilas Boas", 837: "Guilherme Bargiela",
    866: "Guillermo Moreno", 910: "Guilherme Oliveira", 932: "Leandro Sousa",
    949: "Isabel Simon", 959: "Ligia Gonçalves", 960: "Leandro Durans",
    963: "Mayara Silva", 968: "Lucas Viana", 972: "João Santos",
    973: "Helene Mazzieiro", 975: "Queila Souza", 1140: "Natane da Silva",
    1249: "Pamela Silva", 1293: "Marcos Conceição", 1315: "Pedro Muniz",
    1388: "Lys Senna", 1406: "Leticia Santos", 1407: "Luzia Rocha",
    1411: "Sabryna Eiras", 1416: "Karoline Soares", 1424: "Lucas Dias",
    1433: "Livia Sales", 1436: "Khalian Silva", 1463: "N/A",
    1464: "Priscila Ribeiro", 1474: "Raphaela Moutinho",
    1476: "Leonardo Zinzani", 1478: "Guilherme Vaillant",
    1479: "Nicole Ribeiro", 1481: "Igor Cassamassimo",
    1485: "Rafael Rodrigues", 1529: "Nicolly Silva", 1530: "Nicole Richardot",
    491: "Stephanie Nascimento", 976: "Tatiane Santos", 514: "Thamara Mendes",
    955: "VIctor Junior", 969: "Vinicius Caires", 1341: "Vitor Soares",
    1531: "Weglysam Carvalho", 956: "Wellington Conceição",
    950: "Yasmin Gomes", 1619: "Thiago Santos", 1672: "Joyce Nascimento",
    1673: "Rafaela Sousa", 1674: "Dener Quintino",
}

# CONFIRMAR (ainda em aberto): com só o número de parcelas, 0 ou 1 parcela
# pode ser tanto PIX/TED (fator 2.0) quanto Cartão 1x/Boleto único (fator
# 1.5) — o docx separa os dois, mas não há sinal de MÉTODO aqui, só
# quantidade. Por ora assumo o valor mais conservador (1.5) pra não inflar
# pontos por engano; ajusto se você confirmar outro critério.
FATOR_PAGAMENTO_A_VISTA_CONSERVADOR = 1.5


def fator_por_quantidade_parcelas(qtd):
    """Bucketiza pela QUANTIDADE de parcelas (docx seção 2/'Receita
    multiplicador'). qtd pode vir como float/int/None."""
    if qtd is None:
        return None
    qtd = round(float(qtd))
    if qtd <= 1:
        return FATOR_PAGAMENTO_A_VISTA_CONSERVADOR
    if 2 <= qtd <= 6:
        return 1.0
    if 7 <= qtd <= 10:
        return 0.7
    return 0.5  # 11+

# ---------------------------------------------------------------------------
# Funis considerados na ARENA (docx: squads Sniper=SDR, Elite e Olympus=Closers;
# Navigator incluído em 02/09 — João confirmou que reunião validada desse
# funil também deve contar, achado depois de uma reunião do Alisson Santos
# não aparecer no Ranking SDR por estar no Navigator). João confirmou: a
# ARENA conta SÓ negócio desses 4 funis — qualquer negócio de outro funil
# (outras squads, CS, renovação etc.) fica de fora do cálculo de pontos
# inteiro, mesmo que a pessoa dona dele também apareça como Closer/SDR em
# algum lugar. IDs conferidos via `python arena.py discover-pipelines`.
#
# VANGUARD (pipeline_id=45, confirmado 09/10 via Pipedrive ao vivo — é um
# time/funil novo e diferente, não é o Navigator renomeado) foi acrescentado
# aqui pedido do João, no contexto da nova regra de "reuniões FEITAS e
# VALIDADAS" (dash de reuniões): SDR do Sniper pode agendar reunião pra um
# negócio no funil Vanguard, e essa reunião precisa continuar sendo
# reconhecida/validada (João confirmou via AskUserQuestion, 09/10: "continua
# só dos SDRs do Sniper, mas tem algumas reuniões que os SDRs do Sniper
# agendaram para outros times, como o Vanguard").
#
# IMPORTANTE: Vanguard NÃO entra em PIPELINE_IDS_CAMPANHA (abaixo) de
# propósito — aquele conjunto é só pros 4 funis-squad originais (usado pelo
# lado CLOSER: pódio de vendas, Atingimento por squad, Destaque do dia/
# contínuo de Closer). Vanguard não é squad do painel, só um funil onde
# SDR do Sniper pode ter reunião — colocá-lo em PIPELINE_IDS_CAMPANHA
# passaria a contar negócio de Vanguard errado nessas métricas de Closer.
PIPELINE_IDS = {
    "SNIPER": 88,
    "OLYMPUS": 46,
    "ELITE": 87,
    "NAVIGATOR": 51,
    "VANGUARD": 45,
}
PIPELINE_IDS_CAMPANHA = {
    PIPELINE_IDS["SNIPER"], PIPELINE_IDS["OLYMPUS"],
    PIPELINE_IDS["ELITE"], PIPELINE_IDS["NAVIGATOR"],
}


def eh_pipeline_campanha(pipeline_id):
    """True se o negócio está num dos 4 funis da campanha (Sniper/Elite/
    Olympus/Navigator — Navigator incluído em 02/09). pipeline_id pode vir
    como int ou string — normaliza antes."""
    if pipeline_id is None:
        return False
    try:
        return int(pipeline_id) in PIPELINE_IDS_CAMPANHA
    except (TypeError, ValueError):
        return False

# ---------------------------------------------------------------------------
# Tabela de meta mensal por nível — CLOSER (docx seção "Premiação"/tabela de closers)
# nível -> meta mensal em R$
CLOSER_LEVEL_META = {
    1: 200_000,
    3: 265_000,
    4: 305_000,
    5: 350_000,
}

# Peso na squad = meta do closer / soma das metas da squad (docx já calculou,
# aqui recalculamos dinamicamente a partir da meta pra não depender de % fixo)

# CONFIRMAR: docx não trouxe tabela nível -> meta mensal de agendamentos pro SDR.
# Preencher assim que a planilha de colaboradores vier com essa informação.
SDR_LEVEL_META_AGENDAMENTOS = {
    # nivel: meta_mensal_agendamentos
    # 1: None,
    # 2: None,
    # 3: None,
}

# ---------------------------------------------------------------------------
# Dias úteis de setembro/2026 (docx seção "O mês, semana a semana": 21 d.u.,
# feriado dia 7, fechamento na quarta dia 30)
DIAS_UTEIS_SETEMBRO_2026 = 21

# ---------------------------------------------------------------------------
# NOVA REGRA (pptx "ARENA Campanha Setembro 2026 v2", recebido em 02/09,
# "Segue nova regra atualizada" — SUBSTITUI o motor de pontos inteiro).
#
# Pódio diário: todo dia tem 1º/2º/3º lugar, tanto pra vendas (Closer) quanto
# pra reuniões validadas (SDR). 8/6/4 pontos pros 3 primeiros, 0 pro resto.
# Empate Closer: desempata por maior receita no multiplicador. Empate SDR: o
# pptx diz "quem confirmou a reunião na véspera" — o Pipedrive não guarda
# esse dado, então o desempate usado aqui é uma aproximação (ordem
# alfabética do nome), documentada como limitação conhecida.
PODIO_PONTOS = [8, 6, 4]  # 1º, 2º, 3º lugar do dia; 4º em diante = 0

# ---------------------------------------------------------------------------
# Pontuação — SDR (pptx "A régua", slide 3, atualizado 03/09)
#
# NOTA (03/09): a pedido do João, o bônus de confirmação (+2 por reunião
# validada, além do pódio) e a "meta semanal cheia" (+25) que existiam até
# 02/09 foram REMOVIDOS — por enquanto só o pódio diário pontua (ver
# config.PODIO_PONTOS, acima). Ele pode trazer uma regra nova pra semana que
# vem, com pontuação própria — quando isso acontecer, adicionar aqui.
PONTOS_SDR = {
    # --- Chaves antigas (motores anteriores), mantidas só como referência
    # histórica. rules.py não lê mais nenhuma delas.
    # "reuniao_validada_confirmada": 2,
    # "meta_semanal_cheia": 25,
    # "reuniao_validada": 5,
    # "reuniao_nao_realizada": 1,
    # "reuniao_quarta_bonus": 2,
    # "reuniao_resgate_bonus": 5,
    # "venda_origem_sdr": 10,
    # "pipe_em_dia_sexta": 5,
    # "sequencia_3_dias": 2,
    # "sequencia_5_dias": 5,
    # "sequencia_10_dias": 12,
    # "reuniao_validada_mesmo_dia_bonus": 2,
}

# Pontuação — Closer (pptx "A régua", slide 3, atualizado 03/09)
PONTOS_CLOSER = {
    "reais_por_ponto_receita": 1000,  # ainda usado só pro desempate do pódio de vendas (receita no multiplicador)

    # --- Chaves antigas (motores anteriores), mantidas só como referência
    # histórica. rules.py não lê mais nenhuma delas.
    # "reuniao_validada_confirmada": 2,
    # "venda_resgate_multiplicador": 2,
    # "reuniao_dia_marcado": 1,
    # "reuniao_quarta_bonus": 2,
    # "pipe_fechado_sexta": 5,
    # "sequencia_3_dias": 2,
    # "sequencia_5_dias": 5,
    # "sequencia_10_dias": 12,
}
