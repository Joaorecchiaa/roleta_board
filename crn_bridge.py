"""
crn_bridge.py — ponte entre o board5anos-dashboard e a biblioteca `crn`
("Centralização de Regras de Negócio da Board Academy", repo privado
negocios87-sketch/CRN, branch main, instalada localmente a partir do
instalar.bat da CRN).

Este módulo NÃO reimplementa nenhuma regra. Ele só faz o "encanamento"
que a CRN deixa por conta de cada painel:
  - mapear o nome da variável de ambiente do token (o painel sempre usou
    PIPEDRIVE_API_TOKEN; a CRN só lê PIPEDRIVE_TOKEN);
  - carregar Colab/Metas do mês (crn.base.fontes, via URL_COLAB/URL_METAS);
  - montar os conjuntos de ids (sdr_ids, lideranca_ids) que crn.regras.
    m6_reunioes_sdr.reunioes_validadas() e outras regras pedem como
    parâmetro, a partir de R2 (papel) e H1 (hierarquia);
  - buscar deals/atividades pelos filtros e campos OFICIAIS da CRN
    (config/regras.json), nunca mais os filtros antigos do painel;
  - montar o carimbo de parâmetros com a versão da CRN.

Toda decisão de regra (o que é reunião validada, quem é SDR/Closer,
squad, dono válido, moeda aceita, cortesia, ganho automático,
licenciado etc.) vem das funções reais em crn.regras.* — ver os
comentários em cada chamada abaixo apontando a regra oficial usada.
"""
import os

# --- Token: mapeia PIPEDRIVE_API_TOKEN (nome usado pelo painel) para
# PIPEDRIVE_TOKEN (nome que crn.base.ambiente.variavel() exige), SEM
# mudar a env var na Vercel nem pedir que o João troque de nome lá —
# regra 1 da migração. Import de `config` primeiro só para garantir que
# load_dotenv() já rodou antes de olhar os.environ.
import config as _config  # noqa: F401  (garante load_dotenv() antes do mapeamento)

if os.environ.get("PIPEDRIVE_API_TOKEN") and not os.environ.get("PIPEDRIVE_TOKEN"):
    os.environ["PIPEDRIVE_TOKEN"] = os.environ["PIPEDRIVE_API_TOKEN"]

import crn
from crn.base import fontes, pipedrive, texto
from crn.base.config import campo, filtro
from crn.regras import h1_hierarquia, r2_papel

# Não existe crn.versao() oficial na biblioteca — "Faltou na CRN" (ver lista
# de divergências entregue ao João). Mas o cabeçalho de auto-update deste
# painel (início do app.py) seta `crn.versao` na própria instância em
# memória assim que baixa/atualiza a lib: no Vercel é o commit curto do
# GitHub (ex.: "319846e"), local é o que `crn.__version__` disser. Por isso
# checamos `.versao()` primeiro (pega o commit real usado NESTE carregamento)
# e só caímos pro `__version__` estático se não tiver sido setado.
VERSAO_CRN = crn.versao() if hasattr(crn, "versao") else getattr(crn, "__version__", "desconhecida")


def carimbo_parametros(month_str, extras=None):
    """Texto curto pro rodapé do painel: mês calculado + versão da CRN
    usada neste cálculo (pedido explícito do João, regra 4 da migração).
    `extras` é um dict opcional {rótulo: valor} pra acrescentar depois."""
    partes = [f"CRN {VERSAO_CRN}", f"regras calculadas para {month_str}"]
    if extras:
        partes += [f"{k}: {v}" for k, v in extras.items()]
    return " · ".join(partes)


def carregar_colab_e_metas(ano, mes):
    """Colab e Metas do mês, via crn.base.fontes.carregar_colab/
    carregar_metas (lê URL_COLAB/URL_METAS — CSV publicado por aba,
    formato exigido pela CRN; ver fontes/planilhas.md). Deixa
    fontes.FonteInvalida subir — quem chama decide como avisar na tela,
    igual já fazia com colaboradores.ColaboradoresError."""
    colab = fontes.carregar_colab(ano, mes)
    metas = fontes.carregar_metas(ano, mes)
    return colab, metas


def squad_do_painel(pessoa_colab):
    """Este painel só mostra o squad OLYMPUS (confirmado com o João,
    22/10: 'vamos usar apenas o OLYMPUS que na planilha colab é o MGM').
    `pessoa_colab` é um dict como carregar_colab() devolve — 'squad' já
    vem resolvido pela CRN via squad_oficial()/config()['squads']
    ['alias_colab'] (hoje {'MGM': 'Olympus'})."""
    return pessoa_colab.get("squad") == "Olympus"


def ids_por_papel(metas, usuarios_pipedrive):
    """sdr_ids / closer_ids (ids do Pipedrive) a partir do papel oficial
    (R2 — crn.regras.r2_papel, calculado de cima da aba Metas: SDR se
    meta_reunioes > 0, Closer se só meta_financeira > 0). Substitui
    inteiramente CLOSERS_DO_MES / nomes_sdr-por-planilha do painel
    antigo."""
    sdrs_norm = r2_papel.sdrs(metas)
    closers_norm = r2_papel.closers(metas)
    sdr_ids, closer_ids = set(), set()
    for uid, nome in usuarios_pipedrive.items():
        nn = texto.norm(nome)
        if nn in sdrs_norm:
            sdr_ids.add(uid)
        if nn in closers_norm:
            closer_ids.add(uid)
    return sdr_ids, closer_ids


def ids_lideranca(colab, usuarios_pipedrive):
    """Ids do Pipedrive de quem é Head ou Team Leader na Colab (H1 —
    crn.regras.h1_hierarquia.eh_head/eh_team_leader, a partir das
    colunas 'Equipe (Nivel Head)'/'Liderança (TEAM LIDER)'). Serve como
    `lideranca_ids` para m6_reunioes_sdr.reunioes_validadas(): quando o
    dono do negócio é um SDR de cota mas também está aqui, a RN1 (gap de
    outra atividade) não é exigida — substitui LIDERANCAS_FIXAS/
    LIDERES_QUE_AGENDAM_COMO_SDR do painel antigo, agora sem lista fixa
    de nomes."""
    lideres_norm = {
        p["nome_norm"] for p in colab
        if h1_hierarquia.eh_head(p, colab) or h1_hierarquia.eh_team_leader(p, colab)
    }
    return {uid for uid, nome in usuarios_pipedrive.items() if texto.norm(nome) in lideres_norm}


def deals_validados_e_donos(usuarios_pipedrive=None):
    """Conjunto de deal_ids com 'Reunião Válida?' = Sim (filtro oficial
    `reuniao_validada` do config/regras.json da CRN — substitui a
    checagem manual de campo que existia em rules.py) + dono atual de
    cada um (texto.dono_id). Único GET que usa filtro salvo (deals_do_
    filtro) em vez de busca por período — é assim que a própria CRN
    espera que `deals_validados` de m6_reunioes_sdr.reunioes_validadas()
    seja montado (ver crn/regras/m6_reunioes_sdr.py)."""
    deals = pipedrive.deals_do_filtro(filtro("reuniao_validada"))
    validados = {d["id"] for d in deals}
    dono_do_deal = {d["id"]: texto.dono_id(d) for d in deals}
    return validados, dono_do_deal, {d["id"]: d for d in deals}
