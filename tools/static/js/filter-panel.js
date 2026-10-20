/* filter-panel.js — закрытие поповера «Настройки фильтра» (change
 * filter-settings-trigger).
 *
 * Подключается и в live-консоли, и в статическом слепке (shell.html), поэтому
 * работает одинаково в обоих режимах. Прогрессивное улучшение: <details>
 * открывается и закрывается нативно и без скрипта; здесь добавляются только
 * закрытие кликом вне панели и клавишей Escape с возвратом фокуса на summary.
 * Содержимое панели рендерит сервер, скрипт его не подменяет.
 */

(function () {
  "use strict";

  function init(details) {
    const summary = details.querySelector("summary");
    if (!summary) return;

    document.addEventListener("click", (event) => {
      if (details.open && !details.contains(event.target)) {
        details.open = false;
      }
    });

    details.addEventListener("keydown", (event) => {
      if (event.key !== "Escape" || !details.open) return;
      event.preventDefault();
      details.open = false;
      summary.focus();
    });
  }

  document.querySelectorAll("details.filter-settings").forEach(init);
})();
