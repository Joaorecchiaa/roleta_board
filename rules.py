"""
Motor de pontos da ARENA.

Cada função aqui documenta, no próprio docstring, de qual regra do docx
"ARENA — Direcionamento Técnico" ela vem, e o que é heurística/aproximação
(marcado com CONFIRMAR). Isso é proposital: se uma regra apurar errado, tem
que ser fácil achar qual trecho do código mexer.

MIGRAÇÃO CRN (22/10) — a função `eventos_validados_crn`, no final deste
arquivo, SUBSTITUIU o caminho que o app.py usa pra decidir "reunião feita
e validada": em vez de is_reuniao_validada_estrita/_dono_mudou_depois/
_sdr_id_e_nome (toda essa família de funções ABAIXO), a regra agora vem
direto de crn.regras.m6_reunioes_sdr.reunioes_validadas() — "dono válido"
deixou de ser lista fixa de nome (CLOSERS_DO_MES/DONOS_VALIDOS_EXTRA/
Denise Mussolin/Gustavo Fabro/Thais/Fernanda) e passou a ser R2 (papel,
pela aba Metas) + H1 (hierarquia, pela Colab) + RN1 (a própria exceção
"dono mudou depois", agora de verdade na regra oficial, não reimplementada
aqui). As funções antigas abaixo (is_reuniao_validada, is_reuniao_validada_
estrita, _dono_mudou_depois, _campo_validada_bloqueia,
_rotulo_reuniao_validada_simples, nomes_donos_nao_reconhecidos,
deduplicar_atividades_exatas, build_deal_activity_map, _sdr_id_e_nome)
NÃO são mais chamadas pelo app.py — ficaram só porque compute_sdr_scores/
compute_closer_scores (também não chamadas pelo app.py desta versão
"enxuta", herdadas do arena-dashboard/) ainda dependem delas. Não apague
sem checar se algum outro painel ainda importa essas duas."""

from collections import defaultdict
from datetime import datetime, timedelta, timezone

import config
import crn_bridge
from crn.base.config import tipo_atividade
from crn.base.fuso import atividade_dia, atividade_momento
from crn.base.texto import dono_id
from crn.regras import m6_reunioes_sdr
from crn.regras._atividades import do_tipo as _crn_do_tipo


def _parse_date(s):
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00")).date()


def _dia_brasilia(s):
    """Converte um timestamp ISO em UTC (como won_time vem da API do
    Pipedrive) pro DIA correspondente em horário de Brasília
    (config.AJUSTE_FUSO_HORAS) — mesmo ajuste de fuso que due_datetime_
    brasilia já fazia pras atividades (due_date/due_time), só que faltava
    aplicar em won_time. Bug real achado pelo João em 03/09: uma venda do
    Francisco fechada tarde da noite em Brasília virava 'dia seguinte' em
    UTC, e contava no pódio/Ranking Closer do dia ERRADO. _parse_date
    (acima) continua existindo pra quem não precisa desse ajuste (ex:
    log_time em is_lead_resgatado, onde o critério é 'há quantos DIAS',
    não 'em qual dia exato')."""
    if not s:
        return None
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return (dt + timedelta(hours=config.AJUSTE_FUSO_HORAS)).date()


def due_datetime_brasilia(activity):
    """Combina due_date + due_time da atividade (em UTC, como a API devolve)
    e aplica o ajuste de fuso (seção 7 do logica_classificacao_reunioes.md)
    antes de qualquer cálculo de dia/mês/dia-da-semana. Sem due_time, assume
    meio-dia UTC (só pra não quebrar o ajuste de fuso perto da virada)."""
    due_date = activity.get("due_date")
    if not due_date:
        return None
    due_time = activity.get("due_time") or "12:00:00"
    dt = datetime.fromisoformat(f"{due_date}T{due_time}").replace(tzinfo=timezone.utc)
    return dt + timedelta(hours=config.AJUSTE_FUSO_HORAS)


def classify_desfecho(activity_type_key):
    """Docx seção 2: Desfecho da reunião = Realizada / No-show / Reagendada.
    Inferido pelo TIPO da atividade. ACTIVITY_TYPES_RESCHEDULE cobre os dois
    tipos parecidos achados na conta real ('reagendamento' e 'reagendado') —
    ver aviso em config.py, ainda precisa confirmar com o João se são a
    mesma coisa."""
    if activity_type_key == config.ACTIVITY_TYPE_MEETING:
        return "realizada"
    if activity_type_key == config.ACTIVITY_TYPE_NO_SHOW:
        return "no_show"
    if activity_type_key in config.ACTIVITY_TYPES_RESCHEDULE:
        return "reagendada"
    return None


def reuniao_valida_do_negocio(deal):
    """Lê o campo 'Reunião Válida?' (Sim/Não/No Show) do negócio. Retorna o
    label (str) ou None se o campo não estiver preenchido (negócio ainda não
    chegou na etapa Negociação)."""
    custom = deal.get("custom_fields") or {}
    raw = custom.get(config.REUNIAO_VALIDA_FIELD_KEY)
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw.get("label")
    return config.REUNIAO_VALIDA_LABELS.get(raw, raw)


