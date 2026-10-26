"""
BOARD 5ANOS — dashboard web (Flask), painel enxuto pra outubro/2026.

Nasceu como uma versão reduzida do ARENA (setembro/2026): reaproveita os
mesmos arquivos de lógica (config.py, colaboradores.py, pipedrive_client.py,
rules.py — sincronizados manualmente com arena-dashboard/, copie de novo se
mudar algo lá) mas SEM o pódio Top 3. Tem:
  - Destaque do dia (Closer e SDR) — 1º a bater o Alvo do dia, igual já
    existia no ARENA (_primeiro_closer_bateu_meta / _primeiro_sdr_bateu_meta).
    A meta diária do Closer é comparada com a receita COM MULTIPLICADOR
    (mesmo campo já usado no Atingimento Olympus), não o valor bruto do
    negócio — pedido do João, 06/10.
  - Detalhamento do dia (SDR, com quadradinhos de progresso Validadas/
    Agendadas — igual o ARENA) e Detalhamento do dia (Closer, só squad
    OLYMPUS, com meta/vendido do dia em multiplicador) — reintroduzido a
    pedido do João, 06/10 (tinha saído na 1ª versão enxuta).
  - Meta do time — só Sniper e Olympus (Elite tirado a pedido do João, 05/10).
  - Destaque contínuo (Closer e SDR) — card que fica com a mesma pessoa até
    alguém bater o número ACUMULADO DO MÊS dela (reuniões validadas pro SDR;
    venda BRUTA acumulada no mês, sem multiplicador, pro Closer — critério
    diferente do multiplicador usado na meta diária acima, de propósito:
    pedido do João, 06/10). Mostra foto + selo de "há X dias". REESCRITO
    26/10 pra ser SEM ESTADO (ver _destaque_continuo_sem_estado): a
    liderança é recalculada do zero a cada request, simulando dia a dia os
    números já computados — não depende mais de arquivo em disco, então
    funciona igual local e na Vercel.

Rodar local:
    pip install -r requirements.txt
    cp .env.example .env   # cole seu token (ou copie o .env do arena-dashboard)
    python app.py          # abre em http://localhost:5001 (porta diferente do ARENA)
"""

# ──────────────────────────────────────────────────────────────────────
# CRN — atualização automática. Dois mecanismos OFICIAIS da própria CRN
# (não reimplementados — colados dos modelos do repositório), escolhidos
# pelo ambiente:
#   - Vercel (modelos/vercel_carregar_crn.py): a Vercel não repassa
#     variáveis de ambiente pro instalador do build, então a linha
#     `crn @ git+...` no requirements.txt falha lá. Esse modelo baixa o
#     tarball da branch main pela API do GitHub (com CRN_GITHUB_TOKEN,
#     que funciona em tempo de EXECUÇÃO, diferente do build) e injeta no
#     sys.path quando o painel liga.
#   - Local (modelos/painel_local_cabecalho.py, colado antes a pedido do
#     João 26/10 — painel rodando num PC sem o instalar.bat): confere o
#     GitHub via `git ls-remote` toda vez que abre e reinstala com pip se
#     tiver commit novo; sem Git/internet, segue com o que já tem
#     instalado.
# Detecção: a própria Vercel sempre define a env var VERCEL=1 nas
# funções Python — não é suposição nossa, é documentado pela Vercel.
# Roda ANTES de qualquer `import crn`/`import crn_bridge`. Token/URLs de
# planilha deste painel continuam vindo do .env de sempre (config.py já
# cuida disso), não duplicados aqui.
import os as _os_crn_update

if _os_crn_update.environ.get("VERCEL"):
    # --- modelos/vercel_carregar_crn.py (colado sem alteração) ---------
    import io

    def _carregar_crn():
        import importlib.util
        import shutil
        import sys
        import tarfile
        import tempfile
        if importlib.util.find_spec("crn") is not None:
            return None
        import requests
        token = (_os_crn_update.environ.get("CRN_GITHUB_TOKEN") or _os_crn_update.environ.get("GITHUB_TOKEN") or "").strip()
        if not token:
            raise RuntimeError("CRN_GITHUB_TOKEN não está nas Environment Variables da Vercel.")
        r = requests.get(
            "https://api.github.com/repos/negocios87-sketch/CRN/tarball/main",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
            timeout=30,
        )
        if r.status_code != 200:
            raise RuntimeError(f"Não consegui baixar a CRN do GitHub (HTTP {r.status_code}). Confira o CRN_GITHUB_TOKEN.")
        base = tempfile.mkdtemp(prefix="crn_")
        with tarfile.open(fileobj=io.BytesIO(r.content), mode="r:gz") as tar:
            tar.extractall(base, filter="data")
        raiz = _os_crn_update.path.join(base, _os_crn_update.listdir(base)[0])
        destino = _os_crn_update.path.join(base, "pacote", "crn")
        shutil.copytree(_os_crn_update.path.join(raiz, "lib"), destino)
        shutil.copytree(_os_crn_update.path.join(raiz, "config"), _os_crn_update.path.join(destino, "config"))
        sys.path.insert(0, _os_crn_update.path.join(base, "pacote"))
        return _os_crn_update.path.basename(raiz).rsplit("-", 1)[-1][:7]

    _COMMIT_CRN = _carregar_crn()
    import crn as _crn_startup
    if _COMMIT_CRN:
        _crn_startup.versao = lambda: _COMMIT_CRN
    print(f"[CRN] versão {_crn_startup.versao() if hasattr(_crn_startup, 'versao') else getattr(_crn_startup, '__version__', 'desconhecida')} (Vercel)")
else:
    # --- modelos/painel_local_cabecalho.py (só o trecho de auto-update) -
    import subprocess
    import sys as _sys_crn_update

    _CRN_GIT = "https://github.com/negocios87-sketch/CRN.git"

    def _atualizar_crn():
        import json as _json_crn_update
        from importlib import metadata as _metadata_crn_update
        instalada = ""
        try:
            info = _json_crn_update.loads(
                _metadata_crn_update.distribution("crn").read_text("direct_url.json") or "{}"
            )
            instalada = (info.get("vcs_info") or {}).get("commit_id", "")
        except Exception:
            pass
        try:
            saida = subprocess.run(
                ["git", "ls-remote", _CRN_GIT, "refs/heads/main"],
                capture_output=True, text=True, timeout=30, check=True,
            ).stdout
            remota = saida.split()[0] if saida else ""
        except Exception as e:
            print(f"[CRN] Não consegui consultar o GitHub ({e}). Seguindo com a versão instalada.")
            return
        if remota and remota == instalada:
            return
        print("[CRN] Regras novas no GitHub. Atualizando...")
        try:
            subprocess.run(
                [_sys_crn_update.executable, "-m", "pip", "install", "-q", "--upgrade",
                 "--force-reinstall", "--no-deps", f"crn @ git+{_CRN_GIT}"],
                check=True, timeout=300,
            )
        except Exception as e:
            print(f"[CRN] Falhou a atualização ({e}). Seguindo com a versão instalada.")

    _atualizar_crn()
    import crn as _crn_startup  # noqa: E402  (sempre depois da atualização)
    _versao_crn_startup = _crn_startup.versao() if hasattr(_crn_startup, "versao") else getattr(_crn_startup, "__version__", "desconhecida")
    print(f"[CRN] versão {_versao_crn_startup} (local)")
# ──────────────────────────────────────────────────────────────────────

import json
import math
import os
import threading
import time
import urllib.parse
from collections import defaultdict
from datetime import date, datetime, timedelta

import requests
from flask import Flask, render_template, request
from jinja2 import ChoiceLoader, FileSystemLoader
from jinja2.exceptions import TemplateNotFound

import config
import crn_bridge
import rules
from crn.base import fontes
from crn.base import fuso as crn_fuso
from crn.base import pipedrive as crn_pd
from crn.base import texto as crn_texto
from crn.base.config import campo as crn_campo
from crn.base.config import filtro as crn_filtro
from crn.regras import (
    fr2_agendamentos_dia,
    h1_hierarquia,
    m1_ganho_closer,
    m2_faturamento_closer,
    m4_ganho_sdr,
)

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, static_folder=os.path.join(_BASE_DIR, "static"))
app.jinja_loader = ChoiceLoader([
    FileSystemLoader(os.path.join(_BASE_DIR, "templates")),
    FileSystemLoader(_BASE_DIR),
])

