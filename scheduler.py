"""
Módulo de geração automática da escala militar.

Tipos de escala:
  preta   – Pernoite Dia Útil  (08h–próximas 08h). Fila: antigo→moderno.
  diario  – Serviço Diário Leve (12h–16h).           Fila: moderno→antigo.
  vermelha– Final de Semana/Feriado comum (08h–08h). Fila: antigo→moderno.
  roxa    – Feriado crítico/Recesso (08h–08h).       Fila: moderno→antigo +
            histórico de evento.

Regra de descanso:
  Entre preta↔vermelha ou vermelha↔preta: diferença mínima de 2 dias
  (= 1 dia de descanso real).
"""

from datetime import date, timedelta
from calendar import monthrange
from models import db, Military, Afastamento, Servico, FeriadoEspecial

# ─────────────────────────────────────────────────────────────
# Datas críticas fixas (mês, dia)
# ─────────────────────────────────────────────────────────────
CRITICOS_FIXOS = [
    (12, 24, 'Véspera de Natal'),
    (12, 25, 'Natal'),
    (12, 31, 'Véspera de Ano Novo'),
    (1,   1, 'Ano Novo'),
]

# ─────────────────────────────────────────────────────────────
# Cálculo de Páscoa (algoritmo anônimo gregoriano)
# ─────────────────────────────────────────────────────────────
def calcular_pascoa(ano: int) -> date:
    a = ano % 19
    b = ano // 100
    c = ano % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day   = ((h + l - 7 * m + 114) % 31) + 1
    return date(ano, month, day)


def get_datas_criticas(ano: int) -> dict:
    """Retorna {date: nome_evento} para datas críticas (Roxa)."""
    criticas = {}
    for mes, dia, nome in CRITICOS_FIXOS:
        criticas[date(ano, mes, dia)] = nome

    # Carnaval = 48 e 47 dias antes da Páscoa
    pascoa = calcular_pascoa(ano)
    criticas[pascoa - timedelta(days=48)] = 'Carnaval'
    criticas[pascoa - timedelta(days=47)] = 'Carnaval'

    # Feriados críticos customizados no banco
    feriados_db = FeriadoEspecial.query.filter_by(tipo='critico').all()
    for f in feriados_db:
        if f.recorrente:
            try:
                criticas[date(ano, f.data.month, f.data.day)] = f.nome
            except ValueError:
                pass
        elif f.data.year == ano:
            criticas[f.data] = f.nome

    return criticas


def get_feriados_comuns(ano: int) -> set:
    """Retorna conjunto de datas de feriados nacionais comuns."""
    pascoa = calcular_pascoa(ano)
    feriados = {
        date(ano, 1, 1),    # Ano Novo  (será critico, mas também feriado)
        date(ano, 4, 21),   # Tiradentes
        date(ano, 5, 1),    # Dia do Trabalho
        date(ano, 9, 7),    # Independência
        date(ano, 10, 12),  # N. Sra. Aparecida
        date(ano, 11, 2),   # Finados
        date(ano, 11, 15),  # Proclamação da República
        date(ano, 12, 25),  # Natal (será critico)
        pascoa - timedelta(days=2),   # Sexta-Feira Santa
        pascoa,                        # Domingo de Páscoa
        pascoa + timedelta(days=60),   # Corpus Christi
    }
    # Feriados comuns customizados no banco
    feriados_db = FeriadoEspecial.query.filter_by(tipo='comum').all()
    for f in feriados_db:
        if f.recorrente:
            try:
                feriados.add(date(ano, f.data.month, f.data.day))
            except ValueError:
                pass
        elif f.data.year == ano:
            feriados.add(f.data)
    return feriados


def classificar_dia(dt: date) -> tuple:
    """
    Retorna (tipo, nome_evento):
      'critico' → Roxa
      'feriado' → Vermelha
      'util'    → Preta + Diário
    """
    criticas = get_datas_criticas(dt.year)
    if dt in criticas:
        return 'critico', criticas[dt]

    if dt.weekday() in (5, 6):           # Sáb ou Dom
        return 'feriado', 'Fim de Semana'

    if dt in get_feriados_comuns(dt.year):
        return 'feriado', 'Feriado Nacional'

    return 'util', None


