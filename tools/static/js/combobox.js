/* combobox.js — прогрессивное автодополнение селектов моделей (change
 * console-wave3-data-scale).
 *
 * Подключается только в live-режиме консоли (shell.html); в слепке скрипт не
 * грузится, и селекты остаются обычными. Для каждого select[data-combobox]
 * строится текстовый input с ролью combobox и listbox: фильтрация опций без
 * серверных запросов (подстрока имени/id), группировка опций по агенту
 * (data-agent), управление клавиатурой (↓/↑/Enter/Esc), выбор кликом.
 *
 * Выбор пишется в исходный select и диспатчит change — страницы слушают его
 * для автопереходов (фильтр истории) и валидации (форма вердикта). Blur и
 * клик вне списка возвращают прежнее значение: произвольный текст в select
 * не попадает.
 */

(function () {
  "use strict";

  let counter = 0;

  function optionLabel(option) {
    return (option.textContent || "").trim();
  }

  function init(select) {
    const emptyOption = select.options.length ? select.options[0] : null;
    const placeholder =
      emptyOption && emptyOption.value === ""
        ? optionLabel(emptyOption)
        : "Начните вводить имя";
    const groupByAgent = Array.prototype.some.call(select.options, (option) => {
      return option.dataset && option.dataset.agent;
    });

    const wrap = document.createElement("div");
    wrap.className = "combobox";
    select.parentNode.insertBefore(wrap, select);
    wrap.appendChild(select);
    select.classList.add("combobox-native");
    select.setAttribute("tabindex", "-1");

    const input = document.createElement("input");
    input.type = "text";
    input.className = "combobox-input";
    input.autocomplete = "off";
    input.spellcheck = false;
    input.placeholder = placeholder;
    const label = select.getAttribute("data-label");
    if (label) input.setAttribute("aria-label", label);
    input.setAttribute("role", "combobox");
    input.setAttribute("aria-expanded", "false");
    input.setAttribute("aria-autocomplete", "list");
    const listId = "combobox-list-" + (++counter);
    input.setAttribute("aria-controls", listId);

    const list = document.createElement("div");
    list.className = "combobox-list";
    list.id = listId;
    list.setAttribute("role", "listbox");
    list.hidden = true;

    // Опции списка — по элементу на опцию select; заголовки групп — агент.
    const options = [];
    const headings = [];
    let currentGroup = null;
    Array.prototype.forEach.call(select.options, (option, index) => {
      const agent = (option.dataset && option.dataset.agent) || "";
      let heading = null;
      if (groupByAgent) {
        const group = agent || "без агента";
        if (group !== currentGroup) {
          currentGroup = group;
          heading = document.createElement("div");
          heading.className = "combobox-group";
          heading.setAttribute("role", "presentation");
          heading.textContent = group;
          list.appendChild(heading);
          headings.push(heading);
        }
      }
      const item = document.createElement("div");
      item.className = "combobox-option";
      item.id = listId + "-" + index;
      item.setAttribute("role", "option");
      item.setAttribute("aria-selected", "false");
      item.dataset.value = option.value;
      item.textContent = optionLabel(option);
      item.comboboxHeading = heading;
      item.addEventListener("mousedown", (event) => event.preventDefault());
      item.addEventListener("click", () => pick(item));
      list.appendChild(item);
      options.push(item);
    });

    const empty = document.createElement("div");
    empty.className = "combobox-empty";
    empty.textContent = "ничего не найдено";
    empty.hidden = true;
    list.appendChild(empty);

    wrap.appendChild(input);
    wrap.appendChild(list);

    let visible = options.slice();
    let activeItem = null;

    function selectedLabel() {
      const option = select.options[select.selectedIndex];
      if (!option || option.value === "") return "";
      return optionLabel(option);
    }

    function setActive(item) {
      if (activeItem) {
        activeItem.classList.remove("is-active");
        activeItem.setAttribute("aria-selected", "false");
      }
      activeItem = item || null;
      if (activeItem) {
        activeItem.classList.add("is-active");
        activeItem.setAttribute("aria-selected", "true");
        input.setAttribute("aria-activedescendant", activeItem.id);
        activeItem.scrollIntoView({ block: "nearest" });
      } else {
        input.removeAttribute("aria-activedescendant");
      }
    }

    function applyFilter(query) {
      const needle = (query || "").trim().toLowerCase();
      visible = [];
      for (const item of options) {
        const hay = (item.textContent + " " + item.dataset.value).toLowerCase();
        const show = !needle || hay.indexOf(needle) !== -1;
        item.hidden = !show;
        if (show) {
          visible.push(item);
          if (item.comboboxHeading) item.comboboxHeading.dataset.hasVisible = "1";
        }
      }
      for (const heading of headings) {
        heading.hidden = heading.dataset.hasVisible !== "1";
        delete heading.dataset.hasVisible;
      }
      empty.hidden = visible.length !== 0;
      setActive(null);
    }

    function open() {
      if (!list.hidden) return;
      list.hidden = false;
      input.setAttribute("aria-expanded", "true");
      applyFilter(input.value === selectedLabel() ? "" : input.value);
    }

    function close() {
      if (list.hidden) return;
      list.hidden = true;
      input.setAttribute("aria-expanded", "false");
      setActive(null);
    }

    function revert() {
      input.value = selectedLabel();
      close();
    }

    function pick(item) {
      const value = item.dataset.value;
      select.value = value;
      input.value = value === "" ? "" : item.textContent;
      close();
      select.dispatchEvent(new Event("change", { bubbles: true }));
    }

    input.value = selectedLabel();
    input.addEventListener("focus", open);
    input.addEventListener("click", open);
    input.addEventListener("input", () => {
      open();
      applyFilter(input.value);
    });
    input.addEventListener("keydown", (event) => {
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        if (list.hidden) open();
        if (!visible.length) return;
        const current = activeItem ? visible.indexOf(activeItem) : -1;
        let index;
        if (event.key === "ArrowDown") {
          index = current < 0 ? 0 : (current + 1) % visible.length;
        } else {
          index = current <= 0 ? visible.length - 1 : current - 1;
        }
        setActive(visible[index]);
      } else if (event.key === "Enter") {
        if (!list.hidden && activeItem) {
          event.preventDefault();
          pick(activeItem);
        } else if (!list.hidden && visible.length === 1) {
          event.preventDefault();
          pick(visible[0]);
        }
      } else if (event.key === "Escape") {
        if (!list.hidden) {
          event.preventDefault();
          revert();
        }
      } else if (event.key === "Tab") {
        revert();
      }
    });
    input.addEventListener("blur", revert);

    document.addEventListener("mousedown", (event) => {
      if (!wrap.contains(event.target)) revert();
    });
  }

  const selects = document.querySelectorAll("select[data-combobox]");
  Array.prototype.forEach.call(selects, init);
})();