def qualificador_do_negocio(deal):
    """Lê o campo 'Qualificador' do negócio (dropdown, aponta o SDR que
    originou a venda) — usado pro Atingimento FINANCEIRO do Sniper (pedido
    do João 06/10, mesmo critério do painel grande de métricas da empresa).
    Retorna o label (nome do SDR) ou None se vazio/sem opção selecionada.

    CORRIGIDO 07/10 (bug real em produção, achado pelo João — Internal
    Server Error ao abrir o painel): esse campo (dropdown) vem da API v2 do
    Pipedrive como só o ID BRUTO da opção escolhida (int), não como
    {'id':..,'label':'Fulano'} — isso vale pra TODOS os negócios, não só
    pro caso raro. Sem resolver o ID pro nome, o resto do código quebrava
    com TypeError ao tentar normalizar um int (config._sem_acentos exige
    string). 1ª tentativa de correção tratava qualquer ID bruto como "não
    identificado" (retornava None) — isso parou de quebrar a página, mas
    como TODO mundo vem como ID bruto, zerava o financeiro do time inteiro
    (reportado pelo João: "subiu mas zerou a meta financeira de todos").
    Correção de verdade: resolve o ID através de config.QUALIFICADOR_LABELS
    (mapa id->nome puxado direto do Pipedrive). Se formato novo/dict
    aparecer (ex: via outra rota da API), aceita também. Só se o ID não
    estiver nem no mapa (opção nova, criada depois de 07/10) é que volta
    None — aí sim o negócio fica de fora do financeiro, igual já acontece
    com 'N/A' e com qualificador vazio."""
    custom = deal.get("custom_fields") or {}
    raw = custom.get(config.QUALIFICADOR_FIELD_KEY)
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw.get("label")
    if isinstance(raw, str):
        return raw
    return config.QUALIFICADOR_LABELS.get(raw)


def _activity_owner_id(act):
    """Responsável pela atividade. CORRIGIDO 07/10 (pedido do João — código
    de referência do painel grande, 'campo_owner_id'): a prioridade estava
    ERRADA. A API v1 (usada em get_activities, porque só ela filtra por
    due_date) devolve os dois campos 'user_id' E 'owner_id' na mesma
    atividade, mas 'owner_id' nem sempre é confiável nesse payload (pode
    vir desatualizado/diferente do responsável de verdade) — 'user_id' é
    quem reflete certo o responsável. Por isso agora checa 'user_id'
    PRIMEIRO, e só cai pro 'owner_id' se 'user_id' não vier (payload v2,
    que não tem 'user_id' e chama esse campo de 'owner_id')."""
    v = act.get("user_id", act.get("owner_id"))
    if isinstance(v, dict):
        return v.get("value") or v.get("id")
    return v


def _activity_creator_id(act):
    """Quem criou o registro da atividade. v1 chama 'created_by_user_id',
    v2 chama 'creator_user_id' — mesmo problema do _activity_owner_id."""
    return act.get("creator_user_id", act.get("created_by_user_id"))


def _sdr_id_e_nome(grupo_acts, user_names, nomes_sniper=None):
    """Resolve quem é o SDR responsável pela reunião, a partir de TODAS as
    atividades do grupo (mesmo negócio + due_date — ver _criador_da_reuniao
    pra dedupe), não só da atividade 'original' (mais antiga).

    CORRIGIDO 07/10 (pedido do João, confirmado via AskUserQuestion:
    "owner_id, com fallback pro criador") — por padrão usa o owner_id da
    atividade 'original' (quem o Pipedrive diz ser o responsável), não quem
    criou o registro (creator_user_id), porque isso resolve o caso do
    Head/Team Leader que cria a atividade em nome de outra pessoa.

    CORRIGIDO 07/10 de novo (caso real achado ao vivo: negócio 321890,
    Stefan Araujo) — só olhar o owner_id/creator_id da atividade 'original'
    não bastava: a Stephanie Nascimento (líder) criou DUAS atividades pra
    mesma reunião ('Reunião Board Academy...' e 'Agendamento Reunião...',
    mesmo due_date) — a mais antiga ('original') ficou com owner_id = o
    Closer (Caique Klein), e só a SEGUNDA (criada minutos depois) tem
    owner_id = a SDR de verdade (Rafaela Sousa). Como Stephanie também é
    da subárea Sniper (ela é Team Leader DENTRO do Sniper), o fallback
    antigo (só olhar creator_id da 'original') parava nela — errado,
    porque ela é a líder que criou a atividade, não quem agendou.

    Por isso agora, quando `nomes_sniper` é passado, a busca varre TODAS
    as atividades do grupo (em ordem de add_time): primeiro o owner_id de
    cada uma, depois o creator_id de cada uma — e usa a PRIMEIRA pessoa
    encontrada que está na subárea Sniper. Isso acha a Rafaela (owner_id
    da segunda atividade) antes de cair na Stephanie (creator da
    primeira). Se ninguém do grupo bate com a Sniper, devolve o owner_id
    da atividade 'original' mesmo (comportamento antigo — quem chama isso
    decide se descarta a reunião via is_reuniao_validada_estrita).

    CORRIGIDO 07/10 (3ª rodada, pedido do João) — esse mesmo mecanismo de
    varredura PARECIA estar inflando o total da Stephanie Nascimento:
    achei ao vivo (outubro) 7 negócios creditados a ela, contra os 6 reais
    do painel grande, em 5 dos 7 ela criava DUAS atividades (Closer +
    'Agendamento' com ela mesma como owner_id). Tentativa de correção:
    exigir que o líder fosse owner_id de TODAS as atividades do grupo
    (confirmado via AskUserQuestion, "líder só conta quando é a ÚNICA
    pessoa do grupo").

    REVERTIDO 07/10 (4ª rodada, achado ao vivo depois que o João reportou
    "as reuniões que estão faltando são as reuniões da Stephanie que você
    não está contando" — a exigência de exclusividade zerou quase todo
    mundo, 7 pra 1, longe demais dos 6 esperados). Investiguei os 7
    negócios de novo, agora olhando o campo Reunião Válida de cada um: 6
    estão "Sim" e UM (negócio 388137, 'Sergio') está "Não" — ou seja, a
    diferença real de 7 pra 6 nunca teve nada a ver com dono duplicado ou
    exclusividade de grupo; é só esse negócio tendo sido marcado como
    reunião inválida mesmo, por um critério que já existia (ver
    is_reuniao_validada_estrita, bem antes de qualquer mudança de hoje). A
    varredura por nomes_sniper (sem exigência extra nenhuma pro líder)
    sempre esteve certa — bastava deixar o campo Reunião Válida fazer o
    próprio trabalho de descartar o negócio 388137. Função voltou a só
    exigir 'está na subárea Sniper' pra qualquer nome, líder ou não."""
    original = _criador_da_reuniao(grupo_acts)
    sdr_id = _activity_owner_id(original)
    sdr_nome = user_names.get(sdr_id, f"user_{sdr_id}")
    if nomes_sniper is None:
        return sdr_id, sdr_nome

    def _norm(nome):
        return " ".join(config._sem_acentos(nome or "").lower().split())

    def _aceitavel(cid, nome):
        return _norm(nome) in nomes_sniper

    if _aceitavel(sdr_id, sdr_nome):
        return sdr_id, sdr_nome

    ordenadas = sorted(grupo_acts, key=lambda a: a.get("add_time") or "")
    candidatos = [_activity_owner_id(a) for a in ordenadas] + [_activity_creator_id(a) for a in ordenadas]
    for cid in candidatos:
        nome = user_names.get(cid, f"user_{cid}")
        if _aceitavel(cid, nome):
            return cid, nome

    return sdr_id, sdr_nome


