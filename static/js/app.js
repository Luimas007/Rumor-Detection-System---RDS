/* RDS Scraper — Frontend v2 | Vanilla JS */
'use strict';

const API           = '/api';
const POLL_MS       = 2000;

// ── State ─────────────────────────────────────────────────────────────────────
let currentJobId = null;
let pollTimer    = null;
let allArticles  = [];
let currentQuery = '';

// ── DOM helpers ────────────────────────────────────────────────────────────────
const $  = sel => document.querySelector(sel);
const $$ = sel => [...document.querySelectorAll(sel)];
const show  = el => el?.classList.remove('hidden');
const hide  = el => el?.classList.add('hidden');
const esc   = s  => String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');

// ── View router ────────────────────────────────────────────────────────────────
$$('.nav-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    $$('.nav-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    $$('.view').forEach(v => v.classList.remove('active'));
    $(`#view-${btn.dataset.view}`)?.classList.add('active');
    if (btn.dataset.view === 'history') loadHistory();
  });
});

// ── Source chips ───────────────────────────────────────────────────────────────
async function loadSources() {
  try {
    const sources = await apiFetch(`${API}/sources`);
    const container = $('#source-checkboxes');
    container.innerHTML = '';
    sources.forEach(src => {
      const label = document.createElement('label');
      label.className = 'source-chip checked';
      label.innerHTML = `
        <input type="checkbox" name="sources" value="${esc(src.key)}" checked/>
        <span class="source-chip-dot"></span>
        ${esc(src.name)}`;
      label.addEventListener('change', () => label.classList.toggle('checked', label.querySelector('input').checked));
      container.appendChild(label);
    });
  } catch (e) {
    console.warn('Could not load sources:', e);
  }
}

// ── Search ─────────────────────────────────────────────────────────────────────
$('#search-form').addEventListener('submit', async e => {
  e.preventDefault();
  const query = $('#search-input').value.trim();
  if (!query) return;

  const sources = $$('input[name="sources"]:checked').map(cb => cb.value);
  if (!sources.length) { alert('Select at least one source.'); return; }

  const max = parseInt($('#max-articles').value) || 40;
  await startSearch(query, sources, max);
});

async function startSearch(query, sources, maxArticles) {
  clearPoll();
  allArticles  = [];
  currentQuery = query;
  currentJobId = null;

  $('#search-btn').disabled = true;
  resetUI();
  showProgress();

  try {
    const res = await apiPost(`${API}/search`, { query, sources, max_articles: maxArticles });
    currentJobId = res.job_id;
    pollJob();
  } catch (err) {
    showError('Search failed: ' + err.message);
    $('#search-btn').disabled = false;
  }
}

function pollJob() {
  if (!currentJobId) return;
  pollTimer = setTimeout(async () => {
    try {
      const job = await apiFetch(`${API}/job/${currentJobId}`);
      updateProgress(job);

      if (job.status === 'completed') {
        onComplete(job);
      } else if (job.status === 'failed') {
        showError('Scrape failed: ' + (job.error || 'Unknown error'));
        $('#search-btn').disabled = false;
      } else {
        pollJob();
      }
    } catch (_) { pollJob(); }
  }, POLL_MS);
}

function clearPoll() { clearTimeout(pollTimer); pollTimer = null; }

// ── Progress phases ────────────────────────────────────────────────────────────
function showProgress() {
  show($('#progress-panel'));
  ['phase-1','phase-2','phase-3'].forEach(id => {
    const el = $(`#${id}`);
    el?.classList.remove('active','done');
  });
  $('#progress-msg').textContent = 'Starting…';
}

