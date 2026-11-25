"""Pure pagination, validation, and date filtering for ChatGPT chat indexes."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Literal, Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

ArchiveScope = Literal["active", "archived", "all"]
DateField = Literal["created", "updated"]
MAX_PAGE_SIZE = 20
_CONVERSATION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{7,127}$")


class ConversationIndexError(ValueError):
    """The index query or authenticated page payload violated its contract."""


class PageFetcher(Protocol):
    def __call__(
        self,
        offset: int,
        limit: int,
        *,
        archived: bool,
    ) -> dict[str, object]: ...


@dataclass(frozen=True)
class ConversationSummary:
    conversation_id: str
    title: str
    created_at: datetime
    updated_at: datetime
    archived: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.conversation_id,
            "url": f"https://chatgpt.com/c/{self.conversation_id}",
            "title": self.title,
            "created_at": format_utc(self.created_at),
            "updated_at": format_utc(self.updated_at),
            "archived": self.archived,
        }


@dataclass(frozen=True)
class ConversationIndexResult:
    conversations: tuple[ConversationSummary, ...]
    pages_fetched: int


def format_utc(value: datetime) -> str:
    """Render an aware timestamp as stable RFC 3339 UTC."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ConversationIndexError("timestamp must include a timezone")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def calendar_date_bounds(
    from_date: str,
    through_date: str,
    timezone_name: str,
) -> tuple[datetime, datetime]:
    """Return an inclusive-date range as a half-open pair of UTC timestamps."""

    start_date = _parse_calendar_date(from_date, "from-date")
    last_date = _parse_calendar_date(through_date, "to-date")
    if start_date > last_date:
        raise ConversationIndexError("from-date must not be after to-date")
    try:
        selected_timezone = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise ConversationIndexError(
            f"unknown IANA timezone: {timezone_name!r}"
        ) from error
    try:
        end_date = last_date + timedelta(days=1)
    except OverflowError as error:
        raise ConversationIndexError(
            "to-date is outside the supported range"
        ) from error

    start = datetime.combine(start_date, time.min, selected_timezone)
    end = datetime.combine(end_date, time.min, selected_timezone)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def list_recent(
    fetch_page: PageFetcher,
    *,
    limit: int,
    archive_scope: ArchiveScope = "active",
    page_size: int = MAX_PAGE_SIZE,
) -> ConversationIndexResult:
    """Return the most recently updated conversations in the selected scope."""

    _validate_positive_int(limit, "limit")
    _validate_page_size(page_size)
    scopes = _archive_scopes(archive_scope)
    seen: set[str] = set()
    conversations: list[ConversationSummary] = []
    pages_fetched = 0

    # Fetch up to N from each archive partition. Their merged top N is therefore
    # complete even though the website exposes the partitions separately.
    for archived in scopes:
        scope_items, scope_pages = _recent_from_scope(
            fetch_page,
            archived=archived,
            limit=limit,
            page_size=page_size,
            seen=seen,
        )
        conversations.extend(scope_items)
        pages_fetched += scope_pages

    conversations.sort(
        key=lambda item: (item.updated_at, item.conversation_id),
        reverse=True,
    )
    return ConversationIndexResult(tuple(conversations[:limit]), pages_fetched)


def list_date_range(
    fetch_page: PageFetcher,
    *,
    start: datetime,
    end: datetime,
    date_field: DateField = "created",
    archive_scope: ArchiveScope = "all",
    page_size: int = MAX_PAGE_SIZE,
) -> ConversationIndexResult:
    """Return conversations whose selected timestamp is in ``[start, end)``."""

    start_utc = _aware_utc(start, "start")
    end_utc = _aware_utc(end, "end")
    if start_utc >= end_utc:
        raise ConversationIndexError("date range start must be before end")
    if date_field not in ("created", "updated"):
        raise ConversationIndexError("date_field must be 'created' or 'updated'")
    _validate_page_size(page_size)
    scopes = _archive_scopes(archive_scope)
    seen: set[str] = set()
    conversations: list[ConversationSummary] = []
    pages_fetched = 0

    for archived in scopes:
        scope_items, scope_pages = _range_from_scope(
            fetch_page,
            archived=archived,
            start=start_utc,
            end=end_utc,
            date_field=date_field,
            page_size=page_size,
            seen=seen,
        )
        conversations.extend(scope_items)
        pages_fetched += scope_pages

    conversations.sort(
        key=lambda item: (
            item.created_at if date_field == "created" else item.updated_at,
            item.conversation_id,
        ),
        reverse=True,
    )
    return ConversationIndexResult(tuple(conversations), pages_fetched)


def _recent_from_scope(
    fetch_page: PageFetcher,
    *,
    archived: bool,
    limit: int,
    page_size: int,
    seen: set[str],
) -> tuple[list[ConversationSummary], int]:
    offset = 0
    pages_fetched = 0
    conversations: list[ConversationSummary] = []
    previous_update: datetime | None = None

    while len(conversations) < limit:
        page = _read_page(fetch_page, offset, page_size, archived=archived)
        pages_fetched += 1
        if not page:
            break
        previous_update = _validate_update_order(page, previous_update)
        for item in page:
            _remember(item, seen)
            conversations.append(item)
        if len(page) < page_size:
            break
        offset += len(page)

    return conversations, pages_fetched


