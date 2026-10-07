// Benchmark: клиентский рендер результатов из index.json (только чтение,
// same-origin fetch, без форм и отправки данных).
(function () {
  'use strict';

  var CHART_COLORS = ['#60a5fa', '#a78bfa', '#34d399', '#fbbf24', '#f472b6', '#22d3ee'];
  var SUMMARY_LABELS = {
    total: 'Всего прогонов',
    applied: 'Применено',
    voided: 'Отменено',
    tombstone: 'Заглушек',
    skipped: 'Пропущено'
  };
  var FEED_LIMIT = 10;
  var CHART_TOP = 6;

  function esc(text) {
    return String(text)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function fmtDate(iso) {
    var p = String(iso || '').split('-');
    if (p.length !== 3) return String(iso || '—');
    return p[2] + '.' + p[1] + '.' + p[0];
  }

  function plural(n, one, few, many) {
    var n10 = n % 10, n100 = n % 100;
    if (n10 === 1 && n100 !== 11) return one;
    if (n10 >= 2 && n10 <= 4 && (n100 < 10 || n100 >= 20)) return few;
    return many;
  }

  function renderStats(data) {
    var count = Object.keys(data.models).length;
    var total = (data.matchups_summary && data.matchups_summary.total) || data.elo_history.length;
    var stats = [
      [String(count), plural(count, 'модель', 'модели', 'моделей')],
      [String(total), plural(total, 'прогон', 'прогона', 'прогонов')],
      [fmtDate(data.updated), 'обновлено']
    ];
    document.getElementById('bm-stats').innerHTML = stats.map(function (s) {
      return '<li><strong class="stat-num">' + esc(s[0]) + '</strong>' +
             '<span class="stat-label">' + esc(s[1]) + '</span></li>';
    }).join('');
  }

  function renderTable(data) {
    var models = Object.keys(data.models).map(function (id) {
      var m = data.models[id];
      m.id = id;
      return m;
    });
    models.sort(function (a, b) {
      return (b.elo - a.elo) || (b.games - a.games) || a.name.localeCompare(b.name, 'ru');
    });
    document.getElementById('bm-tbody').innerHTML = models.map(function (m, i) {
      return '<tr>' +
        '<td class="bm-rank">' + (i + 1) + '</td>' +
        '<td>' + esc(m.name) + '</td>' +
        '<td class="num bm-elo">' + m.elo + '</td>' +
        '<td class="bm-wdl">' + m.wins + '-' + m.draws + '-' + m.losses + '</td>' +
        '<td class="num">' + m.games + '</td>' +
        '</tr>';
    }).join('');
    return models;
  }

  function buildSeries(data) {
    // Траектория ELO каждой модели: после каждого прогона фиксируем after-значение.
    var history = data.elo_history.slice().sort(function (a, b) { return a.seq - b.seq; });
    var series = {};
    history.forEach(function (r) {
      if (!series[r.model_a_id]) series[r.model_a_id] = [];
      if (!series[r.model_b_id]) series[r.model_b_id] = [];
      series[r.model_a_id].push({ seq: r.seq, date: r.date, elo: r.elo_a.after });
      series[r.model_b_id].push({ seq: r.seq, date: r.date, elo: r.elo_b.after });
    });
    return { series: series, history: history };
  }

  function renderChart(data, models) {
    var built = buildSeries(data);
    var series = built.series;
    var history = built.history;
    if (!history.length) return;

    var top = models.slice(0, CHART_TOP);
    var W = 720, H = 300, PAD_L = 44, PAD_R = 12, PAD_T = 16, PAD_B = 34;
    var plotW = W - PAD_L - PAD_R, plotH = H - PAD_T - PAD_B;
    var maxSeq = history[history.length - 1].seq;

    var eloMin = Infinity, eloMax = -Infinity;
    top.forEach(function (m) {
      (series[m.id] || []).forEach(function (p) {
        if (p.elo < eloMin) eloMin = p.elo;
        if (p.elo > eloMax) eloMax = p.elo;
      });
    });
    if (!isFinite(eloMin)) { eloMin = 0; eloMax = 1; }
    var span = Math.max(eloMax - eloMin, 1);
    eloMin -= span * 0.06;
    eloMax += span * 0.06;

    function x(seq) { return PAD_L + (maxSeq <= 1 ? 0 : (seq - 1) / (maxSeq - 1) * plotW); }
    function y(elo) { return PAD_T + (1 - (elo - eloMin) / (eloMax - eloMin)) * plotH; }

    var svg = ['<svg viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="График динамики рейтингов топ-моделей">'];

    // Горизонтальные линии сетки с подписями ELO.
    for (var i = 0; i <= 4; i++) {
      var val = eloMin + (eloMax - eloMin) * i / 4;
      var yy = y(val);
      svg.push('<line x1="' + PAD_L + '" y1="' + yy.toFixed(1) + '" x2="' + (W - PAD_R) +
               '" y2="' + yy.toFixed(1) + '" stroke="currentColor" stroke-opacity="0.14"/>');
      svg.push('<text x="' + (PAD_L - 8) + '" y="' + (yy + 4).toFixed(1) +
               '" text-anchor="end" font-size="11" fill="currentColor" fill-opacity="0.6">' +
               Math.round(val) + '</text>');
    }

    // Подписи оси X: первая и последняя дата истории.
    var first = history[0], last = history[history.length - 1];
    svg.push('<text x="' + PAD_L + '" y="' + (H - 10) + '" font-size="11" fill="currentColor" fill-opacity="0.6">' +
             fmtDate(first.date) + '</text>');
    svg.push('<text x="' + (W - PAD_R) + '" y="' + (H - 10) + '" text-anchor="end" font-size="11" fill="currentColor" fill-opacity="0.6">' +
             fmtDate(last.date) + '</text>');

    // Линии топ-моделей.
    top.forEach(function (m, idx) {
      var pts = series[m.id] || [];
      if (!pts.length) return;
      var d = pts.map(function (p, j) {
        return (j ? 'L' : 'M') + x(p.seq).toFixed(1) + ' ' + y(p.elo).toFixed(1);
      }).join(' ');
      var color = CHART_COLORS[idx % CHART_COLORS.length];
      svg.push('<path d="' + d + '" fill="none" stroke="' + color + '" stroke-width="2" stroke-linejoin="round"/>');
      var tail = pts[pts.length - 1];
      svg.push('<circle cx="' + x(tail.seq).toFixed(1) + '" cy="' + y(tail.elo).toFixed(1) +
               '" r="3" fill="' + color + '"><title>' + esc(m.name) + ': ' + tail.elo + '</title></circle>');
    });

    svg.push('</svg>');
    document.getElementById('bm-chart').innerHTML = svg.join('');

    document.getElementById('bm-legend').innerHTML = top.map(function (m, idx) {
      return '<li><span class="bm-dot" style="background:' + CHART_COLORS[idx % CHART_COLORS.length] + '"></span>' +
             esc(m.name) + ' <b>' + m.elo + '</b></li>';
    }).join('');
  }

  function renderFeed(data, models) {
    var byId = {};
    models.forEach(function (m) { byId[m.id] = m; });
    // Свежие прогоны: последние записи истории, новые — первыми.
    var recent = data.elo_history.slice().sort(function (a, b) { return b.seq - a.seq; }).slice(0, FEED_LIMIT);

    document.getElementById('bm-feed').innerHTML = recent.map(function (r) {
      var a = byId[r.model_a_id], b = byId[r.model_b_id];
      var nameA = a ? a.name : r.model_a_id;
      var nameB = b ? b.name : r.model_b_id;
      var winA = r.winner === 'a', winB = r.winner === 'b', draw = r.winner === 'draw';
      function side(name, win, delta) {
        var cls = 'bm-side' + (draw ? ' is-draw' : (win ? ' is-win' : ''));
        var sign = delta > 0 ? '+' : '';
        var dcls = draw ? '' : (delta > 0 ? 'pos' : (delta < 0 ? 'neg' : ''));
        return '<span class="' + cls + '">' + esc(name) +
               (draw ? '' : '<span class="bm-delta ' + dcls + '">' + sign + delta + '</span>') + '</span>';
      }
      return '<li>' +
        '<div class="bm-meta"><span>' + fmtDate(r.date) + '</span>' +
        '<span class="bm-chip">' + esc(r.matchup) + '</span>' +
        '<span>' + (draw ? 'ничья' : 'победа') + '</span></div>' +
        '<div class="bm-match">' +
        side(nameA, winA, r.elo_a.delta) +
        '<span class="bm-vs">против</span>' +
        side(nameB, winB, r.elo_b.delta) +
        '</div></li>';
    }).join('');
  }

  function renderSummary(data) {
    var summary = data.matchups_summary || {};
    var cards = Object.keys(SUMMARY_LABELS).filter(function (key) {
      return Object.prototype.hasOwnProperty.call(summary, key);
    }).map(function (key) {
      return '<div><dt>' + esc(SUMMARY_LABELS[key]) + '</dt><dd>' + summary[key] + '</dd></div>';
    });
    cards.push('<div><dt>Обновлено</dt><dd>' + fmtDate(data.updated) + '</dd></div>');
    document.getElementById('bm-summary').innerHTML = cards.join('');
  }

  function fail(message) {
    var loading = document.getElementById('bm-loading');
    if (loading) loading.hidden = true;
    var box = document.getElementById('bm-error');
    box.textContent = message;
    box.hidden = false;
  }

  fetch('index.json')
    .then(function (res) {
      if (!res.ok) throw new Error('HTTP ' + res.status);
      return res.json();
    })
    .then(function (data) {
      if (!data || !data.models || !data.elo_history) throw new Error('неожиданная структура index.json');
      document.getElementById('bm-loading').hidden = true;
      renderStats(data);
      var models = renderTable(data);
      renderChart(data, models);
      renderFeed(data, models);
      renderSummary(data);
    })
    .catch(function (err) {
      fail('Не удалось загрузить index.json: ' + err.message);
    });
})();