NOME_PAINEL = "BOARD 5ANOS"

# ---------------------------------------------------------------------------
# Metas diárias FIXAS (pedido do João, 06/10) — diferente do ARENA, que
# calcula a meta diária do SDR com "ritmo" a partir da meta mensal da
# planilha (meta_reunioes / dias_uteis). Aqui a meta diária é um número
# fixo direto, sem depender da planilha de Metas pra esse cálculo (a
# planilha continua valendo pra Meta do time/mês, só a meta DIÁRIA de
# indivíduo é que virou fixa). Aplica tanto no "1º a bater a Meta do dia"
# quanto no Detalhamento com quadradinhos (os dois leem metas_diarias_sdr).
METAS_DIARIAS_SDR_PADRAO = 5
METAS_DIARIAS_SDR_EXCECOES = {
    "Bruna Goes": 7,
}

# Mesma ideia pro Closer, mas só pra 4 pessoas específicas — os demais
# continuam com a conta de sempre (meta_financeira / dias_uteis da
# planilha). Aplica tanto no "1º Closer a bater a Meta do dia" quanto no
# Detalhamento Olympus (os dois leem metas_diarias_closer).
METAS_DIARIAS_CLOSER_FIXA = 12000.0
NOMES_CLOSER_META_FIXA = {"Caique Klein", "Lucas Dias", "Michel Nascimento", "Paulo Gomes"}


def _iniciais(nome):
    partes = (nome or "").split()
    if not partes:
        return "?"
    if len(partes) == 1:
        return partes[0][:2].upper()
    return (partes[0][0] + partes[-1][0]).upper()


app.jinja_env.filters["iniciais"] = _iniciais

# Fotos do time — mesmo repositório público já usado no ARENA (ver
# arena-dashboard/app.py pra explicação completa de por que é uma lista de
# candidatas em vez de um mapeamento fixo nome -> arquivo).
FOTOS_REPO_BASE = "https://raw.githubusercontent.com/negocios87-sketch/fotos_time_comercial/main/"
FOTOS_EXTENSOES = ["jpg", "jpeg", "png", "JPG", "JPEG", "PNG"]


def _candidatos_foto(nome):
    if not nome:
        return []
    variantes_nome = []
    for variante in (nome, config._sem_acentos(nome)):
        if variante and variante not in variantes_nome:
            variantes_nome.append(variante)
    candidatos = []
    for variante in variantes_nome:
        for ext in FOTOS_EXTENSOES:
            url = FOTOS_REPO_BASE + urllib.parse.quote(f"{variante}.{ext}")
            if url not in candidatos:
                candidatos.append(url)
    return candidatos


app.jinja_env.filters["fotos"] = _candidatos_foto

# ---------------------------------------------------------------------------
# Cache em memória (mesma ideia do ARENA) — evita recalcular tudo a cada F5.
_CACHE = {}
_LOCKS = defaultdict(threading.Lock)
CACHE_TTL_SEGUNDOS = 15 * 60

# ---------------------------------------------------------------------------
# Destaque CONTÍNUO (pedido do João, 05/10) — card que só troca de pessoa
# quando o número dela supera o recorde atual.
#
# REESCRITO 26/10 (pedido do João, depois de notar que o card tinha sumido
# na Vercel) — a versão original guardava a liderança num arquivo em disco
# (destaque_continuo.json), que precisava sobreviver de uma execução pra
# outra. Isso quebra na Vercel (sistema de arquivos só leitura em
# produção, fora /tmp, que nem sobrevive entre execuções). Em vez de
# resolver com um banco externo, dava pra perceber que a liderança do mês
# inteiro é só uma FUNÇÃO dos números que a gente já calcula (eventos_
# validados_mes pro SDR, deals_won pro Closer) — não precisa de memória
# nenhuma: a cada request, _destaque_continuo_sem_estado reconstrói o
# "filme" dia a dia (acumulado até cada dia do mês) e simula a MESMA regra
# de antes (record só muda quando alguém supera estritamente o valor de
# quem está no posto; "há X dias" só reseta quando a liderança muda de
# pessoa) — zero chamada extra ao Pipedrive, funciona igual local e na
# Vercel, e resolve de graça o bug antigo do recorde "preso" em alguém que
# saiu da população válida (ele nunca nem entra na simulação).
def _destaque_continuo_sem_estado(serie_diaria, fim):
    """serie_diaria: lista de (dia, {nome: valor ACUMULADO até esse dia}),
    em ordem crescente de dia, cobrindo do início do mês até `fim`
    (inclusive). Retorna {"nome", "valor", "dias"} pronto pro template, ou
    None se ninguém pontuou ainda no mês."""
    nome_atual = valor_atual = desde = None
    for dia, candidatos in serie_diaria:
        if not candidatos:
            continue
        nome_top, valor_top = max(candidatos.items(), key=lambda kv: kv[1])
        if not valor_top or valor_top <= 0:
            continue
        if valor_atual is None or valor_top > valor_atual:
            if nome_top != nome_atual:
                desde = dia
            nome_atual, valor_atual = nome_top, valor_top
    if nome_atual is None:
        return None
    dias = (fim - desde).days + 1
    return {"nome": nome_atual, "valor": valor_atual, "dias": max(dias, 1)}


def _dias_do_mes_ate(inicio, fim):
    if fim < inicio:
        return []
    return [inicio + timedelta(days=i) for i in range((fim - inicio).days + 1)]


def _serie_diaria_validadas_sdr(eventos_validados_mes, nomes_sniper_norm, lideres_sniper_norm, inicio, fim):
    """Reuniões validadas ACUMULADAS até cada dia, por SDR — mesma
    população do Sniper (sem líderes, sem SDR_EXCLUIDOS) já usada em
    validadas_mes_por_sdr acima. Fonte: eventos_validados_mes, já
    calculado pela M6 oficial — nenhuma regra nova aqui, só acumulação."""
    acumulado = defaultdict(int)
    serie = []
    for dia in _dias_do_mes_ate(inicio, fim):
        for ev in eventos_validados_mes.get(dia, []):
            if not ev["sdr"]:
                continue
            sdr_norm = crn_texto.norm(ev["sdr"])
            if sdr_norm in lideres_sniper_norm or sdr_norm not in nomes_sniper_norm:
                continue
            acumulado[ev["sdr"]] += 1
        serie.append((dia, dict(acumulado)))
    return serie


def _serie_diaria_vendas_brutas_closer(deals_won_mes, usuarios, membros_olympus_norm, inicio, fim):
    """Venda bruta ACUMULADA até cada dia, por Closer — mesma
    elegibilidade (Colab squad OLYMPUS) de _vendas_brutas_mes_por_closer
    acima, só que repartida por dia do won_time (Brasília) em vez de um
    total único do mês."""
    por_dia = defaultdict(lambda: defaultdict(float))
    for deal in deals_won_mes:
        if not (deal.get("value") or 0) > 0:
            continue
        nome = usuarios.get(crn_texto.dono_id(deal))
        if not nome or crn_texto.norm(nome) not in membros_olympus_norm:
            continue
        if not config.deve_pontuar_como_closer(nome):
            continue
        dia = crn_fuso.data_brasil(deal.get("won_time"))
        if dia is None:
            continue
        por_dia[dia][nome] += deal.get("value") or 0
    acumulado = defaultdict(float)
    serie = []
    for dia in _dias_do_mes_ate(inicio, fim):
        for nome, v in por_dia.get(dia, {}).items():
            acumulado[nome] += v
        serie.append((dia, dict(acumulado)))
    return serie


def _valor_multiplicador(deal):
    """Campo 'Multiplicador' do negócio — receita já com o fator de forma
    de pagamento aplicado. MIGRAÇÃO CRN (22/10): mesma leitura, agora via
    crn.regras.m2_faturamento_closer.multiplicador() (M2-M) sobre uma lista
    de 1 negócio só, em vez de reler o campo na mão — campo idêntico
    (MULTIPLICADOR_FIELD_KEY == crn campo('multiplicador'), conferido)."""
    return m2_faturamento_closer.multiplicador([deal])


