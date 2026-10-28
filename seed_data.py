"""
Script de população com dados de exemplo.
Execute: python seed_data.py
"""

from app import app
from models import db, Military, Afastamento, FeriadoEspecial
from datetime import date

MILITARES = [
    # (nome, graduacao, especialidade, numero_antiguidade, data_entrada)
    ('João Pereira da Silva',        'Contramestre-Mor',        'Manobras',       1,  date(2018, 3, 1)),
    ('Carlos Eduardo Menezes',       'Primeiro-Contramestre',   'Navegação',      2,  date(2018, 7, 15)),
    ('Fernando Alves Costa',         'Primeiro-Contramestre',   'Comunicações',   3,  date(2019, 1, 10)),
    ('Rodrigo Santos Lima',          'Segundo-Contramestre',    'Manobras',       4,  date(2019, 6, 1)),
    ('Marcos Antônio Ferreira',      'Segundo-Contramestre',    'Administração',  5,  date(2019, 11, 20)),
    ('Paulo Roberto Souza',          'Contramestre',            'Manobras',       6,  date(2020, 3, 5)),
    ('André Luís Rodrigues',         'Contramestre',            'Comunicações',   7,  date(2020, 8, 1)),
    ('Lucas Gabriel Oliveira',       'Contramestre',            'Logística',      8,  date(2021, 2, 15)),
    ('Matheus Henrique Barbosa',     'Suboficial',              'Manobras',       9,  date(2021, 7, 10)),
    ('Rafael Augusto Cardoso',       'Suboficial',              'Navegação',      10, date(2021, 12, 1)),
    ('Diego Mariano Teixeira',       'Primeiro-Sargento',       'Comunicações',   11, date(2022, 4, 20)),
    ('Guilherme César Nascimento',   'Primeiro-Sargento',       'Administração',  12, date(2022, 9, 5)),
    ('Vinicius Augusto Pires',       'Segundo-Sargento',        'Manobras',       13, date(2023, 1, 15)),
    ('Thiago Leandro Campos',        'Segundo-Sargento',        'Logística',      14, date(2023, 6, 1)),
    ('Bruno Leonardo Farias',        'Terceiro-Sargento',       'Manobras',       15, date(2024, 1, 10)),
]

FERIADOS_CUSTOMIZADOS = [
    # Recessos operacionais de exemplo
    (date(2025, 1, 2),  'Recesso Pós-Ano Novo',  'critico', False),
    (date(2025, 6, 19), 'Feriado Municipal',       'comum',  False),
]

def seed():
    with app.app_context():
        if Military.query.count() > 0:
            print('Banco já populado. Use --force para limpar e repopular.')
            return

        for nome, grad, esp, num, entrada in MILITARES:
            m = Military(
                nome=nome, graduacao=grad, especialidade=esp,
                numero_antiguidade=num, status='ativo',
                data_entrada_escala=entrada, ativo=True,
            )
            db.session.add(m)
        db.session.flush()

        # Afastamento exemplo (militar 3 - de férias)
        m3 = Military.query.filter_by(numero_antiguidade=3).first()
        m12 = Military.query.filter_by(numero_antiguidade=12).first()
        hoje = date.today()

        if m3:
            db.session.add(Afastamento(
                military_id=m3.id, tipo='ferias',
                data_inicio=date(hoje.year, hoje.month, 1),
                data_fim=date(hoje.year, hoje.month, 20),
                motivo='Férias anuais programadas',
            ))

        if m12:
            db.session.add(Afastamento(
                military_id=m12.id, tipo='curso',
                data_inicio=date(hoje.year, hoje.month, 5),
                data_fim=date(hoje.year, hoje.month, 25),
                motivo='Curso de Atualização',
            ))

        # Feriados customizados
        for dt, nome, tipo, rec in FERIADOS_CUSTOMIZADOS:
            if FeriadoEspecial.query.filter_by(data=dt).first() is None:
                db.session.add(FeriadoEspecial(
                    data=dt, nome=nome, tipo=tipo, recorrente=rec,
                ))

        db.session.commit()
        print(f'✅ {len(MILITARES)} militares inseridos com sucesso.')
        print('   Execute: python app.py para iniciar o servidor.')
        print('   Acesse:  http://localhost:5000')

if __name__ == '__main__':
    import sys
    if '--force' in sys.argv:
        with app.app_context():
            db.drop_all()
        print('Banco limpo. Execute: flask db upgrade')
    seed()
