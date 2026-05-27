"""
Sistema Inteligente de Escala Militar — Contramestre
"""

from flask import (Flask, render_template, request, redirect,
                   url_for, flash, jsonify, abort)
from flask_sqlalchemy import SQLAlchemy
from datetime import date, datetime
from calendar import monthrange
import os

from models import (db, Military, Afastamento, Servico, FeriadoEspecial,
                    GRADUACOES, STATUS_LABELS, ESCALA_LABELS, ESCALA_DESCRICAO)
from scheduler import (gerar_escala_mensal, build_calendario,
                       classificar_dia, get_militares_disponiveis,
                       get_datas_criticas, get_feriados_comuns,
                       tem_conflito)

# ─────────────────────────────────────────────────────────────
app = Flask(__name__)
app.config['SECRET_KEY']                  = os.environ.get('SECRET_KEY', 'escala-naval-secret-2025')
app.config['SQLALCHEMY_DATABASE_URI']     = 'sqlite:///escala.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

MESES_PT = ['', 'Janeiro','Fevereiro','Março','Abril','Maio','Junho',
            'Julho','Agosto','Setembro','Outubro','Novembro','Dezembro']
DIAS_SEMANA = ['Seg','Ter','Qua','Qui','Sex','Sáb','Dom']

# ─────────────────────────────────────────────────────────────
# Context processors
# ─────────────────────────────────────────────────────────────
@app.context_processor
def inject_globals():
    hoje = date.today()
    return dict(
        hoje=hoje,
        ano_atual=hoje.year,
        mes_atual=hoje.month,
        meses_pt=MESES_PT,
        dias_semana=DIAS_SEMANA,
        escala_labels=ESCALA_LABELS,
        status_labels=STATUS_LABELS,
    )

# ─────────────────────────────────────────────────────────────
# DASHBOARD
# ─────────────────────────────────────────────────────────────
@app.route('/')
def dashboard():
    hoje = date.today()
    ano, mes = hoje.year, hoje.month
    ini_mes = date(ano, mes, 1)
    fim_mes = date(ano, mes, monthrange(ano, mes)[1])

    total_mil    = Military.query.filter_by(ativo=True).count()
    disponiveis  = len(get_militares_disponiveis(hoje))
    afastados    = total_mil - disponiveis
    serv_mes     = Servico.query.filter(Servico.data >= ini_mes,
                                        Servico.data <= fim_mes).count()
    trocas_mes   = Servico.query.filter(Servico.data >= ini_mes,
                                        Servico.data <= fim_mes,
                                        Servico.troca_forcada == True).count()

    # Carga operacional por militar (ano corrente)
    militares_ativos = (Military.query.filter_by(ativo=True)
                        .order_by(Military.numero_antiguidade).all())

    carga = []
    for m in militares_ativos:
        preta    = m.count_tipo('preta',    ano)
        diario   = m.count_tipo('diario',   ano)
        vermelha = m.count_tipo('vermelha', ano)
        roxa     = m.count_tipo('roxa',     ano)
        total    = preta + diario + vermelha + roxa
        pesado   = preta + vermelha + roxa
        carga.append(dict(
            militar=m, preta=preta, diario=diario,
            vermelha=vermelha, roxa=roxa, total=total, pesado=pesado,
        ))
    carga.sort(key=lambda x: -x['total'])

    # Alertas de fadiga: pesado >= threshold
    threshold_pesado = 8
    alertas_fadiga = [c for c in carga if c['pesado'] >= threshold_pesado]

    # Próximos serviços (7 dias)
    prox = (Servico.query
            .filter(Servico.data >= hoje)
            .order_by(Servico.data)
            .limit(15).all())

    # Militares indisponíveis agora
    indisponiveis = (
        Afastamento.query
        .filter(Afastamento.data_inicio <= hoje, Afastamento.data_fim >= hoje)
        .all()
    )

    # Escala do mês já foi gerada?
    escala_gerada = Servico.query.filter(
        Servico.data >= ini_mes, Servico.data <= fim_mes,
        Servico.gerado_auto == True,
    ).count() > 0

    return render_template('index.html',
        total_mil=total_mil, disponiveis=disponiveis, afastados=afastados,
        serv_mes=serv_mes, trocas_mes=trocas_mes,
        carga=carga, alertas_fadiga=alertas_fadiga,
        prox_servicos=prox, indisponiveis=indisponiveis,
        escala_gerada=escala_gerada,
    )

