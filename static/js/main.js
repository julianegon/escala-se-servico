/* Escala Naval — JS principal */

// ── Sidebar toggle (mobile) ─────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  const toggle  = document.getElementById('sidebarToggle');
  const sidebar = document.getElementById('sidebar');
  const overlay = document.getElementById('sidebarOverlay');

  if (toggle) {
    toggle.addEventListener('click', () => {
      sidebar.classList.toggle('open');
      if (overlay) overlay.classList.toggle('d-none');
    });
  }
  if (overlay) {
    overlay.addEventListener('click', () => {
      sidebar.classList.remove('open');
      overlay.classList.add('d-none');
    });
  }

  // ── Auto-fechar flash messages ──────────────────────────────
  document.querySelectorAll('.flash-msg').forEach(msg => {
    const btn = msg.querySelector('button');
    if (btn) btn.addEventListener('click', () => msg.remove());
    setTimeout(() => msg && msg.parentNode && msg.remove(), 6000);
  });

  // ── Confirmar ações destrutivas ─────────────────────────────
  document.querySelectorAll('[data-confirm]').forEach(el => {
    el.addEventListener('click', e => {
      if (!confirm(el.dataset.confirm)) e.preventDefault();
    });
  });

  // ── Confirmação de formulários destrutivos ──────────────────
  document.querySelectorAll('form[data-confirm]').forEach(form => {
    form.addEventListener('submit', e => {
      if (!confirm(form.dataset.confirm)) e.preventDefault();
    });
  });

  // ── Dashboard chart ─────────────────────────────────────────
  buildDashboardChart();

  // ── Verificação de conflito no formulário de serviço ────────
  setupConflictCheck();
});

// ── Dashboard: gráfico de carga ─────────────────────────────
function buildDashboardChart() {
  const canvas = document.getElementById('cargaChart');
  if (!canvas) return;

  const ano = canvas.dataset.ano || new Date().getFullYear();

  fetch(`/api/carga/${ano}`)
    .then(r => r.json())
    .then(data => {
      if (!data.length) return;
      const labels   = data.map(d => d.nome.split(' ').slice(0, 2).join(' '));
      const preta    = data.map(d => d.preta);
      const diario   = data.map(d => d.diario);
      const vermelha = data.map(d => d.vermelha);
      const roxa     = data.map(d => d.roxa);

      new Chart(canvas, {
        type: 'bar',
        data: {
          labels,
          datasets: [
            { label: 'Preta',    data: preta,    backgroundColor: '#4b5563' },
            { label: 'Diário',   data: diario,   backgroundColor: '#238636' },
            { label: 'Vermelha', data: vermelha, backgroundColor: '#da3633' },
            { label: 'Roxa',     data: roxa,     backgroundColor: '#8957e5' },
          ]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { labels: { color: '#9198a1', font: { size: 11 } } },
            tooltip: { mode: 'index', intersect: false }
          },
          scales: {
            x: {
              stacked: true,
              ticks: { color: '#9198a1', font: { size: 10 } },
              grid:  { color: '#30363d' }
            },
            y: {
              stacked: true, beginAtZero: true,
              ticks: { color: '#9198a1', stepSize: 1 },
              grid:  { color: '#30363d' }
            }
          }
        }
      });
    })
    .catch(() => {});
}

// ── Verificação de conflito ao adicionar serviço ─────────────
function setupConflictCheck() {
  const milSel  = document.getElementById('military_id');
  const dataInp = document.getElementById('data_input');
  const tipoSel = document.getElementById('tipo_escala');
  const alertEl = document.getElementById('conflito_alert');

  if (!milSel || !dataInp || !tipoSel || !alertEl) return;

  function check() {
    const mid  = milSel.value;
    const data = dataInp.value;
    const tipo = tipoSel.value;
    if (!mid || !data || !tipo) { alertEl.style.display = 'none'; return; }

    fetch(`/api/conflitos/check?military_id=${mid}&data=${data}&tipo=${tipo}`)
      .then(r => r.json())
      .then(d => {
        if (d.conflito) {
          alertEl.style.display = 'block';
          alertEl.querySelector('.conflito-msg').textContent = d.motivo || 'Conflito de descanso detectado.';
        } else {
          alertEl.style.display = 'none';
        }
      })
      .catch(() => alertEl.style.display = 'none');
  }

  milSel.addEventListener('change', check);
  dataInp.addEventListener('change', check);
  tipoSel.addEventListener('change', check);
}

// ── Utilitário: submit form por POST ────────────────────────
function submitPost(action, confirm_msg) {
  if (confirm_msg && !confirm(confirm_msg)) return;
  const form = document.createElement('form');
  form.method = 'POST';
  form.action = action;
  document.body.appendChild(form);
  form.submit();
}