def _nome_proprietario(deal, user_names):
    owner = deal.get("owner_id")
    owner_id = owner.get("value") if isinstance(owner, dict) else owner
    return user_names.get(owner_id)


def is_reuniao_validada(deal, user_names, sdr_nome=None):
    """Critério OFICIAL de 'reunião validada' (logica_classificacao_reunioes.md
    seções 4 e 5, ajustado a pedido do João em 02/09): campo 'Reunião
    Válida?' == 'Sim' OU VAZIO (negócio ainda não chegou/não passou pela
    etapa que preenche o campo) — só 'Não' e 'No Show' DESQUALIFICAM. Antes
    exigia 'Sim' ESTRITO; a mudança trata "ainda sem resposta" como
    validado por padrão, em vez de esperar o campo ser preenchido. E o
    proprietário do negócio precisa ser um Closer do mês — reconhecido pela
    tabela geral (CLOSERS_DO_MES) OU, só pra negócio do funil Navigator,
    pela exceção da Denise Mussolin (config.eh_closer_do_mes recebe o
    pipeline_id do negócio pra aplicar isso certo; ver comentário em
    config.DENISE_MUSSOLIN_NOME) —, E (quando sdr_nome é informado) o
    proprietário do negócio é DIFERENTE da pessoa cujo ponto está sendo
    calculado — seção 5, item 3: 'não conta se ela marcou reunião pra um
    negócio dela mesma'. Sem esse terceiro crivo, um closer que atende a
    própria reunião (sem SDR real envolvido) virava 'SDR de origem' de si
    mesmo — foi o bug que zerava a diferença entre os dois rankings na
    primeira rodada de validação."""
    if deal is None:
        return False
    valor_campo = reuniao_valida_do_negocio(deal)
    if valor_campo not in (None, "Sim"):
        return False
    dono = _nome_proprietario(deal, user_names)
    if not config.eh_closer_do_mes(dono, pipeline_id=deal.get("pipeline_id")):
        return False
    if sdr_nome is not None and dono == sdr_nome:
        return False
    return True


def _rotulo_reuniao_validada_simples(deal):
    """Lê o campo 'Reunião Válida?' do negócio reconhecendo SÓ os rótulos
    Sim/Não (ids 411/412) — espelha 'rotulo_validada()' do módulo de regras
    que o João mandou em 20/10 (api/index.py do dash de reuniões,
    autocontido). QUALQUER outra coisa — campo vazio OU a opção 'No Show'
    do PRÓPRIO campo (id 481, ver config.REUNIAO_VALIDA_LABELS) — conta
    como 'em branco' pra este critério; intencional, o módulo de referência
    só reconhece 411/412 nesse dict e trata o resto como None. Diferente de
    reuniao_valida_do_negocio (acima), que ainda resolve 'No Show' como
    rótulo próprio — essa continua existindo só pro diagnóstico
    nomes_donos_nao_reconhecidos, que não muda com isso."""
    custom = deal.get("custom_fields") or {}
    raw = custom.get(config.REUNIAO_VALIDA_FIELD_KEY)
    if isinstance(raw, dict):
        raw = raw.get("label", raw.get("value"))
    if raw in (None, ""):
        return None
    if isinstance(raw, (int, float)) or (isinstance(raw, str) and raw.strip().lstrip("-").isdigit()):
        return {411: "Sim", 412: "Não"}.get(int(raw))
    return str(raw)


def _campo_validada_bloqueia(deal):
    """True só quando 'Reunião Válida?' é 'Não' EXPLÍCITO (ver
    _rotulo_reuniao_validada_simples acima) — 'Sim', vazio, ou qualquer
    rótulo não reconhecido (incl. 'No Show' do campo) NÃO bloqueia."""
    r = _rotulo_reuniao_validada_simples(deal)
    return r is not None and config._sem_acentos(r).lower().strip() == "nao"