# ─────────────────────────────────────────────────────────────
# MILITARES
# ─────────────────────────────────────────────────────────────
@app.route('/militares')
def militares_lista():
    q = request.args.get('q', '').strip()
    status_f = request.args.get('status', '')
    query = Military.query.order_by(Military.numero_antiguidade)
    if q:
        query = query.filter(Military.nome.ilike(f'%{q}%'))
    if status_f:
        query = query.filter_by(status=status_f)
    militares = query.all()
    return render_template('militares/index.html',
                           militares=militares, q=q, status_f=status_f,
                           status_labels=STATUS_LABELS, graduacoes=GRADUACOES)


@app.route('/militares/novo', methods=['GET', 'POST'])
def militar_novo():
    if request.method == 'POST':
        try:
            m = Military(
                nome=request.form['nome'].strip(),
                graduacao=request.form['graduacao'],
                especialidade=request.form.get('especialidade', '').strip() or None,
                numero_antiguidade=int(request.form['numero_antiguidade']),
                status=request.form.get('status', 'ativo'),
                data_entrada_escala=date.fromisoformat(request.form['data_entrada_escala']),
                observacoes=request.form.get('observacoes', '').strip() or None,
            )
            db.session.add(m)
            db.session.commit()
            flash(f'Militar {m.nome} cadastrado com sucesso.', 'success')
            return redirect(url_for('militares_lista'))
        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao cadastrar: {e}', 'danger')

    proximo_num = (db.session.query(db.func.max(Military.numero_antiguidade)).scalar() or 0) + 1
    return render_template('militares/form.html',
                           militar=None, graduacoes=GRADUACOES,
                           status_labels=STATUS_LABELS,
                           proximo_num=proximo_num)


@app.route('/militares/<int:id>/editar', methods=['GET', 'POST'])
def militar_editar(id):
    m = Military.query.get_or_404(id)
    if request.method == 'POST':
        try:
            m.nome               = request.form['nome'].strip()
            m.graduacao          = request.form['graduacao']
            m.especialidade      = request.form.get('especialidade', '').strip() or None
            m.numero_antiguidade = int(request.form['numero_antiguidade'])
            m.status             = request.form.get('status', 'ativo')
            m.data_entrada_escala = date.fromisoformat(request.form['data_entrada_escala'])
            m.observacoes        = request.form.get('observacoes', '').strip() or None
            db.session.commit()
            flash('Militar atualizado.', 'success')
            return redirect(url_for('militares_lista'))
        except Exception as e:
            db.session.rollback()
            flash(f'Erro: {e}', 'danger')
    return render_template('militares/form.html',
                           militar=m, graduacoes=GRADUACOES,
                           status_labels=STATUS_LABELS)


@app.route('/militares/<int:id>/detalhe')
def militar_detalhe(id):
    m = Military.query.get_or_404(id)
    ano = int(request.args.get('ano', date.today().year))
    servicos_ano = (m.servicos.filter(
        db.extract('year', Servico.data) == ano)
        .order_by(Servico.data).all())

    historico_roxa = (m.servicos
                       .filter_by(tipo_escala='roxa')
                       .order_by(Servico.data.desc()).all())
    afastamentos_list = (m.afastamentos
                          .order_by(Afastamento.data_inicio.desc()).all())

    stats = dict(
        preta=m.count_tipo('preta', ano), diario=m.count_tipo('diario', ano),
        vermelha=m.count_tipo('vermelha', ano), roxa=m.count_tipo('roxa', ano),
    )
    return render_template('militares/detalhe.html',
                           m=m, ano=ano, servicos_ano=servicos_ano,
                           historico_roxa=historico_roxa,
                           afastamentos_list=afastamentos_list, stats=stats)


