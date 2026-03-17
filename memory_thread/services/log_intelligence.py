"""
Log Intelligence Service — Structured log parsing for Memory Thread.

Parses structured and unstructured log files into Galaxy Schema facts.

Supported formats:
  - JSON logs (one JSON object per line)
  - Key=value logs (timestamp=... level=... message=...)
  - Plain text logs ([timestamp] LEVEL message)
  - CSV logs (headers on first line)

All extracted knowledge is stored as Galaxy Schema facts,
making log files queryable through MT's memory system.
"""

import re
import json
import csv
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from collections import Counter, defaultdict
from datetime import datetime
import sys

from memory_thread.utils.logger import get_logger

log = get_logger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class LogEvent:
    """A single log event/line."""

    timestamp: str
    level: str
    message: str
    source: str
    metadata: dict
    line_number: int


@dataclass
class LogPattern:
    """A recurring log message pattern."""

    pattern: str
    count: int
    first_seen: str
    last_seen: str
    severity: str


@dataclass
class LogAnalysis:
    """Complete analysis of a log file."""

    file_path: str
    file_name: str
    total_lines: int
    total_events: int
    error_count: int
    warning_count: int
    time_range_start: str
    time_range_end: str
    events: List[LogEvent] = field(default_factory=list)
    patterns: List[LogPattern] = field(default_factory=list)
    anomalies: List[str] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════════════
# LOG INTELLIGENCE SERVICE
# ═══════════════════════════════════════════════════════════════════════════════


