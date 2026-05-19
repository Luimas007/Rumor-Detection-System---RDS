/* RDS — Rumor Detection System | Frontend Application */
'use strict';

// ─── Constants ────────────────────────────────────────────────────────────────
const API = '/api';
const POLL_INTERVAL_MS = 2500;
const SOURCE_COLORS = {
  google_news: '#4285f4',
  bing_news:   '#00897b',
  reddit:      '#ff4500',
};

// ─── State ────────────────────────────────────────────────────────────────────
let currentJobId   = null;
let pollTimer      = null;
let allArticles    = [];
let currentQuery   = '';

// ─── DOM helpers ──────────────────────────────────────────────────────────────
const $  = (sel, ctx = document) => ctx.querySelector(sel);
const $$ = (sel, ctx = document) => [...ctx.querySelectorAll(sel)];

function show(el) { el?.classList.remove('hidden'); }
function hide(el) { el?.classList.add('hidden'); }
function toggle(el, force) { el?.classList.toggle('hidden', !force); }

// ─── View routing ─────────────────────────────────────────────────────────────
function initNav() {
  $$('.nav-link').forEach(link => {
    link.addEventListener('click', e => {
      e.preventDefault();
      const view = link.dataset.view;
      $$('.nav-link').forEach(l => l.classList.remove('active'));
      link.classList.add('active');
      $$('.view').forEach(v => v.classList.remove('active'));
      $(`#view-${view}`)?.classList.add('active');
      if (view === 'history') loadHistory();
    });
  });
}

// ─── Search ───────────────────────────────────────────────────────────────────
function initSearch() {
  const form  = $('#search-form');
  const input = $('#search-input');

  form.addEventListener('submit', async e => {
    e.preventDefault();
    const query = input.value.trim();
    if (!query) return;

    const sources = $$('input[name="sources"]:checked').map(cb => cb.value);
    if (!sources.length) { alert('Select at least one source.'); return; }

    const maxArticles = parseInt($('#max-articles').value) || 30;
    await startSearch(query, sources, maxArticles);
  });
}

async function startSearch(query, sources, maxArticles) {
  clearPoll();
  allArticles    = [];
  currentQuery   = query;
  currentJobId   = null;

  $('#search-btn').disabled = true;
  resetResultsUI();
  showProgress('Submitting search…', '');

  try {
    const res = await post(`${API}/search`, { query, sources, max_articles: maxArticles });
    currentJobId = res.job_id;
    pollJob();
  } catch (err) {
    showError('Failed to start search: ' + err.message);
    $('#search-btn').disabled = false;
  }
}

function pollJob() {
  if (!currentJobId) return;
  pollTimer = setTimeout(async () => {
    try {
      const job = await get(`${API}/job/${currentJobId}`);
      updateProgress(job);

      if (job.status === 'completed') {
        onJobComplete(job);
      } else if (job.status === 'failed') {
        showError('Job failed: ' + (job.error || 'Unknown error'));
        $('#search-btn').disabled = false;
      } else {
        pollJob();  // keep polling
      }
    } catch (err) {
      console.error('Poll error:', err);
      pollJob(); // retry
    }
  }, POLL_INTERVAL_MS);
}

function clearPoll() {
  if (pollTimer) { clearTimeout(pollTimer); pollTimer = null; }
}

function updateProgress(job) {
  const stats = job.stats || {};
  showProgress(
    job.progress_message || 'Processing…',
    `Found ${stats.total_found||0} · Fetched ${stats.fetched||0} · Analysed ${stats.analyzed||0}`
  );
}

function onJobComplete(job) {
  clearPoll();
  $('#search-btn').disabled = false;
  hide($('#progress-panel'));

  allArticles = job.articles || [];
  if (!allArticles.length) {
    show($('#empty-state'));
    return;
  }
  populateThemeFilter(allArticles);
  renderArticles(allArticles);
  showResultsBar(allArticles.length, currentQuery);
}

// ─── Rendering ────────────────────────────────────────────────────────────────
function renderArticles(articles) {
  const grid = $('#articles-grid');
  grid.innerHTML = '';
  hide($('#empty-state'));

  articles.forEach(a => {
    const card = buildCard(a);
    grid.appendChild(card);
  });
}

