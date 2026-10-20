/* lines-picker.js — выбор моделей для «Динамики ELO»: одно текстовое поле
 * (источник правды), чипы и предупреждения — результат серверного разбора
 * (change fix-elo-dynamics-model-picker).
 *
 * Поле принимает список моделей через запятую: имя, `id` или однозначная
 * часть имени. Разбор делает сервер (GET /stats/models/resolve) — те же
 * правила, что у рендера страницы, поэтому скрипт только показывает ответ:
 * чипы, предупреждения («не найдено», «неоднозначно», «не вошло») и
 * подсказки по последнему токену.
 *
 * Без JavaScript выбор применяет та же GET-форма: поле — источник правды,
 * кнопка «Показать» отправляет список на сервер.
 *
 * Скрипт подключается только в локальной консоли (shell.html); в слепке
 * контролы выбора линий не отображаются, и скрипт не грузится.
 */

(function () {
  "use strict";

  const DEBOUNCE_MS = 180;

  function init(root) {
    const input = root.querySelector("[data-lines-input]");
    const chips = root.querySelector("[data-lines-chips]");
    const results = root.querySelector("[data-lines-results]");
    const warnings = root.querySelector("[data-lines-warnings]");
    const dirty = root.querySelector("[data-lines-dirty]");
    if (!input || !chips || !results) return;

    // Применённый выбор — из адреса: с ним сверяется черновик поля.
    const applied = (root.dataset.linesApplied || "")
      .split(",")
      .map((part) => part.trim())
      .filter(Boolean);

    function tokens() {
      return input.value
        .split(",")
        .map((part) => part.trim())
        .filter(Boolean);
    }

    function setTokens(list) {
      input.value = list.join(", ");
      refresh();
    }

    function removeToken(raw) {
      setTokens(tokens().filter((token) => token !== raw));
    }

    function replaceLast(token) {
      const list = tokens();
      if (list.length) {
        list[list.length - 1] = token;
      } else {
        list.push(token);
      }
      setTokens(list);
    }

    function renderChips(list) {
      chips.textContent = "";
      list.forEach((chip) => {
        const span = document.createElement("span");
        const name = document.createElement("span");
        name.className = "lines-chip-name";
        if (chip.kind === "model") {
          span.className = "lines-chip";
          span.dataset.linesId = chip.id;
          span.dataset.linesRaw = chip.raw;
          span.dataset.linesName = chip.name;
          name.textContent = chip.name;
          const remove = document.createElement("button");
          remove.type = "button";
          remove.className = "lines-chip-remove";
          remove.dataset.linesRemove = chip.raw;
          remove.setAttribute("aria-label", "Убрать " + chip.name);
          remove.textContent = "×";
          span.appendChild(name);
          span.appendChild(remove);
        } else {
          span.className = "lines-chip lines-chip-problem";
          span.dataset.linesRaw = chip.raw;
          name.textContent =
            (chip.status === "ambiguous" ? "неоднозначно: " : "не найдено: ") +
            chip.raw;
          if (chip.candidates && chip.candidates.length) {
            span.title =
              "Подходит: " + chip.candidates.map((c) => c.name).join(", ");
          }
          span.appendChild(name);
        }
        chips.appendChild(span);
      });
    }

    function renderWarnings(list) {
      if (!warnings) return;
      warnings.textContent = "";
      list.forEach((text) => {
        const row = document.createElement("div");
        row.className = "lines-warning";
        row.textContent = text;
        warnings.appendChild(row);
      });
      warnings.hidden = !list.length;
    }

    function renderDirty(ids) {
      if (!dirty) return;
      const same =
        ids.length === applied.length &&
        ids.every((id, index) => id === applied[index]);
      dirty.hidden = same;
    }

    function showCandidates(list) {
      results.textContent = "";
      if (!list.length) {
        results.hidden = true;
        return;
      }
      list.forEach((item) => {
        const li = document.createElement("li");
        const button = document.createElement("button");
        button.type = "button";
        button.dataset.linesAdd = item.token || item.id;
        const name = document.createElement("span");
        name.textContent = item.name;
        const elo = document.createElement("span");
        elo.className = "lines-result-elo";
        elo.textContent = String(item.elo);
        button.appendChild(name);
        button.appendChild(elo);
        li.appendChild(button);
        results.appendChild(li);
      });
      results.hidden = false;
    }

    function applyResult(data) {
      renderChips(data.chips || []);
      renderWarnings(data.warnings || []);
      renderDirty(data.ids || []);
      const list = data.tokens || [];
      const last = list.length ? list[list.length - 1] : null;
      showCandidates(last && last.candidates ? last.candidates : []);
    }

    let timer = null;
    let controller = null;

    function load() {
      if (controller) controller.abort();
      controller = new AbortController();
      fetch("/stats/models/resolve?q=" + encodeURIComponent(input.value), {
        signal: controller.signal,
      })
        .then((response) => (response.ok ? response.json() : null))
        .then((data) => {
          if (data) applyResult(data);
        })
        .catch(() => {});
    }

    function refresh() {
      window.clearTimeout(timer);
      timer = window.setTimeout(load, DEBOUNCE_MS);
    }

    input.addEventListener("input", refresh);

    chips.addEventListener("click", (event) => {
      const button = event.target.closest("[data-lines-remove]");
      if (!button) return;
      removeToken(button.dataset.linesRemove);
    });

    results.addEventListener("click", (event) => {
      const button = event.target.closest("[data-lines-add]");
      if (!button) return;
      replaceLast(button.dataset.linesAdd);
      input.focus();
    });

    // Подсказки закрыты до первого ввода: на странице уже стоит разбор
    // сервера, дублировать его при загрузке незачем.
    results.hidden = true;
  }

  function initAll() {
    document.querySelectorAll("[data-lines-picker]").forEach(init);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initAll);
  } else {
    initAll();
  }
})();