@app.route('/militares/<int:id>/toggle', methods=['POST'])
def militar_toggle(id):
    m = Military.query.get_or_404(id)
    m.ativo = not m.ativo
    db.session.commit()
    estado = 'reativado' if m.ativo else 'desativado'
    flash(f'{m.nome} foi {estado}.', 'info')
    return redirect(url_for('militares_lista'))


@app.route('/militares/<int:id>/excluir', methods=['POST'])
def militar_excluir(id):
    m = Military.query.get_or_404(id)
    nome = m.nome
    db.session.delete(m)
    db.session.commit()
    flash(f'Militar {nome} removido.', 'warning')
    return redirect(url_for('militares_lista'))

# ─────────────────────────────────────────────────────────────
# AFASTAMENTOS
# ─────────────────────────────────────────────────────────────
@app.route('/afastamentos')
def afastamentos_lista():
    militar_id = request.args.get('militar_id', type=int)
    apenas_ativos = request.args.get('ativos', '') == '1'
    hoje = date.today()

    query = Afastamento.query.order_by(Afastamento.data_inicio.desc())
    if militar_id:
        query = query.filter_by(military_id=militar_id)
    if apenas_ativos:
        query = query.filter(Afastamento.data_inicio <= hoje,
                             Afastamento.data_fim >= hoje)

    afastamentos = query.all()
    militares_todos = Military.query.filter_by(ativo=True).order_by(
        Military.numero_antiguidade).all()
    return render_template('afastamentos/index.html',
                           afastamentos=afastamentos,
                           militares_todos=militares_todos,
                           militar_id=militar_id,
                           apenas_ativos=apenas_ativos)


@app.route('/afastamentos/novo', methods=['GET', 'POST'])
def afastamento_novo():
    militares_todos = Military.query.filter_by(ativo=True).order_by(
        Military.numero_antiguidade).all()
    if request.method == 'POST':
        try:
            di = date.fromisoformat(request.form['data_inicio'])
            df = date.fromisoformat(request.form['data_fim'])
            if df < di:
                raise ValueError('Data fim anterior à data início.')
            af = Afastamento(
                military_id=int(request.form['military_id']),
                tipo=request.form['tipo'],
                data_inicio=di, data_fim=df,
                motivo=request.form.get('motivo', '').strip() or None,
                observacoes=request.form.get('observacoes', '').strip() or None,
            )
            db.session.add(af)
            db.session.commit()
            flash('Afastamento registrado.', 'success')
            return redirect(url_for('afastamentos_lista'))
        except Exception as e:
            db.session.rollback()
            flash(f'Erro: {e}', 'danger')
    mil_id = request.args.get('military_id', type=int)
    return render_template('afastamentos/form.html',
                           af=None, militares_todos=militares_todos,
                           status_labels=STATUS_LABELS,
                           pre_mil_id=mil_id)


@app.route('/afastamentos/<int:id>/editar', methods=['GET', 'POST'])
def afastamento_editar(id):
    af = Afastamento.query.get_or_404(id)
    militares_todos = Military.query.filter_by(ativo=True).order_by(
        Military.numero_antiguidade).all()
    if request.method == 'POST':
        try:
            di = date.fromisoformat(request.form['data_inicio'])
            df = date.fromisoformat(request.form['data_fim'])
            if df < di:
                raise ValueError('Data fim anterior à data início.')
            af.military_id  = int(request.form['military_id'])
            af.tipo         = request.form['tipo']
            af.data_inicio  = di
            af.data_fim     = df
            af.motivo       = request.form.get('motivo', '').strip() or None
            af.observacoes  = request.form.get('observacoes', '').strip() or None
            db.session.commit()
            flash('Afastamento atualizado.', 'success')
            return redirect(url_for('afastamentos_lista'))
        except Exception as e:
            db.session.rollback()
            flash(f'Erro: {e}', 'danger')
    return render_template('afastamentos/form.html',
                           af=af, militares_todos=militares_todos,
                           status_labels=STATUS_LABELS,
                           pre_mil_id=af.military_id)


@app.route('/afastamentos/<int:id>/excluir', methods=['POST'])
def afastamento_excluir(id):
    af = Afastamento.query.get_or_404(id)
    db.session.delete(af)
    db.session.commit()
    flash('Afastamento removido.', 'warning')
    return redirect(url_for('afastamentos_lista'))