function buildCard(a) {
  const card = document.createElement('div');
  card.className = 'article-card';
  card.dataset.id = a.id;

  const accentColor = sourceColor(a.source);
  const sentClass   = `sentiment-${a.sentiment || 'neutral'}`;
  const relScore    = (a.reliability_score || 0.5) * 100;
  const relClass    = relScore >= 65 ? 'bar-high' : relScore >= 40 ? 'bar-medium' : 'bar-low';
  const dateStr     = formatDate(a.published);

  const claimsHtml = (a.key_claims || []).slice(0, 2).map(c =>
    `<li class="claim-item">${esc(c.length > 110 ? c.slice(0, 110) + '…' : c)}</li>`
  ).join('');

  const themesHtml = (a.themes || []).slice(0, 4).map(t =>
    `<span class="tag theme">${esc(t)}</span>`
  ).join('');

  card.innerHTML = `
    <div class="card-accent" style="background: linear-gradient(90deg,${accentColor},${accentColor}80)"></div>
    <div class="card-header">
      <span class="card-source">${esc(shortSource(a.source))}</span>
      <span class="card-date">${esc(dateStr)}</span>
    </div>
    <div class="card-title">${esc(a.title || 'Untitled')}</div>
    <div class="card-body">
      ${a.summary ? `<div class="card-summary">${esc(a.summary)}</div>` : ''}
      ${claimsHtml ? `
        <div>
          <div class="card-section-label">Key Claims</div>
          <ul class="claims-preview">${claimsHtml}</ul>
        </div>` : ''}
      ${themesHtml ? `<div class="tags-row">${themesHtml}</div>` : ''}
    </div>
    <div class="card-footer">
      <div class="sentiment-badge ${sentClass}">${sentimentLabel(a.sentiment)}</div>
      <div class="reliability-bar">
        <div class="bar-track"><div class="bar-fill ${relClass}" style="width:${relScore.toFixed(0)}%"></div></div>
        <span>${relScore.toFixed(0)}%</span>
      </div>
      <span class="card-read-more">Details →</span>
    </div>`;

  card.addEventListener('click', () => openModal(a));
  return card;
}

// ─── Modal ────────────────────────────────────────────────────────────────────
function openModal(a) {
  const dateStr = formatDate(a.published);
  const relScore = ((a.reliability_score || 0.5) * 100).toFixed(0);
  const sentClass = `sentiment-${a.sentiment || 'neutral'}`;

  const claimsHtml = (a.key_claims || []).map(c =>
    `<li>${esc(c)}</li>`
  ).join('') || '<li style="color:var(--text3)">No claims extracted.</li>';

  const themesHtml = (a.themes || []).map(t =>
    `<span class="tag theme">${esc(t)}</span>`
  ).join('') || '<span style="color:var(--text3);font-size:13px">None detected</span>';

  $('#modal-content').innerHTML = `
    <div class="modal-source">${esc(a.source)} · ${esc(dateStr)}</div>
    <h2 class="modal-title">${esc(a.title || 'Untitled')}</h2>

    <div style="display:flex;gap:16px;flex-wrap:wrap;margin-bottom:8px">
      <div class="sentiment-badge ${sentClass}" style="font-size:12px">${sentimentLabel(a.sentiment)} (${(a.sentiment_score*100).toFixed(0)}%)</div>
      <div class="reliability-bar">
        <div class="bar-track" style="width:80px">
          <div class="bar-fill ${relScore >= 65 ? 'bar-high' : relScore >= 40 ? 'bar-medium' : 'bar-low'}"
               style="width:${relScore}%"></div>
        </div>
        <span style="font-size:12px;color:var(--text2)">Reliability: ${relScore}%</span>
      </div>
    </div>

    <div class="modal-section">
      <h4>Summary</h4>
      <p class="modal-summary">${esc(a.summary || 'No summary generated.')}</p>
    </div>
    <div class="modal-section">
      <h4>Key Claims</h4>
      <ul class="claims-list">${claimsHtml}</ul>
    </div>
    <div class="modal-section">
      <h4>Themes</h4>
      <div class="tags-row">${themesHtml}</div>
    </div>
    ${a.clean_content ? `
    <div class="modal-section">
      <h4>Article Excerpt</h4>
      <div class="modal-content-text">${esc(a.clean_content.slice(0, 800))}${a.clean_content.length > 800 ? '…' : ''}</div>
    </div>` : ''}
    <a class="modal-link" href="${esc(a.url)}" target="_blank" rel="noopener noreferrer">
      Open original article ↗
    </a>`;

  show($('#article-modal'));
}

