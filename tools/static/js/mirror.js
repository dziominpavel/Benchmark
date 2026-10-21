/* mirror.js — клиентский слой статического слепка консоли Benchmark.
 *
 * Подключается в shell.html только в режиме «только просмотр»: у слепка
 * нет сервера, поэтому фильтры «Показывать», чипы «Агент»/«Компания»,
 * режим «Подсвечивать», счётчики, порядок чипов, листание «Истории» и
 * распределение Elo на «Аналитике» воспроизводит этот скрипт.
 *
 * Данные — из островов JSON (mirror-models / mirror-stats-data), строки
 * архива — из тегов template (mirror-archived-rows / mirror-table-wrap);
 * и то и другое кладёт в страницы tools/export_web.py. Состояние фильтров
 * отражается в адресе через replaceState — ссылкой внутри слепка можно
 * поделиться; адреса разделов и очереди остаются обычными файлами.
 */

(function () {
  "use strict";

  const HISTORY_PAGE_SIZE = 20;
  const DEFAULT_ELO = 1200;

  /* ── Реестр моделей и утилиты ───────────────────────────────────── */

  function readIsland(id) {
    const node = document.getElementById(id);
    if (!node) return null;
    try {
      return JSON.parse(node.textContent);
    } catch (err) {
      return null;
    }
  }

  const MODELS = readIsland("mirror-models") || readIsland("mirror-stats-data") || {};
  const MODEL_IDS = Object.keys(MODELS);

  function modelName(mid) {
    const info = MODELS[mid];
    return info && info.n ? info.n : mid;
  }

  function modelCaption(mid) {
    const info = MODELS[mid];
    return info && info.c ? info.c : "";
  }

  function modelGames(mid) {
    const info = MODELS[mid];
    return info && typeof info.g === "number" ? info.g : 0;
  }

  function modelElo(mid) {
    const info = MODELS[mid];
    return info && typeof info.e === "number" ? info.e : DEFAULT_ELO;
  }

  function isArchived(mid) {
    return Boolean(MODELS[mid]) && MODELS[mid].s === "archived";
  }

  // Статусный критерий «Показывать» — как в консоли.
  function statusMatches(mode, mid) {
    if (mode === "all") return true;
    if (mode === "active") return !isArchived(mid);
    return isArchived(mid);
  }

  // Полный ранг реестра: сортировка консоли (-elo, id).
  const ALL_RANKS = (() => {
    const ids = MODEL_IDS.slice().sort(
      (a, b) => modelElo(b) - modelElo(a) || (a < b ? -1 : a > b ? 1 : 0)
    );
    const ranks = new Map();
    ids.forEach((mid, index) => ranks.set(mid, index + 1));
    return ranks;
  })();

  function knownTagValues(key) {
    const values = new Set();
    for (const mid of MODEL_IDS) values.add(MODELS[mid][key] || "");
    return values;
  }

  const AGENT_VALUES = knownTagValues("a");
  const PROVIDER_VALUES = knownTagValues("p");

  function passesTags(mid, agentSel, providerSel) {
    const info = MODELS[mid] || {};
    if (agentSel.size && !agentSel.has(info.a || "")) return false;
    if (providerSel.size && !providerSel.has(info.p || "")) return false;
    return true;
  }

  function splitCsv(raw) {
    return raw ? raw.split(",").map((s) => s.trim()).filter(Boolean) : [];
  }

  function tagsCsv(sel) {
    const items = [];
    for (const value of sel) items.push(value === "" ? "none" : value);
    items.sort((a, b) => {
      const la = a.toLowerCase();
      const lb = b.toLowerCase();
      return la < lb ? -1 : la > lb ? 1 : 0;
    });
    return items.join(",");
  }

  function esc(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#x27;");
  }

  function writeUrl(pairs) {
    const params = new URLSearchParams();
    for (const [name, value] of pairs) {
      if (value) params.set(name, value);
    }
    const query = params.toString();
    window.history.replaceState(
      null,
      "",
      location.pathname + (query ? "?" + query : "") + location.hash
    );
  }

  function setShown(el, shown) {
    if (el) el.style.display = shown ? "" : "none";
  }

  function htmlToNode(html) {
    const template = document.createElement("template");
    template.innerHTML = html;
    return template.content.firstElementChild;
  }

  function templateRows(id) {
    const node = document.getElementById(id);
    if (!node) return [];
    const table = node.content.querySelector("table");
    return table ? [...table.rows] : [];
  }

  function modelIdFromLink(node) {
    const link = node.querySelector ? node.querySelector('a.edit-link[href*="model/"]') : null;
    if (!link) return "";
    let href = link.getAttribute("href") || "";
    href = href.split("#")[0].split("?")[0];
    const match = href.match(/model\/([^/]+)\/?$/);
    if (!match) return "";
    try {
      return decodeURIComponent(match[1]);
    } catch (err) {
      return match[1];
    }
  }

  function modelIdFromFlags(row) {
    const box = row.querySelector('input[name="flag"]');
    if (!box) return "";
    return (box.value || "").split("||")[0];
  }

  function ensureTableWrap(card, templateId) {
    if (card.querySelector(".table-wrap")) return;
    const node = document.getElementById(templateId);
    if (!node) return;
    const wrap = node.content.firstElementChild;
    if (!wrap) return;
    const heading = card.querySelector("h2");
    if (heading) heading.after(wrap);
    else card.prepend(wrap);
  }

  function emptyBox(card) {
    let el = card.querySelector(".empty-state");
    if (!el) {
      el = document.createElement("div");
      el.className = "empty-state";
      const wrap = card.querySelector(".table-wrap");
      if (wrap) wrap.after(el);
      else card.appendChild(el);
    }
    return el;
  }

  function hintBox(card) {
    let el = card.querySelector('.hint[data-mirror="hint"]');
    if (!el) {
      el = document.createElement("div");
      el.className = "hint";
      el.dataset.mirror = "hint";
      const wrap = card.querySelector(".table-wrap");
      if (wrap) wrap.after(el);
      else card.appendChild(el);
    }
    return el;
  }

  /* ── Общий блок «Фильтр» страниц ────────────────────────────────── */

  function panelForm() {
    return document.querySelector("form.filter-card");
  }

  function checkedValue(form, name, fallback) {
    const el = form.querySelector('input[name="' + name + '"]:checked');
    return el ? el.value : fallback;
  }

  function isChecked(form, name) {
    const box = form.querySelector('input[name="' + name + '"]');
    return Boolean(box && box.checked);
  }

  function formTags(form, name) {
    const sel = new Set();
    form.querySelectorAll('input[name="' + name + '"]:checked').forEach((el) => {
      sel.add(el.value === "none" ? "" : el.value);
    });
    return sel;
  }

  // Переносит фильтры из адреса в контролы формы (до первого рендера).
  function syncFromUrl(form, tagNames, selectNames = []) {
    const params = new URLSearchParams(location.search);
    for (const name of ["filter", "answer_filter", "view", "chips"]) {
      const inputs = [...form.querySelectorAll('input[name="' + name + '"]')];
      if (!inputs.length) continue;
      const wanted = (params.get(name) || "").toLowerCase();
      if (inputs.some((el) => el.value === wanted)) {
        inputs.forEach((el) => {
          el.checked = el.value === wanted;
        });
      }
    }
    for (const name of ["only_debts", "include_inactive", "include_voided"]) {
      const inputs = [...form.querySelectorAll('input[name="' + name + '"]')];
      if (!inputs.length || params.get(name) === null) continue;
      inputs.forEach((el) => {
        el.checked = params.get(name) === "1";
      });
    }
    // Подписи: флажок «Отражать агент-компанию» — параметр `captions`
    // (дефолт «скрыты», значит показ = `captions=show`).
    const captionBox = form.querySelector('input[name="captions"]');
    if (captionBox) {
      captionBox.checked = (params.get("captions") || "").toLowerCase() === "show";
    }
    for (const name of tagNames) {
      const tokens = new Set(splitCsv(params.getAll(name).join(",")));
      form.querySelectorAll('input[name="' + name + '"]').forEach((el) => {
        el.checked = tokens.has(el.value);
      });
    }
    for (const name of selectNames) {
      const select = form.querySelector('select[name="' + name + '"]');
      if (select && params.get(name)) select.value = params.get(name);
    }
    return params;
  }

  // Порядок чипов: «по алфавиту» консоли или «по ELO» (макс. Elo значения,
  // ничьи — по алфавиту); чип «без …» всегда последний.
  function chipsOrder(form, order) {
    for (const name of ["agents", "providers"]) {
      const first = form.querySelector('input[name="' + name + '"]');
      if (!first) continue;
      const box = first.closest(".filter-chips");
      if (!box) continue;
      const key = name === "agents" ? "a" : "p";
      const maxElo = new Map();
      for (const mid of MODEL_IDS) {
        const value = MODELS[mid][key] || "";
        const elo = modelElo(mid);
        if (!maxElo.has(value) || elo > maxElo.get(value)) maxElo.set(value, elo);
      }
      const labels = [...box.querySelectorAll("label.chip")];
      const valueOf = (label) => {
        const input = label.querySelector("input");
        if (!input) return "";
        return input.value === "none" ? "" : input.value;
      };
      labels.sort((a, b) => {
        const va = valueOf(a);
        const vb = valueOf(b);
        if (va === "" || vb === "") {
          return va === vb ? 0 : va === "" ? 1 : -1;
        }
        if (order === "elo") {
          const ea = maxElo.has(va) ? maxElo.get(va) : DEFAULT_ELO;
          const eb = maxElo.has(vb) ? maxElo.get(vb) : DEFAULT_ELO;
          if (ea !== eb) return eb - ea;
        }
        const la = va.toLowerCase();
        const lb = vb.toLowerCase();
        return la < lb ? -1 : la > lb ? 1 : 0;
      });
      for (const label of labels) box.appendChild(label);
    }
  }

  function updateBadge(form, view, chips, captions) {
    const summary = form.querySelector("details.filter-settings > summary");
    if (!summary) return;
    const parts = [];
    if (view === "highlight") parts.push("подсветка");
    if (chips === "elo") parts.push("чипы по ELO");
    if (captions) parts.push("подписи видны");
    summary.textContent = parts.length
      ? "Настройки фильтра — " + parts.join(" · ")
      : "Настройки фильтра";
  }

  function paginationItems(page, pages) {
    if (pages <= 10) {
      const all = [];
      for (let p = 1; p <= pages; p += 1) all.push(p);
      return all;
    }
    const visible = new Set([1, pages]);
    for (let p = page - 2; p <= page + 2; p += 1) {
      if (p >= 1 && p <= pages) visible.add(p);
    }
    const ordered = [...visible].sort((a, b) => a - b);
    const items = [];
    ordered.forEach((p, index) => {
      if (index) {
        const gap = p - ordered[index - 1];
        if (gap === 2) items.push(p - 1);
        else if (gap > 2) items.push(null);
      }
      items.push(p);
    });
    return items;
  }

  /* ── Страница «Рейтинг» ─────────────────────────────────────────── */

  function initRating() {
    const card = document.querySelector(".rating-card");
    const form = panelForm();
    if (!card || !form) return;

    ensureTableWrap(card, "mirror-table-wrap");
    const body = card.querySelector("table tbody");
    if (!body) return;

    // Кандидаты строк: базовый пул страницы и архив из шаблона.
    const actives = new Map();
    const archived = new Map();
    const addRow = (row) => {
      const mid = modelIdFromLink(row);
      if (!mid) return;
      const store = isArchived(mid) ? archived : actives;
      if (!store.has(mid)) store.set(mid, row.outerHTML);
    };
    [...body.rows].forEach(addRow);
    templateRows("mirror-archived-rows").forEach(addRow);

    const statsEl = document.querySelector(".controls .stats");
    let statsTail = "";
    if (statsEl) {
      const text = (statsEl.textContent || "").replace(/\s+/g, " ").trim();
      const match = text.match(/Вердиктов:.*$/);
      statsTail = match ? match[0].trim() : "";
    }

    const state = () => ({
      mode: checkedValue(form, "filter", "active"),
      view: checkedValue(form, "view", "hide") === "highlight" ? "highlight" : "hide",
      chips: checkedValue(form, "chips", "alpha") === "elo" ? "elo" : "alpha",
      agentSel: formTags(form, "agents"),
      providerSel: formTags(form, "providers"),
      captions: isChecked(form, "captions"),
    });

    const byRank = (a, b) => ALL_RANKS.get(a) - ALL_RANKS.get(b);

    function emptyMessage(mode) {
      if (mode === "inactive") return "Нет неактивных (архивных) моделей.";
      if (mode === "all") return "Нет моделей. Добавьте модель через «Настройки», чтобы начать.";
      return "Нет активных моделей. Переключите фильтр или добавьте новую модель.";
    }

    function updateArchivedSection(st) {
      const section = card.querySelector(".archived-section");
      if (!section) return;
      let shown = 0;
      section.querySelectorAll("li").forEach((li) => {
        const mid = modelIdFromLink(li);
        const ok = !mid || passesTags(mid, st.agentSel, st.providerSel);
        setShown(li, ok);
        if (ok) shown += 1;
      });
      setShown(section, st.mode === "active" && st.view === "hide" && shown > 0);
      const summary = section.querySelector("summary");
      if (summary) summary.textContent = "Архивные модели (" + shown + ")";
    }

    function render(st) {
      // Пул: активные — в порядке консоли, архивные — по полному рангу.
      let ids;
      if (st.mode === "active") ids = [...actives.keys()];
      else if (st.mode === "inactive") ids = [...archived.keys()].sort(byRank);
      else ids = [...actives.keys(), ...archived.keys()].sort(byRank);
      body.innerHTML = ids
        .map((mid) => actives.get(mid) || archived.get(mid))
        .join("\n");
      [...body.rows].forEach((row, index) => {
        const num = row.querySelector(".rank-num");
        if (num) num.textContent = String(index + 1);
      });

      const highlight = st.view === "highlight";
      const all = [...body.rows];
      let visible = 0;
      let hits = 0;
      const marks = all.map((row) => {
        const mid = modelIdFromLink(row);
        const tags = passesTags(mid, st.agentSel, st.providerSel);
        if (tags) visible += 1;
        if (tags && statusMatches(st.mode, mid)) {
          if (highlight) hits += 1;
          return { row, tags, hit: true };
        }
        return { row, tags, hit: false };
      });
      const anyHits = highlight && hits > 0;
      for (const mark of marks) {
        if (highlight) {
          setShown(mark.row, true);
          mark.row.classList.toggle("filter-hit", anyHits && mark.hit);
          mark.row.classList.toggle("filter-miss", anyHits && !mark.hit);
        } else {
          setShown(mark.row, mark.tags);
          mark.row.classList.remove("filter-hit", "filter-miss");
        }
      }

      if (statsEl) {
        const total = MODEL_IDS.length;
        const left = highlight
          ? total + " · подсвечено " + hits
          : visible + " из " + total;
        statsEl.textContent =
          "Моделей: " + left + (statsTail ? " · " + statsTail : "");
      }

      const empty = emptyBox(card);
      let message = "";
      if (!highlight) {
        if (!all.length) message = emptyMessage(st.mode);
        else if (!visible) {
          message =
            "Под выбранный фильтр не попала ни одна модель. Сбросьте фильтр, чтобы увидеть список.";
        }
      }
      setShown(card.querySelector(".table-wrap"), !message);
      setShown(empty, Boolean(message));
      if (message) empty.textContent = message;

      const hint = hintBox(card);
      const showHint = highlight && all.length > 0 && hits === 0;
      setShown(hint, showHint);
      if (showHint) {
        hint.textContent =
          "Ничего не подсвечено — ни одна модель не проходит выбранные условия.";
      }

      updateArchivedSection(st);
    }

    const apply = () => {
      const st = state();
      chipsOrder(form, st.chips);
      updateBadge(form, st.view, st.chips, st.captions);
      applyCaptions(st.captions);
      render(st);
      writeUrl([
        ["filter", st.mode !== "active" ? st.mode : ""],
        ["agents", st.agentSel.size ? tagsCsv(st.agentSel) : ""],
        ["providers", st.providerSel.size ? tagsCsv(st.providerSel) : ""],
        ["view", st.view === "highlight" ? "highlight" : ""],
        ["chips", st.chips === "elo" ? "elo" : ""],
        ["captions", st.captions ? "show" : ""],
      ]);
    };

    syncFromUrl(form, ["agents", "providers"]);
    form.addEventListener("change", apply);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      apply();
    });
    apply();
  }

  /* ── Страница «История» ─────────────────────────────────────────── */

  function initHistory() {
    const card = document.getElementById("history-list");
    const form = panelForm();
    if (!card || !form) return;
    const rows = [...card.querySelectorAll(".history-item")];
    const select = form.querySelector('select[name="model"]');
    const statsEl = document.querySelector(".controls .stats");

    const params = syncFromUrl(form, ["agents", "providers"], ["model"]);
    // Выбранная из адреса модель могла не попасть в опции (архивная или под
    // чипом): консоль сохраняет её в выпадайке — повторяем.
    const urlModel = (params.get("model") || "").trim();
    if (select && urlModel && select.value !== urlModel && MODELS[urlModel]) {
      const option = document.createElement("option");
      option.value = urlModel;
      option.textContent =
        modelName(urlModel) + (isArchived(urlModel) ? " (неактивна)" : "");
      option.selected = true;
      select.appendChild(option);
    }

    let currentPage = 1;
    {
      const raw = parseInt((params.get("page") || "1").trim(), 10);
      if (!Number.isNaN(raw)) currentPage = Math.max(1, raw);
    }

    const state = () => ({
      model: select ? select.value : "",
      includeInactive: isChecked(form, "include_inactive"),
      includeVoided: isChecked(form, "include_voided"),
      view: checkedValue(form, "view", "hide") === "highlight" ? "highlight" : "hide",
      chips: checkedValue(form, "chips", "alpha") === "elo" ? "elo" : "alpha",
      agentSel: formTags(form, "agents"),
      providerSel: formTags(form, "providers"),
      captions: isChecked(form, "captions"),
    });

    function rebuildDropdown(st) {
      if (!select) return;
      const sorted = MODEL_IDS.slice().sort((a, b) => {
        const na = modelName(a).toLowerCase();
        const nb = modelName(b).toLowerCase();
        return na < nb ? -1 : na > nb ? 1 : 0;
      });
      const parts = [
        '<option value=""' + (st.model ? "" : " selected") + ">Все</option>",
      ];
      for (const mid of sorted) {
        if (isArchived(mid) && !st.includeInactive && mid !== st.model) continue;
        if (mid !== st.model && !passesTags(mid, st.agentSel, st.providerSel)) continue;
        parts.push(
          '<option value="' + esc(mid) + '"' + (mid === st.model ? " selected" : "") + ">" +
            esc(modelName(mid)) + (isArchived(mid) ? " (неактивна)" : "") +
            "</option>"
        );
      }
      select.innerHTML = parts.join("");
    }

    function navigation(pages) {
      let nav = card.querySelector("nav.pagination");
      if (pages <= 1) {
        if (nav) setShown(nav, false);
        return;
      }
      const parts = [
        currentPage > 1
          ? '<a class="page-arrow" href="?page=' + (currentPage - 1) +
            '" rel="prev" aria-label="Назад">←</a>'
          : '<span class="page-arrow disabled" aria-disabled="true">←</span>',
      ];
      for (const item of paginationItems(currentPage, pages)) {
        if (item === null) parts.push('<span class="ellipsis" aria-hidden="true">...</span>');
        else if (item === currentPage) {
          parts.push('<span class="current" aria-current="page">' + item + "</span>");
        } else {
          parts.push('<a href="?page=' + item + '">' + item + "</a>");
        }
      }
      parts.push(
        currentPage < pages
          ? '<a class="page-arrow" href="?page=' + (currentPage + 1) +
            '" rel="next" aria-label="Вперёд">→</a>'
          : '<span class="page-arrow disabled" aria-disabled="true">→</span>'
      );
      if (!nav) {
        nav = document.createElement("nav");
        nav.className = "pagination";
        nav.setAttribute("aria-label", "Пагинация");
        card.appendChild(nav);
      }
      setShown(nav, true);
      nav.innerHTML = parts.join("\n");
      nav.querySelectorAll("a").forEach((link) => {
        link.addEventListener("click", (event) => {
          event.preventDefault();
          const match = (link.getAttribute("href") || "").match(/page=(\d+)/);
          if (!match) return;
          currentPage = Number(match[1]);
          apply(false); // рендер + адрес с номером страницы
          card.scrollIntoView({ block: "start" });
        });
      });
    }

    function render(st) {
      rebuildDropdown(st);
      const keepAll = st.view === "highlight";
      const states = rows.map((row) => {
        const a = row.dataset.a || "";
        const b = row.dataset.b || "";
        const voided = row.classList.contains("history-item-voided");
        const modelMatch = Boolean(st.model) && (a === st.model || b === st.model);
        const tagMatch =
          passesTags(a, st.agentSel, st.providerSel) ||
          passesTags(b, st.agentSel, st.providerSel);
        const matches = keepAll || (st.model ? modelMatch : tagMatch);
        const shown = matches && (!voided || st.includeVoided);
        return { row, shown, hit: keepAll && (st.model ? modelMatch : tagMatch), voided };
      });
      const visible = states.filter((s) => s.shown).length;
      const voidedVisible = states.filter((s) => s.shown && s.voided).length;
      const hits = keepAll ? states.filter((s) => s.hit).length : 0;
      const pages = Math.max(1, Math.ceil(visible / HISTORY_PAGE_SIZE));
      currentPage = Math.max(1, Math.min(currentPage, pages));

      const anyHits = keepAll && hits > 0;
      let index = 0;
      for (const s of states) {
        let onPage = false;
        if (s.shown) {
          const pos = index;
          index += 1;
          onPage =
            pos >= (currentPage - 1) * HISTORY_PAGE_SIZE &&
            pos < currentPage * HISTORY_PAGE_SIZE;
        }
        setShown(s.row, s.shown && onPage);
        s.row.classList.toggle("filter-hit", anyHits && s.hit);
        s.row.classList.toggle("filter-miss", anyHits && !s.hit);
      }

      if (statsEl) {
        let text = "Всего записей: " + visible;
        if (st.includeVoided) text += " · аннулированных: " + voidedVisible;
        if (keepAll) text += " · подсвечено: " + hits;
        else if (st.model) text += " · Фильтр: " + modelName(st.model);
        statsEl.textContent = text;
      }

      const empty = emptyBox(card);
      const message = visible ? "" : "Нет истории";
      setShown(empty, Boolean(message));
      if (message) empty.textContent = message;

      const hint = hintBox(card);
      const showHint = keepAll && visible > 0 && hits === 0;
      setShown(hint, showHint);
      if (showHint) {
        hint.textContent =
          "Ничего не подсвечено — ни одна запись не проходит выбранные условия.";
      }

      navigation(pages);
    }

    const apply = (resetPage) => {
      if (resetPage) currentPage = 1;
      const st = state();
      chipsOrder(form, st.chips);
      updateBadge(form, st.view, st.chips, st.captions);
      applyCaptions(st.captions);
      render(st);
      writeUrl([
        ["model", st.model],
        ["include_inactive", st.includeInactive ? "1" : ""],
        ["include_voided", st.includeVoided ? "1" : ""],
        ["agents", st.agentSel.size ? tagsCsv(st.agentSel) : ""],
        ["providers", st.providerSel.size ? tagsCsv(st.providerSel) : ""],
        ["view", st.view === "highlight" ? "highlight" : ""],
        ["chips", st.chips === "elo" ? "elo" : ""],
        ["captions", st.captions ? "show" : ""],
        ["page", currentPage > 1 ? String(currentPage) : ""],
      ]);
    };

    form.addEventListener("change", () => apply(true));
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      apply(true);
    });
    apply(false);
  }

  /* ── Страница «Аналитика» ───────────────────────────────────────── */

  const RATING_PAGE_SIZE = 50;
  const MIDDOT = "·";

  function buildScale(elos) {
    let lo = Math.min(...elos);
    let hi = Math.max(...elos);
    if (lo === hi) {
      lo -= 10;
      hi += 10;
    }
    const anchors = [];
    if (lo < DEFAULT_ELO) anchors.push([lo, 0], [(lo + DEFAULT_ELO) / 2, 1]);
    anchors.push([DEFAULT_ELO, 2]);
    if (hi > DEFAULT_ELO) anchors.push([(DEFAULT_ELO + hi) / 2, 3], [hi, 4]);
    return anchors;
  }

  function scaleSegment(elo, anchors) {
    if (elo <= anchors[0][0]) return [0, 0];
    for (let i = 0; i < anchors.length - 1; i += 1) {
      const segLo = anchors[i][0];
      const segHi = anchors[i + 1][0];
      if (elo < segHi) return [i, (elo - segLo) / (segHi - segLo)];
    }
    return [anchors.length - 2, 1];
  }

  // Порт confidence_half_width (render_helpers.py): половина интервала
  // рейтинга — round(400 / √игр); без игр интервала нет.
  function confidenceHalf(games) {
    const n = Number(games) || 0;
    if (n <= 0) return null;
    return Math.round(400 / Math.sqrt(n));
  }

  // Порт plural_ru (render_helpers.py): русская форма слова по числу.
  function pluralRu(n, one, few, many) {
    const abs = Math.abs(Number(n) || 0);
    const mod100 = abs % 100;
    if (mod100 >= 11 && mod100 <= 14) return many;
    const last = abs % 10;
    if (last === 1) return one;
    if (last >= 2 && last <= 4) return few;
    return many;
  }

  // Порт interval_groups (render_helpers.py): группы неразличимых мест —
  // цепочки перекрывающихся интервалов соседей (транзитивно).
  function intervalGroups(rows) {
    const ordered = [...rows].sort((a, b) => {
      const diff = modelElo(b.mid) - modelElo(a.mid);
      if (diff) return diff;
      return a.mid < b.mid ? -1 : a.mid > b.mid ? 1 : 0;
    });
    ordered.forEach((row) => {
      const elo = modelElo(row.mid);
      row.half = confidenceHalf(modelGames(row.mid));
      row.hasInterval = row.half !== null;
      row.lo = row.hasInterval ? elo - row.half : elo;
      row.hi = row.hasInterval ? elo + row.half : elo;
      row.group = 0;
    });
    const groups = [];
    let i = 0;
    while (i < ordered.length) {
      let j = i;
      while (
        j + 1 < ordered.length &&
        ordered[j].hasInterval &&
        ordered[j + 1].hasInterval &&
        ordered[j].lo <= ordered[j + 1].hi
      ) {
        j += 1;
      }
      if (j > i) {
        const number = groups.length + 1;
        groups.push({ number, start: i, end: j });
        for (let k = i; k <= j; k += 1) ordered[k].group = number;
      }
      i = j + 1;
    }
    return { rows: ordered, groups };
  }

  // Порт rating_page (render_helpers.py): страница строк карточки «Рейтинг»
  // и её фрагменты групп; место строки — место во всём пуле.
  function ratingPage(rows, groups, page) {
    const total = rows.length;
    const pages = Math.max(1, Math.ceil(total / RATING_PAGE_SIZE));
    const current = Math.max(1, Math.min(page || 1, pages));
    const start = (current - 1) * RATING_PAGE_SIZE;
    const stop = Math.min(start + RATING_PAGE_SIZE, total);
    const bounds = new Map();
    groups.forEach((group) => bounds.set(group.number, group));
    const pageRows = [];
    for (let index = start; index < stop; index += 1) {
      const row = Object.assign({}, rows[index]);
      const group = bounds.get(row.group);
      row.rank = index + 1;
      row.groupFull = Boolean(
        row.group && group && group.start >= start && group.end < stop
      );
      row.groupSize = row.group && group ? group.end - group.start + 1 : 0;
      pageRows.push(row);
    }
    return { rows: pageRows, page: current, pages, total };
  }

  // Порт build_rating_svg (render_helpers.py): строка карточки «Рейтинг» —
  // место, имя, ELO, интервал ±400/√игр и градиентный бар. Шкала и ширина
  // колонки имён считаются по всему пулу, а не по странице.
  function buildRating(pageRows, pool, highlight) {
    const width = 860;
    const elos = pool.map((row) => modelElo(row.mid));
    let lo = Math.min(...elos);
    let hi = Math.max(...elos);
    if (lo === hi) {
      lo -= 10;
      hi += 10;
    }
    const pad = Math.max(15.0, (hi - lo) * 0.08);
    lo -= pad;
    hi += pad;
    const scale = buildScale(elos);
    const mean = elos.reduce((sum, v) => sum + v, 0) / elos.length;

    const rowH = 30;
    const barH = 18;
    const top = 44;
    const bottom = 30;
    const rankX = 8;
    const nameX = 52;
    let maxName = 0;
    pool.forEach((row) => {
      maxName = Math.max(
        maxName,
        String(modelName(row.mid)).length,
        String(modelCaption(row.mid)).length
      );
    });
    const nameW = Math.max(150, Math.min(360, Math.trunc(maxName * 7.0)));
    const eloX = nameX + nameW + 14;
    const halfX = eloX + 54;
    const plotX0 = halfX + 16;
    const plotX1 = width - 16;
    const height = top + rowH * pageRows.length + bottom;
    const rowsBottom = top + rowH * pageRows.length;
    const x = (v) => plotX0 + (plotX1 - plotX0) * ((v - lo) / (hi - lo));
    const clampX = (v) => Math.max(plotX0, Math.min(plotX1, x(v)));

    const parts = [];

    // Группы неразличимых мест — полосой по видимому фрагменту. Надписи над
    // строками нет: смысл признака объясняет легенда карточки, детали — тултип.
    const groups = [];
    pageRows.forEach((row, i) => {
      if (!row.group) return;
      const last = groups[groups.length - 1];
      if (last && last[0] === row.group) last[2] = i;
      else groups.push([row.group, i, i]);
    });
    groups.forEach(([, start, end]) => {
      const bandY = top + start * rowH + 2;
      const bandH = rowH * (end - start + 1) - 4;
      const full = pageRows[start].groupFull !== false;
      const size = pageRows[start].groupSize || end - start + 1;
      const visible = end - start + 1;
      let tip =
        "Группа неразличимых мест: " + size + " " +
        pluralRu(size, "модель", "модели", "моделей") +
        " — интервалы соседей перекрываются, точный порядок статистически не различим";
      if (!full) {
        tip +=
          "; на этой странице видно " + visible +
          ", продолжение — на соседней странице";
      }
      parts.push(
        '<rect x="4" y="' + bandY.toFixed(1) + '" width="' + (width - 8) +
          '" height="' + bandH.toFixed(1) + '" rx="6" class="interval-group-band">' +
          "<title>" + esc(tip) + "</title></rect>"
      );
    });

    const step = hi - lo <= 400 ? 50 : 100;
    let tick = Math.ceil(lo / step) * step;
    while (tick <= hi) {
      const gx = x(tick);
      parts.push(
        '<line x1="' + gx.toFixed(1) + '" y1="' + (top - 14) + '" x2="' +
          gx.toFixed(1) + '" y2="' + rowsBottom + '" class="chart-grid"/>' +
          '<text x="' + gx.toFixed(1) + '" y="20" text-anchor="middle" ' +
          'class="chart-tick">' + tick + "</text>"
      );
      tick += step;
    }

    [
      [DEFAULT_ELO, "dist-line-start", "старт: 1200"],
      [mean, "dist-line-mean", "среднее: " + mean.toFixed(1)],
    ].forEach(([value, cls, tip]) => {
      const gx = x(value);
      parts.push(
        '<line x1="' + gx.toFixed(1) + '" y1="' + top + '" x2="' + gx.toFixed(1) +
          '" y2="' + rowsBottom + '" class="' + cls + '"><title>' + esc(tip) +
          "</title></line>"
      );
    });

    pageRows.forEach((row, i) => {
      const elo = modelElo(row.mid);
      const mid = row.mid;
      const rawName = modelName(mid);
      const caption = modelCaption(mid);
      const grouped = Boolean(row.group);
      const [seg, frac] = scaleSegment(elo, scale);
      const style =
        "--a:var(--dist-s" + scale[seg][1] + ");" +
        "--b:var(--dist-s" + scale[seg + 1][1] + ");" +
        "--p:" + (frac * 100).toFixed(1) + "%";
      let cls = "dist-pt";
      if (highlight) cls += row.hit ? " filter-hit" : " filter-miss";
      const tipName = caption ? rawName + " (" + caption + ")" : rawName;
      let tip = tipName + " · " + elo + " · игр: " + modelGames(mid);
      if (row.hasInterval) {
        tip += " · интервал " + row.lo + "–" + row.hi;
      } else {
        tip += " · игр нет, интервал не определён";
      }
      tip = esc(tip);
      const cy = top + i * rowH + rowH / 2;

      let bar =
        '<rect x="' + x(lo).toFixed(1) + '" y="' + (cy - barH / 2).toFixed(1) +
        '" width="' + Math.max(1.0, x(elo) - x(lo)).toFixed(1) + '" height="' +
        barH + '" rx="4" class="' + cls + '" style="' + style + '">' +
        "<title>" + tip + "</title></rect>";
      if (mid) bar = '<a href="/model/' + esc(mid) + '" class="dist-link">' + bar + "</a>";
      parts.push(bar);

      if (row.hasInterval) {
        const bx1 = clampX(row.lo);
        const bx2 = clampX(row.hi);
        parts.push(
          '<line x1="' + bx1.toFixed(1) + '" y1="' + cy.toFixed(1) + '" x2="' +
            bx2.toFixed(1) + '" y2="' + cy.toFixed(1) + '" class="interval-bar' +
            (grouped ? " interval-bar-grouped" : "") + '"><title>' + esc(rawName) +
            ": интервал " + row.lo + "–" + row.hi + "</title></line>"
        );
      }

      // У места в группе — подсказка: почему оно помечено «≈».
      const rankTip = grouped
        ? "<title>место не определено: интервалы соседей перекрываются, " +
          "точный порядок статистически не различим</title>"
        : "";
      parts.push(
        '<text x="' + rankX + '" y="' + (cy + 4).toFixed(1) + '" class="interval-rank' +
          (grouped ? " interval-rank-grouped" : "") + '">' +
          (grouped ? "≈" : "") + row.rank + rankTip + "</text>"
      );
      parts.push(
        '<text x="' + nameX + '" y="' + (cy + 4).toFixed(1) + '">' +
          '<a href="/model/' + esc(mid) + '" class="dist-name">' + esc(rawName) +
          "<title>" + tip + "</title></a></text>"
      );
      if (caption) {
        parts.push(
          '<text x="' + nameX + '" y="' + (cy + 15).toFixed(1) +
            '" class="dist-caption">' + esc(caption) + "</text>"
        );
      }
      parts.push(
        '<text x="' + eloX + '" y="' + (cy + 4).toFixed(1) +
          '" text-anchor="end" class="interval-elo">' + elo + "</text>"
      );
      parts.push(
        '<text x="' + halfX + '" y="' + (cy + 4).toFixed(1) +
          '" text-anchor="end" class="interval-gap">' +
          (row.hasInterval ? "±" + row.half : "—") + "</text>"
      );
      parts.push(
        '<circle cx="' + x(elo).toFixed(1) + '" cy="' + cy.toFixed(1) +
          '" r="4" class="chart-dot' +
          (grouped ? " interval-dot-grouped" : "") +
          '"><title>' + tip + "</title></circle>"
      );
    });

    const visibleGroups = new Set(
      pageRows.map((row) => row.group).filter((group) => group)
    ).size;
    return (
      '<svg viewBox="0 0 ' + width + " " + height + '" class="chart chart-rating" ' +
      'role="img" aria-label="Рейтинг: ' + pageRows.length + " моделей, " +
      "групп неразличимых мест: " + visibleGroups + '">' +
      parts.join("") +
      "</svg>"
    );
  }

  function initStats() {
    const card = document.getElementById("rating");
    const form = panelForm();
    if (!card || !form) return;
    const statsEl = card.querySelector(".stats");
    let currentPage = 1;

    const state = () => ({
      mode: checkedValue(form, "filter", "active") === "all" ? "all" : "active",
      view: checkedValue(form, "view", "hide") === "highlight" ? "highlight" : "hide",
      chips: checkedValue(form, "chips", "alpha") === "elo" ? "elo" : "alpha",
      agentSel: formTags(form, "agents"),
      providerSel: formTags(form, "providers"),
      captions: isChecked(form, "captions"),
    });

    function poolRows(st) {
      const highlight = st.view === "highlight";
      const rows = [];
      for (const mid of MODEL_IDS) {
        const statusOk = st.mode === "all" || !isArchived(mid);
        const tagOk = passesTags(mid, st.agentSel, st.providerSel);
        if (highlight) rows.push({ mid, hit: statusOk && tagOk });
        else if (statusOk && tagOk) rows.push({ mid, hit: true });
      }
      return rows;
    }

    function navigation(pages) {
      let wrap = card.querySelector(".analytics-pagination");
      if (pages <= 1) {
        if (wrap) setShown(wrap, false);
        return;
      }
      if (!wrap) {
        wrap = document.createElement("div");
        wrap.className = "analytics-pagination";
        card.appendChild(wrap);
      }
      setShown(wrap, true);
      const parts = [
        currentPage > 1
          ? '<a class="page-arrow" href="?rank_page=' + (currentPage - 1) +
            '" rel="prev" aria-label="Назад">←</a>'
          : '<span class="page-arrow disabled" aria-disabled="true">←</span>',
      ];
      for (const item of paginationItems(currentPage, pages)) {
        if (item === null) parts.push('<span class="ellipsis" aria-hidden="true">...</span>');
        else if (item === currentPage) {
          parts.push('<span class="current" aria-current="page">' + item + "</span>");
        } else {
          parts.push('<a href="?rank_page=' + item + '">' + item + "</a>");
        }
      }
      parts.push(
        currentPage < pages
          ? '<a class="page-arrow" href="?rank_page=' + (currentPage + 1) +
            '" rel="next" aria-label="Вперёд">→</a>'
          : '<span class="page-arrow disabled" aria-disabled="true">→</span>'
      );
      let nav = wrap.querySelector("nav.pagination");
      if (!nav) {
        nav = document.createElement("nav");
        nav.className = "pagination";
        nav.setAttribute("aria-label", "Пагинация");
        wrap.appendChild(nav);
      }
      nav.innerHTML = parts.join("\n");
      nav.querySelectorAll("a").forEach((link) => {
        link.addEventListener("click", (event) => {
          event.preventDefault();
          const match = (link.getAttribute("href") || "").match(/rank_page=(\d+)/);
          if (!match) return;
          currentPage = Number(match[1]);
          render(state());
          card.scrollIntoView({ block: "start" });
        });
      });
    }

    function render(st) {
      const highlight = st.view === "highlight";
      const info = intervalGroups(poolRows(st));
      const all = info.rows;
      const determined = all.filter((row) => !row.group).length;

      let summary = "моделей: 0";
      if (all.length) {
        const elos = all.map((row) => modelElo(row.mid));
        const n = elos.length;
        const mean = elos.reduce((sum, v) => sum + v, 0) / n;
        const below = elos.filter((v) => v < DEFAULT_ELO).length;
        summary =
          "моделей: " + n + " " + MIDDOT + " ниже 1200: " + below +
          " " + MIDDOT + " выше/равно 1200: " + (n - below) +
          " " + MIDDOT + " среднее: " + Math.round(mean) +
          " " + MIDDOT + " мест определено: " + determined;
        if (highlight) {
          summary += " " + MIDDOT + " подсвечено: " +
            all.filter((row) => row.hit).length;
        }
      }
      if (statsEl) statsEl.textContent = summary;

      // Легенда объясняет пометку «≈» — показывается, только если в
      // отобранном составе есть группы неразличимых мест.
      const legend = card.querySelector("#rating-legend");
      if (legend) legend.hidden = info.groups.length === 0;

      const page = ratingPage(all, info.groups, currentPage);
      const old = card.querySelector("svg.chart, .empty-state");
      const node = all.length
        ? htmlToNode(buildRating(page.rows, all, highlight))
        : htmlToNode(
            '<div class="empty-state">Под выбранный фильтр не попала ни одна модель.</div>'
          );
      if (old) old.replaceWith(node);
      else card.appendChild(node);

      navigation(page.pages);
    }

    const apply = () => {
      const st = state();
      chipsOrder(form, st.chips);
      updateBadge(form, st.view, st.chips, st.captions);
      applyCaptions(st.captions);
      render(st);
      writeUrl([
        ["filter", st.mode === "all" ? "all" : ""],
        ["agents", st.agentSel.size ? tagsCsv(st.agentSel) : ""],
        ["providers", st.providerSel.size ? tagsCsv(st.providerSel) : ""],
        ["view", st.view === "highlight" ? "highlight" : ""],
        ["chips", st.chips === "elo" ? "elo" : ""],
        ["captions", st.captions ? "show" : ""],
        ["rank_page", currentPage > 1 ? String(currentPage) : ""],
      ]);
    };

    syncFromUrl(form, ["agents", "providers"]);
    form.addEventListener("change", () => {
      currentPage = 1;
      apply();
    });
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      currentPage = 1;
      apply();
    });
    apply();
  }

  /* ── Страница «Настройки» ───────────────────────────────────────── */

  function initSettings() {
    const card = document.getElementById("answer-coverage");
    const form = panelForm();
    if (!card || !form) return;
    ensureTableWrap(card, "mirror-table-wrap");
    const table = card.querySelector("table.flags-table");
    const body = table ? table.querySelector("tbody") : null;
    if (!body) return;

    const rowHtml = new Map();
    const addRow = (row) => {
      const mid = modelIdFromFlags(row);
      if (mid && !rowHtml.has(mid)) rowHtml.set(mid, row.outerHTML);
    };
    [...body.rows].forEach(addRow);
    templateRows("mirror-archived-rows").forEach(addRow);

    const idsSorted = [...rowHtml.keys()].sort((a, b) => {
      const na = modelName(a).toLowerCase();
      const nb = modelName(b).toLowerCase();
      return na < nb ? -1 : na > nb ? 1 : 0;
    });

    const state = () => ({
      mode: checkedValue(form, "answer_filter", "active"),
      view: checkedValue(form, "view", "hide") === "highlight" ? "highlight" : "hide",
      chips: checkedValue(form, "chips", "alpha") === "elo" ? "elo" : "alpha",
      onlyDebts: isChecked(form, "only_debts"),
      agentSel: formTags(form, "agents"),
      providerSel: formTags(form, "providers"),
      captions: isChecked(form, "captions"),
    });

    function debtOf(row) {
      const cells = row.querySelectorAll("td");
      if (cells.length < 2) return 0;
      const value = parseInt((cells[cells.length - 2].textContent || "0").trim(), 10);
      return Number.isNaN(value) ? 0 : value;
    }

    function updateModelLists(st) {
      document.querySelectorAll("#models details.model-row").forEach((details) => {
        const list = details.querySelector(".model-list");
        if (!list) return;
        const items = [...list.querySelectorAll("li")].filter(
          (li) => !li.classList.contains("model-empty")
        );
        // Подсветка списки не сужает (и счётчики показывает полные);
        // скрывающий режим сужает списки чипами, счётчик — по видимым.
        const highlight = st.view === "highlight";
        let shown = 0;
        for (const li of items) {
          const mid = modelIdFromLink(li);
          const ok =
            highlight || !mid || passesTags(mid, st.agentSel, st.providerSel);
          setShown(li, ok);
          if (ok) shown += 1;
        }
        const value = highlight ? items.length : shown;
        const count = details.querySelector("summary span:last-child");
        if (count) count.textContent = String(value);
        let empty = list.querySelector("li.model-empty");
        if (value === 0 && !empty) {
          empty = document.createElement("li");
          empty.className = "model-empty";
          list.appendChild(empty);
        }
        if (empty) {
          const labelEl = details.querySelector(".mg-label");
          const label = labelEl ? labelEl.textContent : "";
          empty.textContent =
            label.indexOf("Активных") !== -1
              ? "Нет активных моделей"
              : "Нет неактивных моделей";
          setShown(empty, value === 0);
        }
      });
    }

    function render(st) {
      const highlight = st.view === "highlight";
      const poolIds = highlight
        ? idsSorted.slice()
        : idsSorted.filter((mid) => statusMatches(st.mode, mid));
      body.innerHTML = poolIds.map((mid) => rowHtml.get(mid)).join("\n");

      let visible = 0;
      let hits = 0;
      const marks = [...body.rows].map((row) => {
        const mid = modelIdFromFlags(row);
        const tags = passesTags(mid, st.agentSel, st.providerSel);
        const debt = !st.onlyDebts || debtOf(row) > 0;
        const hit = tags && statusMatches(st.mode, mid) && debt;
        const shown = highlight || (tags && debt);
        if (shown) visible += 1;
        if (highlight && hit) hits += 1;
        return { row, shown, hit };
      });
      const anyHits = highlight && hits > 0;
      for (const mark of marks) {
        setShown(mark.row, mark.shown);
        mark.row.classList.toggle("filter-hit", anyHits && mark.hit);
        mark.row.classList.toggle("filter-miss", anyHits && !mark.hit);
      }

      const empty = emptyBox(card);
      let message = "";
      if (!highlight && visible === 0) {
        if (st.agentSel.size || st.providerSel.size) {
          message = "Под выбранный фильтр не попала ни одна модель.";
        } else if (st.onlyDebts) {
          message = "Долгов нет.";
        } else if (st.mode === "inactive") {
          message = "Нет неактивных моделей для учёта.";
        } else if (st.mode === "all") {
          message = "Нет моделей для учёта.";
        } else {
          message = "Нет активных моделей для учёта.";
        }
      }
      setShown(empty, Boolean(message));
      if (message) empty.textContent = message;
      setShown(card.querySelector(".table-wrap"), !message);
      const fieldset = card.querySelector("fieldset#flagsForm");
      if (fieldset) {
        fieldset.querySelectorAll(":scope > .hint, :scope > .card-actions").forEach((el) => {
          setShown(el, !message);
        });
      }

      const hint = hintBox(card);
      const showHint = highlight && marks.length > 0 && hits === 0;
      setShown(hint, showHint);
      if (showHint) {
        hint.textContent =
          "Ничего не подсвечено — ни одна модель не проходит выбранные условия.";
      }

      updateModelLists(st);
    }

    const apply = () => {
      const st = state();
      chipsOrder(form, st.chips);
      updateBadge(form, st.view, st.chips, st.captions);
      applyCaptions(st.captions);
      render(st);
      writeUrl([
        ["answer_filter", st.mode !== "active" ? st.mode : ""],
        ["only_debts", st.onlyDebts ? "1" : ""],
        ["agents", st.agentSel.size ? tagsCsv(st.agentSel) : ""],
        ["providers", st.providerSel.size ? tagsCsv(st.providerSel) : ""],
        ["view", st.view === "highlight" ? "highlight" : ""],
        ["chips", st.chips === "elo" ? "elo" : ""],
        ["captions", st.captions ? "show" : ""],
      ]);
    };

    syncFromUrl(form, ["agents", "providers"]);
    form.addEventListener("change", apply);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      apply();
    });
    apply();
  }

  /* Подписи «Компания · Агент» и разделитель «·» перед ними: слепок
   * статичен, поэтому состояние берётся из адреса — подписи видны только
   * при ?captions=show (change caption-visibility-toggle). Флажок панели
   * работает как в живой консоли: состояние живёт в форме и в адресе.
   * Скрытие применяется только к страницам с блоком «Фильтр»: у страницы
   * модели и страницы задачи панели нет, там подпись видна всегда. */
  function applyCaptions(shown) {
    if (!panelForm()) return;
    document.body.classList.toggle("captions-off", !shown);
  }

  function captionsFromUrl() {
    const params = new URLSearchParams(location.search);
    return (params.get("captions") || "").toLowerCase() === "show";
  }

  /* ── Запуск: страница сама выбирает, что инициализировать ───────── */

  applyCaptions(captionsFromUrl());
  initRating();
  initHistory();
  initStats();
  initSettings();
})();