# ─────────────────────────────────────────────────────────────
# Disponibilidade
# ─────────────────────────────────────────────────────────────
def get_militares_disponiveis(dt: date):
    """Militares ativos SEM afastamento na data."""
    afastados_ids = (
        db.session.query(Afastamento.military_id)
        .filter(Afastamento.data_inicio <= dt, Afastamento.data_fim >= dt)
        .all()
    )
    ids_set = [a[0] for a in afastados_ids]
    query = Military.query.filter(Military.ativo == True)
    if ids_set:
        query = query.filter(~Military.id.in_(ids_set))
    return query.order_by(Military.numero_antiguidade).all()


# ─────────────────────────────────────────────────────────────
# Construção da fila / ordenação
# ─────────────────────────────────────────────────────────────
def _score_basico(m, tipo, data_ref, temp_servicos=None):
    """
    Contagem + dias desde o último deste tipo.
    Considera tanto o banco de dados quanto serviços temporários (em memória).
    """
    # Contagem no banco
    db_count = Servico.query.filter(
        Servico.military_id == m.id,
        Servico.tipo_escala == tipo,
        Servico.data < data_ref,
    ).count()

    # Contagem nos temporários
    temp_count = 0
    temp_last_date = None
    if temp_servicos:
        temp_servs = [s for s in temp_servicos
                      if s['military_id'] == m.id
                      and s['tipo_escala'] == tipo
                      and s['data'] < data_ref]
        temp_count = len(temp_servs)
        if temp_servs:
            temp_last_date = max(s['data'] for s in temp_servs)

    count = db_count + temp_count

    # Último serviço do banco
    db_last = (
        Servico.query
        .filter(Servico.military_id == m.id, Servico.tipo_escala == tipo,
                Servico.data < data_ref)
        .order_by(Servico.data.desc())
        .first()
    )
    db_last_date = db_last.data if db_last else None

    # Mais recente entre banco e temp
    candidates = [d for d in [db_last_date, temp_last_date] if d is not None]
    if candidates:
        effective_last = max(candidates)
        dias_sem = (data_ref - effective_last).days
    else:
        dias_sem = 9999

    return count, dias_sem


def get_fila(militares, tipo, data_ref, nome_evento=None, temp_servicos=None):
    """
    Retorna lista ordenada de militares para o tipo de escala.

    Vermelha / Preta : (count↑, antiguidade↑)  ← antigo primeiro
    Diário            : (count↑, antiguidade↓)  ← moderno primeiro
    Roxa              : (count_evento↑, dias_sem_evento↓, antiguidade↓)
    """
    if tipo in ('preta', 'vermelha'):
        scored = sorted(
            militares,
            key=lambda m: (_score_basico(m, tipo, data_ref, temp_servicos)[0],
                           m.numero_antiguidade)
        )
    elif tipo == 'diario':
        scored = sorted(
            militares,
            key=lambda m: (_score_basico(m, tipo, data_ref, temp_servicos)[0],
                           -m.numero_antiguidade)
        )
    elif tipo == 'roxa':
        def _roxa_key(m):
            if nome_evento:
                # Conta no banco
                cnt_ev = Servico.query.filter(
                    Servico.military_id == m.id,
                    Servico.tipo_escala == 'roxa',
                    Servico.nome_evento == nome_evento,
                    Servico.data < data_ref,
                ).count()
                # Conta no temp
                if temp_servicos:
                    cnt_ev += sum(1 for s in temp_servicos
                                  if s['military_id'] == m.id
                                  and s['tipo_escala'] == 'roxa'
                                  and s.get('nome_evento') == nome_evento
                                  and s['data'] < data_ref)
                # Último no banco
                last_ev = Servico.query.filter(
                    Servico.military_id == m.id,
                    Servico.tipo_escala == 'roxa',
                    Servico.nome_evento == nome_evento,
                    Servico.data < data_ref,
                ).order_by(Servico.data.desc()).first()
                dias_ev = (data_ref - last_ev.data).days if last_ev else 9999
            else:
                cnt_ev, dias_ev = _score_basico(m, 'roxa', data_ref, temp_servicos)
            return (cnt_ev, -dias_ev, -m.numero_antiguidade)
        scored = sorted(militares, key=_roxa_key)
    else:
        scored = militares[:]
    return scored


# ─────────────────────────────────────────────────────────────
# Verificação de conflito de descanso
# ─────────────────────────────────────────────────────────────
_PESADOS = ('preta', 'vermelha', 'roxa')