function initModal() {
  $('#modal-close').addEventListener('click', () => hide($('#article-modal')));
  $('#article-modal').addEventListener('click', e => {
    if (e.target === $('#article-modal')) hide($('#article-modal'));
  });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') hide($('#article-modal'));
  });
}

// ─── Filter & Sort ────────────────────────────────────────────────────────────
function populateThemeFilter(articles) {
  const themeSet = new Set();
  articles.forEach(a => (a.themes || []).forEach(t => themeSet.add(t)));
  const sel = $('#theme-filter');
  sel.innerHTML = '<option value="">All themes</option>';
  [...themeSet].sort().forEach(t => {
    const opt = document.createElement('option');
    opt.value = t; opt.textContent = t;
    sel.appendChild(opt);
  });
}

function initFilters() {
  $('#theme-filter').addEventListener('change', applyFilters);
  $('#sort-select').addEventListener('change', applyFilters);
}

function applyFilters() {
  const theme = $('#theme-filter').value;
  const sort  = $('#sort-select').value;

  let filtered = [...allArticles];
  if (theme) filtered = filtered.filter(a => (a.themes || []).includes(theme));

  if (sort === 'reliability') {
    filtered.sort((a, b) => (b.reliability_score||0) - (a.reliability_score||0));
  } else if (sort === 'sentiment') {
    const order = { positive: 0, neutral: 1, negative: 2 };
    filtered.sort((a, b) => (order[a.sentiment]||1) - (order[b.sentiment]||1));
  }
  // date sort is default from server

  renderArticles(filtered);
  $('#results-count').textContent = `${filtered.length} article${filtered.length !== 1 ? 's' : ''}`;
}

// ─── Analyze Text ─────────────────────────────────────────────────────────────
function initAnalyze() {
  $('#analyze-btn').addEventListener('click', async () => {
    const text = $('#analyze-input').value.trim();
    if (!text) return;

    $('#analyze-btn').disabled = true;
    $('#analyze-btn').textContent = 'Analysing…';
    hide($('#analyze-results'));

    try {
      const res = await post(`${API}/analyze`, { text });
      showAnalysisResults(res);
    } catch (err) {
      alert('Analysis failed: ' + err.message);
    } finally {
      $('#analyze-btn').disabled = false;
      $('#analyze-btn').textContent = 'Run Analysis';
    }
  });
}

function showAnalysisResults(res) {
  $('#a-summary').textContent = res.summary || 'No summary generated.';

  const claimsList = $('#a-claims');
  claimsList.innerHTML = '';
  (res.key_claims || []).forEach(c => {
    const li = document.createElement('li');
    li.textContent = c;
    claimsList.appendChild(li);
  });
  if (!res.key_claims?.length) {
    claimsList.innerHTML = '<li style="color:var(--text3)">No key claims extracted.</li>';
  }

  const themesEl = $('#a-themes');
  themesEl.innerHTML = (res.themes || []).map(t =>
    `<span class="tag theme">${esc(t)}</span>`
  ).join('') || '<span style="color:var(--text3);font-size:13px">None detected</span>';

  const sentClass = `sentiment-${res.sentiment || 'neutral'}`;
  $('#a-sentiment').className = `sentiment-badge ${sentClass}`;
  $('#a-sentiment').textContent = sentimentLabel(res.sentiment) +
    ` (${((res.sentiment_score||0)*100).toFixed(0)}%)`;

  const relScore = ((res.reliability_score || 0.5) * 100).toFixed(0);
  $('#a-reliability').textContent = `${relScore}%`;
  $('#a-reliability').style.color = relScore >= 65 ? 'var(--green)' :
                                     relScore >= 40 ? 'var(--amber)' : 'var(--red)';

  show($('#analyze-results'));
}