def _dono_mudou_depois(activity, deal, deal_id, by_deal_acts, user_names,
                        nomes_sniper, nomes_donos_validos_extra):
    """EXCEÇÃO 'dono mudou depois' (regra do dash de reuniões, mandada pelo
    João em 20/10 — caso real #411006: SDR agenda e FAZ a reunião, mas o
    negócio acaba repassado/reaberto e hoje está com outra pessoa como
    Proprietário — ex: um Head cobrindo, não reconhecido como 'dono
    válido'). A reunião do SDR continua validada se existe, no MESMO
    negócio, outra atividade (de responsável DIFERENTE do SDR) que: está
    feita (done), é do MESMO tipo, cai no mesmo dia ou ±1 dia (comparando
    devido_date BRUTO em UTC, sem ajuste de fuso — igual o módulo de
    referência faz), e cujo responsável é um dono válido OU alguém que nem
    está na população de SDRs (nomes_sniper) — ou seja, não é só "mais um
    SDR agendando de novo", é alguém de fora que efetivamente assumiu o
    negócio."""
    if not deal_id or not activity.get("due_date"):
        return False
    try:
        d0 = datetime.fromisoformat(str(activity["due_date"])[:10])
    except ValueError:
        return False
    owner_a = _activity_owner_id(activity)
    tipo_a = activity.get("type")
    for b in by_deal_acts.get(deal_id, []):
        if b is activity or b.get("id") == activity.get("id"):
            continue
        owner_b = _activity_owner_id(b)
        if not owner_b or owner_b == owner_a:
            continue
        if b.get("is_deleted") or not b.get("done") or b.get("type") != tipo_a:
            continue
        try:
            d1 = datetime.fromisoformat(str(b.get("due_date"))[:10])
        except (ValueError, TypeError):
            continue
        if abs((d1 - d0).days) > 1:
            continue
        nome_b = user_names.get(owner_b)
        nome_b_norm = " ".join(config._sem_acentos(nome_b or "").lower().split())
        dono_valido = config.eh_closer_do_mes(nome_b, pipeline_id=deal.get("pipeline_id"))
        if not dono_valido and nomes_donos_validos_extra is not None:
            dono_valido = nome_b_norm in nomes_donos_validos_extra
        fora_da_populacao_sdr = nomes_sniper is not None and nome_b_norm not in nomes_sniper
        if dono_valido or fora_da_populacao_sdr:
            return True
    return False


def is_reuniao_validada_estrita(deal, user_names, sdr_nome=None, nomes_sniper=None,
                                 nomes_donos_validos_extra=None, activity=None,
                                 deal_id=None, by_deal_acts=None):
    """Variante ESTRITA de is_reuniao_validada — só pro dashboard usar na
    métrica 'Validadas hoje' do Alvo do dia (due_date == hoje). João pediu
    (02/09), depois de achar um caso real de double-count: um lead de
    REAPLICAÇÃO já estava com 'Reunião Válida?'='Sim' de um ciclo anterior,
    e uma atividade nova de reunião com due_date=hoje ligada a esse mesmo
    negócio fez ele contar de novo como "validada hoje" — mesmo não sendo
    uma validação nova de verdade.

    Critério exato que o João passou pra essa métrica originalmente:
    due_date == hoje (checado por quem chama esta função, não aqui), done
    == true, e o campo 'Reunião Válida?' == 'Sim' ESTRITO — vazio NÃO
    contava aqui.

    TESTE 07/10 (pedido do João) — relaxado pra bater com is_reuniao_
    validada: agora aceita 'Sim' OU vazio (campo ainda não preenchido,
    negócio não chegou na etapa que valida) — só 'Não'/'No Show'
    desqualificam. Objetivo: não perder reunião que já rolou mas ainda não
    foi validada manualmente no Pipedrive (devido ao atraso do validador).
    Se isso trouxer de volta o double-count de REAPLICAÇÃO que motivou a
    versão estrita original (comentário acima, 02/09), reverter pra
    `!= "Sim"`.

    CORRIGIDO 06/10 — exigência de dono TROCADA (confirmado pelo João
    comparando com a regra real do painel grande): não é mais "o dono do
    negócio precisa ser um Closer do mês reconhecido". Agora é "quem FEZ A
    ATIVIDADE (o SDR) precisa ser da subárea Sniper na COLAB" — não importa
    quem é o dono do negócio, só que não seja a mesma pessoa (critério de
    não-auto-atendimento, mantido). `nomes_sniper` é o conjunto (nomes
    normalizados) de quem está na subárea Sniper no mês — quem chama esta
    função é responsável por montar isso a partir de pessoas_do_mes.

    CORRIGIDO 07/10 — pedido do João, depois de ele passar o conjunto
    OFICIAL de regras do painel grande por escrito: lá o critério de "dono
    válido" (owner_id da ATIVIDADE == a pessoa auditada, E Proprietário do
    NEGÓCIO precisa ser Closer do mês/Denise Mussolin/Legionário) nunca
    saiu — a troca de 06/10 (linha acima) tinha removido essa exigência de
    dono por engano, achando que ela tinha sido substituída pela exigência
    de Sniper. Confirmado via AskUserQuestion (07/10, "Exigir os dois"): a
    partir de agora V exige AMBOS, não um OU outro — quem agendou precisa
    ser da subárea Sniper (nomes_sniper, acima) E o dono do negócio precisa
    ser um 'dono válido': Closer do mês reconhecido (config.eh_closer_do_mes,
    que já cobre Denise Mussolin pro funil Navigator e Gustavo Fabro) OU
    alguém com cargo Legionário/Legionária no mês (nomes_donos_validos_extra
    — conjunto de nomes normalizados que quem chama esta função monta a
    partir de pessoas_do_mes, mesmo padrão de nomes_sniper). Se
    nomes_donos_validos_extra vier None, essa parte extra do crivo não é
    aplicada (comportamento anterior a 07/10, só pra compatibilidade com
    quem ainda não repassa esse conjunto).

    ATUALIZADO 20/10 (regras do dash de reuniões, mandadas pelo João por
    escrito — módulo api/index.py autocontido): duas mudanças, pra alinhar
    com o critério de lá:

    1) O campo 'Reunião Válida?' passou a usar _campo_validada_bloqueia
    (só 'Não' EXPLÍCITO bloqueia; antes 'No Show' também bloqueava —
    ver docstring de _rotulo_reuniao_validada_simples).

    2) Quando o dono do negócio NÃO é um 'dono válido' (nem Closer do mês/
    extra), antes disso já desqualificava a reunião. Agora, SE `activity`
    e `by_deal_acts` forem passados (quem chama é responsável por montar
    isso — ver app.py), cai pra exceção 'dono mudou depois'
    (_dono_mudou_depois): o negócio pode ter sido reaberto/repassado DEPOIS
    da reunião, perdendo o dono válido original — se outra atividade feita
    no mesmo negócio (responsável diferente, mesmo tipo, ±1 dia) mostra que
    quem assumiu é válido ou nem é SDR, a reunião continua contando. Se
    `activity`/`by_deal_acts` não forem passados, esse crivo extra não roda
    (comportamento anterior, só compatibilidade)."""
    if deal is None:
        return False
    if _campo_validada_bloqueia(deal):
        return False
    dono = _nome_proprietario(deal, user_names)
    if sdr_nome is not None and dono == sdr_nome:
        return False
    if nomes_sniper is not None:
        sdr_norm = " ".join(config._sem_acentos(sdr_nome or "").lower().split())
        if sdr_norm not in nomes_sniper:
            return False
    if nomes_donos_validos_extra is not None:
        dono_norm = " ".join(config._sem_acentos(dono or "").lower().split())
        dono_valido = config.eh_closer_do_mes(dono, pipeline_id=deal.get("pipeline_id"))
        if not dono_valido:
            dono_valido = dono_norm in nomes_donos_validos_extra
        if not dono_valido and activity is not None and by_deal_acts is not None:
            dono_valido = _dono_mudou_depois(
                activity, deal, deal_id, by_deal_acts, user_names,
                nomes_sniper, nomes_donos_validos_extra,
            )
        if not dono_valido:
            return False
    return True


