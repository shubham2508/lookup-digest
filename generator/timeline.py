"""Relative days → PT datetimes for a given anchor (date of day 30). DST-correct via zoneinfo."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from email.utils import format_datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Los_Angeles")
UTC = ZoneInfo("UTC")


class Timeline:
    def __init__(self, anchor: date, days: int = 30):
        self.anchor = anchor
        self.days = days

    def date(self, day: int) -> date:
        return self.anchor - timedelta(days=self.days - day)

    def day_of(self, d: date) -> int:
        return self.days - (self.anchor - d).days

    def dt(self, day: int, hhmm: str, second: int = 0) -> datetime:
        h, m = (int(x) for x in hhmm.split(":"))
        return datetime.combine(self.date(day), time(h, m, second), tzinfo=TZ)

    def rfc2822(self, when: datetime) -> str:
        return format_datetime(when)

    @staticmethod
    def ics_utc(when: datetime) -> str:
        return when.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")

    @staticmethod
    def ics_local(when: datetime) -> str:
        return when.strftime("%Y%m%dT%H%M%S")

    def in_window(self, when: datetime, before_days: int = 0, after_days: int = 0) -> bool:
        lo = datetime.combine(self.date(1) - timedelta(days=before_days), time(0, 0), tzinfo=TZ)
        hi = datetime.combine(self.date(self.days) + timedelta(days=after_days), time(23, 59, 59), tzinfo=TZ)
        return lo <= when <= hi
