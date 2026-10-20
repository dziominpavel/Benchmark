/* lines-picker.js — выбор моделей для «Динамики ELO» без перечисления
 * всего реестра (change console-wave6-analytics-scale).
 *
 * Источник правды — текстовое поле со списком id через запятую: с ним
 * работает и страница без JavaScript. Скрипт добавляет к нему поиск по
 * реестру (серверный поиск /stats/models?q=…) и чипы выбранных моделей
 * с кнопкой удаления. Поле не перечисляет модели: выбор идёт через поиск,
 * поэтому карточка остаётся лёгкой на пуле в сотни и тысячи моделей.
 *
 * Скрипт подключается только в локальной консоли (shell.html); в слепке
 * контролы выбора линий не отображаются, и скрипт не грузится.
 */

(function () {
  "use strict";

  const MAX_LINES = 10;
  const DEBOUNCE_MS = 180;

  function init(root) {
    const input = root.querySelector("[data-lines-input]");
    const chips = root.querySelector("[data-lines-chips]");
    const search = root.querySelector("[data-lines-search]");
    const results = root.querySelector("[data-lines-results]");
    if (!input || !chips || !search || !results) return;

    // Имена известных моделей: из серверных чипов и из результатов поиска.
    const names = new Map();
    chips.querySelectorAll("[data-lines-id]").forEach((chip) => {
      names.set(chip.dataset.linesId, chip.dataset.linesName || chip.dataset.linesId);
    });

    function ids() {
      return input.value
        .split(",")
        .map((part) => part.trim())
        .filter(Boolean);
    }

    function label(mid) {
      return names.get(mid) || mid;
    }

    function setIds(list) {
      input.value = list.join(",");
      renderChips();
    }

    function renderChips() {
      const list = ids();
      chips.textContent = "";
      list.forEach((mid) => {
        const chip = document.createElement("span");
        chip.className = "lines-chip";
        chip.dataset.linesId = mid;
        chip.dataset.linesName = label(mid);
        const name = document.createElement("span");
        name.className = "lines-chip-name";
        name.textContent = label(mid);
        const remove = document.createElement("button");
        remove.type = "button";
        remove.className = "lines-chip-remove";
        remove.dataset.linesRemove = mid;
        remove.setAttribute("aria-label", "Убрать " + label(mid));
        remove.textContent = "×";
        chip.appendChild(name);
        chip.appendChild(remove);
        chips.appendChild(chip);
      });
    }

    function clearResults() {
      results.textContent = "";
      results.hidden = true;
    }

    function showResults(found) {
      results.textContent = "";
      if (!found.length) {
        results.hidden = true;
        return;
      }
      const chosen = new Set(ids());
      found.forEach((item) => {
        const li = document.createElement("li");
        const button = document.createElement("button");
        button.type = "button";
        button.dataset.linesAdd = item.id;
        const name = document.createElement("span");
        name.textContent = item.name;
        const elo = document.createElement("span");
        elo.className = "lines-result-elo";
        elo.textContent = chosen.has(item.id) ? "уже выбрана" : String(item.elo);
        if (chosen.has(item.id)) elo.className = "lines-result-added";
        button.appendChild(name);
        button.appendChild(elo);
        li.appendChild(button);
        results.appendChild(li);
      });
      results.hidden = false;
    }

    let timer = null;
    let controller = null;

    function searchNow() {
      const query = search.value.trim();
      if (!query) {
        clearResults();
        return;
      }
      if (controller) controller.abort();
      controller = new AbortController();
      fetch("/stats/models?q=" + encodeURIComponent(query), {
        signal: controller.signal,
      })
        .then((response) => (response.ok ? response.json() : []))
        .then((data) => {
          (data || []).forEach((item) => names.set(item.id, item.name));
          showResults(Array.isArray(data) ? data : []);
        })
        .catch(() => {});
    }

    search.addEventListener("input", () => {
      window.clearTimeout(timer);
      timer = window.setTimeout(searchNow, DEBOUNCE_MS);
    });

    results.addEventListener("click", (event) => {
      const button = event.target.closest("[data-lines-add]");
      if (!button) return;
      const mid = button.dataset.linesAdd;
      const list = ids();
      if (list.includes(mid)) {
        setIds(list.filter((item) => item !== mid));
      } else if (list.length < MAX_LINES) {
        setIds(list.concat([mid]));
      }
      searchNow();
    });

    chips.addEventListener("click", (event) => {
      const button = event.target.closest("[data-lines-remove]");
      if (!button) return;
      const mid = button.dataset.linesRemove;
      setIds(ids().filter((item) => item !== mid));
    });

    input.addEventListener("input", renderChips);

    renderChips();
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