def _contar_agendamentos_hoje(activities, hoje, usuarios):
    """Conta quantos agendamentos cada pessoa fez hoje (atividade CRIADA
    hoje — add_time em Brasília, pro próprio dia OU pra outro dia) — regra
    FR2 da CRN (crn.regras.fr2_agendamentos_dia.agendamentos), sem
    reimplementar nada aqui: só filtra pelos 3 tipos de 'reunião' (reuniao/
    no_show/reagendamento) com negócio vinculado antes de repassar pra
    FR2, porque FR2 em si não filtra tipo/deal_id (lê qualquer atividade
    que receber).

    Retorna {nome: total} — total = 'no_dia' + 'para_outros' (toda
    atividade criada hoje, independente do due_date — mesmo critério de
    'quantas reuniões o SDR AGENDOU hoje' que o widget antigo usava,
    exceto que agora conta cada atividade individual em vez de 1 por
    grupo de due_date; ver nota de migração no topo do app.py)."""
    from crn.base.config import tipo_atividade
    codigos = {tipo_atividade(t) for t in ("reuniao", "no_show", "reagendamento")}
    filtradas = [a for a in activities if a.get("type") in codigos and a.get("deal_id")]
    por_id = fr2_agendamentos_dia.agendamentos(filtradas, hoje)
    contagem = defaultdict(int)
    for uid, c in por_id.items():
        nome = usuarios.get(uid)
        if nome:
            contagem[nome] += c["no_dia"] + c["para_outros"]
    return dict(contagem)


def _vendas_do_dia_detalhado(deals_won_hoje, usuarios, membros_olympus_norm):
    """Vendas GANHAS hoje, por Closer — quantidade, valor BRUTO e valor com
    MULTIPLICADOR (M2-M). MIGRAÇÃO CRN (22/10): elegibilidade deixou de ser
    'funil da campanha + CLOSERS_DO_MES' e passou a ser 'dono está na Colab
    deste mês com squad OLYMPUS' (membros_olympus_norm, montado em
    _calcular_dados a partir de crn_bridge.squad_do_painel — M1). 'à vista'
    continua usando G5 (quantidade de parcelas <= 1), CLOSERS_SEM_PONTUACAO
    continua sendo um ajuste do PAINEL (não é regra da CRN — gente que
    destrava reunião de SDR mas não pontua/aparece como Closer)."""
    from crn.regras import g5_parcelas
    por_closer = defaultdict(lambda: {"quantidade": 0, "valor_bruto": 0.0, "valor_multiplicador": 0.0, "a_vista": 0})
    for deal in deals_won_hoje:
        if not (deal.get("value") or 0) > 0:
            continue
        nome = usuarios.get(crn_texto.dono_id(deal))
        if not nome or crn_texto.norm(nome) not in membros_olympus_norm:
            continue
        if not config.deve_pontuar_como_closer(nome):
            continue
        info = por_closer[nome]
        info["quantidade"] += 1
        info["valor_bruto"] += deal.get("value") or 0
        info["valor_multiplicador"] += _valor_multiplicador(deal)
        if g5_parcelas.parcelas(deal) <= 1:
            info["a_vista"] += 1
    return dict(por_closer)


def _vendas_brutas_mes_por_closer(deals_won_mes, usuarios, membros_olympus_norm):
    """Venda bruta ACUMULADA NO MÊS, por Closer — alimenta o destaque
    CONTÍNUO do Closer. Mesma elegibilidade (Colab squad OLYMPUS) de
    _vendas_do_dia_detalhado."""
    por_closer = defaultdict(float)
    for deal in deals_won_mes:
        if not (deal.get("value") or 0) > 0:
            continue
        nome = usuarios.get(crn_texto.dono_id(deal))
        if not nome or crn_texto.norm(nome) not in membros_olympus_norm:
            continue
        if not config.deve_pontuar_como_closer(nome):
            continue
        por_closer[nome] += deal.get("value") or 0
    return dict(por_closer)


def _primeiro_closer_bateu_meta(deals_won_hoje, usuarios, membros_olympus_norm, metas_diarias_closer):
    """1º Closer a bater o Alvo do dia — comparado com a receita COM
    MULTIPLICADOR (M2-M), não o valor bruto. Mesma elegibilidade (Colab
    squad OLYMPUS) das outras métricas de venda acima."""
    por_closer = defaultdict(list)
    for deal in deals_won_hoje:
        nome = usuarios.get(crn_texto.dono_id(deal))
        if not nome or crn_texto.norm(nome) not in membros_olympus_norm:
            continue
        if not config.deve_pontuar_como_closer(nome):
            continue
        won_time = deal.get("won_time")
        if not won_time:
            continue
        por_closer[nome].append((won_time, _valor_multiplicador(deal)))

    candidatos = []
    for nome, vendas in por_closer.items():
        alvo = metas_diarias_closer.get(nome)
        if not alvo:
            continue
        vendas.sort(key=lambda t: t[0])
        acumulado = 0.0
        for won_time, valor in vendas:
            acumulado += valor
            if acumulado >= alvo:
                candidatos.append((won_time, nome, acumulado, alvo))
                break

    if not candidatos:
        return None
    candidatos.sort(key=lambda c: c[0])
    _, nome, valor_no_momento, alvo = candidatos[0]
    return {"nome": nome, "valor_no_momento": valor_no_momento, "alvo_diario": alvo}


def _primeiro_sdr_bateu_meta(eventos_validados_hoje, metas_diarias_sdr, agendamentos_por_sdr=None):
    """1º SDR a bater o Alvo do dia — MIGRAÇÃO CRN (22/10): a lista de
    quem validou reunião hoje (e quando) agora vem pronta de
    rules.eventos_validados_crn (regra M6 oficial), em vez de reconstruir
    grupo-por-negócio/dia aqui. `eventos_validados_hoje` é a lista de
    eventos do dia de hoje (eventos_por_dia.get(hoje, []) — cada um já tem
    'sdr'/'momento'). Continua exigindo bater as DUAS metas do dia
    (Validadas E Agendadas) pra ganhar o troféu, igual antes.
    SDRS_SEM_DESTAQUE_DIA continua sendo um ajuste do PAINEL (rampagem
    temporária), não uma regra da CRN."""
    por_sdr = defaultdict(list)
    for ev in eventos_validados_hoje:
        sdr_nome = ev["sdr"]
        if not sdr_nome or sdr_nome in config.SDRS_SEM_DESTAQUE_DIA:
            continue
        por_sdr[sdr_nome].append(ev["momento"])

    candidatos = []
    for nome, horarios in por_sdr.items():
        alvo = metas_diarias_sdr.get(nome)
        if not alvo:
            continue
        horarios.sort()
        necessarias = math.ceil(alvo)
        if len(horarios) < necessarias:
            continue
        agendamentos_hoje = (agendamentos_por_sdr or {}).get(nome, 0)
        if agendamentos_hoje < alvo:
            continue
        candidatos.append((horarios[necessarias - 1], nome, necessarias, alvo))

    if not candidatos:
        return None
    candidatos.sort(key=lambda c: c[0])
    _, nome, quantidade_no_momento, alvo = candidatos[0]
    return {"nome": nome, "quantidade_no_momento": quantidade_no_momento, "alvo_diario": alvo}


def _month_bounds(month_str):
    import calendar
    year, month = (int(x) for x in month_str.split("-"))
    ultimo_dia = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, ultimo_dia)


def _mes_atual():
    hoje = date.today()
    return f"{hoje.year:04d}-{hoje.month:02d}"


