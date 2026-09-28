"""Signal formulas (architecture §6.4), each a small pure function with a unit test. Code only, never an LLM.

Business days = Mon–Fri, no holidays (v1). OPEN_QUESTIONS #8 (a): "days quiet" counts weekday dates strictly
after the message date and strictly before the run date.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from ..schemas import DeepWorkBlock

WEEKDAY_NAMES = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")


def is_business_day(d: date) -> bool:
    return d.weekday() < 5


def business_days_between(after: date, before: date) -> int:
    """Weekday dates d with after < d < before. Fri→Mon = 0, Fri→Tue = 1, Thu→Tue = 2, Wed→Tue = 3."""
    n = 0
    d = after + timedelta(days=1)
    while d < before:
        if is_business_day(d):
            n += 1
        d += timedelta(days=1)
    return n


def next_business_day(d: date) -> date:
    d = d + timedelta(days=1)
    while not is_business_day(d):
        d += timedelta(days=1)
    return d


def day_label(d: date, today: date) -> str:
    """'today (Thu)', 'tomorrow (Fri)', 'next business day (Mon)', or 'Mon 28 Sep' — so the LLM never does date math."""
    wd = d.strftime("%a")
    if d == today:
        return f"today ({wd})"
    if d == today + timedelta(days=1):
        return f"tomorrow ({wd})"
    if d == next_business_day(today):
        return f"next business day ({wd})"
    return d.strftime("%a %d %b")


def end_of_business_day(dt: datetime) -> datetime:
    """23:59:59 of the business day a message counts as arriving on (weekend mail arrives Monday)."""
    d = dt.date()
    if not is_business_day(d):
        d = next_business_day(d)
    return datetime.combine(d, time(23, 59, 59), tzinfo=dt.tzinfo)


def overlap_minutes(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> int:
    """Minutes the two intervals share; touching edges (end == start) overlap by 0."""
    start = max(a_start, b_start)
    end = min(a_end, b_end)
    return max(0, int((end - start).total_seconds() // 60))


def block_windows(blocks: list[DeepWorkBlock], day: date, tzinfo) -> list[tuple[datetime, datetime]]:
    """The protected windows on `day` from the profile's deep-work blocks."""
    out: list[tuple[datetime, datetime]] = []
    name = WEEKDAY_NAMES[day.weekday()]
    for b in blocks:
        if name in b.days:
            hs, ms = (int(x) for x in b.start.split(":"))
            he, me = (int(x) for x in b.end.split(":"))
            out.append((datetime.combine(day, time(hs, ms), tzinfo=tzinfo), datetime.combine(day, time(he, me), tzinfo=tzinfo)))
    return out


def hours_since(t: datetime, as_of: datetime) -> float:
    return round((as_of - t).total_seconds() / 3600, 2)


def days_since(t: datetime, as_of: datetime) -> float:
    return round((as_of - t).total_seconds() / 86400, 2)


@dataclass
class CadenceStats:
    baseline_median_days: float | None
    recent_median_days: float | None
    current_gap_days: float
    ratio: float | None
    baseline_gaps: list[float] = field(default_factory=list)
    recent_gaps: list[float] = field(default_factory=list)
    recent_used_current_gap: bool = False


def cadence_stats(inbound: list[datetime], as_of: datetime, baseline: tuple[int, int] = (1, 20),
                  recent: tuple[int, int] = (21, 30), window_days: int = 30) -> CadenceStats | None:
    """OPEN_QUESTIONS #11: each gap belongs to the window of its later message (day 1 = as_of − 30d); if the recent
    window has no complete gap, the current gap (as_of − last inbound) stands in. None when fewer than 2 messages."""
    times = sorted(t for t in inbound if t <= as_of)
    if len(times) < 2:
        return None
    start = as_of - timedelta(days=window_days)

    def day_of(t: datetime) -> int:
        return int((t - start).total_seconds() // 86400) + 1

    base_gaps: list[float] = []
    recent_gaps: list[float] = []
    for prev, cur in zip(times, times[1:], strict=False):
        gap = (cur - prev).total_seconds() / 86400
        d = day_of(cur)
        if baseline[0] <= d <= baseline[1]:
            base_gaps.append(gap)
        elif recent[0] <= d <= recent[1]:
            recent_gaps.append(gap)
    current = (as_of - times[-1]).total_seconds() / 86400
    used_current = False
    if not recent_gaps:
        recent_gaps = [current]
        used_current = True
    bm = statistics.median(base_gaps) if base_gaps else None
    rm = statistics.median(recent_gaps)
    ratio = (rm / bm) if bm else None
    return CadenceStats(round(bm, 2) if bm is not None else None, round(rm, 2), round(current, 2),
                        round(ratio, 2) if ratio is not None else None, [round(g, 2) for g in base_gaps],
                        [round(g, 2) for g in recent_gaps], used_current)


def recruiter_window(times: list[datetime], as_of: datetime, count: int = 3, window_days: int = 7,
                     lookback_days: int = 7) -> tuple[datetime, datetime, int] | None:
    """≥count messages inside any window_days-long window that ends within the last lookback_days → (start, end, n)."""
    times = sorted(t for t in times if t <= as_of)
    best: tuple[datetime, datetime, int] | None = None
    for i, t in enumerate(times):
        end = t
        if end < as_of - timedelta(days=lookback_days):
            continue
        start = end - timedelta(days=window_days)
        n = sum(1 for u in times[: i + 1] if start <= u <= end)
        if n >= count and (best is None or n > best[2]):
            best = (start, end, n)
    return best


def due_bucket(due: datetime | None, as_of: datetime) -> str | None:
    """'overdue' if due < as_of, 'today' if due falls on as_of's date, else None."""
    if due is None:
        return None
    if due < as_of:
        return "overdue"
    if due.date() == as_of.date():
        return "today"
    return None


def days_overdue(due: datetime, as_of: datetime) -> int:
    return max(0, int((as_of - due).total_seconds() // 86400))


def cadence_days(cadence: str | None) -> int | None:
    c = (cadence or "").strip().lower()
    table = {"daily": 1, "weekly": 7, "biweekly": 14, "fortnightly": 14, "monthly": 30, "quarterly": 91, "annual": 365,
             "yearly": 365, "every week": 7, "every month": 30, "every quarter": 91}
    for k, v in table.items():
        if k in c:
            return v
    return None