# ─────────────────────────────────────────────────────────────
# ESCALA
# ─────────────────────────────────────────────────────────────
@app.route('/escala')
def escala_redirect():
    hoje = date.today()
    return redirect(url_for('escala_mensal', ano=hoje.year, mes=hoje.month))


@app.route('/escala/<int:ano>/<int:mes>')
def escala_mensal(ano, mes):
    if not (1 <= mes <= 12):
        abort(404)
    semanas = build_calendario(ano, mes)
    ano_ant, mes_ant = (ano - 1, 12) if mes == 1 else (ano, mes - 1)
    ano_prox, mes_prox = (ano + 1, 1) if mes == 12 else (ano, mes + 1)

    # Totais do mês por tipo
    ini = date(ano, mes, 1)
    fim = date(ano, mes, monthrange(ano, mes)[1])
    totais = dict(
        preta    = Servico.query.filter(Servico.data >= ini, Servico.data <= fim,
                                        Servico.tipo_escala == 'preta').count(),
        diario   = Servico.query.filter(Servico.data >= ini, Servico.data <= fim,
                                        Servico.tipo_escala == 'diario').count(),
        vermelha = Servico.query.filter(Servico.data >= ini, Servico.data <= fim,
                                        Servico.tipo_escala == 'vermelha').count(),
        roxa     = Servico.query.filter(Servico.data >= ini, Servico.data <= fim,
                                        Servico.tipo_escala == 'roxa').count(),
    )
    trocas = Servico.query.filter(Servico.data >= ini, Servico.data <= fim,
                                   Servico.troca_forcada == True).count()

    escala_gerada = sum(totais.values()) > 0

    return render_template('escala/mensal.html',
                           semanas=semanas, ano=ano, mes=mes,
                           mes_nome=MESES_PT[mes],
                           ano_ant=ano_ant, mes_ant=mes_ant,
                           ano_prox=ano_prox, mes_prox=mes_prox,
                           dias_semana=DIAS_SEMANA,
                           totais=totais, trocas=trocas,
                           escala_gerada=escala_gerada)


@app.route('/escala/gerar', methods=['GET', 'POST'])
def escala_gerar():
    if request.method == 'POST':
        try:
            ano         = int(request.form['ano'])
            mes         = int(request.form['mes'])
            sobrescrever = request.form.get('sobrescrever') == '1'
            qtd, conflitos, erro = gerar_escala_mensal(ano, mes, sobrescrever)
            if erro:
                flash(erro, 'warning')
            else:
                flash(f'Escala gerada: {qtd} serviço(s) para {MESES_PT[mes]}/{ano}.', 'success')
                if conflitos:
                    flash(f'{len(conflitos)} troca(s) forçada(s) registrada(s).', 'warning')
                return redirect(url_for('escala_mensal', ano=ano, mes=mes))
        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao gerar escala: {e}', 'danger')

    hoje = date.today()
    return render_template('escala/gerar.html', hoje=hoje)


@app.route('/escala/servico/novo', methods=['GET', 'POST'])
def servico_novo():
    militares_todos = Military.query.filter_by(ativo=True).order_by(
        Military.numero_antiguidade).all()
    if request.method == 'POST':
        try:
            dt = date.fromisoformat(request.form['data'])
            mid = int(request.form['military_id'])
            tipo = request.form['tipo_escala']
            conflito, motivo = tem_conflito(mid, dt, tipo)
            obs = request.form.get('observacoes', '').strip() or None
            if conflito and not request.form.get('ignorar_conflito'):
                flash(f'⚠ Conflito detectado: {motivo}. Marque "Ignorar conflito" para prosseguir.',
                      'warning')
            else:
                srv = Servico(
                    military_id=mid, data=dt, tipo_escala=tipo,
                    nome_evento=request.form.get('nome_evento', '').strip() or None,
                    observacoes=obs, troca_forcada=bool(conflito),
                    gerado_auto=False,
                )
                db.session.add(srv)
                db.session.commit()
                flash('Serviço adicionado manualmente.', 'success')
                return redirect(url_for('escala_mensal', ano=dt.year, mes=dt.month))
        except Exception as e:
            db.session.rollback()
            flash(f'Erro: {e}', 'danger')

    pre_data = request.args.get('data', '')
    pre_tipo = request.args.get('tipo', '')
    return render_template('escala/servico_form.html',
                           militares_todos=militares_todos,
                           escala_labels=ESCALA_LABELS,
                           pre_data=pre_data, pre_tipo=pre_tipo)


