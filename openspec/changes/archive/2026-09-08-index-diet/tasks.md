## 1. Движок кэша

- [x] 1.1 Заменить `build_matchups_index` на `build_matchups_summary` (счётчики `total/applied/voided/tombstone/skipped` без resolved ids), `generate_index` SHALL писать `matchups_summary` вместо `matchups_index`, `main()` SHALL печатать сводку из агрегата; проверить: `test_elo.py` зелёный
- [x] 1.2 Удалить `after_matchup` из записей `recalculate` (+ докстринг); проверить: `test_elo.py` зелёный, `elo.py --check` зелёный после пересчёта

## 2. Потребители и спеки

- [x] 2.1 Сервер: `matchups_count` из `matchups_summary.total` с fallback на `len(matchups_index)` для старого кэша; проверить: главная рендерится и со свежим, и со старым форматом кэша (старый — подменой из git)
- [x] 2.2 Замерить реальный размер `data/index.json` и маржинальную цену вердикта, вписать факты в дельту «Масштаб хранилища» при расхождении >10%; проверить: `openspec validate "index-diet"` валиден

## 3. Финал

- [x] 3.1 Финальная проверка: `test_elo.py`, `test_pairing.py`, `elo.py --check` зелёные; главная, `/model/<id>`, `/history` отвечают 200; зафиксировать результат отметками
