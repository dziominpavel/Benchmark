/* live-search.js — живой поиск по имени/id (change live-search).
 *
 * Подключается только в live-режиме консоли (shell.html). Один модуль
 * обслуживает три поиска:
 *   - local: главная (`q`) и «Личные встречи» (`h2h_q`) — строки уже есть
 *     в DOM, меняется только их hidden;
 *   - remote: история (`pair`) — результаты постраничны, поэтому с задержкой
 *     180 мс запрашивается HTML-фрагмент /history/results.
 *
 * Разметка контракта:
 *   [data-live-search="local|remote"]  корень поиска (body страницы);
 *   [data-live-param]                  имя GET-параметра поиска;
 *   [data-live-input]                  поле ввода;
 *   [data-search]                      строка local-поиска;
 *   [data-hit="1"]                     строка, прошедшая отбор (подсветка);
 *   [data-live-results]                контейнер remote-результатов;
 *   [data-live-count-value]            значение счётчика;
 *   [data-live-hits-value]             значение счётчика подсветки;
 *   [data-live-empty]                  пустое состояние поиска;
 *   [data-live-table]                  обёртка таблицы local-поиска;
 *   [data-live-hit-hint]               подсказка «ничего не подсвечено»;
 *   [data-live-link]                   ссылка, сохраняющая поисковый параметр;
 *   [data-live-reset]                  ссылка «Сбросить»;
 *   [data-live-status]                 aria-live-статус.
 *
 * Прогрессивное улучшение: без скрипта остаются серверные GET-формы и
 * onchange; скрипт снимает onchange только с самого поля поиска.
 */