// ─── History ──────────────────────────────────────────────────────────────────
async function loadHistory() {
  const list = $('#history-list');
  list.innerHTML = '<p style="color:var(--text2);font-size:14px">Loading…</p>';
  try {
    const jobs = await get(`${API}/jobs`);
    if (!jobs.length) {
      list.innerHTML = '<p style="color:var(--text2);font-size:14px">No previous searches.</p>';
      return;
    }
    list.innerHTML = '';
    jobs.forEach(job => {
      const item = document.createElement('div');
      item.className = 'history-item';
      const stats = job.stats || {};
      item.innerHTML = `
        <div>
          <div class="history-query">${esc(job.query)}</div>
          <div class="history-meta">
            ${formatDate(job.created_at)} · ${stats.analyzed||0} articles analysed
            · Sources: ${(job.sources||[]).join(', ')}
          </div>
        </div>
        <span class="history-status status-${job.status}">${job.status}</span>`;

      item.addEventListener('click', () => {
        if (job.status === 'completed') {
          currentJobId = job.id;
          currentQuery = job.query;
          $('#search-input').value = job.query;
          // Switch to search view and load results
          $$('.nav-link').forEach(l => l.classList.remove('active'));
          $('[data-view="search"]').classList.add('active');
          $$('.view').forEach(v => v.classList.remove('active'));
          $('#view-search').classList.add('active');
          fetchAndShowJob(job.id);
        }
      });
      list.appendChild(item);
    });
  } catch (err) {
    list.innerHTML = `<p style="color:var(--red);font-size:14px">Error loading history: ${esc(err.message)}</p>`;
  }
}

async function fetchAndShowJob(jobId) {
  try {
    const job = await get(`${API}/job/${jobId}`);
    if (job.status === 'completed') {
      allArticles  = job.articles || [];
      currentQuery = job.query;
      populateThemeFilter(allArticles);
      renderArticles(allArticles);
      showResultsBar(allArticles.length, currentQuery);
    }
  } catch (err) {
    console.error(err);
  }
}

$('#refresh-history-btn')?.addEventListener('click', loadHistory);

// ─── UI State helpers ─────────────────────────────────────────────────────────
function showProgress(title, stats) {
  show($('#progress-panel'));
  $('#progress-title').textContent = title;
  $('#progress-stats').textContent = stats;
  hide($('#results-bar'));
  hide($('#empty-state'));
  $('#articles-grid').innerHTML = '';
}

function showResultsBar(count, query) {
  show($('#results-bar'));
  $('#results-count').textContent = `${count} article${count !== 1 ? 's' : ''}`;
  $('#results-query-text').textContent = query;
}

function resetResultsUI() {
  hide($('#progress-panel'));
  hide($('#results-bar'));
  hide($('#empty-state'));
  $('#articles-grid').innerHTML = '';
  $('#theme-filter').innerHTML = '<option value="">All themes</option>';
}

function showError(msg) {
  hide($('#progress-panel'));
  const grid = $('#articles-grid');
  grid.innerHTML = `<div style="grid-column:1/-1;text-align:center;padding:40px;color:var(--red)">${esc(msg)}</div>`;
}

// ─── API helpers ──────────────────────────────────────────────────────────────
async function get(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

async function post(url, body) {
  const r = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await r.json();
  if (!r.ok) throw new Error(data.error || `HTTP ${r.status}`);
  return data;
}

// ─── Formatting helpers ───────────────────────────────────────────────────────
function formatDate(str) {
  if (!str) return '—';
  const d = new Date(str);
  if (isNaN(d)) return str.slice(0, 16).replace('T', ' ');
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

function shortSource(src) {
  if (!src) return 'Unknown';
  const map = {
    'Google News': 'Google News',
    'Bing News': 'Bing News',
    'reddit': 'Reddit',
  };
  for (const [k, v] of Object.entries(map)) {
    if (src.toLowerCase().includes(k.toLowerCase())) return v;
  }
  if (src.toLowerCase().startsWith('reddit/')) return src.slice(7);
  return src.length > 25 ? src.slice(0, 25) + '…' : src;
}

function sourceColor(src) {
  if (!src) return '#6366f1';
  const l = src.toLowerCase();
  if (l.includes('google')) return '#4285f4';
  if (l.includes('bing'))   return '#00897b';
  if (l.includes('reddit')) return '#ff4500';
  return '#6366f1';
}

function sentimentLabel(s) {
  return s === 'positive' ? '▲ Positive' :
         s === 'negative' ? '▼ Negative' : '● Neutral';
}

function esc(str) {
  if (str == null) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ─── Boot ─────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  initNav();
  initSearch();
  initFilters();
  initAnalyze();
  initModal();
});
