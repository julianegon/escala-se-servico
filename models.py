from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date

db = SQLAlchemy()

GRADUACOES = [
    'Contramestre-Mor', 'Primeiro-Contramestre', 'Segundo-Contramestre',
    'Contramestre', 'Suboficial', 'Primeiro-Sargento', 'Segundo-Sargento',
    'Terceiro-Sargento', 'Cabo', 'Marinheiro', 'Recruta'
]

STATUS_LABELS = {
    'ativo': 'Ativo',
    'ferias': 'Férias',
    'licenca_gestante': 'Lic. Gestante',
    'viagem_servico': 'Viagem a Serviço',
    'destacado': 'Destacado',
    'afastado': 'Afastado',
    'licenca_medica': 'Lic. Médica',
    'curso': 'Curso',
    'dispensado': 'Dispensado',
}

STATUS_CORES = {
    'ativo': 'success',
    'ferias': 'info',
    'licenca_gestante': 'pink',
    'viagem_servico': 'warning',
    'destacado': 'secondary',
    'afastado': 'danger',
    'licenca_medica': 'orange',
    'curso': 'primary',
    'dispensado': 'dark',
}

ESCALA_LABELS = {
    'preta': 'Preta',
    'diario': 'Diário',
    'vermelha': 'Vermelha',
    'roxa': 'Roxa',
}

ESCALA_DESCRICAO = {
    'preta': 'Pernoite Dia Útil — 08h–12h, 16h–06h próximo dia',
    'diario': 'Serviço Diário Leve — 12h–16h',
    'vermelha': 'Final de Semana — 08h ao próximo dia 08h',
    'roxa': 'Feriado Crítico / Recesso — 08h ao próximo dia 08h',
}

ESCALA_PESO = {
    'diario': 1,
    'preta': 2,
    'vermelha': 3,
    'roxa': 3,
}


class Military(db.Model):
    __tablename__ = 'militares'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(200), nullable=False)
    graduacao = db.Column(db.String(100), nullable=False)
    especialidade = db.Column(db.String(100))
    numero_antiguidade = db.Column(db.Integer, nullable=False)
    # 1 = mais antigo/sênior; número maior = mais moderno/jovem na hierarquia
    status = db.Column(db.String(50), default='ativo', nullable=False)
    data_entrada_escala = db.Column(db.Date, nullable=False)
    ativo = db.Column(db.Boolean, default=True, nullable=False)
    observacoes = db.Column(db.Text)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    servicos = db.relationship('Servico', backref='militar', lazy='dynamic',
                               cascade='all, delete-orphan')
    afastamentos = db.relationship('Afastamento', backref='militar', lazy='dynamic',
                                   cascade='all, delete-orphan')

    # -------------------------------------------------------
    def is_disponivel_em(self, dt):
        if not self.ativo:
            return False
        af = self.afastamentos.filter(
            Afastamento.data_inicio <= dt,
            Afastamento.data_fim >= dt
        ).first()
        return af is None

    def count_tipo(self, tipo, ano=None, mes=None):
        from sqlalchemy import extract
        q = self.servicos.filter_by(tipo_escala=tipo)
        if ano:
            q = q.filter(extract('year', Servico.data) == ano)
        if mes:
            q = q.filter(extract('month', Servico.data) == mes)
        return q.count()

    def count_total(self, ano=None, mes=None):
        from sqlalchemy import extract
        q = self.servicos
        if ano:
            q = q.filter(extract('year', Servico.data) == ano)
        if mes:
            q = q.filter(extract('month', Servico.data) == mes)
        return q.count()

    def peso_total(self, ano=None, mes=None):
        from sqlalchemy import extract
        q = self.servicos
        if ano:
            q = q.filter(extract('year', Servico.data) == ano)
        if mes:
            q = q.filter(extract('month', Servico.data) == mes)
        total = 0
        for s in q.all():
            total += ESCALA_PESO.get(s.tipo_escala, 1)
        return total

    def ultimo_servico_tipo(self, tipo):
        return self.servicos.filter_by(tipo_escala=tipo).order_by(
            Servico.data.desc()).first()

    def count_evento(self, nome_evento):
        return self.servicos.filter(
            Servico.tipo_escala == 'roxa',
            Servico.nome_evento == nome_evento
        ).count()

    def ultimo_evento(self, nome_evento):
        return self.servicos.filter(
            Servico.tipo_escala == 'roxa',
            Servico.nome_evento == nome_evento
        ).order_by(Servico.data.desc()).first()

    @property
    def status_label(self):
        return STATUS_LABELS.get(self.status, self.status)

    @property
    def status_cor(self):
        return STATUS_CORES.get(self.status, 'secondary')

    def __repr__(self):
        return f'<Military {self.nome}>'


class Afastamento(db.Model):
    __tablename__ = 'afastamentos'

    id = db.Column(db.Integer, primary_key=True)
    military_id = db.Column(db.Integer, db.ForeignKey('militares.id'), nullable=False)
    tipo = db.Column(db.String(50), nullable=False)
    data_inicio = db.Column(db.Date, nullable=False)
    data_fim = db.Column(db.Date, nullable=False)
    motivo = db.Column(db.String(500))
    observacoes = db.Column(db.Text)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def tipo_label(self):
        return STATUS_LABELS.get(self.tipo, self.tipo)

    @property
    def duracao_dias(self):
        return (self.data_fim - self.data_inicio).days + 1

    @property
    def ativo_hoje(self):
        hoje = date.today()
        return self.data_inicio <= hoje <= self.data_fim

    def __repr__(self):
        return f'<Afastamento {self.military_id} {self.tipo} {self.data_inicio}>'


class Servico(db.Model):
    __tablename__ = 'servicos'

    id = db.Column(db.Integer, primary_key=True)
    military_id = db.Column(db.Integer, db.ForeignKey('militares.id'), nullable=False)
    data = db.Column(db.Date, nullable=False)
    tipo_escala = db.Column(db.String(20), nullable=False)
    nome_evento = db.Column(db.String(100))   # Natal, Ano Novo, Carnaval, etc.
    observacoes = db.Column(db.Text)
    troca_forcada = db.Column(db.Boolean, default=False, nullable=False)
    gerado_auto = db.Column(db.Boolean, default=True, nullable=False)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.Index('idx_srv_data_tipo', 'data', 'tipo_escala'),
        db.Index('idx_srv_mil_data', 'military_id', 'data'),
    )

    @property
    def tipo_label(self):
        return ESCALA_LABELS.get(self.tipo_escala, self.tipo_escala)

    @property
    def is_pesado(self):
        return self.tipo_escala in ('preta', 'vermelha', 'roxa')

    @property
    def peso(self):
        return ESCALA_PESO.get(self.tipo_escala, 1)

    def __repr__(self):
        return f'<Servico {self.tipo_escala} {self.data} mid={self.military_id}>'


class FeriadoEspecial(db.Model):
    __tablename__ = 'feriados_especiais'

    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.Date, nullable=False)
    nome = db.Column(db.String(200), nullable=False)
    tipo = db.Column(db.String(20), nullable=False)   # 'critico' | 'comum'
    recorrente = db.Column(db.Boolean, default=False)
    descricao = db.Column(db.Text)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Feriado {self.nome} {self.data}>'
