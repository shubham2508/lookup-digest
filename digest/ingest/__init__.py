"""Ingest: parse the world's raw files as of a timestamp (architecture §3). Code only, no LLM."""
from .eml import RawMessage, parse_eml, parse_eml_bytes
from .ics import RawEvent, parse_ics_bytes
from .loader import VARIANTS, DataMissing, RawWorld, SourceStatus, load_world
from .notes import RawNote, parse_note, parse_note_text
from .tasks import parse_tasks, parse_tasks_text

__all__ = [
    "VARIANTS", "DataMissing", "RawEvent", "RawMessage", "RawNote", "RawWorld", "SourceStatus", "load_world",
    "parse_eml", "parse_eml_bytes", "parse_ics_bytes", "parse_note", "parse_note_text", "parse_tasks", "parse_tasks_text",
]