def nomes_donos_nao_reconhecidos(deals_by_id, user_names):
    """Diagnóstico: lista nomes de proprietário de negócio que têm 'Reunião
    Válida?'='Sim' mas NÃO batem com nenhum Closer do mês reconhecido pro
    funil daquele negócio (CLOSERS_DO_MES, ou a exceção da Denise Mussolin
    só pro Navigator — ver config.eh_closer_do_mes) — ou seja, candidatos a
    estar faltando/errados na configuração. Não afeta o cálculo, só ajuda a
    auditar."""
    nomes = set()
    for deal in deals_by_id.values():
        if not config.eh_pipeline_campanha(deal.get("pipeline_id")):
            continue
        if reuniao_valida_do_negocio(deal) != "Sim":
            continue
        dono = _nome_proprietario(deal, user_names)
        if dono and not config.eh_closer_do_mes(dono, pipeline_id=deal.get("pipeline_id")):
            nomes.add(dono)
    return nomes


def deduplicar_atividades_exatas(activities):
    """Colapsa atividade duplicada EXATA — mesmo negócio, mesmo tipo, mesmo
    due_date e due_time (string bruta, sem ajuste de fuso) — numa só,
    preferindo a que já está 'done' (regra 'deduplicar()' do módulo de
    regras que o João mandou em 20/10). Atividade sem deal_id passa direto
    (nada pra deduplicar). Diferente do agrupamento por dia em
    _eventos_reuniao_validada_por_dia/_contar_* (que junta atividades do
    MESMO negócio no MESMO dia, mesmo com due_time diferente, pra achar
    quem é o SDR de verdade — ver _sdr_id_e_nome) — isso aqui só remove
    registro repetido de verdade, não mexe nessa outra lógica."""
    vistos = {}
    ordem = []
    for a in activities:
        if not a.get("deal_id"):
            ordem.append(a)
            continue
        chave = (a.get("deal_id"), a.get("type"), str(a.get("due_date")), str(a.get("due_time")))
        if chave not in vistos:
            vistos[chave] = a
            ordem.append(chave)
        elif a.get("done") and not vistos[chave].get("done"):
            vistos[chave] = a
    return [vistos[x] if isinstance(x, tuple) else x for x in ordem]


def build_deal_activity_map(activities):
    """Agrupa atividades por negócio, pra saber se um negócio teve
    reagendamento (mais de um tipo de atividade de reunião associada)."""
    by_deal = defaultdict(list)
    for act in activities:
        deal_id = act.get("deal_id")
        if deal_id:
            by_deal[deal_id].append(act)
    return by_deal


def payment_multiplier(deal):
    """Docx seção 2 (Receita multiplicador): fator pela forma de pagamento.

    Usa o campo NUMÉRICO "Quantidade de Parcelas" (indicado pelo João, mais
    confiável que a lista suspensa manual). Ainda não distingue PIX/TED
    (fator 2.0) de Cartão 1x/Boleto (fator 1.5) quando qtd<=1 — ver
    FATOR_PAGAMENTO_A_VISTA_CONSERVADOR em config.py."""
    custom = deal.get("custom_fields") or {}
    raw = custom.get(config.QTD_PARCELAS_NUMERO_FIELD_KEY)
    qtd = raw.get("value") if isinstance(raw, dict) else raw
    return config.fator_por_quantidade_parcelas(qtd)


def is_lead_resgatado(deal, flow_events, month_start, month_end):
    """Docx seção 2 (Lead resgatado): negócio que estava perdido há 90+ dias
    na data da reabertura, reaberto e trabalhado no mês.

    Implementação: procura no changelog (deal flow) a transição mais recente
    para status='lost' antes da reabertura, e a transição seguinte de volta
    pra 'open'. Se a reabertura caiu dentro do mês e o intervalo perdido>=90
    dias, conta como resgate.

    CONFIRMAR: a Pipedrive pode reportar o campo mudado como 'status' com
    old_value/new_value 'lost'/'open' — testar contra um caso real primeiro.
    """
    lost_at = None
    reopened_at = None
    for ev in sorted(flow_events, key=lambda e: e.get("data", {}).get("log_time", "")):
        d = ev.get("data", {})
        if d.get("field_key") != "status":
            continue
        log_time = _parse_date(d.get("log_time"))
        if d.get("new_value") == "lost":
            lost_at = log_time
        elif d.get("new_value") == "open" and lost_at:
            reopened_at = log_time
            break

    if not (lost_at and reopened_at):
        return False
    if not (month_start <= reopened_at <= month_end):
        return False
    return (reopened_at - lost_at).days >= 90


