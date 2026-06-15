from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass
from itertools import islice
from typing import Generic, TypeVar

from terminalvelocity.models import NormalizedEvent

CacheValue = TypeVar('CacheValue')


class LRUResultCache(Generic[CacheValue]):
    """A small LRU cache for repeated investigation queries."""

    def __init__(self, capacity: int = 128) -> None:
        if capacity <= 0:
            raise ValueError('capacity must be greater than zero')
        self.capacity = capacity
        self._items: OrderedDict[str, CacheValue] = OrderedDict()

    def get(self, key: str) -> CacheValue | None:
        """Return a cached value and promote it to most recently used."""

        if key not in self._items:
            return None
        self._items.move_to_end(key)
        return self._items[key]

    def set(self, key: str, value: CacheValue) -> None:
        """Insert or update a cache entry."""

        self._items[key] = value
        self._items.move_to_end(key)
        if len(self._items) > self.capacity:
            self._items.popitem(last=False)

    def get_or_set(self, key: str, factory: Callable[[], CacheValue]) -> CacheValue:
        """Return a cached value or compute and store it."""

        cached = self.get(key)
        if cached is not None:
            return cached
        value = factory()
        self.set(key, value)
        return value

    def clear(self) -> None:
        """Remove all cached values."""

        self._items.clear()


@dataclass(slots=True)
class PagedResult(Generic[CacheValue]):
    """A page of results with navigation metadata."""

    items: list[CacheValue]
    page: int
    page_size: int
    total_items: int

    @property
    def total_pages(self) -> int:
        """Return the total number of pages."""

        return max((self.total_items + self.page_size - 1) // self.page_size, 1)

    @property
    def has_next(self) -> bool:
        """Return True when another page is available."""

        return self.page < self.total_pages

    @property
    def has_previous(self) -> bool:
        """Return True when a prior page is available."""

        return self.page > 1


def paginate_sequence(items: Sequence[CacheValue], *, page: int = 1, page_size: int = 100) -> PagedResult[CacheValue]:
    """Return a single page from an in-memory sequence."""

    _validate_pagination(page=page, page_size=page_size)
    start = (page - 1) * page_size
    stop = start + page_size
    return PagedResult(items=list(items[start:stop]), page=page, page_size=page_size, total_items=len(items))


def paginate_iterable(items: Iterable[CacheValue], *, page: int = 1, page_size: int = 100) -> PagedResult[CacheValue]:
    """Paginate a generic iterable with a single pass over the data."""

    _validate_pagination(page=page, page_size=page_size)
    start = (page - 1) * page_size
    stop = start + page_size
    page_items: list[CacheValue] = []
    total_items = 0
    for total_items, item in enumerate(items, start=1):
        index = total_items - 1
        if start <= index < stop:
            page_items.append(item)
    return PagedResult(items=page_items, page=page, page_size=page_size, total_items=total_items)


def batched_events(events: Iterable[NormalizedEvent], *, batch_size: int = 500) -> Iterator[list[NormalizedEvent]]:
    """Yield ordered event batches for large result sets."""

    if batch_size <= 0:
        raise ValueError('batch_size must be greater than zero')
    iterator = iter(sorted(events, key=lambda event: event.timestamp))
    while True:
        batch = list(islice(iterator, batch_size))
        if not batch:
            break
        yield batch


def deduplicate_events(events: Iterable[NormalizedEvent]) -> list[NormalizedEvent]:
    """Deduplicate events using stable identifiers while preserving timestamp order."""

    seen: set[str] = set()
    unique: list[NormalizedEvent] = []
    for event in sorted(events, key=lambda item: item.timestamp):
        stable_id = event.stable_id()
        if stable_id in seen:
            continue
        seen.add(stable_id)
        unique.append(event)
    return unique


def _validate_pagination(*, page: int, page_size: int) -> None:
    if page <= 0:
        raise ValueError('page must be greater than zero')
    if page_size <= 0:
        raise ValueError('page_size must be greater than zero')
