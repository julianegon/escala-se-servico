# ⚓ Sistema Inteligente de Escala Militar — Contramestre

Sistema web completo para geração automática e controle operacional da escala de serviço militar, com histórico permanente, gestão de afastamentos e distribuição justa de serviços.

---

## 🚀 Instalação e Execução

```bash
# 1. Clonar / entrar no repositório
cd escala-se-servico

# 2. Instalar dependências
pip install -r requirements.txt

# 3. Popular com dados de exemplo (opcional)
python seed_data.py

# 4. Iniciar o servidor
python app.py
```

Acesse: **http://localhost:5000**

---

## 🎯 Funcionalidades

### 📋 Tipos de Escala
| Tipo | Descrição | Horário | Fila |
|------|-----------|---------|------|
| 🖤 **Preta** | Pernoite Dia Útil | 08h → 08h próximo dia | Antigo → Moderno |
| 💚 **Diário** | Serviço Leve | 12h → 16h | Moderno → Antigo |
| ❤️ **Vermelha** | FDS / Feriado Comum | 08h → 08h próximo dia | Antigo → Moderno |
| 💜 **Roxa** | Feriado Crítico / Recesso | 08h → 08h próximo dia | Moderno → Antigo + Histórico |

### ⚙️ Geração Automática
- Identifica automaticamente o tipo de cada dia do mês
- Aplica regras de ordenação por antiguidade
- Verifica disponibilidade (afastamentos)
- Detecta conflitos de descanso (Preta↔Vermelha: mín. 2 dias de diferença)
- Realiza **trocas forçadas (TF)** quando necessário, registrando motivo
- Prioriza militares **mais modernos** para feriados críticos (Roxa)
- Rastreia **histórico por evento** (ex: quem fez Natal em 2024 tem prioridade baixa em 2025)

### 🚫 Regras de Descanso
- ❌ Proibido: Preta → Vermelha com intervalo ≤ 1 dia
- ❌ Proibido: Vermelha → Preta com intervalo ≤ 1 dia
- ✅ Mínimo: 2 dias de diferença entre escalas pesadas consecutivas

### 👥 Gestão de Militares
- Cadastro completo com graduação, especialidade, número de antiguidade
- Controle de status operacional (férias, licença, destacado, etc.)
- Afastamentos com data início/fim — saem e entram automaticamente na escala
- Histórico individual de todos os serviços

### 📊 Dashboard
- Carga operacional por militar (gráfico)
- Alertas de fadiga (militares com muitos serviços pesados)
- Militares indisponíveis hoje
- Próximos serviços agendados

### 📜 Histórico e Relatórios
- Histórico completo com filtros por militar, tipo, ano, evento
- Distribuição de feriados críticos por militar
- Trocas forçadas registradas
- Carga operacional anual comparativa

---

## 📁 Estrutura do Projeto

```
escala-se-servico/
├── app.py              # Aplicação Flask principal (rotas)
├── models.py           # Modelos do banco de dados (SQLAlchemy)
├── scheduler.py        # Motor de geração da escala
├── seed_data.py        # Dados de exemplo
├── requirements.txt
├── static/
│   ├── css/style.css   # Tema militar escuro
│   └── js/main.js      # JavaScript (chart, conflitos, etc.)
└── templates/
    ├── base.html
    ├── index.html           # Dashboard
    ├── militares/           # CRUD de militares
    ├── escala/              # Calendário e geração
    ├── afastamentos/        # CRUD de afastamentos
    ├── historico/           # Histórico com filtros
    ├── feriados/            # Feriados customizados
    └── relatorios/          # Relatórios operacionais
```

---

## 🗓️ Feriados Críticos (Escala Roxa)
Calculados automaticamente:
- **Carnaval** (segunda e terça, 48/47 dias antes da Páscoa)
- **Véspera de Natal** (24/12) e **Natal** (25/12)
- **Véspera de Ano Novo** (31/12) e **Ano Novo** (01/01)

Feriados comuns nacionais (Escala Vermelha):
- Tiradentes, Dia do Trabalho, Independência, N. Sra. Aparecida,
  Finados, Proclamação da República, Sexta-Feira Santa, Corpus Christi

**Recessos operacionais** devem ser cadastrados em **Feriados → Adicionar** como tipo "Crítico".

---

## 🛠️ Tecnologias
- **Python 3.10+** / **Flask 3** / **SQLAlchemy** / **SQLite**
- **Bootstrap 5** (CDN) + CSS customizado tema militar escuro
- **Chart.js** para gráficos de carga
- Banco de dados SQLite — arquivo único `escala.db`