function updateProgress(job) {
  const msg = job.progress_message || '';
  $('#progress-msg').textContent = msg;

  const p1 = $('#phase-1'), p2 = $('#phase-2'), p3 = $('#phase-3');

  if (msg.includes('Phase 1')) {
    p1.classList.add('active');
    p2.classList.remove('active','done');
    p3.classList.remove('active','done');
  } else if (msg.includes('Phase 2')) {
    p1.classList.replace('active','done') || p1.classList.add('done');
    p2.classList.add('active');
    p3.classList.remove('active','done');
  } else if (msg.includes('Phase 3') || msg.includes('Cleaning')) {
    p1.classList.add('done'); p1.classList.remove('active');
    p2.classList.add('done'); p2.classList.remove('active');
    p3.classList.add('active');
  } else if (job.status === 'completed') {
    ['phase-1','phase-2','phase-3'].forEach(id => {
      const el = $(`#${id}`);
      el.classList.add('done'); el.classList.remove('active');
    });
  }
}

function onComplete(job) {
  clearPoll();
  $('#search-btn').disabled = false;
  hide($('#progress-panel'));

  allArticles = job.articles || [];
  renderStats(job.stats || {});
  populateSourceFilter(allArticles);

  if (!allArticles.length) { show($('#empty-state')); return; }

  renderArticles(allArticles);
  updateToolbar(allArticles.length, currentQuery);
}

// ── Stats bar ──────────────────────────────────────────────────────────────────
function renderStats(stats) {
  show($('#stats-bar'));
  const elapsed = stats.elapsed_seconds != null ? `${stats.elapsed_seconds}s` : '—';

  const items = [
    { val: stats.total_urls        ?? 0, lbl: 'URLs found',      cls: '' },
    { val: stats.unique_urls       ?? 0, lbl: 'Unique',          cls: '' },
    { val: stats.fetched_full      ?? 0, lbl: 'Full articles',   cls: 'green' },
    { val: stats.fetched_snippet   ?? 0, lbl: 'Snippet only',    cls: 'amber' },
    { val: stats.fetch_failed      ?? 0, lbl: 'Failed',          cls: 'red' },
    { val: stats.duplicates_removed ?? 0, lbl: 'Deduped',        cls: 'purple' },
    { val: stats.final_count       ?? 0, lbl: 'Final articles',  cls: '' },
    { val: elapsed,                       lbl: 'Time taken',      cls: '' },
  ];

  $('#stats-grid').innerHTML = items.map(i =>
    `<div class="stat-item ${i.cls}">
       <span class="stat-val">${esc(i.val)}</span>
       <span class="stat-lbl">${esc(i.lbl)}</span>
     </div>`
  ).join('');

  // Per-source breakdown
  const counts = stats.source_counts || {};
  if (Object.keys(counts).length) {
    const src = Object.entries(counts)
      .map(([k,v]) => `<div class="stat-item"><span class="stat-val">${v}</span><span class="stat-lbl">${k}</span></div>`)
      .join('');
    $('#stats-grid').insertAdjacentHTML('beforeend', src);
  }
}

// ── Toolbar ────────────────────────────────────────────────────────────────────
function updateToolbar(count, query) {
  show($('#results-toolbar'));
  $('#result-count').textContent = `${count} article${count !== 1 ? 's' : ''}`;
  $('#result-query').textContent = `for "${query}"`;
}

function populateSourceFilter(articles) {
  const types = [...new Set(articles.map(a => a.source_type).filter(Boolean))].sort();
  const sel = $('#source-filter');
  sel.innerHTML = '<option value="">All sources</option>';
  types.forEach(t => sel.insertAdjacentHTML('beforeend', `<option value="${esc(t)}">${esc(t)}</option>`));
}

['source-filter','mode-filter','sort-select'].forEach(id =>
  $(`#${id}`)?.addEventListener('change', applyFilters)
);
$('#filter-input')?.addEventListener('input', applyFilters);