@app.route('/escala/servico/<int:id>/editar', methods=['GET', 'POST'])
def servico_editar(id):
    srv = Servico.query.get_or_404(id)
    militares_todos = Military.query.filter_by(ativo=True).order_by(
        Military.numero_antiguidade).all()
    if request.method == 'POST':
        try:
            srv.military_id  = int(request.form['military_id'])
            srv.tipo_escala  = request.form['tipo_escala']
            srv.nome_evento  = request.form.get('nome_evento', '').strip() or None
            srv.observacoes  = request.form.get('observacoes', '').strip() or None
            db.session.commit()
            flash('Serviço atualizado.', 'success')
            return redirect(url_for('escala_mensal', ano=srv.data.year, mes=srv.data.month))
        except Exception as e:
            db.session.rollback()
            flash(f'Erro: {e}', 'danger')
    return render_template('escala/servico_form.html',
                           srv=srv, militares_todos=militares_todos,
                           escala_labels=ESCALA_LABELS,
                           pre_data=str(srv.data),
                           pre_tipo=srv.tipo_escala)


@app.route('/escala/servico/<int:id>/excluir', methods=['POST'])
def servico_excluir(id):
    srv = Servico.query.get_or_404(id)
    ano, mes = srv.data.year, srv.data.month
    db.session.delete(srv)
    db.session.commit()
    flash('Serviço removido.', 'warning')
    return redirect(url_for('escala_mensal', ano=ano, mes=mes))

# ─────────────────────────────────────────────────────────────
# HISTÓRICO
# ─────────────────────────────────────────────────────────────
@app.route('/historico')
def historico():
    militar_id = request.args.get('militar_id', type=int)
    tipo_f     = request.args.get('tipo', '')
    ano_f      = request.args.get('ano', type=int)
    evento_f   = request.args.get('evento', '')
    page       = request.args.get('page', 1, type=int)

    query = Servico.query.order_by(Servico.data.desc())
    if militar_id:
        query = query.filter_by(military_id=militar_id)
    if tipo_f:
        query = query.filter_by(tipo_escala=tipo_f)
    if ano_f:
        query = query.filter(db.extract('year', Servico.data) == ano_f)
    if evento_f:
        query = query.filter(Servico.nome_evento.ilike(f'%{evento_f}%'))

    paginado = query.paginate(page=page, per_page=50, error_out=False)
    militares_todos = Military.query.order_by(Military.numero_antiguidade).all()

    anos_disp = [r[0] for r in db.session.query(
        db.extract('year', Servico.data).label('ano')
    ).distinct().order_by(db.desc('ano')).all()]

    return render_template('historico/index.html',
                           paginado=paginado, militares_todos=militares_todos,
                           anos_disp=anos_disp, escala_labels=ESCALA_LABELS,
                           militar_id=militar_id, tipo_f=tipo_f,
                           ano_f=ano_f, evento_f=evento_f)

# ─────────────────────────────────────────────────────────────
# FERIADOS ESPECIAIS
# ─────────────────────────────────────────────────────────────
@app.route('/feriados')
def feriados_lista():
    ano_f = request.args.get('ano', type=int, default=date.today().year)
    feriados_db = (FeriadoEspecial.query
                   .order_by(FeriadoEspecial.data).all())

    # Feriados automáticos calculados
    criticos_auto = get_datas_criticas(ano_f)
    comuns_auto   = get_feriados_comuns(ano_f)

    return render_template('feriados/index.html',
                           feriados_db=feriados_db,
                           criticos_auto=sorted(criticos_auto.items()),
                           comuns_auto=sorted(comuns_auto),
                           ano_f=ano_f)