(function () {
  "use strict";

  const DEBOUNCE_MS = 180;
  const SKIP_FIELDS = new Set(["page", "v", "success", "error"]);

  function normalize(value) {
    const text = String(value == null ? "" : value);
    try {
      return text.normalize("NFKC").toLowerCase();
    } catch (error) {
      return text.toLowerCase();
    }
  }

  function setStatus(status, text) {
    if (!status || status.textContent === text) return;
    status.textContent = text;
  }

  function setBusy(results, busy) {
    if (!results) return;
    results.setAttribute("aria-busy", busy ? "true" : "false");
    results.classList.toggle("is-loading", busy);
  }

  /* «Сбросить» видима, пока задан поиск или активен другой фильтр. */
  function setResetVisibility(root, hasQuery) {
    root.querySelectorAll("[data-live-reset]").forEach((link) => {
      link.hidden = !(hasQuery || link.dataset.otherActive === "1");
    });
  }

  function withParam(href, param, value) {
    const url = new URL(href, window.location.href);
    if (value) url.searchParams.set(param, value);
    else url.searchParams.delete(param);
    return url.pathname + url.search + url.hash;
  }

  function updateLinks(root, param, value) {
    root.querySelectorAll("[data-live-link]").forEach((link) => {
      const href = link.getAttribute("href");
      if (!href) return;
      link.setAttribute("href", withParam(href, param, value));
    });
  }

  function replaceLocationParam(param, value) {
    const url = new URL(window.location.href);
    if (value) url.searchParams.set(param, value);
    else url.searchParams.delete(param);
    window.history.replaceState(null, "", url.pathname + url.search + url.hash);
  }

  /* ─── local-режим: строки уже в DOM ─────────────────────────────────── */

  function initLocal(root, input, status) {
    const param = root.dataset.liveParam || "q";
    const highlightMode = root.dataset.liveHighlight === "1";
    const rows = Array.from(root.querySelectorAll("[data-search]"));
    const table = root.querySelector("[data-live-table]");
    const emptyStates = Array.from(root.querySelectorAll("[data-live-empty]"));
    const countValues = Array.from(root.querySelectorAll("[data-live-count-value]"));
    const hitsValues = Array.from(root.querySelectorAll("[data-live-hits-value]"));
    const hitHint = root.querySelector("[data-live-hit-hint]");
    const emptyText = root.querySelector("[data-live-empty-text]");
    const form = input.closest("form");

    input.removeAttribute("onchange");

    function apply() {
      const raw = input.value;
      const typed = raw.trim();
      const needle = normalize(raw).trim();
      let visible = 0;
      let hits = 0;
      const matched = new Map();

      for (const row of rows) {
        const hay = normalize(row.dataset.search || "");
        const show = !needle || hay.indexOf(needle) !== -1;
        matched.set(row, show);
        /* В режиме «Подсвечивать» поиск не сужает состав: несовпавшие
           строки остаются в таблице и приглушаются. */
        row.hidden = highlightMode ? false : !show;
        if (highlightMode || show) visible += 1;
        if (show && row.dataset.hit === "1") hits += 1;
      }

      /* Подсветка: «filter-hit»/«filter-miss» — по тем же правилам, что и на
         сервере (классы есть, только когда отобрана хотя бы одна отобранная
         строка). Иначе подсветка не появлялась бы после очистки поиска.
         Вне режима «Подсвечивать» классы не трогаем — там их нет вовсе. */
      if (highlightMode) {
        if (hits > 0) {
          for (const row of rows) {
            const isHit = row.dataset.hit === "1" && matched.get(row);
            row.classList.toggle("filter-hit", Boolean(isHit));
            row.classList.toggle("filter-miss", !isHit);
          }
        } else {
          for (const row of rows) {
            row.classList.remove("filter-hit");
            row.classList.remove("filter-miss");
          }
        }
      }

      for (const el of countValues) el.textContent = String(visible);
      for (const el of hitsValues) el.textContent = String(hits);
      if (emptyText) {
        emptyText.textContent = typed
          ? "Ничего не найдено по запросу «" + typed + "»."
          : "Ничего не найдено.";
      }

      const hasPool = rows.length > 0;
      if (table) table.hidden = hasPool && visible === 0;
      for (const el of emptyStates) el.hidden = !(hasPool && visible === 0);
      if (hitHint) hitHint.hidden = !(visible > 0 && hits === 0);

      setResetVisibility(root, Boolean(typed));
      updateLinks(root, param, typed);
      replaceLocationParam(param, typed);
      if (highlightMode) {
        setStatus(status, typed ? "Подсвечено: " + hits : "Показано: " + visible);
      } else {
        setStatus(status, typed ? "Найдено: " + visible : "Показано: " + visible);
      }
    }

    input.addEventListener("input", apply);
    input.addEventListener("search", apply);
    if (form) {
      form.addEventListener("submit", (event) => {
        event.preventDefault();
        apply();
      });
    }

    /* «Сбросить поиск» в пустом состоянии: очищаем поле без перезагрузки. */
    root.querySelectorAll("[data-live-clear]").forEach((link) => {
      link.addEventListener("click", (event) => {
        event.preventDefault();
        input.value = "";
        apply();
        input.focus();
      });
    });
  }

  /* ─── remote-режим: фрагмент /history/results ─────────────────────────── */

  function formParams(form) {
    const params = new URLSearchParams();
    const data = new FormData(form);
    for (const [name, raw] of data.entries()) {
      if (SKIP_FIELDS.has(name)) continue;
      const value = String(raw);
      if (!value.trim()) continue;
      params.append(name, value);
    }
    return params;
  }

  /* URL после успешного ответа: текущие фильтры + живой запрос, без page/v. */
  function syncHistoryLocation(param, value) {
    const url = new URL(window.location.href);
    url.searchParams.delete("page");
    url.searchParams.delete("v");
    url.searchParams.delete("success");
    url.searchParams.delete("error");
    if (value) url.searchParams.set(param, value);
    else url.searchParams.delete(param);
    window.history.replaceState(null, "", url.pathname + url.search + url.hash);
  }

  function initRemote(root, input, status) {
    let results = root.querySelector("[data-live-results]");
    if (!results) return;
    const form = input.closest("form");
    if (!form) return;
    const param = root.dataset.liveParam || "pair";
    const endpoint = root.dataset.liveEndpoint || "/history/results";
    let timer = null;
    let controller = null;
    let sequence = 0;

    input.removeAttribute("onchange");

    /* Устаревший запрос не должен примениться: гасим его сразу. */
    function invalidate() {
      if (timer !== null) {
        window.clearTimeout(timer);
        timer = null;
      }
      sequence += 1;
      if (controller) {
        controller.abort();
        controller = null;
      }
    }

    async function request() {
      if (timer !== null) {
        window.clearTimeout(timer);
        timer = null;
      }
      if (controller) controller.abort();

      const requestSequence = ++sequence;
      const abort = new AbortController();
      controller = abort;
      const params = formParams(form);
      const query = params.toString();
      const url = endpoint + (query ? "?" + query : "");

      setBusy(results, true);
      setStatus(status, "Идёт поиск…");

      try {
        const response = await fetch(url, {
          signal: abort.signal,
          cache: "no-store",
          headers: { "X-Requested-With": "fetch" },
        });
        if (!response.ok) throw new Error("HTTP " + response.status);
        const html = await response.text();
        if (requestSequence !== sequence) return;

        const template = document.createElement("template");
        template.innerHTML = html.trim();
        const next = template.content.querySelector("[data-live-results]");
        if (!next) throw new Error("пустой фрагмент истории");

        results.replaceWith(next);
        results = next;

        const title = next.dataset.historyTitle;
        if (title) document.title = title;
        const found = next.dataset.historyFound || "";
        setStatus(status, found ? "Найдено: " + found : "Результаты обновлены");
        syncHistoryLocation(param, input.value.trim());
      } catch (error) {
        if (error && error.name === "AbortError") return;
        if (requestSequence !== sequence) return;
        setStatus(status, "Не удалось обновить результаты");
      } finally {
        if (requestSequence === sequence) {
          controller = null;
          setBusy(results, false);
        }
      }
    }

    function schedule() {
      invalidate();
      setResetVisibility(root, Boolean(input.value.trim()));
      timer = window.setTimeout(request, DEBOUNCE_MS);
    }

    input.addEventListener("input", schedule);
    input.addEventListener("search", schedule);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      invalidate();
      request();
    });
  }

  function init(root) {
    const mode = root.dataset.liveSearch;
    const param = root.dataset.liveParam || "q";
    const input = root.querySelector("[data-live-input]") ||
      root.querySelector('input[name="' + param + '"]');
    if (!input) return;
    const status = root.querySelector("[data-live-status]");
    if (mode === "remote") initRemote(root, input, status);
    else initLocal(root, input, status);
  }

  document.querySelectorAll("[data-live-search]").forEach(init);
})();
