"""Job data models and parser type definitions for Job Hunter."""

from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Any, Callable


@dataclass
class Job:
    job_id: str  # stable global id for dedupe: "<ats>:<slug>:<id>"
    ats: str
    company: str
    title: str
    location: str
    url: str
    description: str
    posted_at: str | None = None
    salary: str | None = None
    # filled in later by the pipeline
    score: float | None = None
    reason: str | None = None
    draft: dict[str, Any] = field(default_factory=dict)

    @property
    def score_100(self) -> int:
        if self.score is None:
            return 0
        return round(max(0.0, min(10.0, float(self.score))) * 10)

    @property
    def queue_category(self) -> str:
        s = self.score_100
        if s >= 90:
            return "Exceptional"
        elif s >= 80:
            return "Strong Apply"
        elif s >= 70:
            return "Apply"
        elif s >= 60:
            return "Consider"
        else:
            return "Skip"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["score_100"] = self.score_100
        d["queue_category"] = self.queue_category
        return d


ParserFunc = Callable[[str, str, Any], list[Job]]