def _resolve_adj(db_srv, temp_list, military_id, data_ref, depois=True):
    """Resolve serviço pesado adjacente (de DB + memória temporária)."""
    if depois:
        temps = [s for s in temp_list
                 if s['military_id'] == military_id
                 and s['tipo_escala'] in _PESADOS
                 and s['data'] > data_ref]
        db_q = (Servico.query
                .filter(Servico.military_id == military_id,
                        Servico.data > data_ref,
                        Servico.tipo_escala.in_(_PESADOS))
                .order_by(Servico.data.asc())
                .first())
    else:
        temps = [s for s in temp_list
                 if s['military_id'] == military_id
                 and s['tipo_escala'] in _PESADOS
                 and s['data'] < data_ref]
        db_q = (Servico.query
                .filter(Servico.military_id == military_id,
                        Servico.data < data_ref,
                        Servico.tipo_escala.in_(_PESADOS))
                .order_by(Servico.data.desc())
                .first())

    candidates = []
    if db_q:
        candidates.append({'data': db_q.data, 'tipo_escala': db_q.tipo_escala})
    if temps:
        fn = min if depois else max
        best = fn(temps, key=lambda s: s['data'])
        candidates.append(best)

    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    fn = min if depois else max
    return fn(candidates, key=lambda s: s['data'])


def tem_conflito(military_id, nova_data, novo_tipo, temp_servicos=None):
    """
    Retorna (bool, str_motivo).
    Regra: preta↔vermelha com diff <= 1 dia = CONFLITO.
    """
    if novo_tipo == 'diario':
        return False, None
    if novo_tipo not in _PESADOS:
        return False, None

    temp = temp_servicos or []

    prev = _resolve_adj(None, temp, military_id, nova_data, depois=False)
    nxt  = _resolve_adj(None, temp, military_id, nova_data, depois=True)

    # Pares que exigem intervalo mínimo de 2 dias:
    # preta↔vermelha | preta↔roxa | vermelha↔roxa | roxa↔roxa
    _CONFLITO_PARES = {
        ('preta',    'vermelha'), ('vermelha', 'preta'),
        ('preta',    'roxa'),     ('roxa',     'preta'),
        ('vermelha', 'roxa'),     ('roxa',     'vermelha'),
        ('roxa',     'roxa'),
    }

    if prev:
        diff = (nova_data - prev['data']).days
        pt = prev['tipo_escala']
        if (pt, novo_tipo) in _CONFLITO_PARES and diff <= 1:
            return True, (f"Conflito: {pt} em {prev['data']} + "
                          f"{novo_tipo} em {nova_data} (diff={diff}d, mín=2)")
    if nxt:
        diff = (nxt['data'] - nova_data).days
        nt = nxt['tipo_escala']
        if (novo_tipo, nt) in _CONFLITO_PARES and diff <= 1:
            return True, (f"Conflito: {novo_tipo} em {nova_data} + "
                          f"{nt} em {nxt['data']} (diff={diff}d, mín=2)")

    return False, None


def _ja_tem_hoje(military_id, dt, temp_servicos):
    """Retorna True se militar já tem serviço nessa data."""
    if Servico.query.filter_by(military_id=military_id, data=dt).first():
        return True
    return any(
        s['military_id'] == military_id and s['data'] == dt
        for s in temp_servicos
    )


# ─────────────────────────────────────────────────────────────
# Atribuição de um slot
# ─────────────────────────────────────────────────────────────
def atribuir_servico(dt, tipo, nome_evento, excluidos, temp_servicos):
    """
    Tenta atribuir um serviço. Retorna dict ou None.
    excluidos: IDs já atribuídos nesse dia.
    """
    disponiveis = [m for m in get_militares_disponiveis(dt)
                   if m.id not in excluidos
                   and not _ja_tem_hoje(m.id, dt, temp_servicos)]

    if not disponiveis:
        return None

    fila = get_fila(disponiveis, tipo, dt, nome_evento, temp_servicos)

    for militar in fila:
        conflito, _ = tem_conflito(militar.id, dt, tipo, temp_servicos)
        if not conflito:
            return dict(military_id=militar.id, data=dt, tipo_escala=tipo,
                        nome_evento=nome_evento, observacoes=None,
                        troca_forcada=False, gerado_auto=True,
                        _nome=militar.nome)

    # Todos com conflito → forçar primeiro da fila
    if fila:
        m = fila[0]
        return dict(military_id=m.id, data=dt, tipo_escala=tipo,
                    nome_evento=nome_evento,
                    observacoes='TF - Ajuste operacional para intervalo entre serviços',
                    troca_forcada=True, gerado_auto=True, _nome=m.nome)

    return None