class LogIntelligenceService:
    """
    Log file analysis → Galaxy Schema facts.

    Parses log files into structured knowledge that agents can query:
      - "What errors occurred in the last hour?"
      - "Which service has the most failures?"
      - "Show me error bursts"
      - "What patterns are recurring?"
    """

    MAX_LINES = 10000

    LEVELS = {"DEBUG", "INFO", "WARNING", "WARN", "ERROR", "CRITICAL", "FATAL", "TRACE"}

    def analyze_file(self, path: str) -> Optional[LogAnalysis]:
        """Analyze a log file → LogAnalysis."""
        file_path = Path(path)
        if not file_path.exists():
            return None

        analysis = LogAnalysis(
            file_path=str(file_path.resolve()),
            file_name=file_path.name,
            total_lines=0,
            total_events=0,
            error_count=0,
            warning_count=0,
            time_range_start="",
            time_range_end="",
        )

        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
        except Exception as e:
            log.error(f"Failed to read {path}: {e}")
            return None

        analysis.total_lines = len(lines)

        if analysis.total_lines > self.MAX_LINES:
            log.info(
                f"Large log file ({analysis.total_lines} lines) — analyzing first {self.MAX_LINES}"
            )
            lines = lines[: self.MAX_LINES]

        fmt = self._detect_format(lines)
        log.info(f"Detected log format: {fmt} for {file_path.name}")

        if fmt == "json":
            analysis.events = self._parse_json_logs(lines)
        elif fmt == "keyvalue":
            analysis.events = self._parse_keyvalue_logs(lines)
        elif fmt == "csv":
            analysis.events = self._parse_csv_logs(lines, file_path.name)
        else:
            analysis.events = self._parse_plaintext_logs(lines, file_path.name)

        analysis.total_events = len(analysis.events)
        analysis.error_count = sum(
            1 for e in analysis.events if e.level in {"ERROR", "CRITICAL", "FATAL"}
        )
        analysis.warning_count = sum(1 for e in analysis.events if e.level in {"WARNING", "WARN"})

        if analysis.events:
            analysis.time_range_start = analysis.events[0].timestamp
            analysis.time_range_end = analysis.events[-1].timestamp

        analysis.patterns = self._detect_patterns(analysis.events)
        analysis.anomalies = self._detect_anomalies(analysis.events, analysis.patterns)

        return analysis

    # ═══════════════════════════════════════════════════════════════════════════════
    # FORMAT DETECTION
    # ═══════════════════════════════════════════════════════════════════════════════

    def _detect_format(self, lines: List[str]) -> str:
        """Detect log format from first non-empty lines."""
        sample = [l.strip() for l in lines[:20] if l.strip()]

        if not sample:
            return "plaintext"

        json_count = 0
        keyvalue_count = 0
        csv_count = 0

        for line in sample:
            if not line:
                continue

            try:
                json.loads(line)
                json_count += 1
            except Exception:
                pass

            if "=" in line and not line.startswith("{"):
                parts = line.split()
                if sum(1 for p in parts if "=" in p) >= 2:
                    keyvalue_count += 1

            if "," in line and "=" not in line:
                csv_count += 1

        if json_count >= len(sample) * 0.5:
            return "json"
        if keyvalue_count >= len(sample) * 0.5:
            return "keyvalue"
        if csv_count >= len(sample) * 0.5:
            return "csv"

        return "plaintext"

    # ═══════════════════════════════════════════════════════════════════════════════
    # PARSING
    # ═══════════════════════════════════════════════════════════════════════════════

    def _parse_json_logs(self, lines: List[str]) -> List[LogEvent]:
        """Parse JSON-formatted logs (one object per line)."""
        events = []

        for i, line in enumerate(lines, 1):
            line = line.strip()
            if not line:
                continue

            try:
                obj = json.loads(line)
            except Exception:
                continue

            level = (obj.get("level") or obj.get("severity") or "INFO").upper()
            if level == "WARN":
                level = "WARNING"

            timestamp = ""
            for ts_field in ["timestamp", "time", "ts", "@timestamp", "datetime"]:
                if ts_field in obj:
                    timestamp = str(obj[ts_field])
                    break

            message = str(obj.get("message") or obj.get("msg") or obj.get("text") or "")

            source = str(
                obj.get("source")
                or obj.get("logger")
                or obj.get("service")
                or obj.get("component", "")
            )

            metadata = {
                k: v
                for k, v in obj.items()
                if k
                not in {
                    "message",
                    "msg",
                    "text",
                    "level",
                    "severity",
                    "timestamp",
                    "time",
                    "ts",
                    "datetime",
                    "source",
                    "logger",
                    "service",
                    "component",
                }
            }

            events.append(
                LogEvent(
                    timestamp=timestamp,
                    level=level,
                    message=message,
                    source=source,
                    metadata=metadata,
                    line_number=i,
                )
            )

        return events

    def _parse_keyvalue_logs(self, lines: List[str]) -> List[LogEvent]:
        """Parse key=value formatted logs."""
        events = []

        for i, line in enumerate(lines, 1):
            line = line.strip()
            if not line:
                continue

            parts = line.split()
            kv = {}
            for part in parts:
                if "=" in part:
                    key, _, value = part.partition("=")
                    kv[key.strip()] = value.strip()

            if not kv:
                continue

            level = (kv.get("level") or kv.get("severity") or "INFO").upper()
            if level == "WARN":
                level = "WARNING"

            timestamp = str(kv.get("timestamp") or kv.get("time") or kv.get("ts") or "")
            message = str(kv.get("message") or kv.get("msg") or kv.get("text") or line)
            source = str(
                kv.get("source") or kv.get("logger") or kv.get("service") or kv.get("component", "")
            )

            metadata = {
                k: v
                for k, v in kv.items()
                if k
                not in {
                    "message",
                    "msg",
                    "text",
                    "level",
                    "severity",
                    "timestamp",
                    "time",
                    "ts",
                    "datetime",
                    "source",
                    "logger",
                    "service",
                    "component",
                }
            }

            events.append(
                LogEvent(
                    timestamp=timestamp,
                    level=level,
                    message=message,
                    source=source,
                    metadata=metadata,
                    line_number=i,
                )
            )

        return events

    def _parse_plaintext_logs(self, lines: List[str], source: str) -> List[LogEvent]:
        """Parse plain text logs with various formats."""
        events = []

        timestamp_patterns = [
            r"^\[?(\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)\]?",
            r"^\[?(\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2})\]?",
            r"^\[?(\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\]?",
            r"^(\d{10,13})\s+",
        ]

        level_pattern = r"\b(DEBUG|INFO|WARN(?:ING)?|ERROR|CRITICAL|FATAL|TRACE)\b"

        for i, line in enumerate(lines, 1):
            line = line.strip()
            if not line:
                continue

            timestamp = ""
            for pattern in timestamp_patterns:
                match = re.search(pattern, line)
                if match:
                    timestamp = match.group(1)
                    break

            level_match = re.search(level_pattern, line, re.IGNORECASE)
            level = level_match.group(1).upper() if level_match else "INFO"
            if level == "WARN":
                level = "WARNING"

            message = line
            if timestamp:
                message = re.sub(timestamp_patterns[0], "", message)
                message = re.sub(timestamp_patterns[1], "", message)
                message = re.sub(timestamp_patterns[2], "", message)
                message = re.sub(timestamp_patterns[3], "", message)
            message = re.sub(level_pattern, "", message, flags=re.IGNORECASE)
            message = message.strip("[] -:").strip()

            if not message:
                message = line

            events.append(
                LogEvent(
                    timestamp=timestamp,
                    level=level,
                    message=message[:500],
                    source=source,
                    metadata={},
                    line_number=i,
                )
            )

        return events

    def _parse_csv_logs(self, lines: List[str], source: str) -> List[LogEvent]:
        """Parse CSV-formatted logs."""
        events = []

        if not lines:
            return events

        try:
            reader = csv.DictReader(lines)
            headers = reader.fieldnames or []
        except Exception:
            return self._parse_plaintext_logs(lines, source)

        for i, row in enumerate(reader, 2):
            level = "INFO"
            timestamp = ""
            message = ""
            metadata = {}

            for col in headers:
                col_lower = col.lower()
                value = row.get(col, "")

                if col_lower in {"level", "severity", "loglevel"}:
                    level = value.upper()
                    if level == "WARN":
                        level = "WARNING"
                elif col_lower in {"timestamp", "time", "ts", "datetime", "date"}:
                    timestamp = value
                elif col_lower in {"message", "msg", "text", "log"}:
                    message = value
                else:
                    metadata[col] = value

            if not message:
                message = str(row)

            events.append(
                LogEvent(
                    timestamp=timestamp,
                    level=level,
                    message=message,
                    source=source,
                    metadata=metadata,
                    line_number=i,
                )
            )

        return events

    # ═══════════════════════════════════════════════════════════════════════════════
    # PATTERN DETECTION
    # ═══════════════════════════════════════════════════════════════════════════════

    def _detect_patterns(self, events: List[LogEvent]) -> List[LogPattern]:
        """Group similar messages and count occurrences."""
        if not events:
            return []

        pattern_groups: Dict[str, List[LogEvent]] = defaultdict(list)

        for event in events:
            pattern = self._normalize_message(event.message)
            pattern_groups[pattern].append(event)

        patterns = []
        for pattern, evts in pattern_groups.items():
            if len(evts) < 2:
                continue

            severities = [e.level for e in evts]
            max_severity = "INFO"
            for s in severities:
                if s in {"CRITICAL", "FATAL"}:
                    max_severity = "CRITICAL"
                    break
                elif s == "ERROR" and max_severity != "CRITICAL":
                    max_severity = "ERROR"
                elif s == "WARNING" and max_severity not in {"ERROR", "CRITICAL"}:
                    max_severity = "WARNING"

            timestamps = [e.timestamp for e in evts if e.timestamp]
            first_seen = timestamps[0] if timestamps else ""
            last_seen = timestamps[-1] if timestamps else ""

            patterns.append(
                LogPattern(
                    pattern=pattern,
                    count=len(evts),
                    first_seen=first_seen,
                    last_seen=last_seen,
                    severity=max_severity,
                )
            )

        patterns.sort(key=lambda p: p.count, reverse=True)
        return patterns[:50]

    def _normalize_message(self, message: str) -> str:
        """Normalize message by replacing variable parts with placeholders."""
        message = re.sub(r"\d+\.\d+\.\d+\.\d+", "<IP>", message)
        message = re.sub(r"\b\d{10,13}\b", "<TIMESTAMP>", message)
        message = re.sub(
            r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", "<UUID>", message
        )
        message = re.sub(r"0x[0-9a-fA-F]+", "<HEX>", message)
        message = re.sub(r"\$[0-9,.]+", "<AMOUNT>", message)
        return message[:100]

    # ═══════════════════════════════════════════════════════════════════════════════
    # ANOMALY DETECTION
    # ═══════════════════════════════════════════════════════════════════════════════

    def _detect_anomalies(self, events: List[LogEvent], patterns: List[LogPattern]) -> List[str]:
        """Detect unusual patterns: error bursts, unusual sequences."""
        anomalies = []

        if not events:
            return anomalies

        error_events = [e for e in events if e.level in {"ERROR", "CRITICAL", "FATAL"}]
        warning_events = [e for e in events if e.level in {"WARNING", "WARN"}]

        if len(error_events) > 10:
            anomalies.append(f"Burst detected: {len(error_events)} errors in log file")

        for pattern in patterns:
            if pattern.count >= 5 and pattern.severity in {"ERROR", "CRITICAL", "FATAL"}:
                anomalies.append(
                    f"Recurring error: {pattern.pattern} ({pattern.count} occurrences)"
                )

        if len(warning_events) > len(error_events) * 3:
            anomalies.append(
                f"Unusual: {len(warning_events)} warnings vs {len(error_events)} errors"
            )

        return anomalies[:10]

    # ═══════════════════════════════════════════════════════════════════════════════
    # GALAXY SCHEMA CONVERSION
    # ═══════════════════════════════════════════════════════════════════════════════

    def to_galaxy_facts(self, analysis: LogAnalysis) -> List[Dict[str, str]]:
        """Convert LogAnalysis into Galaxy Schema facts."""
        facts = []
        fn = analysis.file_name

        sources = set(e.source for e in analysis.events if e.source)
        source_str = ", ".join(sorted(sources)) if sources else "unknown"

        summary_fact = (
            f"[LOG SUMMARY] {fn}\n"
            f"  Period: {analysis.time_range_start or 'unknown'} to {analysis.time_range_end or 'unknown'}\n"
            f"  Events: {analysis.total_events:,} total, {analysis.error_count} errors, {analysis.warning_count} warnings\n"
            f"  Sources: {source_str}"
        )
        facts.append({"content": summary_fact, "type": "log_summary", "source": analysis.file_path})

        if analysis.error_count > 0:
            error_fact = f"[LOG ERRORS] {fn}"
            error_events = [e for e in analysis.events if e.level in {"ERROR", "CRITICAL", "FATAL"}]

            error_messages: Dict[str, List[LogEvent]] = defaultdict(list)
            for e in error_events:
                pattern = self._normalize_message(e.message)
                error_messages[pattern].append(e)

            for pattern, evts in sorted(error_messages.items(), key=lambda x: -len(x[1]))[:10]:
                first_ts = evts[0].timestamp if evts[0].timestamp else "unknown"
                error_fact += (
                    f"\n  {evts[0].level}: {pattern} ({len(evts)} occurrences, first: {first_ts})"
                )

            facts.append(
                {"content": error_fact, "type": "log_errors", "source": analysis.file_path}
            )

        if analysis.anomalies:
            anomaly_fact = f"[LOG ANOMALY] {fn}"
            for anomaly in analysis.anomalies:
                anomaly_fact += f"\n  {anomaly}"
            facts.append(
                {"content": anomaly_fact, "type": "log_anomaly", "source": analysis.file_path}
            )

        if analysis.patterns:
            pattern_fact = f"[LOG PATTERN] {fn} — recurring events"
            for p in analysis.patterns[:10]:
                pattern_fact += f"\n  {p.severity}: {p.pattern} ({p.count}x)"
            facts.append(
                {"content": pattern_fact, "type": "log_pattern", "source": analysis.file_path}
            )

        return facts


log_intelligence = LogIntelligenceService()