function applyFilters() {
  const text   = ($('#filter-input').value || '').toLowerCase();
  const source = $('#source-filter').value;
  const mode   = $('#mode-filter').value;
  const sort   = $('#sort-select').value;

  let list = [...allArticles];
  if (text)   list = list.filter(a => (a.title + a.content + a.snippet).toLowerCase().includes(text));
  if (source) list = list.filter(a => a.source_type === source);
  if (mode)   list = list.filter(a => a.fetch_mode === mode);

  if (sort === 'words_desc') list.sort((a,b) => (b.word_count||0) - (a.word_count||0));
  else if (sort === 'words_asc') list.sort((a,b) => (a.word_count||0) - (b.word_count||0));
  // default: date (already sorted server-side)

  renderArticles(list);
  $('#result-count').textContent = `${list.length} article${list.length !== 1 ? 's' : ''}`;
}

// ── Render articles ────────────────────────────────────────────────────────────
function renderArticles(articles) {
  const grid = $('#articles-grid');
  grid.innerHTML = '';
  hide($('#empty-state'));

  if (!articles.length) { show($('#empty-state')); return; }

  articles.forEach(a => {
    const card = buildCard(a);
    grid.appendChild(card);
  });
}

function buildCard(a) {
  const div = document.createElement('div');
  div.className = 'article-card';

  const stripeClass = `stripe-${a.source_type || 'default'}`;
  const modeBadge   = modeBadgeHTML(a.fetch_mode);
  const preview     = (a.content || a.snippet || '').slice(0, 280).trim();
  const dateStr     = fmtDate(a.published);
  const source      = shortSource(a.source);

  div.innerHTML = `
    <div class="card-stripe ${stripeClass}"></div>
    <div class="card-head">
      <span class="card-source">${esc(source)}</span>
      <span class="card-date">${esc(dateStr)}</span>
    </div>
    <div class="card-title">${esc(a.title || 'Untitled')}</div>
    ${preview ? `<div class="card-preview">${esc(preview)}${(a.content || '').length > 280 ? '…' : ''}</div>` : ''}
    <div class="card-foot">
      ${modeBadge}
      ${a.word_count ? `<span class="badge badge-words">${a.word_count} words</span>` : ''}
      ${a.language && a.language !== 'unknown' ? `<span class="badge badge-lang">${esc(a.language)}</span>` : ''}
      <span class="card-link">Details →</span>
    </div>`;

  div.addEventListener('click', () => openModal(a));
  return div;
}

function modeBadgeHTML(mode) {
  if (mode === 'full')         return '<span class="badge badge-full">Full article</span>';
  if (mode === 'snippet_only') return '<span class="badge badge-snippet">Snippet</span>';
  return '<span class="badge badge-failed">Failed</span>';
}

// ── Modal ──────────────────────────────────────────────────────────────────────
function openModal(a) {
  const dateStr = fmtDate(a.published);
  const hasContent = a.content && a.content.length > 30;

  $('#modal-body').innerHTML = `
    <div class="modal-source">${esc(a.source)} · ${esc(a.source_type)}</div>
    <h2 class="modal-title">${esc(a.title || 'Untitled')}</h2>
    <div class="modal-meta">
      ${modeBadgeHTML(a.fetch_mode)}
      ${a.word_count ? `<span class="badge badge-words">${a.word_count} words</span>` : ''}
      ${a.language && a.language !== 'unknown' ? `<span class="badge badge-lang">${esc(a.language)}</span>` : ''}
      ${a.author ? `<span class="badge badge-words">by ${esc(a.author)}</span>` : ''}
      ${dateStr ? `<span class="badge badge-words">${esc(dateStr)}</span>` : ''}
    </div>

    ${hasContent ? `
    <div class="modal-section">
      <div class="modal-section-title">Article Content</div>
      <div class="modal-content">${esc(a.content)}</div>
    </div>` : ''}

    ${a.snippet && !hasContent ? `
    <div class="modal-section">
      <div class="modal-section-title">Snippet</div>
      <p class="modal-snippet">${esc(a.snippet)}</p>
    </div>` : ''}

    <a class="modal-link" href="${esc(a.url)}" target="_blank" rel="noopener">
      Open original article ↗
    </a>`;

  show($('#modal-overlay'));
}