# ─────────────────────────────────────────────────────────────
# Geração mensal
# ─────────────────────────────────────────────────────────────
def gerar_escala_mensal(ano: int, mes: int, sobrescrever: bool = False):
    """
    Gera a escala do mês. Retorna (qtd, lista_conflitos, msg_erro).
    """
    inicio = date(ano, mes, 1)
    fim    = date(ano, mes, monthrange(ano, mes)[1])

    existentes = Servico.query.filter(
        Servico.data >= inicio,
        Servico.data <= fim,
        Servico.gerado_auto == True,
    ).count()

    if existentes and not sobrescrever:
        return 0, [], (f'Já existe escala para {mes:02d}/{ano}. '
                       'Marque "Sobrescrever" para regenerar.')

    if sobrescrever and existentes:
        Servico.query.filter(
            Servico.data >= inicio, Servico.data <= fim,
            Servico.gerado_auto == True,
        ).delete(synchronize_session=False)
        db.session.commit()

    temp: list[dict] = []
    conflitos: list[dict] = []

    for dia_num in range(1, monthrange(ano, mes)[1] + 1):
        dt = date(ano, mes, dia_num)
        tipo_dia, nome_evento = classificar_dia(dt)
        excluidos_hoje = []

        if tipo_dia == 'util':
            for tipo in ('preta', 'diario'):
                s = atribuir_servico(dt, tipo, None, excluidos_hoje, temp)
                if s:
                    if s['troca_forcada']:
                        conflitos.append(dict(data=str(dt), tipo=tipo,
                                              militar=s['_nome'],
                                              motivo=s['observacoes']))
                    excluidos_hoje.append(s['military_id'])
                    temp.append(s)

        elif tipo_dia == 'feriado':
            s = atribuir_servico(dt, 'vermelha', nome_evento, excluidos_hoje, temp)
            if s:
                if s['troca_forcada']:
                    conflitos.append(dict(data=str(dt), tipo='vermelha',
                                          militar=s['_nome'], motivo=s['observacoes']))
                temp.append(s)

        elif tipo_dia == 'critico':
            s = atribuir_servico(dt, 'roxa', nome_evento, excluidos_hoje, temp)
            if s:
                if s['troca_forcada']:
                    conflitos.append(dict(data=str(dt), tipo='roxa',
                                          militar=s['_nome'], motivo=s['observacoes']))
                temp.append(s)

    # Persistir
    for s in temp:
        db.session.add(Servico(
            military_id=s['military_id'], data=s['data'],
            tipo_escala=s['tipo_escala'], nome_evento=s['nome_evento'],
            observacoes=s['observacoes'], troca_forcada=s['troca_forcada'],
            gerado_auto=s['gerado_auto'],
        ))
    db.session.commit()

    return len(temp), conflitos, None


# ─────────────────────────────────────────────────────────────
# Calendário (dados para template)
# ─────────────────────────────────────────────────────────────
def build_calendario(ano: int, mes: int) -> list:
    """
    Retorna lista de semanas; cada semana é lista de 7 células (None ou dict).
    """
    inicio = date(ano, mes, 1)
    fim    = date(ano, mes, monthrange(ano, mes)[1])

    servicos_db = (
        Servico.query
        .filter(Servico.data >= inicio, Servico.data <= fim)
        .order_by(Servico.data)
        .all()
    )
    por_dia: dict[int, list] = {}
    for s in servicos_db:
        por_dia.setdefault(s.data.day, []).append(s)

    criticas = get_datas_criticas(ano)
    feriados  = get_feriados_comuns(ano)
    hoje = date.today()

    semanas = []
    semana  = [None] * 7
    primeiro_dia_semana = inicio.weekday()  # 0=Seg

    for i in range(primeiro_dia_semana):
        semana[i] = None

    for dia_num in range(1, fim.day + 1):
        dt = date(ano, mes, dia_num)
        dsem = dt.weekday()
        tipo_dia, nome_ev = classificar_dia(dt)

        semana[dsem] = dict(
            dia=dia_num, data=dt,
            tipo_dia=tipo_dia, nome_evento=nome_ev,
            servicos=por_dia.get(dia_num, []),
            hoje=(dt == hoje),
        )

        if dsem == 6 or dia_num == fim.day:
            semanas.append(semana[:])
            semana = [None] * 7

    return semanas
