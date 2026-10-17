#!/usr/bin/env python3
"""
data_cache.py — memo-слой производных структур консоли.

DataKey — снимок входных данных:
  * дайджест журнала событий data/matchups/journal.jsonl — sha256
    содержимого файла; при неизменных (mtime_ns, size) перехэширование
    не повторяется (миллисекунды вместо десятков на 10k строк);
  * sha256 управляющих файлов: models.yaml, answer_flags.yaml,
    settings.yaml, lookups.yaml — файлы малы, хэшируются на каждый вызов.

cached(name, builder) возвращает значение из мемо; при смене DataKey мемо
сбрасывается целиком и builder вызывается заново. Сборка идёт под
threading.RLock (однократно даже при параллельных запросах). Значения
разделяются между вызовами: вызывающие не должны менять их структуру —
только читать. Ключ проверяется на каждом вызове, поэтому правка журнала
или управляющего файла (в том числе другим процессом) видна следующему
запросу: устаревших ответов дольше одного запроса не бывает.

Зависимости: только stdlib + elo.py + lookups.py.
"""

from __future__ import annotations

import hashlib
import threading
from pathlib import Path

import elo
import lookups


class _JournalDigest:
    """sha256 журнала с кэшем по (mtime_ns, size) файла."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stat_key: tuple[int, int] | None = None
        self._digest: str | None = None

    def get(self) -> str:
        try:
            st = elo.JOURNAL_PATH.stat()
            stat_key: tuple[int, int] | None = (st.st_mtime_ns, st.st_size)
        except OSError:
            stat_key = None
        with self._lock:
            if self._digest is not None and stat_key == self._stat_key:
                return self._digest
        digest = elo.matchups_digest()
        with self._lock:
            self._stat_key = stat_key
            self._digest = digest
        return digest

    def reset(self) -> None:
        """Забывает кэшированный дайджест (тесты, смена пути)."""
        with self._lock:
            self._stat_key = None
            self._digest = None


_JOURNAL = _JournalDigest()

_LOCK = threading.RLock()
_key: tuple | None = None
_values: dict[str, object] = {}


def _file_sha256(path: Path) -> str:
    """sha256 файла; отсутствующий/недоступный файл — sha256 пустых данных."""
    h = hashlib.sha256()
    try:
        h.update(path.read_bytes())
    except OSError:
        pass
    return h.hexdigest()


def control_file_paths() -> tuple[Path, ...]:
    """Пути управляющих файлов, влияющих на производные консоли."""
    return (
        elo.MODELS_PATH,
        elo.ANSWER_FLAGS_PATH,
        elo.SETTINGS_PATH,
        lookups.LOOKUPS_PATH,
    )


def data_key() -> tuple:
    """Снимок входных данных: (дайджест журнала, sha256 управляющих файлов)."""
    parts: list[str] = [_JOURNAL.get()]
    for path in control_file_paths():
        parts.append(_file_sha256(path))
    return tuple(parts)


def cached(name: str, builder):
    """Возвращает мемо-значение `name`, пересобирая его при смене DataKey.

    `builder` вызывается один раз на имя при одном ключе; результат
    сохраняется до следующей смены ключа. Повторный вызов с тем же ключом
    не выполняет builder и не читает источники заново.
    """
    global _key, _values
    key = data_key()
    with _LOCK:
        if key != _key:
            _key = key
            _values = {}
        if name not in _values:
            _values[name] = builder()
        return _values[name]


def clear() -> None:
    """Сбрасывает мемо и кэш дайджеста (тесты и явная инвалидация)."""
    global _key, _values
    with _LOCK:
        _key = None
        _values = {}
    _JOURNAL.reset()


def memo_stats() -> dict:
    """Диагностика мемо: имена собранных записей и число записей."""
    with _LOCK:
        return {"names": sorted(_values), "size": len(_values)}