def alvo_diario_closer(nivel, dias_uteis=config.DIAS_UTEIS_SETEMBRO_2026):
    """Docx seção 2 (Alvo diário) — meta de RECEITA REALIZADA por dia, pro closer."""
    meta_mensal = config.CLOSER_LEVEL_META.get(nivel)
    if meta_mensal is None:
        return None
    return meta_mensal / dias_uteis


def alvo_diario_sdr(nivel, dias_uteis=config.DIAS_UTEIS_SETEMBRO_2026):
    """Docx seção 2 (Alvo diário) — meta de AGENDAMENTOS por dia, pro SDR.
    CONFIRMAR: depende de config.SDR_LEVEL_META_AGENDAMENTOS, que ainda não
    foi definido (docx só trouxe a tabela de metas pros Closers)."""
    meta_mensal = config.SDR_LEVEL_META_AGENDAMENTOS.get(nivel)
    if meta_mensal is None:
        return None
    return meta_mensal / dias_uteis


class PersonScore:
    def __init__(self, name):
        self.name = name
        self.pontos = 0
        self.detalhe = []  # lista de (motivo, pontos)
        # Lista de (due_date da reunião, deal_id) só pras reuniões que
        # pontuaram como "validada" — usado pelo Alvo do dia (dashboard)
        # pra descobrir, olhando o changelog do negócio, EM QUE DIA o campo
        # "Reunião Válida?" virou 'Sim' (que pode ser bem diferois do dia da
        # própria reunião — o closer só confirma depois).
        self.reunioes_validadas = []

    def add(self, motivo, pontos, reuniao_validada_deal_id=None, reuniao_validada_due=None):
        if pontos:
            self.pontos += pontos
            self.detalhe.append((motivo, pontos))
        if reuniao_validada_deal_id is not None:
            self.reunioes_validadas.append((reuniao_validada_due, reuniao_validada_deal_id))

    def as_dict(self):
        return {"nome": self.name, "pontos": self.pontos, "detalhe": self.detalhe}


def _eventos_reuniao_validada_por_dia(activities, deals_by_id, user_names, nomes_sniper=None,
                                       nomes_donos_validos_extra=None):
    """Agrupa, por due_date (dia da reunião), todo evento de 'reunião feita e
    validada' (pptx 'ARENA Campanha Setembro 2026 v2', recebido 02/09) — o
    MESMO critério do widget 'Validadas hoje' do dashboard:
    is_reuniao_validada_estrita (campo 'Reunião Válida?'=='Sim' ESTRITO,
    quem agendou é da subárea Sniper, dono != SDR) + done==true na
    atividade. João confirmou (02/09) que 'reunião confirmada e realizada'
    do bloco de confirmação = esse mesmo evento.

    Usa a mesma dedupe por (negócio, due_date) das outras métricas — pega a
    atividade 'original' do grupo (rules._criador_da_reuniao) pra saber quem
    é o SDR de origem. Retorna {date: [{"sdr": nome, "closer": nome,
    "deal_id": id}, ...]} — "closer" aqui é só o dono do negócio (pode ser
    qualquer um, não precisa mais ser Closer do mês reconhecido — ver
    CORRIGIDO 06/10 abaixo).

    CORRIGIDO 06/10 (pedido do João, "qualquer funil que ela tenha
    reunião, não só ela mas qualquer SDR" + confirmação da regra real do
    painel grande) — duas mudanças: (1) removido o filtro de funil da
    campanha daqui; (2) a exigência de dono TROCOU de "Closer do mês
    reconhecido" pra "quem agendou é da subárea Sniper" (ver
    is_reuniao_validada_estrita) — `nomes_sniper` (nomes normalizados) é
    quem chama esta função monta a partir de pessoas_do_mes e repassa pra
    baixo. A fonte dos dados (app.py) também teve que trocar de filtro
    salvo pra busca por período, porque o filtro salvo tinha "funil da
    campanha" embutido do lado do Pipedrive.

    ATUALIZADO 20/10 — repassa pra is_reuniao_validada_estrita a atividade
    'original' do grupo + o mapa negócio->atividades, pra habilitar a
    exceção 'dono mudou depois' (ver is_reuniao_validada_estrita e
    _dono_mudou_depois). NÃO aplica deduplicar_atividades_exatas aqui —
    tentei, mas quebra o caso real do teste
    TestSdrIdVarreGrupoInteiro: duas atividades do MESMO due_date+due_time
    só diferem no owner_id (Closer vs SDR de verdade, atribuição
    reatribuída) — colapsar pela chave (negócio, tipo, data, hora) derruba
    exatamente a atividade que _sdr_id_e_nome precisa ver pra achar o SDR
    certo. O agrupamento por (negócio, dia) abaixo já evita contar a mesma
    reunião duas vezes; deduplicar_atividades_exatas fica só documentada
    (útil se algum dia processarmos lista já filtrada por UM responsável
    só, como o módulo de referência faz)."""
    eventos = defaultdict(list)
    by_deal = build_deal_activity_map(activities)
    for deal_id, acts in by_deal.items():
        deal = deals_by_id.get(deal_id)
        reuniao_acts = [a for a in acts if classify_desfecho(a.get("type")) == "realizada"]
        if not reuniao_acts:
            continue
        grupos = defaultdict(list)
        for a in reuniao_acts:
            due_dt = due_datetime_brasilia(a)
            if due_dt is None:
                continue
            grupos[due_dt.date()].append(a)
        for due, grupo_acts in grupos.items():
            if not any(a.get("done") for a in grupo_acts):
                continue
            # CORRIGIDO 07/10 — ver _sdr_id_e_nome: owner_id (varrendo TODO
            # o grupo de atividades, não só a mais antiga), com fallback
            # pro criador quando ninguém do grupo é da subárea Sniper.
            sdr_id, sdr_nome = _sdr_id_e_nome(grupo_acts, user_names, nomes_sniper=nomes_sniper)
            if sdr_nome in config.SDR_EXCLUIDOS:
                continue
            atividade_original = _criador_da_reuniao(grupo_acts)
            if not is_reuniao_validada_estrita(
                deal, user_names, sdr_nome=sdr_nome, nomes_sniper=nomes_sniper,
                nomes_donos_validos_extra=nomes_donos_validos_extra,
                activity=atividade_original, deal_id=deal_id, by_deal_acts=by_deal,
            ):
                continue
            closer_nome = _nome_proprietario(deal, user_names)
            eventos[due].append({"sdr": sdr_nome, "closer": closer_nome, "deal_id": deal_id})
    return eventos


