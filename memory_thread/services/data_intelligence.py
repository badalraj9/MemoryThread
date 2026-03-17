"""
Data Intelligence Service — Structured data parsing for Memory Thread.

Parses JSON and CSV data files into Galaxy Schema facts.

Supported formats:
  - JSON array ([{...}, {...}])
  - JSON object ({...} or nested)
  - JSONL (one JSON object per line)
  - CSV (with headers)
  - TSV (tab separated)

All extracted knowledge is stored as Galaxy Schema facts,
making data files queryable through MT's memory system.
"""

import json
import csv
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from collections import Counter, defaultdict
import sys

from memory_thread.utils.logger import get_logger

log = get_logger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class FieldProfile:
    """Profile of a single field/column."""

    name: str
    data_type: str
    null_count: int
    unique_count: int
    sample_values: List[str]
    min_value: Optional[str]
    max_value: Optional[str]


@dataclass
class DataRecord:
    """A single data record."""

    record_id: str
    content: dict
    classified_type: str
    confidence: float
    timestamp: Optional[str]


@dataclass
class DataAnalysis:
    """Complete analysis of a data file."""

    file_path: str
    file_name: str
    format: str
    total_records: int
    fields: List[FieldProfile] = field(default_factory=list)
    records: List[DataRecord] = field(default_factory=list)
    schema_summary: str = ""
    key_insights: List[str] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════════════
# DATA INTELLIGENCE SERVICE
# ═══════════════════════════════════════════════════════════════════════════════