def _calcular_dados(month_str):
    """Busca tudo no Pipedrive + planilha e monta o pacote de dados que o
    template precisa.

    MIGRAÇÃO CRN (22/10) — toda busca no Pipedrive (sem filtro salvo, só
    *_do_periodo + o ÚNICO filtro oficial que a própria regra pede —
    `reuniao_validada`, pra montar deals_validados do M6) e toda regra de
    negócio (reunião validada, papel SDR/Closer, squad, dono válido,
    moeda aceita, ganho automático, licenciado, qualificador, parcelas)
    vem da biblioteca crn — nunca mais reimplementada aqui. O que CONTINUA
    sendo do PAINEL, não é regra da CRN:
      - squad do painel = só OLYMPUS (confirmado com o João, 22/10);
      - metas diárias FIXAS (METAS_DIARIAS_SDR_PADRAO/EXCECOES,
        METAS_DIARIAS_CLOSER_FIXA/NOMES_CLOSER_META_FIXA);
      - SDRS_SEM_DESTAQUE_DIA (rampagem temporária) e
        CLOSERS_SEM_PONTUACAO (quem destrava reunião mas não pontua);
      - DONOS_VALIDOS_EXTRA_FINANCEIRO_OLYMPUS — ajuste pontual pra gente
        que vende no funil Olympus mas ainda não está cadastrada na Colab
        deste mês (ver bloco "realizado_olympus" abaixo — "Faltou na
        CRN", não existe mecanismo equivalente na biblioteca);
      - destaque contínuo (estado em disco, não é cálculo de regra)."""
    month_start, month_end = _month_bounds(month_str)
    ano, mes = month_start.year, month_start.month
    avisos = []

    try:
        colab, metas = crn_bridge.carregar_colab_e_metas(ano, mes)
    except crn_bridge.fontes.FonteInvalida as e:
        avisos.append(f"Não consegui ler Colab/Metas pela CRN ({e}) — squads/metas ficam incompletos neste cálculo.")
        colab, metas = [], []

    usuarios = crn_pd.usuarios()
    funis = crn_pd.funis()
    meta_por_nome = {m["nome_norm"]: m for m in metas}

    # R2 (papel) + H1 (hierarquia) — ids do Pipedrive de quem é SDR de
    # cota e de quem é Head/Team Leader, pros parâmetros que M6 pede.
    sdr_ids, closer_ids = crn_bridge.ids_por_papel(metas, usuarios)
    lideranca_ids = crn_bridge.ids_lideranca(colab, usuarios)

    hoje = crn_fuso.hoje_brasil()

    # --- Ganhos do mês (M1/R3/R4/G1) — único GET por período, sem filtro
    # salvo (regra 3 da migração). `validos` já sai sem cortesia (R4),
    # outra moeda (R3) e ganho automático (G1).
    deals_won = crn_pd.ganhos_do_periodo(month_start, month_end)
    ganhos = m1_ganho_closer.separar_ganhos(deals_won, ano, mes, usuarios)
    validos = ganhos["validos"]
    # REMOVIDO 23/10 (pedido do João: "pode remover isso!") — o aviso de
    # R3/R4/G1 (cortesia/fora do BRL/ganho automático fora dos totais) saía
    # na tela. A regra em si CONTINUA valendo (ganhos["validos"], usado em
    # todo o resto do cálculo, já sai sem esses três grupos — só o AVISO
    # visual sumiu, o comportamento do painel não muda).

    # --- Reuniões validadas no mês (M6) — o filtro oficial `reuniao_
    # validada` só serve pra montar deals_validados/dono_do_deal (é assim
    # que a própria regra espera receber esse conjunto).
    #
    # As atividades do mês: atividades_do_periodo(ini, fim) sem nenhum
    # filter_id varre TODO tipo de atividade (ligação, e-mail, tarefa...)
    # ordenado por due_date, e nessa conta isso passa de 200 páginas antes
    # de chegar no início do período (volume de atividade futura de todo
    # tipo é grande demais) — RuntimeError de MAX_PAGINAS em
    # crn.base.pipedrive, bug real da CRN, não daqui. A correção NÃO é
    # trocar de filtro: o próprio docstring de m6_reunioes_sdr já diz que
    # as atividades devem vir do filtro oficial 1310451 (filtro("reunioes")
    # na config da CRN — só tipo Reunião). Passando esse filter_id pra
    # atividades_do_periodo (a própria base.pipedrive aceita filter_id como
    # kwarg extra, repassado direto pra query), o volume cai muito (só
    # reuniões, não qualquer atividade) e a varredura por página volta a
    # fechar bem antes do limite — confirmado ao vivo em 23/10: ~500
    # atividades cobrem só alguns dias por página, longe de 200 páginas
    # pro mês inteiro. Isso também elimina a divergência que o filtro
    # salvo FILTER_ID_ATIVIDADES_REALIZADAS_MES (1671347, feito à mão aqui
    # no painel, com condições próprias) podia introduzir frente ao que a
    # regra M6 realmente espera receber.
    deals_validados, dono_do_deal, _ = crn_bridge.deals_validados_e_donos()
    atividades_mes = crn_pd.atividades_do_periodo(
        month_start, month_end, filter_id=crn_filtro("reunioes")
    )
    eventos_validados_mes = rules.eventos_validados_crn(
        atividades_mes, month_start, month_end,
        deals_validados=deals_validados, dono_do_deal=dono_do_deal,
        sdr_ids=sdr_ids, lideranca_ids=lideranca_ids, usuarios=usuarios,
    )

    # SOBREPOSIÇÃO LOCAL 23/10 (pedido explícito do João, depois de
    # confirmarmos ao vivo o problema) — líderes sem meta individual de
    # reuniões (ex.: Stephanie Nascimento, Marlon Silva: estão em
    # lideranca_ids via H1, mas não têm meta_reunioes própria na aba
    # Metas) devem contar no total do time Sniper mesmo sem cota pessoal.
    # A chamada oficial crn.regras.m6_reunioes_sdr.reunioes_validadas()
    # não credita nenhuma reunião pra esse grupo este mês — investigado ao
    # vivo em 23/10 com 4 rodadas de depuração (print de todos os
    # responsáveis creditados pela M6, chamada direta da função oficial,
    # réplica portão-a-portão de TODA a lógica documentada — feita, dentro
    # do período, dedup, deal validado via filtro `reuniao_validada`,
    # auto-exclusão responsável==dono, e RN1 quando o dono é SDR de cota
    # sem cargo de liderança): nenhuma das ~30 reuniões de Stephanie/
    # Marlon no mês bateu em qualquer motivo de exclusão documentado — a
    # causa raiz dentro da versão da biblioteca crn instalada não foi
    # encontrada. João decidiu (23/10): "caso o crn não deixe vamos criar
    # uma regra para sobrepor".
    #
    # Esta sobreposição replica EXATAMENTE os mesmos critérios da M6
    # (mesmas funções crn.regras._comum.deduplicar/no_intervalo e
    # crn.regras.m6_reunioes_sdr._rn1, importadas da própria biblioteca —
    # nada reescrito à mão), mas só roda pra quem está em
    # `ids_lideres_sem_meta_reunioes` (líder, H1, sem meta_reunioes
    # própria). Não duplica ninguém: só entra quem a chamada oficial acima
    # não credita. Se um dia a CRN corrigir a causa raiz lá na origem,
    # basta remover este bloco (o resto do painel não depende dele).
    from crn.regras._comum import deduplicar as _crn_deduplicar, no_intervalo as _crn_no_intervalo
    from crn.regras._atividades import do_tipo as _crn_do_tipo
    from crn.regras.m6_reunioes_sdr import _rn1 as _crn_rn1
    from crn.base.texto import feita as _crn_feita, responsavel_id as _crn_responsavel_id
    from crn.base.fuso import atividade_dia as _crn_atividade_dia, atividade_momento as _crn_atividade_momento

    ids_lideres_sem_meta_reunioes = {
        uid for uid in lideranca_ids
        if meta_por_nome.get(crn_texto.norm(usuarios.get(uid, "")), {}).get("meta_reunioes") is None
    }
    if ids_lideres_sem_meta_reunioes:
        from crn.regras.m6_reunioes_sdr import reunioes_validadas as _crn_reunioes_validadas
        _atividades_reuniao = _crn_do_tipo(atividades_mes, ["reuniao"], month_start, month_end, so_feitas=True)
        _ja_creditados_oficial = set(_crn_reunioes_validadas(
            _atividades_reuniao, month_start, month_end,
            deals_validados=deals_validados, dono_do_deal=dono_do_deal,
            sdr_ids=sdr_ids, lideranca_ids=lideranca_ids,
        ).keys())
        _alvo_override = ids_lideres_sem_meta_reunioes - _ja_creditados_oficial
        if _alvo_override:
            _por_deal_override = {}
            for _a in _atividades_reuniao:
                if _a.get("deal_id"):
                    _por_deal_override.setdefault(_a["deal_id"], []).append(_a)
            for _a in _crn_deduplicar(_atividades_reuniao):
                resp = _crn_responsavel_id(_a)
                if resp not in _alvo_override:
                    continue
                deal = _a.get("deal_id")
                if not deal or not _crn_feita(_a) or not _crn_no_intervalo(_crn_atividade_dia(_a), month_start, month_end):
                    continue
                if deal not in deals_validados:
                    continue
                dono = dono_do_deal.get(deal)
                if dono is not None and resp == dono:
                    continue
                if dono in sdr_ids and dono not in lideranca_ids and not _crn_rn1(_a, _por_deal_override.get(deal, []), sdr_ids):
                    continue
                dia = _crn_atividade_dia(_a)
                if dia is None:
                    continue
                closer_id = dono_do_deal.get(deal)
                momento = _crn_atividade_momento(_a) or datetime.combine(dia, datetime.min.time())
                eventos_validados_mes[dia].append({
                    "sdr": usuarios.get(resp), "closer": usuarios.get(closer_id),
                    "deal_id": deal, "momento": momento,
                })

    reunioes_validadas_no_mes_total = sum(len(evs) for evs in eventos_validados_mes.values())

    # --- Detalhe das reuniões validadas no mês, por SDR (botão "Detalhes"
    # no Detalhamento do dia · SDR).
    reunioes_detalhe_por_sdr = defaultdict(list)
    for dia, eventos in eventos_validados_mes.items():
        for ev in eventos:
            if not ev["sdr"]:
                continue
            reunioes_detalhe_por_sdr[ev["sdr"]].append({
                "data": dia.strftime("%d/%m"),
                "data_iso": dia.isoformat(),
                "deal_id": ev["deal_id"],
                "deal_titulo": f"Negócio #{ev['deal_id']}",
                "closer": ev["closer"],
            })
    for lista in reunioes_detalhe_por_sdr.values():
        lista.sort(key=lambda r: r["data_iso"])

    # --- Widgets de "HOJE" — tudo derivado dos mesmos dados do mês já
    # buscados acima (sem GET extra): eventos_validados_mes já tem os
    # eventos de hoje, deals_won já cobre o mês (hoje está dentro dele).
    eventos_validados_hoje = eventos_validados_mes.get(hoje, [])
    validadas_hoje_por_sdr = defaultdict(int)
    for ev in eventos_validados_hoje:
        if ev["sdr"]:
            validadas_hoje_por_sdr[ev["sdr"]] += 1

    # "Agendadas" hoje (FR2) — atividade CRIADA hoje (add_time), feita ou
    # não. atividades_mes agora vem escopado pelo filtro oficial da CRN
    # (filtro("reunioes"), só tipo Reunião) — não dá pra reusar aqui porque
    # esse filtro não cobre No Show/Reagendamento, que esse widget também
    # conta. Usa o 2º filtro salvo, FILTER_ID_ATIVIDADES_AGENDADAS_HOJE
    # (mesma lista de tipos do painel antigo, sem corte de concluído).
    # ATENÇÃO: esse filtro
    # ainda está com a condição de FUNIL no Pipedrive (ver config.py) — o
    # João precisa remover ela, senão volta a excluir agendamento de SDR
    # pra closer de outro funil, igual o caso da Bruna Goes.
    if month_str == _mes_atual():
        atividades_hoje_criadas = crn_pd.atividades(filter_id=config.FILTER_ID_ATIVIDADES_AGENDADAS_HOJE)
    else:
        # Mês passado: "hoje" nunca cai dentro do período pedido, então o
        # resultado sempre dá vazio de qualquer forma — reusa atividades_mes
        # (período) só pra não fazer um GET a mais à toa.
        atividades_hoje_criadas = atividades_mes
    agendamentos_hoje_por_sdr = _contar_agendamentos_hoje(atividades_hoje_criadas, hoje, usuarios)

    deals_won_hoje = [d for d in deals_won if crn_fuso.data_brasil(d.get("won_time")) == hoje]

    # --- Squad do painel = só OLYMPUS (Colab subárea MGM, confirmado com
    # o João 22/10) — substitui inteiramente CARGOS_ATINGIMENTO_FINANCEIRO/
    # membros_olympus do painel antigo (que exigia funil da campanha +
    # cargo financeiro). Aqui basta estar cadastrado na Colab deste mês
    # com esse squad.
    membros_olympus = [p for p in colab if crn_bridge.squad_do_painel(p)]
    membros_olympus_norm = {p["nome_norm"] for p in membros_olympus}

    vendas_do_dia_detalhado = _vendas_do_dia_detalhado(deals_won_hoje, usuarios, membros_olympus_norm)

    # R2 (papel) com nomes como aparecem na Colab deste mês (pro resto do
    # painel usar nome "de exibição", não nome_norm) — SDR_EXCLUIDOS
    # continua sendo um ajuste do painel por cima do papel oficial.
    excluidos_normalizados = {crn_texto.norm(n) for n in config.SDR_EXCLUIDOS}
    sdrs_norm_oficial = {m["nome_norm"] for m in metas if m["papel"] == "sdr"}
    closers_norm_oficial = {m["nome_norm"] for m in metas if m["papel"] == "closer"}
    nomes_sdr = {
        p["nome"] for p in colab
        if p["nome_norm"] in sdrs_norm_oficial and p["nome_norm"] not in excluidos_normalizados
    }
    nomes_closer = {
        p["nome"] for p in colab
        if p["nome_norm"] in closers_norm_oficial and p["nome_norm"] not in excluidos_normalizados
    }

    # --- Meta diária do SDR: FIXA (ajuste do painel, não é regra da CRN —
    # ver METAS_DIARIAS_SDR_PADRAO/EXCECOES no topo do arquivo).
    _sdr_excecoes_norm = {crn_texto.norm(n): v for n, v in METAS_DIARIAS_SDR_EXCECOES.items()}
    metas_diarias_sdr = {}
    alvo_do_dia_sdr = []
    for nome in sorted(nomes_sdr):
        alvo_diario = _sdr_excecoes_norm.get(crn_texto.norm(nome), METAS_DIARIAS_SDR_PADRAO)
        metas_diarias_sdr[nome] = alvo_diario
        feitas_hoje = validadas_hoje_por_sdr.get(nome, 0)
        agendamentos_hoje = agendamentos_hoje_por_sdr.get(nome, 0)
        reunioes_mes_nome = reunioes_detalhe_por_sdr.get(nome, [])
        alvo_do_dia_sdr.append({
            "nome": nome,
            "alvo_diario": alvo_diario,
            "feitas_hoje": feitas_hoje,
            "bateu": feitas_hoje >= alvo_diario,
            "agendamentos_hoje": agendamentos_hoje,
            "bateu_agendamento": agendamentos_hoje >= alvo_diario,
            "reunioes_mes": reunioes_mes_nome,
            # Contagem pro resumo do botão "detalhamento" (pedido do João,
            # 23/10: "coloque nos detalhes quanto cada um tem, uma
            # contagem") — mesmo tamanho de reunioes_mes, só pra não
            # precisar contar no template.
            "qtd_reunioes_mes": len(reunioes_mes_nome),
        })
    alvo_do_dia_sdr.sort(key=lambda d: (-d["feitas_hoje"], d["nome"]))

    # --- Meta diária do Closer: fixa pras pessoas em NOMES_CLOSER_META_
    # FIXA (ajuste do painel); os demais usam meta_financeira/dias_uteis
    # da aba Metas — dias_uteis segue vindo da Metas por pessoa (CRN usa
    # A2/dias_uteis_calendario só pro total do mês, não por pessoa; a
    # coluna de dias úteis individual da aba Metas é um ajuste do painel,
    # não uma regra da CRN).
    #
    # "Faltou na CRN": a aba Metas oficial da CRN (crn.base.fontes.
    # carregar_metas) só tem nome/meta_reunioes/meta_financeira/papel —
    # NÃO tem a coluna "Dias Úteis" POR PESSOA que a planilha antiga usava
    # (que também levava em conta rampagem/entrada no meio do mês). Pra
    # quem não está em NOMES_CLOSER_META_FIXA, a meta diária agora usa os
    # dias úteis do CALENDÁRIO do mês inteiro (A2 — crn.base.fontes.
    # dias_uteis_total, com feriados de URL_FERIADOS), igual pra todo
    # mundo — perde a nuance de alguém que entrou no meio do mês. Avisar
    # o João se isso distorcer a meta de quem está em rampagem.
    try:
        feriados = fontes.carregar_feriados()
        dias_uteis_mes = fontes.dias_uteis_total(ano, mes, feriados)
    except crn_bridge.fontes.FonteInvalida as e:
        avisos.append(f"Não consegui ler Feriados pela CRN ({e}) — meta diária do Closer (fora dos fixos) ficou incompleta.")
        dias_uteis_mes = None

    _nomes_closer_fixa_norm = {crn_texto.norm(n) for n in NOMES_CLOSER_META_FIXA}
    metas_diarias_closer = {}
    for nome in nomes_closer:
        if crn_texto.norm(nome) in _nomes_closer_fixa_norm:
            metas_diarias_closer[nome] = METAS_DIARIAS_CLOSER_FIXA
            continue
        meta = meta_por_nome.get(crn_texto.norm(nome))
        if not meta or not meta.get("meta_financeira") or not dias_uteis_mes:
            continue
        metas_diarias_closer[nome] = meta["meta_financeira"] / dias_uteis_mes

    # --- Meta do time: SNIPER e OLYMPUS.
    #
    # OLYMPUS ("% da Meta do Mês - Batida"): realizado = M2-M (multiplicador)
    # dos ganhos válidos (M1) cujo squad da venda (M1.squad_da_venda, com a
    # exceção de head — H1 — pro funil dela) é "Olympus"; meta = soma de
    # meta_financeira (Metas) de quem está na Colab deste mês com squad
    # Olympus. Nem um nem outro depende mais de funil/pipeline específico
    # — é 100% squad da Colab, como a CRN define (M1/A1).
    ganhos_por_closer_colab = m1_ganho_closer.ganhos_por_closer(validos, colab, funis, usuarios)
    deals_olympus = [
        d for info in ganhos_por_closer_colab.values() for d in info["deals"]
        if info["squad_por_deal"].get(d.get("id")) == "Olympus"
    ]
    realizado_olympus = m2_faturamento_closer.multiplicador(deals_olympus)
    meta_olympus = sum(
        meta_por_nome[p["nome_norm"]]["meta_financeira"]
        for p in membros_olympus
        if p["nome_norm"] in meta_por_nome and meta_por_nome[p["nome_norm"]].get("meta_financeira")
    )

    # "Faltou na CRN" — DONOS_VALIDOS_EXTRA_FINANCEIRO_OLYMPUS (Thais
    # Montalvão/Fernanda Alves, pedido do João 09/10): gente que vende no
    # funil Olympus mas ainda não está cadastrada na Colab deste mês. A
    # CRN não tem um mecanismo pra isso (squad vem 100% da Colab) — ajuste
    # pontual do painel, somado por fora, só pra quem NÃO está em colab
    # ainda (senão dobraria a conta de quem já está).
    colab_norm_set = {p["nome_norm"] for p in colab}
    _nomes_financeiro_olympus_extra_norm = {
        crn_texto.norm(n) for n in config.DONOS_VALIDOS_EXTRA_FINANCEIRO_OLYMPUS
    }
    for deal in validos:
        dono_norm = crn_texto.norm(usuarios.get(crn_texto.dono_id(deal), ""))
        if dono_norm not in _nomes_financeiro_olympus_extra_norm or dono_norm in colab_norm_set:
            continue
        if deal.get("pipeline_id") is not None and int(deal["pipeline_id"]) == config.PIPELINE_IDS["OLYMPUS"]:
            realizado_olympus += _valor_multiplicador(deal)

    # SNIPER ("Atingimento% - Final" = Financeiro×30% + Reuniões×70%, sem
    # teto): reuniões = eventos M6 cujo SDR está na subárea Sniper da
    # Colab deste mês (qualquer funil, a regra oficial não filtra funil);
    # financeiro = M4 (ganhos atribuídos ao SDR via campo Qualificador —
    # G7 já descarta "N/A"/vazio) restrito à mesma população Sniper. Meta
    # (dos dois lados) = soma de Metas de quem é SDR (R2) OU Head/Team
    # Leader (H1) dentro da subárea Sniper — substitui inteiramente
    # LIDERES_QUE_AGENDAM_COMO_SDR (a exceção nomeada da Stephanie/Marlon
    # virou "é líder de squad Sniper na Colab", sem lista fixa de nome).
    #
    # CORRIGIDO 23/10 — achado comparando com o comportamento documentado
    # no painel antigo (test_smoke.py, caso "financeiro_sniper_exclui_sdr_
    # excluido_e_qualificador_na", bug real de produção corrigido em 07/10):
    # SDR_EXCLUIDOS (Mylena Oliveira, Priscila Ribeiro, Thiago Santos,
    # Raphaela Moutinho, Denise Mussolin, Matheus Paz) precisa continuar de
    # fora do total do SQUAD Sniper inteiro (reuniões E financeiro), não só
    # dos painéis individuais — são pessoas que o João confirmou que NUNCA
    # devem contar (ex: Mylena, cujo volume alto é sessão de onboarding em
    # grupo, não reunião comercial 1:1 de verdade), diferente de Stephanie/
    # Marlon (líderes que PODEM contar no total do time, só não aparecem
    # nos painéis individuais — esses dois nunca estiveram em SDR_EXCLUIDOS,
    # então o filtro abaixo não afeta a decisão "1" que o João já confirmou
    # sobre eles). Sem isso, a migração reintroduziu o mesmo bug de
    # inflação que já tinha sido corrigido uma vez (R$119.800 indevidos,
    # 07/10).
    nomes_sniper_norm = {p["nome_norm"] for p in colab if crn_texto.norm(p.get("subarea") or "") == "sniper"}
    nomes_sniper_norm -= excluidos_normalizados
    lideres_sniper_norm = {
        p["nome_norm"] for p in colab
        if p["nome_norm"] in nomes_sniper_norm
        and (h1_hierarquia.eh_team_leader(p, colab) or h1_hierarquia.eh_head(p, colab))
    }
    populacao_meta_sniper = (sdrs_norm_oficial | lideres_sniper_norm) & nomes_sniper_norm
    # DEBUG TEMPORÁRIO 23/10 — João mostrou a planilha Metas/Colab: lá
    # Stephanie tem 23 reuniões validadas e Marlon 6, mas elas não aparecem
    # no total do Sniper do painel. Hipótese: a subárea delas na Colab não
    # está literalmente como "Sniper" (por serem líderes) — aí
    # nomes_sniper_norm (linha 701, filtro por subarea=="sniper") já exclui
    # as duas ANTES de qualquer coisa, mesmo que a M6 credite as reuniões
    # pra elas. Esse print confirma isso olhando a Colab direto.
    for _nome_alvo in ("Stephanie Nascimento", "Marlon Silva"):
        _nn = crn_texto.norm(_nome_alvo)
        _entrada = next((p for p in colab if p["nome_norm"] == _nn), None)
        print(
            f"[SNIPER DEBUG] {_nome_alvo}: na Colab?", _entrada is not None,
            "| subarea:", _entrada.get("subarea") if _entrada else None,
            "| em nomes_sniper_norm?", _nn in nomes_sniper_norm,
            "| em lideres_sniper_norm?", _nn in lideres_sniper_norm,
            "| em populacao_meta_sniper?", _nn in populacao_meta_sniper,
        )

    # REVERTIDO DE VOLTA 23/10 (pedido do João, achado ao vivo no negócio
    # 243094: a atividade "de verdade" ["Reunião Board Academy..."] ficou
    # com owner_id do CLOSER mas creator_user_id da Stephanie, e uma SEGUNDA
    # atividade ["Agendamento Reunião..."], criada minutos depois, tem
    # owner_id = o SDR de verdade (Vitor Soares). "Como definimos na CRN,
    # não vamos mais olhar quem criou a atividade" — a tentativa anterior
    # (regra ANTIGA do painel, rules._eventos_reuniao_validada_por_dia /
    # _sdr_id_e_nome) reintroduz exatamente isso: quando ninguém do grupo
    # tem OWNER na subárea Sniper, ela cai pro CRIADOR como último recurso
    # — igual a regra oficial M6 nunca faz. Essa varredura por criador é a
    # fonte mais provável do excesso de ~7 reuniões frente ao cálculo manual
    # do João (462 vs 455). Voltando pra M6 pura (eventos_validados_mes, já
    # calculada acima — responsavel_id da atividade, SEM fallback nenhum
    # pra creator_user_id), só filtrando pela população Sniper (nomes_
    # sniper_norm, já sem SDR_EXCLUIDOS) — nada de regra reimplementada
    # aqui, só filtragem de população em cima do que a CRN devolve.
    reunioes_detalhe_sniper = defaultdict(list)
    for _dia, _eventos in eventos_validados_mes.items():
        for _ev in _eventos:
            if not _ev["sdr"] or crn_texto.norm(_ev["sdr"]) not in nomes_sniper_norm:
                continue
            reunioes_detalhe_sniper[_ev["sdr"]].append({
                "data": _dia.strftime("%d/%m"),
                "data_iso": _dia.isoformat(),
                "deal_id": _ev["deal_id"],
                "deal_titulo": f"Negócio #{_ev['deal_id']}",
                "closer": _ev["closer"],
            })
    for _lista in reunioes_detalhe_sniper.values():
        _lista.sort(key=lambda r: r["data_iso"])
    detalhe_reunioes_lista = sorted(
        (
            {"nome": nome, "qtd_reunioes_mes": len(lista), "reunioes_mes": lista}
            for nome, lista in reunioes_detalhe_sniper.items()
        ),
        key=lambda d: -d["qtd_reunioes_mes"],
    )
    reunioes_validadas_no_mes = sum(d["qtd_reunioes_mes"] for d in detalhe_reunioes_lista)
    print(
        "[SNIPER DEBUG] total:", reunioes_validadas_no_mes,
        "| por SDR:", {d["nome"]: d["qtd_reunioes_mes"] for d in detalhe_reunioes_lista},
    )
    opcoes_qualificador = crn_pd.opcoes_campo(crn_campo("qualificador"))
    ganhos_por_sdr_m4 = m4_ganho_sdr.ganhos_por_sdr(validos, opcoes_qualificador)
    realizado_financeiro_sniper = sum(
        m2_faturamento_closer.multiplicador(deals)
        for nome_norm, deals in ganhos_por_sdr_m4.items() if nome_norm in nomes_sniper_norm
    )
    meta_reunioes_sniper = sum(
        meta_por_nome[n]["meta_reunioes"] for n in populacao_meta_sniper
        if n in meta_por_nome and meta_por_nome[n].get("meta_reunioes")
    )
    meta_financeira_sniper = sum(
        meta_por_nome[n]["meta_financeira"] for n in populacao_meta_sniper
        if n in meta_por_nome and meta_por_nome[n].get("meta_financeira")
    )
    # DEBUG TEMPORÁRIO 23/10 — pra responder "a meta você tá pegando de
    # onde?": meta_reunioes_sniper vem 100% da aba Metas (crn.base.fontes.
    # carregar_metas, mesma fonte oficial da CRN — "a planilha metas" que
    # o João citou), somando meta_reunioes de quem está em
    # populacao_meta_sniper (SDR de cota OU líder do squad Sniper) E tem
    # meta_reunioes preenchida. Se o total não bate com 636, é porque
    # populacao_meta_sniper tem gente a mais/a menos que os 8 SDRs de cota
    # do time (líder normalmente não tem meta_reunioes própria na planilha,
    # por isso não soma nada mesmo entrando na população). Print mostra
    # nome a nome pra achar a diferença.
    print(
        "[SNIPER DEBUG] população da meta:",
        {n: meta_por_nome.get(n, {}).get("meta_reunioes") for n in sorted(populacao_meta_sniper)},
    )
    print("[SNIPER DEBUG] meta_reunioes_sniper total:", meta_reunioes_sniper)

    def _pct_atingimento(realizado, meta):
        if not meta:
            return None
        return round((realizado / meta) * 100, 1)

    def _razao_pct(realizado, meta):
        """Mesma conta de _pct_atingimento, mas SEM arredondar — usada só
        pro Sniper (ver _atingimento_final abaixo)."""
        if not meta:
            return None
        return (realizado / meta) * 100

    def _atingimento_final(financeiro_pct, reunioes_pct):
        """Financeiro×30% + Reuniões×70%, sem teto (mesma fórmula do painel
        grande). Se faltar meta de um dos dois lados, usa só o outro em vez
        de quebrar a conta inteira.

        CORRIGIDO 06/10 (pedido do João: '12,5% no painel grande vs 13% aqui
        — pode ser arredondamento?') — SIM, era isso: antes, Financeiro% e
        Reuniões% eram arredondados pra 1 casa CADA UM antes de combinar, e
        só depois o resultado da combinação era arredondado de novo —
        arredondamento duplo, que pode desviar o final em algumas décimas
        do que dá arredondando só uma vez no final. Agora financeiro_pct e
        reunioes_pct chegam aqui com precisão cheia (ver _razao_pct acima,
        chamada em vez de _pct_atingimento pro Sniper) e só o resultado
        final da combinação é arredondado."""
        if financeiro_pct is None and reunioes_pct is None:
            return None
        if financeiro_pct is None:
            return round(reunioes_pct, 1)
        if reunioes_pct is None:
            return round(financeiro_pct, 1)
        return round(financeiro_pct * 0.30 + reunioes_pct * 0.70, 1)

    atingimento_reunioes_sniper = _razao_pct(reunioes_validadas_no_mes, meta_reunioes_sniper)
    atingimento_financeiro_sniper = _razao_pct(realizado_financeiro_sniper, meta_financeira_sniper)

    squads = {
        "OLYMPUS": {
            "realizado": realizado_olympus,
            "meta": meta_olympus,
            "atingimento": _pct_atingimento(realizado_olympus, meta_olympus),
        },
        "SNIPER": {
            "realizado": reunioes_validadas_no_mes,
            "meta": meta_reunioes_sniper,
            "atingimento": _atingimento_final(atingimento_financeiro_sniper, atingimento_reunioes_sniper),
            # Expostos à parte (pedido do João 06/10, pra comparar com o
            # painel grande que mostra "% Reu" e "% Ganhos" separados) —
            # só pra exibição/depuração, não mudam a conta do atingimento
            # final acima.
            "financeiro_pct": round(atingimento_financeiro_sniper, 1) if atingimento_financeiro_sniper is not None else None,
            "reunioes_pct": round(atingimento_reunioes_sniper, 1) if atingimento_reunioes_sniper is not None else None,
            "financeiro_realizado": realizado_financeiro_sniper,
            "financeiro_meta": meta_financeira_sniper,
        },
    }

    # --- Detalhamento Closer (só squad OLYMPUS): meta do dia e vendido
    # hoje em MULTIPLICADOR (M2-M). MIGRAÇÃO CRN (22/10): a população
    # desta tabela virou "está na Colab deste mês com squad Olympus"
    # (membros_olympus) em vez de "papel Closer OU subárea MGM/Atlantis
    # com cargo financeiro" — simplificação aceita junto com a decisão de
    # squad só-Olympus; quem for subárea Atlantis deixa de aparecer aqui
    # até ser cadastrado na Colab com squad Olympus (antes aparecia por
    # uma exceção nomeada só pro caso da Amanda Leal — "Faltou na CRN" se
    # isso for pedido de volta).
    closers_olympus = []
    for p in sorted(membros_olympus, key=lambda p: p["nome"]):
        nome = p["nome"]
        alvo_diario = metas_diarias_closer.get(nome)
        if not alvo_diario:
            continue
        info = vendas_do_dia_detalhado.get(nome, {})
        vendido_hoje_mult = info.get("valor_multiplicador", 0.0)
        closers_olympus.append({
            "nome": nome,
            "alvo_diario": alvo_diario,
            "vendido_hoje": vendido_hoje_mult,
            "bateu": vendido_hoje_mult >= alvo_diario,
            "a_vista_hoje": info.get("a_vista", 0),
        })
    closers_olympus.sort(key=lambda c: (-c["vendido_hoje"], c["nome"]))

    # --- Destaque do dia: 1º Closer e 1º SDR a bater o Alvo do dia (reseta
    # sozinho na virada da meia-noite).
    primeiro_sdr_dia = _primeiro_sdr_bateu_meta(
        eventos_validados_hoje, metas_diarias_sdr, agendamentos_por_sdr=agendamentos_hoje_por_sdr,
    )
    primeiro_closer_dia = _primeiro_closer_bateu_meta(deals_won_hoje, usuarios, membros_olympus_norm, metas_diarias_closer)

    # --- Destaque CONTÍNUO (ver _atualizar_destaque_continuo acima) —
    # acumulado do MÊS pros dois (reuniões validadas pro SDR; venda BRUTA
    # pro Closer). resetar_em_autosuperacao=False: só troca o "desde"
    # (zera os dias) se a LIDERANÇA mudar de pessoa. Esse card é só pra
    # SDR de cota de verdade do time SNIPER (substitui LIDERANCAS_FIXAS,
    # agora é squad Sniper). Precisa restringir a nomes_sniper_norm
    # explicitamente (não dá pra confiar só em "tem reunião validada no
    # mês" — isso pega SDR de QUALQUER squad). nomes_sniper_norm já sai
    # sem SDR_EXCLUIDOS (Raphaela Moutinho, Mylena Oliveira etc. nunca
    # aparecem aqui), e líder de squad Sniper (H1 — lideres_sniper_norm)
    # conta na Meta do time SNIPER mas não disputa esse destaque.
    validadas_mes_por_sdr = defaultdict(int)
    for evs in eventos_validados_mes.values():
        for ev in evs:
            if not ev["sdr"]:
                continue
            sdr_norm = crn_texto.norm(ev["sdr"])
            if sdr_norm in lideres_sniper_norm or sdr_norm not in nomes_sniper_norm:
                continue
            validadas_mes_por_sdr[ev["sdr"]] += 1
    vendido_bruto_mes_por_closer = _vendas_brutas_mes_por_closer(deals_won, usuarios, membros_olympus_norm)
    # SEM ESTADO (ver nota 26/10 acima da função) — funciona igual local e
    # na Vercel, nenhuma leitura/escrita em disco.
    _fim_destaque_continuo = min(hoje, month_end)
    destaque_continuo_sdr = _destaque_continuo_sem_estado(
        _serie_diaria_validadas_sdr(
            eventos_validados_mes, nomes_sniper_norm, lideres_sniper_norm, month_start, _fim_destaque_continuo
        ),
        _fim_destaque_continuo,
    )
    destaque_continuo_closer = _destaque_continuo_sem_estado(
        _serie_diaria_vendas_brutas_closer(
            deals_won, usuarios, membros_olympus_norm, month_start, _fim_destaque_continuo
        ),
        _fim_destaque_continuo,
    )

    return {
        "nome_painel": NOME_PAINEL,
        "month": month_str,
        "gerado_em": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "squads": squads,
        "primeiro_sdr_dia": primeiro_sdr_dia,
        "primeiro_closer_dia": primeiro_closer_dia,
        "alvo_do_dia_sdr": alvo_do_dia_sdr,
        "detalhe_reunioes_lista": detalhe_reunioes_lista,
        "closers_olympus": closers_olympus,
        "destaque_continuo_sdr": destaque_continuo_sdr,
        "destaque_continuo_closer": destaque_continuo_closer,
        "mostrar_destaque_continuo": True,
        "hoje": hoje.strftime("%d/%m/%Y"),
        "avisos": avisos,
        # Carimbo de parâmetros com a versão da CRN (regra 4 da migração)
        # — crn.versao() NÃO EXISTE na biblioteca instalada (só __version__,
        # "Faltou na CRN"); usa isso até a CRN expor uma função oficial.
        "carimbo_crn": crn_bridge.carimbo_parametros(month_str),
    }