@app.route('/feriados/novo', methods=['GET', 'POST'])
def feriado_novo():
    if request.method == 'POST':
        try:
            f = FeriadoEspecial(
                data=date.fromisoformat(request.form['data']),
                nome=request.form['nome'].strip(),
                tipo=request.form['tipo'],
                recorrente=request.form.get('recorrente') == '1',
                descricao=request.form.get('descricao', '').strip() or None,
            )
            db.session.add(f)
            db.session.commit()
            flash('Feriado cadastrado.', 'success')
            return redirect(url_for('feriados_lista'))
        except Exception as e:
            db.session.rollback()
            flash(f'Erro: {e}', 'danger')
    return render_template('feriados/form.html', f=None)


@app.route('/feriados/<int:id>/excluir', methods=['POST'])
def feriado_excluir(id):
    f = FeriadoEspecial.query.get_or_404(id)
    db.session.delete(f)
    db.session.commit()
    flash('Feriado removido.', 'warning')
    return redirect(url_for('feriados_lista'))

# ─────────────────────────────────────────────────────────────
# RELATÓRIOS
# ─────────────────────────────────────────────────────────────
@app.route('/relatorios')
def relatorios():
    ano = int(request.args.get('ano', date.today().year))
    militares_ativos = (Military.query.filter_by(ativo=True)
                        .order_by(Military.numero_antiguidade).all())

    carga = []
    for m in militares_ativos:
        p = m.count_tipo('preta', ano)
        d = m.count_tipo('diario', ano)
        v = m.count_tipo('vermelha', ano)
        r = m.count_tipo('roxa', ano)
        pesado = p + v + r
        carga.append(dict(m=m, preta=p, diario=d, vermelha=v, roxa=r,
                          total=p+d+v+r, pesado=pesado))
    carga.sort(key=lambda x: -x['total'])

    # Histórico roxa por evento
    eventos_roxa = (
        db.session.query(Servico.nome_evento, db.func.count(Servico.id))
        .filter_by(tipo_escala='roxa')
        .filter(Servico.nome_evento != None)
        .group_by(Servico.nome_evento)
        .order_by(db.func.count(Servico.id).desc())
        .all()
    )

    # Distribuição de feriados críticos por militar
    hist_roxa = []
    for m in militares_ativos:
        servs_roxa = (m.servicos.filter_by(tipo_escala='roxa')
                      .order_by(Servico.data.desc()).all())
        hist_roxa.append(dict(militar=m, servicos=servs_roxa,
                               count=len(servs_roxa)))

    anos_disp = [r[0] for r in db.session.query(
        db.extract('year', Servico.data).label('a')
    ).distinct().order_by(db.desc('a')).all()]
    if not anos_disp:
        anos_disp = [ano]

    # Trocas forçadas do ano
    trocas = (Servico.query
              .filter_by(troca_forcada=True)
              .filter(db.extract('year', Servico.data) == ano)
              .order_by(Servico.data)
              .all())

    return render_template('relatorios/index.html',
                           carga=carga, eventos_roxa=eventos_roxa,
                           hist_roxa=hist_roxa, trocas=trocas,
                           ano=ano, anos_disp=anos_disp)

# ─────────────────────────────────────────────────────────────
# API JSON
# ─────────────────────────────────────────────────────────────
@app.route('/api/carga/<int:ano>')
def api_carga(ano):
    militares = (Military.query.filter_by(ativo=True)
                 .order_by(Military.numero_antiguidade).all())
    data = []
    for m in militares:
        data.append(dict(
            nome=m.nome,
            preta=m.count_tipo('preta', ano),
            diario=m.count_tipo('diario', ano),
            vermelha=m.count_tipo('vermelha', ano),
            roxa=m.count_tipo('roxa', ano),
        ))
    return jsonify(data)


@app.route('/api/conflitos/check')
def api_conflito_check():
    try:
        mid   = int(request.args['military_id'])
        dt    = date.fromisoformat(request.args['data'])
        tipo  = request.args['tipo']
        conf, motivo = tem_conflito(mid, dt, tipo)
        return jsonify(dict(conflito=conf, motivo=motivo))
    except Exception as e:
        return jsonify(dict(error=str(e))), 400

# ─────────────────────────────────────────────────────────────
# Init
# ─────────────────────────────────────────────────────────────
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