class DataIntelligenceService:
    """
    Data file analysis → Galaxy Schema facts.

    Parses data files into structured knowledge that agents can query:
      - "What's the schema of transactions.json?"
      - "What are the key insights from this data?"
      - "Show high-value transactions"
      - "What type of records are these?"
    """

    MAX_FILE_SIZE = 10 * 1024 * 1024
    MAX_RECORDS = 1000

    TYPE_INDICATORS = {
        "decision": {
            "decision",
            "approved",
            "rejected",
            "action",
            "choice",
            "outcome",
            "result",
            "status",
        },
        "transaction": {
            "amount",
            "transaction_id",
            "payment",
            "price",
            "cost",
            "fee",
            "quantity",
            "order_id",
            "invoice",
        },
        "event": {
            "timestamp",
            "event_type",
            "occurred_at",
            "created_at",
            "updated_at",
            "date",
            "time",
            "happened_at",
        },
        "config": {
            "config",
            "setting",
            "enabled",
            "disabled",
            "threshold",
            "limit",
            "value",
            "option",
            "parameter",
        },
    }

    def analyze_file(self, path: str) -> Optional[DataAnalysis]:
        """Analyze a data file → DataAnalysis."""
        file_path = Path(path)
        if not file_path.exists():
            return None

        file_size = file_path.stat().st_size
        if file_size > self.MAX_FILE_SIZE:
            log.info(f"Large file ({file_size // 1024 // 1024}MB) — will limit records")

        ext = file_path.suffix.lower()

        analysis = DataAnalysis(
            file_path=str(file_path.resolve()),
            file_name=file_path.name,
            format=ext.lstrip("."),
            total_records=0,
        )

        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            log.error(f"Failed to read {path}: {e}")
            return None

        fmt = self._detect_format(content, ext)
        analysis.format = fmt

        if fmt in {"json", "jsonl"}:
            records = self._parse_json(content, fmt)
        elif fmt in {"csv", "tsv"}:
            records = self._parse_csv(path, fmt)
        else:
            log.warning(f"Unsupported format: {fmt}")
            return None

        analysis.total_records = len(records)

        if not records:
            return analysis

        analysis.fields = self._profile_fields(records)

        for i, record in enumerate(records[: self.MAX_RECORDS]):
            record_id = str(i + 1)
            classified_type, confidence = self._classify_record(record)
            timestamp = self._extract_timestamp(record)

            analysis.records.append(
                DataRecord(
                    record_id=record_id,
                    content=record,
                    classified_type=classified_type,
                    confidence=confidence,
                    timestamp=timestamp,
                )
            )

        analysis.schema_summary = self._generate_schema_summary(analysis.fields)
        analysis.key_insights = self._extract_insights(analysis.records, analysis.fields)

        return analysis

    # ═══════════════════════════════════════════════════════════════════════════════
    # FORMAT DETECTION
    # ═══════════════════════════════════════════════════════════════════════════════

    def _detect_format(self, content: str, ext: str) -> str:
        """Detect data format."""
        if ext == ".json":
            try:
                obj = json.loads(content.strip())
                if isinstance(obj, list):
                    return "json"
                elif isinstance(obj, dict):
                    return "json"
            except Exception:
                pass

        if ext == ".jsonl":
            return "jsonl"

        if ext in {".csv", ".tsv"}:
            return ext.lstrip(".")

        try:
            first_line = content.splitlines()[0] if content.splitlines() else ""
            if first_line.count(",") > first_line.count("\t"):
                return "csv"
            else:
                return "tsv"
        except Exception:
            pass

        return "json"

    # ═══════════════════════════════════════════════════════════════════════════════
    # PARSING
    # ═══════════════════════════════════════════════════════════════════════════════

    def _parse_json(self, content: str, fmt: str) -> List[dict]:
        """Parse JSON or JSONL content."""
        records = []

        if fmt == "json":
            try:
                data = json.loads(content.strip())
                if isinstance(data, list):
                    records = data
                elif isinstance(data, dict):
                    records = [data]
            except Exception as e:
                log.warning(f"JSON parse failed: {e}")
                return []

        elif fmt == "jsonl":
            for line in content.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    if isinstance(obj, dict):
                        records.append(obj)
                except Exception:
                    continue

        if isinstance(records, dict):
            records = [records]

        return records[: self.MAX_RECORDS]

    def _parse_csv(self, path: Path, fmt: str) -> List[dict]:
        """Parse CSV or TSV content."""
        records = []
        delimiter = "," if fmt == "csv" else "\t"

        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                reader = csv.DictReader(f, delimiter=delimiter)
                for row in reader:
                    records.append(dict(row))
        except Exception as e:
            log.warning(f"CSV parse failed: {e}")
            return []

        return records[: self.MAX_RECORDS]

    # ═══════════════════════════════════════════════════════════════════════════════
    # FIELD PROFILING
    # ═══════════════════════════════════════════════════════════════════════════════

    def _profile_fields(self, records: List[dict]) -> List[FieldProfile]:
        """Build field profiles from records."""
        if not records:
            return []

        field_names = set()
        for record in records:
            field_names.update(record.keys())

        profiles = []

        for field in field_names:
            values = [record.get(field) for record in records if field in record]
            non_null = [v for v in values if v is not None and v != ""]
            null_count = len(values) - len(non_null)

            unique_values = set(str(v) for v in non_null)
            unique_count = len(unique_values)

            sample_values = list(unique_values)[:5]

            data_type = self._infer_type(non_null)

            min_value = None
            max_value = None
            if data_type == "number":
                try:
                    numeric_values = [float(v) for v in non_null if v]
                    if numeric_values:
                        min_value = str(min(numeric_values))
                        max_value = str(max(numeric_values))
                except Exception:
                    pass

            profiles.append(
                FieldProfile(
                    name=field,
                    data_type=data_type,
                    null_count=null_count,
                    unique_count=unique_count,
                    sample_values=sample_values,
                    min_value=min_value,
                    max_value=max_value,
                )
            )

        profiles.sort(key=lambda p: p.name)
        return profiles

    def _infer_type(self, values: List[Any]) -> str:
        """Infer data type from values."""
        if not values:
            return "unknown"

        sample = values[:100]

        non_null = [v for v in sample if v is not None and v != ""]
        if not non_null:
            return "null"

        for v in non_null:
            if isinstance(v, bool):
                return "boolean"
            if isinstance(v, (int, float)):
                return "number"

        str_values = [str(v) for v in non_null]

        if all(v.lower() in {"true", "false", "yes", "no", "1", "0"} for v in str_values):
            return "boolean"

        try:
            for v in str_values:
                float(v)
            return "number"
        except Exception:
            pass

        date_patterns = [
            r"^\d{4}-\d{2}-\d{2}",
            r"^\d{2}/\d{2}/\d{4}",
            r"^\d{4}-\d{2}-\d{2}T",
        ]
        for v in str_values[:10]:
            for pattern in date_patterns:
                import re

                if re.match(pattern, v):
                    return "date"

        return "string"

    # ═══════════════════════════════════════════════════════════════════════════════
    # RECORD CLASSIFICATION
    # ═══════════════════════════════════════════════════════════════════════════════

    def _classify_record(self, record: dict) -> Tuple[str, float]:
        """Classify a record as decision/event/fact/transaction/config."""
        field_names = {k.lower() for k in record.keys()}
        field_values = {str(v).lower() for v in record.values()}

        scores = {}

        for record_type, indicators in self.TYPE_INDICATORS.items():
            score = 0
            for indicator in indicators:
                if indicator in field_names:
                    score += 2
                if indicator in field_values:
                    score += 1

            if score > 0:
                scores[record_type] = score

        if not scores:
            return "fact", 0.5

        best_type = max(scores, key=scores.get)
        confidence = min(scores[best_type] / 5.0, 1.0)

        return best_type, confidence

    def _extract_timestamp(self, record: dict) -> Optional[str]:
        """Extract timestamp from record."""
        ts_fields = {
            "timestamp",
            "created_at",
            "updated_at",
            "date",
            "time",
            "event_time",
            "occurred_at",
        }

        for field in record.keys():
            field_lower = field.lower()
            if field_lower in ts_fields:
                return str(record[field])

        return None

    # ═══════════════════════════════════════════════════════════════════════════════
    # INSIGHTS EXTRACTION
    # ═══════════════════════════════════════════════════════════════════════════════

    def _extract_insights(self, records: List[DataRecord], fields: List[FieldProfile]) -> List[str]:
        """Extract notable patterns worth storing as memories."""
        insights = []

        if not records or not fields:
            return insights

        type_counts = Counter(r.classified_type for r in records)
        if type_counts:
            total = sum(type_counts.values())
            type_dist = ", ".join(
                f"{t}({c / total * 100:.0f}%)" for t, c in type_counts.most_common(3)
            )
            insights.append(f"Type distribution: {type_dist}")

        for field in fields:
            if field.data_type == "number" and field.min_value and field.max_value:
                try:
                    min_val = float(field.min_value)
                    max_val = float(field.max_value)
                    if max_val - min_val > 0:
                        range_str = f"{field.name}: {field.min_value} - {field.max_value}"
                        if "amount" in field.name.lower() or "price" in field.name.lower():
                            range_str = f"{field.name}: ${field.min_value} - ${field.max_value}"
                        insights.append(f"Range: {range_str}")
                except Exception:
                    pass

            if field.null_count > 0 and field.null_count / len(records) > 0.3:
                pct = field.null_count / len(records) * 100
                insights.append(f"High nulls: {field.name} ({pct:.0f}% null)")

            if field.unique_count == len(records):
                insights.append(f"Unique field: {field.name} (all unique values)")

        if type_counts:
            top_type = type_counts.most_common(1)[0]
            if top_type[1] / len(records) > 0.8:
                insights.append(f"Predominant type: {top_type[0]} ({top_type[1]} records)")

        return insights[:10]

    # ═══════════════════════════════════════════════════════════════════════════════
    # SCHEMA SUMMARY
    # ═══════════════════════════════════════════════════════════════════════════════

    def _generate_schema_summary(self, fields: List[FieldProfile]) -> str:
        """Generate a schema summary string."""
        if not fields:
            return "No schema information"

        lines = []
        for f in fields:
            line = f.name
            line += f": {f.data_type}"

            if f.unique_count == 1:
                line += ", constant"
            elif f.unique_count > 100:
                line += f", {f.unique_count} unique"

            if f.null_count > 0:
                line += f", {f.null_count} nulls"

            if f.min_value and f.max_value:
                if f.data_type == "number":
                    line += f", range {f.min_value}-{f.max_value}"
                else:
                    line += f", {f.min_value[:20]}-{f.max_value[:20]}"

            lines.append(line)

        return "\n".join(lines)

    # ═══════════════════════════════════════════════════════════════════════════════
    # GALAXY SCHEMA CONVERSION
    # ═══════════════════════════════════════════════════════════════════════════════

    def to_galaxy_facts(self, analysis: DataAnalysis) -> List[Dict[str, str]]:
        """Convert DataAnalysis into Galaxy Schema facts."""
        facts = []
        fn = analysis.file_name

        type_counts = Counter(r.classified_type for r in analysis.records)
        type_str = ", ".join(f"{t} ({c})" for t, c in type_counts.most_common())

        field_names = [f.name for f in analysis.fields]

        summary_fact = (
            f"[DATA SUMMARY] {fn}\n"
            f"  Format: {analysis.format}\n"
            f"  Records: {analysis.total_records:,}\n"
            f"  Fields: {', '.join(field_names[:10])}\n"
            f"  Type distribution: {type_str or 'unknown'}"
        )
        if len(field_names) > 10:
            summary_fact += f"\n  ... and {len(field_names) - 10} more fields"
        facts.append(
            {"content": summary_fact, "type": "data_summary", "source": analysis.file_path}
        )

        if analysis.fields:
            schema_fact = f"[DATA SCHEMA] {fn}\n"
            for f in analysis.fields[:15]:
                schema_fact += f"  {f.name}: {f.data_type}"
                if f.unique_count == 1:
                    schema_fact += ", constant"
                elif f.unique_count > 10:
                    schema_fact += f", {f.unique_count} unique"
                if f.null_count > 0:
                    schema_fact += f", {f.null_count} nulls"
                if f.min_value and f.max_value:
                    schema_fact += f", range {f.min_value[:15]}-{f.max_value[:15]}"
                schema_fact += "\n"
            facts.append(
                {
                    "content": schema_fact.rstrip(),
                    "type": "data_schema",
                    "source": analysis.file_path,
                }
            )

        if analysis.key_insights:
            insight_fact = f"[DATA INSIGHT] {fn}\n"
            for insight in analysis.key_insights:
                insight_fact += f"  {insight}\n"
            facts.append(
                {
                    "content": insight_fact.rstrip(),
                    "type": "data_insight",
                    "source": analysis.file_path,
                }
            )

        high_value_records = [
            r for r in analysis.records if r.classified_type in {"transaction", "decision"}
        ]
        for r in high_value_records[:5]:
            content_preview = str(r.content)[:200]
            record_fact = (
                f"[DATA RECORD] {r.classified_type}:{r.record_id}\n"
                f"  Type: {r.classified_type} (confidence: {r.confidence:.2f})\n"
                f"  Content: {content_preview}"
            )
            facts.append(
                {"content": record_fact, "type": "data_record", "source": analysis.file_path}
            )

        return facts


data_intelligence = DataIntelligenceService()