def _range_from_scope(
    fetch_page: PageFetcher,
    *,
    archived: bool,
    start: datetime,
    end: datetime,
    date_field: DateField,
    page_size: int,
    seen: set[str],
) -> tuple[list[ConversationSummary], int]:
    offset = 0
    pages_fetched = 0
    matches: list[ConversationSummary] = []
    previous_update: datetime | None = None

    while True:
        page = _read_page(fetch_page, offset, page_size, archived=archived)
        pages_fetched += 1
        if not page:
            break
        previous_update = _validate_update_order(page, previous_update)
        for item in page:
            _remember(item, seen)
            selected_time = (
                item.created_at if date_field == "created" else item.updated_at
            )
            if start <= selected_time < end:
                matches.append(item)

        # The endpoint supports only updated-descending order. Once that order
        # crosses the lower bound, no later valid item can match either field:
        # every item's creation time is validated to be no later than its
        # update time.
        if page[-1].updated_at < start:
            break
        if len(page) < page_size:
            break
        offset += len(page)

    return matches, pages_fetched


def _read_page(
    fetch_page: PageFetcher,
    offset: int,
    page_size: int,
    *,
    archived: bool,
) -> list[ConversationSummary]:
    payload = fetch_page(offset, page_size, archived=archived)
    if not isinstance(payload, dict):
        raise ConversationIndexError("conversation page must be an object")
    items = payload.get("items")
    if not isinstance(items, list):
        raise ConversationIndexError("conversation page items must be a list")
    if len(items) > page_size:
        raise ConversationIndexError("conversation page exceeds the requested limit")
    response_offset = payload.get("offset")
    if response_offset is not None and (
        isinstance(response_offset, bool)
        or not isinstance(response_offset, int)
        or response_offset != offset
    ):
        raise ConversationIndexError(
            "conversation page offset mismatch: "
            f"expected {offset}, got {response_offset!r}"
        )
    response_limit = payload.get("limit")
    if response_limit is not None and (
        isinstance(response_limit, bool)
        or not isinstance(response_limit, int)
        or response_limit != page_size
    ):
        raise ConversationIndexError(
            "conversation page limit mismatch: "
            f"expected {page_size}, got {response_limit!r}"
        )

    parsed: list[ConversationSummary] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ConversationIndexError(f"conversation item {index} must be an object")
        parsed.append(_parse_item(item, archived=archived, index=index))
    return parsed


def _parse_item(
    item: dict[str, object],
    *,
    archived: bool,
    index: int,
) -> ConversationSummary:
    conversation_id = item.get("id")
    if not isinstance(conversation_id, str) or not _CONVERSATION_ID.fullmatch(
        conversation_id
    ):
        raise ConversationIndexError(f"conversation item {index} has an invalid id")
    title = item.get("title")
    if not isinstance(title, str):
        raise ConversationIndexError(f"conversation item {index} has an invalid title")
    item_archived = item.get("is_archived")
    if not isinstance(item_archived, bool) or item_archived is not archived:
        raise ConversationIndexError(
            f"conversation item {conversation_id} does not match the archive scope"
        )
    created_at = _parse_timestamp(item.get("create_time"), "create_time")
    updated_at = _parse_timestamp(item.get("update_time"), "update_time")
    if updated_at < created_at:
        raise ConversationIndexError(
            f"conversation item {conversation_id} was updated before it was created"
        )
    return ConversationSummary(
        conversation_id=conversation_id,
        title=title,
        created_at=created_at,
        updated_at=updated_at,
        archived=item_archived,
    )


def _parse_timestamp(value: object, field: str) -> datetime:
    if isinstance(value, bool):
        raise ConversationIndexError(f"{field} must be a timestamp")
    if isinstance(value, (int, float)):
        if not math.isfinite(value):
            raise ConversationIndexError(f"{field} must be finite")
        try:
            return datetime.fromtimestamp(value, timezone.utc)
        except (OverflowError, OSError, ValueError) as error:
            raise ConversationIndexError(
                f"{field} is outside the supported range"
            ) from error
    if not isinstance(value, str) or not value:
        raise ConversationIndexError(f"{field} must be a timestamp")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise ConversationIndexError(f"{field} is not valid ISO 8601") from error
    return _aware_utc(parsed, field)


def _aware_utc(value: datetime, name: str) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ConversationIndexError(f"{name} must include a timezone")
    return value.astimezone(timezone.utc)


def _validate_update_order(
    page: list[ConversationSummary],
    previous_update: datetime | None,
) -> datetime:
    for item in page:
        if previous_update is not None and item.updated_at > previous_update:
            raise ConversationIndexError(
                "conversation pages are not ordered by update_time; retry the query"
            )
        previous_update = item.updated_at
    assert previous_update is not None
    return previous_update


def _remember(item: ConversationSummary, seen: set[str]) -> None:
    if item.conversation_id in seen:
        raise ConversationIndexError(
            f"duplicate conversation {item.conversation_id!r} across pages; "
            "retry the query"
        )
    seen.add(item.conversation_id)


def _parse_calendar_date(value: str, name: str) -> date:
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError) as error:
        raise ConversationIndexError(f"{name} must use YYYY-MM-DD") from error
    if parsed.isoformat() != value:
        raise ConversationIndexError(f"{name} must use YYYY-MM-DD")
    return parsed


def _archive_scopes(scope: ArchiveScope) -> tuple[bool, ...]:
    if scope == "active":
        return (False,)
    if scope == "archived":
        return (True,)
    if scope == "all":
        return (False, True)
    raise ConversationIndexError("archive_scope must be 'active', 'archived', or 'all'")


def _validate_positive_int(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ConversationIndexError(f"{name} must be a positive integer")


def _validate_page_size(page_size: int) -> None:
    _validate_positive_int(page_size, "page_size")
    if page_size > MAX_PAGE_SIZE:
        raise ConversationIndexError(
            f"page_size must not exceed {MAX_PAGE_SIZE}; "
            "index responses include large mappings"
        )