def _dados_com_cache(month_str, forcar=False):
    agora = time.time()
    cache_entry = _CACHE.get(month_str)
    if not forcar and cache_entry and (agora - cache_entry["ts"]) < CACHE_TTL_SEGUNDOS:
        return cache_entry["dados"]
    with _LOCKS[month_str]:
        agora = time.time()
        cache_entry = _CACHE.get(month_str)
        if not forcar and cache_entry and (agora - cache_entry["ts"]) < CACHE_TTL_SEGUNDOS:
            return cache_entry["dados"]
        dados = _calcular_dados(month_str)
        _CACHE[month_str] = {"ts": agora, "dados": dados}
        return dados


def _pagina_carregando():
    return f"""<!doctype html>
<html lang="pt-br">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{NOME_PAINEL}</title>
<style>
  html, body {{ margin: 0; padding: 0; height: 100%; background: #000; }}
  body {{ display: flex; align-items: center; justify-content: center; font-family: system-ui, sans-serif; }}
  .msg {{ color: #f4c542; font-size: 1.5rem; font-weight: 700; letter-spacing: 1px; text-align: center; padding: 0 24px; }}
</style>
</head>
<body>
  <div class="msg" id="msg">Carregando...</div>
  <script>
    (function () {{
      var url = new URL(window.location.href);
      url.searchParams.set("_carregado", "1");
      fetch(url.toString())
        .then(function (r) {{ return r.text(); }})
        .then(function (html) {{
          // CORRIGIDO 07/10 (pedido do João: "a cada 15 min volta pra tela
          // de Carregando...") — document.write troca o CONTEÚDO da
          // página, mas não atualiza a URL da barra de endereço, que
          // ficava parada em "/" (sem _carregado=1). O auto-refresh do
          // próprio dashboard (a cada 15 min) recarrega a URL que está
          // na barra — sem este replaceState, ele recarregava a URL
          // crua e caía nesta tela de novo a cada ciclo, pra sempre.
          history.replaceState(null, "", url.toString());
          document.open();
          document.write(html);
          document.close();
        }})
        .catch(function () {{
          document.getElementById("msg").textContent = "Erro de rede — tentando de novo...";
          setTimeout(function () {{ window.location.reload(); }}, 5000);
        }});
    }})();
  </script>
</body>
</html>"""