def _agrupar_vendas_por_dia(deals_won, user_names):
    """Agrupa negócios ganhos por dia (won_time) e Closer dono, pro pódio
    diário de vendas (pptx seção 'A régua'). Retorna {date: {closer_nome:
    {"quantidade": int, "receita_multiplicador": float}}} — receita_
    multiplicador usa payment_multiplier (mesmo fator já usado no motor
    antigo), e serve só pro desempate oficial do pódio ('venda à vista
    desempata a favor'), não pontua sozinha.

    Negócio ganho com value <= 0 (ou vazio) NÃO conta como venda pro pódio
    (achado pelo João, 03/09 — Willian Maia apareceu em 1º lugar do dia com
    R$0 no multiplicador, 3 negócios "ganhos" sem valor nenhum). Value zerado
    normalmente é erro de preenchimento no Pipedrive (negócio marcado Ganho
    antes de preencher o valor) — sem isso, dava pra "ganhar" o pódio do dia
    inteiro sem vender de verdade."""
    por_dia = defaultdict(lambda: defaultdict(lambda: {"quantidade": 0, "receita_multiplicador": 0.0}))
    for deal in deals_won:
        if not config.eh_pipeline_campanha(deal.get("pipeline_id")):
            continue
        if not (deal.get("value") or 0) > 0:
            continue
        won_time = _dia_brasilia(deal.get("won_time"))
        if not won_time:
            continue
        closer_nome = _nome_proprietario(deal, user_names)
        if not config.eh_closer_do_mes(closer_nome, pipeline_id=deal.get("pipeline_id")):
            continue
        if not config.deve_pontuar_como_closer(closer_nome):
            # Dono "válido" só pra destravar a reunião do SDR (ex: Denise
            # Mussolin no Navigator) — não entra no pódio de vendas.
            continue
        fator = payment_multiplier(deal)
        valor = deal.get("value") or 0
        receita_mult = valor * fator if fator is not None else 0.0
        info = por_dia[won_time][closer_nome]
        info["quantidade"] += 1
        info["receita_multiplicador"] += receita_mult
    return por_dia


def _criador_da_reuniao(grupo_acts):
    """Dado um grupo de atividades que representam a MESMA reunião (mesmo
    negócio, mesmo due_date ajustado, mesmo desfecho — normalmente a
    atividade original + a cópia gerada quando o Responsável é reatribuído
    pro Closer), acha quem criou a reunião de verdade: a atividade mais
    ANTIGA por add_time, ignorando qualquer atividade criada pela automação
    de IA (Matheus Paz) — ela só gera o registro duplicado de log, nunca é
    quem realmente agendou. Retorna a atividade "original" (não a cópia)."""
    candidatas = [a for a in grupo_acts if _activity_creator_id(a) != config.MATHEUS_PAZ_CREATOR_ID]
    if not candidatas:
        candidatas = grupo_acts
    return min(candidatas, key=lambda a: a.get("add_time") or "")


def compute_sdr_scores(activities, deals_by_id, user_names, month_start, month_end):
    """Motor de pontos do SDR — regra "A régua" (slide 3, pptx atualizado
    03/09): SÓ o pódio diário conta, sem nenhum bônus. Pra cada dia do mês,
    ranqueia os SDRs pela quantidade de reuniões 'feita e validada' naquele
    dia (mesmo evento de _eventos_reuniao_validada_por_dia — due ESTRITO,
    done=true, campo 'Reunião Válida?'=='Sim' estrito). 1º, 2º e 3º lugar
    ganham config.PODIO_PONTOS (8/6/4); do 4º em diante (ou quem não teve
    nenhuma reunião validada no dia), 0. Desempate oficial do pptx pro lado
    SDR é "quem confirmou a reunião na véspera" — o Pipedrive não guarda
    esse dado, então aqui o desempate é por ordem alfabética do nome
    (aproximação, não o critério oficial — documentar essa limitação pro
    João).

    NOTA (03/09): o bônus de confirmação (+2 por reunião validada, além do
    pódio) que existia até 02/09 foi REMOVIDO a pedido do João — por
    enquanto só a régua de pódio pontua. Ele pode pedir uma regra nova pra
    semana que vem, com pontuação própria.

    Cada negócio fora dos funis da campanha (Sniper/Elite/Olympus/Navigator)
    já é descartado dentro de _eventos_reuniao_validada_por_dia."""
    scores = {}

    def score_de(nome):
        return scores.setdefault(nome, PersonScore(nome))

    eventos_por_dia = _eventos_reuniao_validada_por_dia(activities, deals_by_id, user_names)

    for due, eventos in sorted(eventos_por_dia.items()):
        if not (month_start <= due <= month_end):
            continue

        contagem = defaultdict(int)
        for ev in eventos:
            contagem[ev["sdr"]] += 1

        # Pódio do dia: mais reuniões validadas primeiro; empate por ordem
        # alfabética (ver docstring — aproximação, pptx pede "quem confirmou
        # na véspera", dado que o Pipedrive não guarda).
        ranking_dia = sorted(contagem.keys(), key=lambda nome: (-contagem[nome], nome))
        for posicao, nome in enumerate(ranking_dia):
            pontos = config.PODIO_PONTOS[posicao] if posicao < len(config.PODIO_PONTOS) else 0
            if pontos:
                score_de(nome).add(
                    f"Pódio do dia {due} — {posicao + 1}º lugar em reuniões validadas ({contagem[nome]})",
                    pontos,
                )

    return scores


