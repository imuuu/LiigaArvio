'use strict';

const $ = (id) => document.getElementById(id);
const state = {today: '', day: '', games: [], selected: null, report: null, tab: 'summary',
  model: 'balanced', generation: 0, controller: null, navigation: {}, demo: false, backtest: null};
try { state.model = localStorage.getItem('liigaarvio-model') === 'simple' ? 'simple' : 'balanced'; } catch (_) {}
const fmt = (n, digits = 2) => n == null ? '—' : Number(n).toLocaleString('fi-FI', {minimumFractionDigits: digits, maximumFractionDigits: digits});
const pct = (n, digits = 1) => n == null ? '—' : `${fmt(n * 100, digits)} %`;
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const score = (r) => `${r.home}–${r.away}`;
const dayText = (day, full = true) => new Date(`${day}T12:00:00Z`).toLocaleDateString('fi-FI', full ? {weekday:'long',day:'numeric',month:'long',year:'numeric',timeZone:'Europe/Helsinki'} : {day:'numeric',month:'numeric',year:'numeric',timeZone:'Europe/Helsinki'});
const dateTime = (s) => new Date(s).toLocaleString('fi-FI', {timeZone:'Europe/Helsinki', dateStyle:'short', timeStyle:'short'});
function shiftDay(day, amount) { const d = new Date(`${day}T12:00:00Z`); d.setUTCDate(d.getUTCDate() + amount); return d.toISOString().slice(0,10); }
function safeLink(url, label = 'Avaa lähde ↗') { return /^https:\/\/(www\.)?liiga\.fi\//.test(url || '') ? `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(label)}</a>` : esc(label === 'Avaa lähde ↗' ? 'Testidata' : label); }

async function api(path, params = {}, signal) {
  const suffix = new URLSearchParams(params).toString();
  const response = await fetch(`${path}${suffix ? '?' + suffix : ''}`, {signal, cache:'no-store'});
  let data;
  try { data = await response.json(); }
  catch (_) { throw new Error('Palvelimen vastausta ei voitu lukea. Tarkista, että KAYNNISTA-ikkuna on edelleen auki.'); }
  if (!response.ok) {
    const error = new Error(data.error || 'Pyyntö epäonnistui.');
    error.help = data.help || '';
    throw error;
  }
  return data;
}
function status(text, extra = 'Ajat Suomen ajassa', kind = '') {
  $('sourceStatus').textContent = text;
  $('sourceTime').textContent = extra;
  $('statusDot').className = `status-dot ${kind}`;
}
function setSourceStatus(sources) {
  if (state.demo) { status('Demotila', 'Keksitty testidata', 'warn'); return; }
  if (!sources?.length) return;
  const stale = sources.some(s => s.stale);
  const oldest = sources.map(s => s.fetched_at).sort()[0];
  status(stale ? 'Vanhentunutta aineistoa' : 'Liiga.fi · tiedot haettu',
    `${stale ? 'Vanha haku' : 'Vanhin käytetty haku'} ${dateTime(oldest)}`, stale ? 'warn' : 'ok');
}
function message(lines) {
  const unique = [...new Set(lines || [])];
  $('notice').hidden = !unique.length;
  $('notice').textContent = unique.join(' ');
}
function errorBox(error, target = 'analysis') {
  $(target).innerHTML = `<div class="error-box"><h3>Tietoja ei saatu haettua</h3><p>${esc(error.message)}</p>${error.help ? `<p class="spaced">${esc(error.help)}</p>` : ''}<p class="spaced">Puuttuvaa dataa ei korvata keksityillä tuloksilla.</p><button type="button" data-action="retry">Yritä uudelleen</button></div>`;
  status('Haku epäonnistui', 'Katso virheilmoitus', 'error');
}
function loading(text = 'Haetaan otteluhistoriaa ja lasketaan arvio…') {
  $('analysis').innerHTML = `<div class="loading"><div class="spinner" aria-hidden="true"></div><div>${esc(text)}</div><small id="loadActivity">Ensimmäinen haku tallentaa tiedot välimuistiin.</small></div>`;
}
function renderGames() {
  $('gameCount').textContent = state.games.length;
  $('dayLabel').textContent = dayText(state.day);
  if (!state.games.length) {
    $('games').innerHTML = '<div class="empty"><h2>Ei pelejä</h2><p>Valittuna päivänä ei ole Liigan runkosarjapelejä.</p></div>';
    return;
  }
  $('games').innerHTML = state.games.map(g => {
    const inProgress = !g.ended && (g.started || new Date(g.start) <= new Date());
    const label = g.ended ? 'Pelattu' : inProgress ? 'Alkamisaika ohitettu' : `klo ${g.time}`;
    return `<button type="button" class="game-card ${state.selected?.key === g.key ? 'selected' : ''}" data-game="${esc(g.key)}" aria-pressed="${state.selected?.key === g.key}"><div class="game-meta"><span>${esc(label)}</span><span>${g.ended ? 'LOPPUTULOS' : 'LIIGA'}</span></div><div class="game-team"><span>${esc(g.home)}</span><span class="score">${g.started && g.home_goals != null ? g.home_goals : '—'}</span></div><div class="game-team"><span>${esc(g.away)}</span><span class="score">${g.started && g.away_goals != null ? g.away_goals : '—'}</span></div></button>`;
  }).join('');
}
function renderHeader() {
  const g = state.selected;
  if (!g) { $('matchHeader').innerHTML = ''; $('tabs').hidden = true; return; }
  $('matchHeader').innerHTML = `<div class="match-top"><div><h2>${esc(g.home)} <span class="muted">–</span> ${esc(g.away)}</h2><p>${esc(dayText(g.date, false))} · klo ${esc(g.time)} · Kausi ${esc(g.season_label)}</p></div><div class="model-control"><label for="modelSelect">Laskentamalli</label><select id="modelSelect"><option value="balanced" ${state.model === 'balanced' ? 'selected' : ''}>Tasoitettu malli</option><option value="simple" ${state.model === 'simple' ? 'selected' : ''}>Perusmaalikeskiarvo</option></select></div></div>`;
}
async function loadDay(day, refresh = false) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(day)) return;
  state.controller?.abort();
  state.controller = new AbortController();
  const generation = ++state.generation;
  state.day = day; state.report = null; state.selected = null; state.games = []; state.backtest = null;
  $('dateInput').value = day;
  $('todayBtn').classList.toggle('active', day === state.today);
  $('tomorrowBtn').classList.toggle('active', day === shiftDay(state.today, 1));
  $('matchHeader').innerHTML = ''; $('tabs').hidden = true;
  $('gameCount').textContent = '—'; $('dayLabel').textContent = dayText(day);
  $('games').innerHTML = '<div class="loading"><div class="spinner" aria-hidden="true"></div></div>';
  message([]); loading('Haetaan päivän otteluohjelmaa…'); status('Haetaan tietoja');
  $('refreshBtn').disabled = true;
  try {
    const data = await api('/api/day', {date:day, refresh:refresh ? 1 : 0}, state.controller.signal);
    if (generation !== state.generation) return;
    state.demo = data.demo; state.games = data.games; state.navigation = data.navigation || {};
    $('demoBanner').hidden = !state.demo;
    renderGames(); message(data.warnings); setSourceStatus(data.sources);
    if (state.games.length) {
      const first = state.games.find(g => !g.started && new Date(g.start) > new Date()) || state.games[0];
      await selectGame(first.key, refresh);
    } else {
      $('analysis').innerHTML = `<div class="empty"><div class="empty-symbol">—</div><h2>Välipäivä.</h2><p>Liigan lähde ei palauta runkosarjapelejä päivälle ${esc(dayText(day, false))}. Harjoitusotteluita, pudotuspelejä tai muiden sarjojen pelejä ei sekoiteta tähän näkymään.</p>${state.navigation.nextGameDate ? `<button type="button" data-action="next-games" class="primary">Seuraava pelipäivä · ${esc(dayText(state.navigation.nextGameDate, false))}</button>` : ''}</div>`;
    }
  } catch (error) {
    if (error.name !== 'AbortError' && generation === state.generation) {
      $('games').innerHTML = '<p class="note-text">Otteluohjelmaa ei voitu varmistaa.</p>';
      errorBox(error);
    }
  } finally { $('refreshBtn').disabled = false; }
}
async function selectGame(key, refresh = false) {
  const game = state.games.find(g => g.key === key);
  if (!game) return;
  state.controller?.abort(); state.controller = new AbortController();
  const generation = ++state.generation;
  state.selected = game; state.report = null;
  renderGames(); renderHeader(); $('tabs').hidden = true; loading();
  const timer = setInterval(async () => {
    try {
      const current = await api('/api/status');
      if (generation === state.generation && $('loadActivity')) $('loadActivity').textContent = current.activity;
    } catch (_) {}
  }, 3500);
  try {
    const data = await api('/api/predict', {date:state.day, game:key, model:state.model, refresh:refresh ? 1 : 0}, state.controller.signal);
    if (generation !== state.generation) return;
    state.report = data; state.demo = data.demo; $('demoBanner').hidden = !data.demo;
    message(data.source_warnings); setSourceStatus(data.sources); $('tabs').hidden = false;
    renderTab();
  } catch (error) {
    if (error.name !== 'AbortError' && generation === state.generation) errorBox(error);
  } finally { clearInterval(timer); }
}
function metric(label, value, detail = '') { return `<div class="metric"><div class="label">${esc(label)}</div><div class="value">${esc(value)}</div><div class="detail">${esc(detail)}</div></div>`; }
function heading(name, badge = '') { return `<div class="panel-head"><h3>${esc(name)}</h3>${badge ? `<span class="badge">${esc(badge)}</span>` : ''}</div>`; }
function warningsBox(report) {
  const important = report.warnings.filter(s => /Alkukausi|Tämä on ennen|jätettiin pois|teknistä rajaa/.test(s));
  return `${important.length ? `<div class="warning-box">${important.map(esc).join('<br>')}</div>` : ''}<details class="detail-block"><summary>Mitä arvio ei huomioi?</summary><p class="note-text">${report.warnings.filter(s => !important.includes(s)).map(esc).join('<br><br>')}</p></details>`;
}
function summaryView(r) {
  const g = r.fixture, p = r.probabilities, main = p.top_final[0], h = r.home.season, a = r.away.season;
  const favHome = p.winner.home >= p.winner.away;
  const tied = Math.abs(p.winner.home - p.winner.away) < 1e-12;
  const fav = tied ? 'Tasavahva arvio' : `${favHome ? g.home : g.away} ${pct(favHome ? p.winner.home : p.winner.away, 0)}`;
  const rows = [ ['Käytettyjä otteluita', h.n, a.n, 0], ['Voitot / tappiot (lopputulos)', `${h.wins} / ${h.losses}`, `${a.wins} / ${a.losses}`, null], ['Tehdyt maalit / ottelu · 60 min', h.gf_avg, a.gf_avg, 2], ['Päästetyt maalit / ottelu · 60 min', h.ga_avg, a.ga_avg, 2], ['Maalit yhteensä · 60 min', `${h.gf}–${h.ga}`, `${a.gf}–${a.ga}`, null], ['Maalit yhteensä · lopputulos', `${h.gf_final}–${h.ga_final}`, `${a.gf_final}–${a.ga_final}`, null] ];
  return `<section class="panel hero">${heading('Yksittäinen todennäköisin lopputulos', 'Sisältää JA/VL')}<div class="hero-core"><div class="hero-team">${esc(g.home)}<small>KOTI</small></div><div class="big-score">${main.home}<span>–</span>${main.away}</div><div class="hero-team">${esc(g.away)}<small>VIERAS</small></div></div><p class="score-caption">Tämän tarkan tuloksen malliosuus <strong>${pct(main.p)}</strong>. Muut tulokset yhteensä ${pct(1-main.p)}.</p><div class="hero-bottom"><span>Mallin suosikki: <strong>${esc(fav)}</strong></span><span>60 minuutin ykköstulos: <strong>${score(p.top_regular[0])}</strong></span></div></section>
    <div class="stats-grid">${metric('Maaliodotus · 60 min', fmt(p.expected_total_60), `${fmt(r.trace.lambda_home)} + ${fmt(r.trace.lambda_away)} maalia`)}${metric('Jatkoajan mahdollisuus', pct(p.regulation.draw, 0), 'Tasapeli 60 minuutin jälkeen')}${metric('Mallin maaliväli · 60 min', `${p.total_range_80[0]}–${p.total_range_80[1]}`, 'Noin 80 % mallijakaumasta')}</div>
    <section class="panel">${heading('Kumpi voittaa?', 'Sisältää JA/VL')}<div class="outcome-labels"><span><small>${esc(g.home)}</small><strong>${pct(p.winner.home)}</strong></span><span><small>${esc(g.away)}</small><strong>${pct(p.winner.away)}</strong></span></div><div class="prob-bar"><div class="home-segment" style="width:${p.winner.home*100}%"></div><div class="away-segment" style="width:${p.winner.away*100}%"></div></div><div class="three-probs"><div><small>1 · Koti, 60 min</small><strong>${pct(p.regulation.home)}</strong></div><div><small>X · Tasapeli, 60 min</small><strong>${pct(p.regulation.draw)}</strong></div><div><small>2 · Vieras, 60 min</small><strong>${pct(p.regulation.away)}</strong></div></div><p class="table-help">Jatkoajan / voittolaukausten voittaja oletetaan tasatilanteessa 50/50. Prosentit ovat mallin arvioita, eivät varmennettuja osumatodennäköisyyksiä.</p></section>
    <section class="panel">${heading('Muita todennäköisiä lopputuloksia')}<div class="top-scores">${p.top_final.slice(1,5).map(s => `<div class="score-option"><strong>${score(s)}</strong><small>${pct(s.p)}</small></div>`).join('')}</div></section>
    <section class="panel">${heading('Tämän kauden maalit ja tulokset', r.sample)}<div class="table-wrap"><table><thead><tr><th scope="col">Ennen ottelupäivää</th><th scope="col">${esc(g.home)}</th><th scope="col">${esc(g.away)}</th></tr></thead><tbody>${rows.map(row => `<tr><td>${esc(row[0])}</td><td>${row[3] == null ? esc(row[1]) : fmt(row[1],row[3])}</td><td>${row[3] == null ? esc(row[2]) : fmt(row[2],row[3])}</td></tr>`).join('')}</tbody></table></div><p class="table-help">60 min -luvut eivät sisällä jatkoajan tai voittolaukauskilpailun ratkaisumaalia. Lopputulosluvut sisältävät sen. Mukana vain laskentaan kelvolliset runkosarjaottelut.</p></section>
    ${warningsBox(r)}`;
}
function teamMath(name, t, simple) {
  const s = t.season;
  const priorDetail = t.previous.n ? `<div class="formula">Ed. kauden pohja GF = (${t.previous.gf} + 10 × ${fmt(state.report.trace.league_mean,4)}) / (${t.previous.n} + 10) = ${fmt(t.prior_gf,4)}<br>Ed. kauden pohja GA = (${t.previous.ga} + 10 × ${fmt(state.report.trace.league_mean,4)}) / (${t.previous.n} + 10) = ${fmt(t.prior_ga,4)}</div>` : `<p class="note-text">Edellisen kauden joukkueaineisto puuttuu. Pohjana sarjakeskiarvo ${fmt(t.prior_gf,4)}.</p>`;
  return `<div class="calc-team"><h3>${esc(name)}</h3>${simple ? `<div class="formula">GF = ${s.gf} / ${s.n} = <strong>${fmt(t.base_gf,4)}</strong><br>GA = ${s.ga} / ${s.n} = <strong>${fmt(t.base_ga,4)}</strong></div><p class="note-text">Perusmalli: ei tasausta eikä lisäpainoja.</p>` : `${priorDetail}<p class="note-text">1. Kauden lukujen tasaus 8 taustaottelulla. Taustan osuus ${pct(t.prior_weight)}.</p><div class="formula">GF₀ = (${s.gf} + 8 × ${fmt(t.prior_gf,4)}) / (${s.n} + 8) = ${fmt(t.base_gf,4)}<br>GA₀ = (${s.ga} + 8 × ${fmt(t.prior_ga,4)}) / (${s.n} + 8) = ${fmt(t.base_ga,4)}</div><p class="note-text">2. Viimeiset ${t.recent.n} ottelua. Paino r = 0,20 × min(n/5, 1) = ${pct(t.recent_weight)}.</p><div class="formula">GF₁ = ${fmt(1-t.recent_weight,4)} × ${fmt(t.base_gf,4)} + ${fmt(t.recent_weight,4)} × ${fmt(t.recent.gf_avg ?? 0,4)} = ${fmt(t.form_gf,4)}<br>GA₁ = ${fmt(1-t.recent_weight,4)} × ${fmt(t.base_ga,4)} + ${fmt(t.recent_weight,4)} × ${fmt(t.recent.ga_avg ?? 0,4)} = ${fmt(t.form_ga,4)}</div><p class="note-text">3. ${t.venue_kind === 'home' ? 'Kotiottelut' : 'Vierasottelut'}: ${t.venue.n} kpl. Paino v = 0,20 × min(n/10, 1) = ${pct(t.venue_weight)}.</p><div class="formula">GF = ${fmt(1-t.venue_weight,4)} × ${fmt(t.form_gf,4)} + ${fmt(t.venue_weight,4)} × ${fmt(t.venue.gf_avg ?? 0,4)} = <strong>${fmt(t.effective_gf,4)}</strong><br>GA = ${fmt(1-t.venue_weight,4)} × ${fmt(t.form_ga,4)} + ${fmt(t.venue_weight,4)} × ${fmt(t.venue.ga_avg ?? 0,4)} = <strong>${fmt(t.effective_ga,4)}</strong></div>`}</div>`;
}
function mathView(r) {
  const t = r.trace, simple = r.model === 'simple';
  const leagueFormula = t.league_previous_mean != null ? `(${t.league_current_goal_sum} / 2 + ${t.league_prior_games} × ${fmt(t.league_previous_mean,4)}) / (${t.league_current_games} + ${t.league_prior_games})` : `${t.league_current_goal_sum} / (2 × ${t.league_current_games})`;
  return `<section class="panel"><div class="step-heading"><span class="step-number">01</span><h3>Aineisto ja joukkueiden maalikeskiarvot</h3></div><p class="note-text">${esc(r.training_scope)}. Vain ennen ${esc(r.as_of_fi)} alkaneet ja haettaessa päättyneiksi merkityt ottelut. Ennustettavan ottelupäivän tuloksia ei käytetä.</p><div class="formula">Sarjan taustakeskiarvo / joukkue = ${leagueFormula} = ${fmt(t.league_mean,4)}</div>${teamMath(r.fixture.home,r.home,simple)}${teamMath(r.fixture.away,r.away,simple)}</section>
    <section class="panel"><div class="step-heading"><span class="step-number">02</span><h3>Hyökkäys kohtaa vastustajan puolustuksen</h3></div><p class="note-text">Joukkueen tehdyt maalit ja vastustajan päästetyt maalit yhdistetään aritmeettisena keskiarvona.</p><div class="formula">λkoti₀ = (${fmt(r.home.effective_gf,4)} + ${fmt(r.away.effective_ga,4)}) / 2 = <strong>${fmt(t.base_home,4)}</strong><br>λvieras₀ = (${fmt(r.away.effective_gf,4)} + ${fmt(r.home.effective_ga,4)}) / 2 = <strong>${fmt(t.base_away,4)}</strong></div></section>
    <section class="panel"><div class="step-heading"><span class="step-number">03</span><h3>Keskinäiset ja lopullinen maaliodotus</h3></div><p class="note-text">Enintään 6 viimeistä kohtaamista: ${t.h2h_current_count} tältä kaudelta ja ${t.h2h_previous_count} edelliseltä. Paino ${simple ? 'perusmallissa 0' : 'h = 0,10 × min(n/5, 1)'} = ${pct(t.h2h_weight)}.</p><div class="formula">λkoti = ${fmt(1-t.h2h_weight,4)} × ${fmt(t.base_home,4)} + ${fmt(t.h2h_weight,4)} × ${fmt(t.h2h_home_avg ?? 0,4)} = <strong>${fmt(t.lambda_home,4)}</strong><br>λvieras = ${fmt(1-t.h2h_weight,4)} × ${fmt(t.base_away,4)} + ${fmt(t.h2h_weight,4)} × ${fmt(t.h2h_away_avg ?? 0,4)} = <strong>${fmt(t.lambda_away,4)}</strong></div><p class="note-text">Ei erillistä arvattua kotietulisää. Tasoitettu malli hyödyntää koti- ja vieraspelien havaittuja lukuja. Painot ovat käsin valittuja, eivät historiatestillä optimoituja. Samat ottelut voivat esiintyä kauden, viime pelien ja keskinäisten aineistoissa.</p></section>
    <section class="panel"><div class="step-heading"><span class="step-number">04</span><h3>Maaleista tulostodennäköisyyksiksi</h3></div><div class="formula">P(k maalia) = exp(−λ) × λ^k / k!<br>P(koti=h, vieras=a) = Pkoti(h) × Pvieras(a)<br>P(kotivoitto, lopputulos) = P(h &gt; a) + 0,5 × P(h = a)<br>E(maalit, lopputulos) = λkoti + λvieras + P(h = a)</div><p class="note-text">Joukkueiden maalit oletetaan riippumattomiksi Poisson-jakaumiksi. Tasatuloksen massa jaetaan lopputuloksiin (h+1)–h ja h–(h+1) puoliksi. Taulukon suurin tulostodennäköisyys valitaan — keskiarvoja ei vain pyöristetä. Maalijakauman numeerinen häntä on alle 10⁻¹³ per joukkue; todennäköisyydet normalisoidaan.</p><p class="note-text spaced">Yhteensä 60 min: ${fmt(r.probabilities.expected_total_60,4)} maalia. Lopputulos: ${fmt(r.probabilities.expected_total_final,4)} maalia. Jakauman summa: ${fmt(r.probabilities.mass,8)}.</p></section>
    <section class="panel">${heading('Maalimäärän malliosuudet · 60 min')}${r.probabilities.over.map(o => `<div class="line-data"><span>Yli ${fmt(o.line,1)} maalia</span><strong>${pct(o.p)}</strong></div>`).join('')}</section>`;
}
function historyTable(games, teamKey) {
  if (!games.length) return '<p class="note-text">Ei otteluita tässä aineistossa. Puuttuvaa historiaa ei keksitä.</p>';
  return `<div class="table-wrap"><table class="history-table"><thead><tr><th>Päivä</th><th>Ottelu</th><th>Loppu</th><th>60 min</th><th>Lähde</th></tr></thead><tbody>${games.map(g => {
    const win = (g.home_key === teamKey && g.home_goals > g.away_goals) || (g.away_key === teamKey && g.away_goals > g.home_goals);
    const extra = g.home_goals !== g.home_60 || g.away_goals !== g.away_60;
    return `<tr><td>${esc(dayText(g.date,false))}</td><td><span class="result-tag ${win ? '' : 'loss'}">${win ? 'V' : 'T'}</span>${esc(g.home)} – ${esc(g.away)}<span class="hist-sub">${esc(g.season_label)}${extra ? ' · JA/VL' : ''}</span></td><td>${g.home_goals}–${g.away_goals}</td><td>${g.home_60}–${g.away_60}</td><td>${safeLink(g.data_url,'↗')}</td></tr>`;
  }).join('')}</tbody></table></div>`;
}
function historyView(r) {
  return `<section class="panel">${heading('Keskinäiset kohtaamiset', `Paino ${pct(r.trace.h2h_weight)}`)}<p class="note-text" style="margin-bottom:14px">Tämän ja edellisen kauden runkosarja, enintään 6 viimeistä. V/T nykyisen kotijoukkueen näkökulmasta.</p>${historyTable(r.h2h.games,r.fixture.home_key)}</section>
    <section class="panel">${heading(`${r.fixture.home} · viimeiset ${r.home.recent.n}`)}${historyTable(r.home.recent.games,r.fixture.home_key)}</section>
    <section class="panel">${heading(`${r.fixture.away} · viimeiset ${r.away.recent.n}`)}${historyTable(r.away.recent.games,r.fixture.away_key)}</section>
    <details class="detail-block"><summary>${esc(r.fixture.home)} · kaikki käytetyt tämän kauden ottelut (${r.home.season.n})</summary><div class="spaced">${historyTable(r.home.season.games,r.fixture.home_key)}</div></details>
    <details class="detail-block"><summary>${esc(r.fixture.away)} · kaikki käytetyt tämän kauden ottelut (${r.away.season.n})</summary><div class="spaced">${historyTable(r.away.season.games,r.fixture.away_key)}</div></details>`;
}
function sourceRow(s) { return `<div class="source-row"><strong class="${s.stale ? 'stale' : ''}">${s.stale ? 'VANHA VÄLIMUISTI · uusi haku epäonnistui' : s.cached ? 'Välimuisti' : 'Verkosta haettu'}</strong>${safeLink(s.url,s.url)}<small>Haettu ${esc(dateTime(s.fetched_at))} Suomen aikaa.</small>${s.error ? `<p class="note-text spaced">${esc(s.error)}</p>` : ''}</div>`; }
function sourcesView(r) {
  return `<section class="panel"><div class="download-row"><div><h3>Laskelman tarkistusjälki</h3><p class="note-text small-gap">Tallenna tilastot, kaavat, ottelurivit ja lähdeosoitteet JSON-tiedostoksi.</p></div><button type="button" class="primary" data-action="export">Tallenna laskelma ↓</button></div></section>
    <section class="panel">${heading('Mistä data haetaan?')}<p class="note-text">Liigan oman sivuston julkisista JSON-ottelutiedoista. Päivän ohjelma, kauden tulokset ja edellisen kauden tausta haetaan erikseen. Ohjelma laskee keskiarvot itse otteluriveistä eikä kopioi hakukoneiden ennustetekstejä.</p><div class="line-data"><span>Aineiston rajaus</span><strong>Vain Liigan runkosarja</strong></div><div class="line-data"><span>Tietoja ajalta ennen</span><strong>${esc(r.as_of_fi)}</strong></div><div class="line-data"><span>Laskentamallin versio</span><strong>${esc(r.model_version)}</strong></div><div class="line-data"><span>Laskennasta pois, puuttuva 60 min</span><strong>${r.excluded_count} ottelua</strong></div><p class="note-text spaced">Pudotuspelit, CHL ja harjoitusottelut eivät sisälly. Rajapinta voi muuttua tai estää yhteyden. Tällöin ohjelma näyttää virheen tai merkitsee vanhan välimuistin näkyvästi.</p></section>
    <section class="panel">${heading('Käytetyt verkkovastaukset', `${r.sources.length} lähdevastausta`)}${r.demo ? '<div class="warning-box">DEMO. Alla ei ole oikeita verkkolähteitä. Kaikki näytetyt tulokset ovat keksittyjä.</div>' : r.sources.slice(0,8).map(sourceRow).join('')}${r.sources.length > 8 ? `<details class="spaced"><summary>Kaikki ${r.sources.length} verkkovastausta</summary>${r.sources.slice(8).map(sourceRow).join('')}</details>` : ''}</section>`;
}
function backtestView() {
  if (!state.backtest) return `<section class="panel backtest-intro"><h3>Miten malli olisi osunut aiempiin peleihin?</h3><p>Laske enintään 100 valittuun päivään mennessä päättyneen tämän kauden ottelun arviot. Jokainen arvio käyttää vain omaa ottelupäiväänsä edeltäviä tuloksia. Ennustettavan pelin tulos ei pääse sen omiin lähtötietoihin.</p><button type="button" class="primary" data-action="backtest">Laske historiatesti</button><p>Testi ei säädä mallia eikä todista tulevaa osumatarkkuutta. Pelkkä voittajan osumaprosentti ei mittaa ennusteiden kalibrointia.</p></section>`;
  const b = state.backtest;
  if (!b.n) return '<div class="empty"><h2>Ei riittävästi historiaa</h2><p>Yhtään aiempaa ottelua ei pystytty arvioimaan ilman puuttuvia lähtötietoja.</p></div>';
  return `${b.demo ? '<div class="warning-box">DEMO: nämä osumat ovat keksityllä aineistolla tehty ohjelmistotesti, eivät todiste ennustekyvystä.</div>' : ''}${b.stale ? '<div class="warning-box">Osa historiatestin aineistosta tulee vanhentuneesta välimuistista.</div>' : ''}
    <div class="report-values">${metric('Arvioituja otteluita',fmt(b.n,0),`${b.skipped} ohitettu puuttuvan historian takia`)}${metric('Tarkka lopputulos oikein',pct(b.exact_rate),`3 suosikkituloksen osuus ${pct(b.top3_rate)}`)}${metric('Suosikki voitti',pct(b.winner_rate),`${b.winner_n} peliä, joissa oli suosikki`)}</div>
    <section class="panel spaced">${heading('Todennäköisyyksien tarkistus · 1X2, 60 min')}<div class="line-data"><span>Brier-pisteytys (pienempi on parempi)</span><strong>${fmt(b.brier,4)}</strong></div><div class="line-data"><span>Tasajaon 1/3–1/3–1/3 vertailuarvo</span><strong>${fmt(b.uniform_brier,4)}</strong></div><div class="line-data"><span>Logaritminen tappio (pienempi on parempi)</span><strong>${fmt(b.logloss,4)}</strong></div><p class="note-text spaced">Brier = Σ(p − havainto)² kolmelle tulosluokalle; asteikko 0–2. Tasajako on vain yksinkertainen vertailukohta, ei vahva urheilumalli. ${esc(b.note)}</p></section>
    <section class="panel">${heading('Viimeiset testatut ottelut', 'Enintään 30 riviä')}<div class="table-wrap"><table class="history-table"><thead><tr><th>Päivä</th><th>Ottelu</th><th>Arvio</th><th>Tulos</th></tr></thead><tbody>${b.rows.map(row => `<tr><td>${esc(dayText(row.game.date,false))}</td><td>${esc(row.game.home)} – ${esc(row.game.away)}</td><td>${row.predicted_home}–${row.predicted_away}${row.exact ? ' ✓' : ''}</td><td>${row.game.home_goals}–${row.game.away_goals}</td></tr>`).join('')}</tbody></table></div></section>`;
}
function renderTab() {
  if (!state.report) return;
  document.querySelectorAll('[data-tab]').forEach(b => { b.classList.toggle('active',b.dataset.tab === state.tab); b.setAttribute('aria-current',b.dataset.tab === state.tab ? 'page' : 'false'); });
  const renderers = {summary:summaryView, math:mathView, history:historyView, sources:sourcesView, backtest:backtestView};
  $('analysis').innerHTML = renderers[state.tab](state.report);
}
async function runBacktest() {
  const generation = state.generation;
  loading('Lasketaan aiempien pelien arviot ilman tulosvuotoa…');
  try {
    const report = await api('/api/backtest',{date:state.day,model:state.model},state.controller.signal);
    if (generation !== state.generation) return;
    state.backtest = report;
    if (state.tab === 'backtest') renderTab();
  } catch (error) { if (error.name !== 'AbortError' && generation === state.generation && state.tab === 'backtest') errorBox(error); }
}
function exportReport() {
  if (!state.report) return;
  const blob = new Blob([JSON.stringify(state.report,null,2)],{type:'application/json;charset=utf-8'});
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob); link.download = `LiigaArvio_${state.day}_${state.selected.key}${state.demo ? '_DEMO' : ''}.json`;
  link.click(); setTimeout(() => URL.revokeObjectURL(link.href),1000);
}
$('todayBtn').addEventListener('click',() => loadDay(state.today));
$('tomorrowBtn').addEventListener('click',() => loadDay(shiftDay(state.today,1)));
$('prevDayBtn').addEventListener('click',() => loadDay(shiftDay(state.day,-1)));
$('nextDayBtn').addEventListener('click',() => loadDay(shiftDay(state.day,1)));
$('dateInput').addEventListener('change',(event) => loadDay(event.target.value));
$('refreshBtn').addEventListener('click',() => loadDay(state.day,true));
document.addEventListener('click',(event) => {
  const game = event.target.closest('[data-game]'); if (game) { selectGame(game.dataset.game); return; }
  const tab = event.target.closest('[data-tab]'); if (tab) { state.tab = tab.dataset.tab; renderTab(); return; }
  const action = event.target.closest('[data-action]')?.dataset.action;
  if (action === 'retry') { if (state.selected) selectGame(state.selected.key,true); else loadDay(state.day,true); }
  if (action === 'next-games') loadDay(state.navigation.nextGameDate);
  if (action === 'export') exportReport();
  if (action === 'backtest') runBacktest();
});
document.addEventListener('change',(event) => {
  if (event.target.id === 'modelSelect') {
    state.model = event.target.value; state.backtest = null;
    try { localStorage.setItem('liigaarvio-model',state.model); } catch (_) {}
    selectGame(state.selected.key);
  }
});
(async () => {
  try {
    const config = await api('/api/config'); state.today = config.today; state.demo = config.demo;
    $('demoBanner').hidden = !config.demo;
    await loadDay(config.today);
  } catch (error) { errorBox(error); }
})();