def _pagina_erro_pipedrive(erro, month_str, modo_tv=False, tv_param=""):
    auto_refresh = (
        f'<meta http-equiv="refresh" content="30;url=?month={month_str}&refresh=1{tv_param}">'
        if modo_tv else ""
    )
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"{auto_refresh}"
        f"<title>{NOME_PAINEL} — instabilidade no Pipedrive</title>"
        "<style>body{background:#000;color:#fff;font-family:system-ui,sans-serif;"
        "display:flex;align-items:center;justify-content:center;height:100vh;margin:0;"
        "text-align:center;padding:24px;box-sizing:border-box}"
        "div{max-width:640px}h1{font-size:1.25rem}p{color:#aaa;font-size:0.9375rem}"
        "a{color:#f4c542}</style></head><body><div>"
        "<h1>⚠️ O Pipedrive não respondeu a tempo</h1>"
        f"<p>{erro}</p>"
        f"<p><a href='?month={month_str}&refresh=1{tv_param}'>Tentar de novo agora</a>"
        f"{' — esta tela recarrega sozinha em 30s.' if modo_tv else ''}</p>"
        "</div></body></html>",
        502,
    )


@app.route("/")
def index():
    if not config.PIPEDRIVE_API_TOKEN:
        return (
            "PIPEDRIVE_API_TOKEN não configurado. Defina a variável de "
            "ambiente PIPEDRIVE_API_TOKEN (no .env local) e recarregue.",
            500,
        )

    if request.args.get("_carregado") != "1":
        return _pagina_carregando()

    month_str = request.args.get("month") or _mes_atual()
    forcar = request.args.get("refresh") == "1"
    modo_tv = request.args.get("tv") == "1"
    try:
        dados = _dados_com_cache(month_str, forcar=forcar)
    except (requests.exceptions.RequestException, RuntimeError, crn_bridge.fontes.FonteInvalida) as e:
        # MIGRAÇÃO CRN (22/10): pc.PipedriveError não existe mais (pipedrive_
        # client.py saiu de uso) — crn.base.pipedrive levanta requests.
        # HTTPError (subclasse de RequestException) ou RuntimeError (limite
        # de requisições); crn.base.fontes levanta FonteInvalida pra dado de
        # planilha que impede um número correto (mostrar na tela, nunca
        # engolir).
        return _pagina_erro_pipedrive(e, month_str, modo_tv=modo_tv, tv_param="&tv=1" if modo_tv else "")
    return render_template("index.html", modo_tv=modo_tv, **dados)


if __name__ == "__main__":
    app.run(debug=False, port=5001)