$('#modal-close').addEventListener('click', () => hide($('#modal-overlay')));
$('#modal-overlay').addEventListener('click', e => { if (e.target === $('#modal-overlay')) hide($('#modal-overlay')); });
document.addEventListener('keydown', e => { if (e.key === 'Escape') hide($('#modal-overlay')); });

// ── History ────────────────────────────────────────────────────────────────────
async function loadHistory() {
  const list = $('#history-list');
  list.innerHTML = '<p style="color:var(--text2);padding:10px">Loading…</p>';
  try {
    const jobs = await apiFetch(`${API}/jobs`);
    if (!jobs.length) {
      list.innerHTML = '<p style="color:var(--text2);padding:10px">No previous searches.</p>';
      return;
    }
    list.innerHTML = '';
    jobs.forEach(job => {
      const card = document.createElement('div');
      card.className = 'history-card';
      const s = job.stats || {};
      card.innerHTML = `
        <div>
          <div class="history-query">${esc(job.query)}</div>
          <div class="history-meta">
            ${fmtDate(job.created_at)} · ${s.final_count || 0} articles
            · ${(job.sources||[]).join(', ')}
            ${s.elapsed_seconds ? `· ${s.elapsed_seconds}s` : ''}
          </div>
        </div>
        <span class="status-badge status-${job.status}">${job.status}</span>`;
      if (job.status === 'completed') {
        card.addEventListener('click', () => reopenJob(job));
      }
      list.appendChild(card);
    });
  } catch (e) {
    list.innerHTML = `<p style="color:var(--red);padding:10px">Error: ${esc(e.message)}</p>`;
  }
}

async function reopenJob(job) {
  // Switch to search view and load the job's articles
  $$('.nav-btn').forEach(b => b.classList.remove('active'));
  $('[data-view="search"]').classList.add('active');
  $$('.view').forEach(v => v.classList.remove('active'));
  $('#view-search').classList.add('active');

  currentQuery  = job.query;
  $('#search-input').value = job.query;
  resetUI();

  try {
    const full = await apiFetch(`${API}/job/${job.id}`);
    allArticles = full.articles || [];
    currentQuery = full.query;
    renderStats(full.stats || {});
    populateSourceFilter(allArticles);
    renderArticles(allArticles);
    updateToolbar(allArticles.length, currentQuery);
  } catch (e) {
    showError('Could not reload job: ' + e.message);
  }
}

$('#refresh-history').addEventListener('click', loadHistory);

// ── UI helpers ─────────────────────────────────────────────────────────────────
function resetUI() {
  hide($('#progress-panel'));
  hide($('#stats-bar'));
  hide($('#results-toolbar'));
  hide($('#empty-state'));
  $('#articles-grid').innerHTML = '';
  $('#source-filter').innerHTML = '<option value="">All sources</option>';
  $('#filter-input').value = '';
}

function showError(msg) {
  hide($('#progress-panel'));
  $('#articles-grid').innerHTML =
    `<div style="grid-column:1/-1;text-align:center;padding:60px;color:var(--red)">${esc(msg)}</div>`;
}

// ── API helpers ────────────────────────────────────────────────────────────────
async function apiFetch(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}
async function apiPost(url, body) {
  const r = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await r.json();
  if (!r.ok) throw new Error(data.error || `HTTP ${r.status}`);
  return data;
}

// ── Formatting ─────────────────────────────────────────────────────────────────
function fmtDate(str) {
  if (!str) return '';
  const d = new Date(str);
  if (isNaN(d)) return str.slice(0, 10);
  return d.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
}

function shortSource(src) {
  if (!src) return 'Unknown';
  if (src.length <= 28) return src;
  return src.slice(0, 26) + '…';
}

// ── Boot ───────────────────────────────────────────────────────────────────────
loadSources();