def compute_closer_scores(deals_won, deals_by_id, activities, user_names, month_start, month_end):
    """Motor de pontos do Closer — regra "A régua" (slide 3, pptx
    atualizado 03/09): SÓ o pódio diário conta, sem nenhum bônus. Por dia
    (won_time), ranqueia os Closers pela quantidade de negócios ganhos
    naquele dia. 1º/2º/3º ganham config.PODIO_PONTOS, resto (ou quem não
    vendeu no dia) 0. Desempate OFICIAL do pptx: maior receita no
    multiplicador (payment_multiplier) — "venda à vista desempata a favor".

    NOTA (03/09): o bônus de confirmação que existia até 02/09 foi REMOVIDO
    a pedido do João — por enquanto só a régua de pódio pontua. `deals_by_id`
    e `activities` continuam na assinatura só por compatibilidade com quem
    já chama esta função (arena.py/app.py); não são mais usados aqui."""
    scores = {}

    def score_de(nome):
        return scores.setdefault(nome, PersonScore(nome))

    vendas_por_dia = _agrupar_vendas_por_dia(deals_won, user_names)

    for dia, por_closer in sorted(vendas_por_dia.items()):
        if not (month_start <= dia <= month_end):
            continue

        ranking_dia = sorted(
            por_closer.keys(),
            key=lambda nome: (-por_closer[nome]["quantidade"], -por_closer[nome]["receita_multiplicador"], nome),
        )
        for posicao, nome in enumerate(ranking_dia):
            pontos = config.PODIO_PONTOS[posicao] if posicao < len(config.PODIO_PONTOS) else 0
            if pontos:
                info = por_closer[nome]
                score_de(nome).add(
                    f"Pódio do dia {dia} — {posicao + 1}º lugar em vendas "
                    f"({info['quantidade']}, R${info['receita_multiplicador']:.0f} no multiplicador)",
                    pontos,
                )

    return scores


# ---------------------------------------------------------------------------
# MIGRAÇÃO CRN (22/10) — ver nota no topo do arquivo.
def eventos_validados_crn(activities, ini, fim, *, deals_validados, dono_do_deal,
                           sdr_ids, lideranca_ids, usuarios):
    """Substitui _eventos_reuniao_validada_por_dia (e, por tabela, is_
    reuniao_validada_estrita/_dono_mudou_depois/_sdr_id_e_nome) pela regra
    OFICIAL M6 da CRN (crn.regras.m6_reunioes_sdr.reunioes_validadas) —
    nenhuma lógica de validação roda aqui, só filtragem de tipo (FR —
    crn.base.config.tipo_atividade('reuniao')) e reagrupamento do
    resultado por DIA, no mesmo formato que o app.py já consumia:
    {date: [{"sdr": nome, "closer": nome, "deal_id": id}, ...]}.

    Parâmetros (todos vindos de crn_bridge, a partir das regras R2/H1):
    - deals_validados: set de deal_id com 'Reunião Válida?'='Sim' (filtro
      oficial `reuniao_validada` da CRN — crn_bridge.deals_validados_e_
      donos()).
    - dono_do_deal: {deal_id: owner_id} desses mesmos negócios.
    - sdr_ids / lideranca_ids: ids do Pipedrive de quem é SDR de cota (R2)
      e de quem é Head/Team Leader (H1) — crn_bridge.ids_por_papel()/
      ids_lideranca().
    - usuarios: {id: nome} (crn.base.pipedrive.usuarios())."""
    tipo_reuniao = tipo_atividade("reuniao")
    atividades_reuniao = _crn_do_tipo(activities, ["reuniao"], ini, fim, so_feitas=True)
    por_responsavel = m6_reunioes_sdr.reunioes_validadas(
        atividades_reuniao, ini, fim,
        deals_validados=deals_validados, dono_do_deal=dono_do_deal,
        sdr_ids=sdr_ids, lideranca_ids=lideranca_ids,
    )
    eventos_por_dia = defaultdict(list)
    for resp_id, atividades_resp in por_responsavel.items():
        sdr_nome = usuarios.get(resp_id)
        for a in atividades_resp:
            dia = atividade_dia(a)
            if dia is None:
                continue
            deal_id = a.get("deal_id")
            closer_id = dono_do_deal.get(deal_id)
            # "momento" tem o horário (due_time) quando a atividade tem um —
            # usado só pra ordenar QUEM bateu a meta do dia primeiro (ver
            # app._primeiro_sdr_bateu_meta); sem due_time, cai pra meia-noite
            # do próprio dia (mesmo fallback que due_datetime_brasilia usava).
            momento = atividade_momento(a) or datetime.combine(dia, datetime.min.time())
            eventos_por_dia[dia].append({
                "sdr": sdr_nome, "closer": usuarios.get(closer_id), "deal_id": deal_id,
                "momento": momento,
            })
    return eventos_por_dia
