from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional

from flask import Flask, jsonify, render_template, request

app = Flask(__name__)


DATA_PATH = Path(__file__).parent / "data" / "meetings.json"


@dataclass
class MeetingRecord:
    id: str
    title: str
    date: datetime
    committee: str
    category: str
    speakers: List[str]
    summary: str
    body: str
    location: str
    keywords: List[str] = field(default_factory=list)

    @property
    def year(self) -> int:
        return self.date.year


class MeetingRepository:
    def __init__(self, dataset: Iterable[dict]):
        self.records: List[MeetingRecord] = [self._to_record(item) for item in dataset]

    @staticmethod
    def _to_record(item: dict) -> MeetingRecord:
        return MeetingRecord(
            id=item["id"],
            title=item["title"],
            date=datetime.strptime(item["date"], "%Y-%m-%d"),
            committee=item["committee"],
            category=item["category"],
            speakers=item.get("speakers", []),
            summary=item.get("summary", ""),
            body=item.get("body", ""),
            keywords=item.get("keywords", []),
            location=item.get("location", ""),
        )

    def search(
        self,
        query: Optional[str],
        committee: Optional[str] = None,
        category: Optional[str] = None,
        year: Optional[int] = None,
        speaker: Optional[str] = None,
    ) -> List[dict]:
        filtered = self.records

        if committee:
            filtered = [record for record in filtered if record.committee == committee]

        if category:
            filtered = [record for record in filtered if record.category == category]

        if year:
            filtered = [record for record in filtered if record.year == year]

        if speaker:
            filtered = [record for record in filtered if speaker in record.speakers]

        if query:
            filtered = self._match_query(filtered, query)

        return [self._to_view_model(record, query or "") for record in filtered]

    def _match_query(self, records: List[MeetingRecord], query: str) -> List[MeetingRecord]:
        keywords = [word for word in re.split(r"\s+", query) if word]
        cleaned = [re.escape(word.lower()) for word in keywords]

        scored = []
        for record in records:
            haystack = " ".join([record.title, record.summary, record.body]).lower()
            score = sum(len(re.findall(token, haystack)) for token in cleaned)
            if score > 0:
                scored.append((score, record))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [record for _, record in scored]

    @staticmethod
    def _highlight_snippet(text: str, query: str, length: int = 160) -> str:
        if not query:
            return text[:length]

        keywords = [word for word in re.split(r"\s+", query) if word]
        focus = keywords[0] if keywords else query

        pattern = re.compile(re.escape(focus), re.IGNORECASE)
        match = pattern.search(text)
        if not match:
            return text[:length]

        start = max(match.start() - 40, 0)
        end = min(match.end() + 80, len(text))
        snippet = text[start:end]
        return pattern.sub(lambda m: f"<mark>{m.group(0)}</mark>", snippet)

    def _to_view_model(self, record: MeetingRecord, query: str) -> dict:
        snippet_source = record.body or record.summary
        snippet = self._highlight_snippet(snippet_source, query)
        return {
            "id": record.id,
            "title": record.title,
            "date": record.date.strftime("%Y-%m-%d"),
            "committee": record.committee,
            "category": record.category,
            "speakers": record.speakers,
            "summary": record.summary,
            "snippet": snippet,
            "location": record.location,
        }


with open(DATA_PATH, "r", encoding="utf-8") as f:
    repository = MeetingRepository(json.load(f))


def parse_int(value: Optional[str]) -> Optional[int]:
    try:
        return int(value) if value else None
    except ValueError:
        return None


@app.route("/")
def index():
    committees = sorted({record.committee for record in repository.records})
    categories = sorted({record.category for record in repository.records})
    speakers = sorted({speaker for record in repository.records for speaker in record.speakers})
    years = sorted({record.year for record in repository.records}, reverse=True)

    query = request.args.get("q", "").strip()
    committee = request.args.get("committee") or None
    category = request.args.get("category") or None
    speaker = request.args.get("speaker") or None
    year = parse_int(request.args.get("year"))

    results = repository.search(query=query or None, committee=committee, category=category, year=year, speaker=speaker)

    return render_template(
        "index.html",
        results=results,
        query=query,
        committee=committee,
        category=category,
        speaker=speaker,
        year=year,
        committees=committees,
        categories=categories,
        speakers=speakers,
        years=years,
    )


@app.route("/api/search")
def api_search():
    query = request.args.get("q", "").strip()
    committee = request.args.get("committee") or None
    category = request.args.get("category") or None
    speaker = request.args.get("speaker") or None
    year = parse_int(request.args.get("year"))

    results = repository.search(query=query or None, committee=committee, category=category, year=year, speaker=speaker)
    return jsonify(results)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
