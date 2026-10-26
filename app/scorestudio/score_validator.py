"""ScoreValidator（§9.3）：小節拍數狀態 + 匯出前問題報告（§15.3）。

狀態：valid | underfilled | overflow | unknown_duration | unresolved_omr
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MeasureCheck:
    measure: int
    measureId: str
    status: str
    expectedTicks: int
    usedTicks: int
    issues: list[dict] = field(default_factory=list)


@dataclass
class ValidationReport:
    ok: bool
    checks: list[MeasureCheck]
    exportWarnings: list[dict]   # §15.3 匯出前報告

    def summary(self) -> str:
        bad = [c for c in self.checks if c.status != "valid"]
        if not bad:
            return f"OK：{len(self.checks)} 小節全部拍數正確"
        parts = []
        for c in bad:
            parts.append(f"小節{c.measure}={c.status}")
        return "｜".join(parts[:6]) + (f"（+{len(bad)-6}）" if len(bad) > 6 else "")


def validate(doc) -> ValidationReport:
    """doc = ScoreDocument。逐小節算 used vs expected，並收錄 §15.3 五類問題。"""
    settings = doc.scoreSettings
    checks: list[MeasureCheck] = []
    export_warnings: list[dict] = []
    for part in doc.parts:
        for m in part.measures:
            expected = m.measure_ticks(settings)
            used = sum(e.durationTicks for e in m.events)
            issues: list[dict] = []
            unknown_dur = [e.id for e in m.events if e.durationStatus == "unknown"]
            unresolved = [e.id for e in m.events if e.type == "unknown"]
            low_conf = [e.id for e in m.events
                       if e.provenance.reviewStatus == "needs_review"]
            bad_chord = []
            for e in m.events:
                for c in e.chords:
                    if c.parsed is None and c.rawText:
                        bad_chord.append({"chord": c.rawText, "eventId": e.id})
            if unresolved or unknown_dur:
                status = "unresolved_omr"
            elif used > expected:
                status = "overflow"
            elif used < expected:
                status = "underfilled"
            else:
                status = "valid"
            if unknown_dur:
                issues.append({"kind": "unknown_duration", "ids": unknown_dur})
            if unresolved:
                issues.append({"kind": "unresolved_omr", "ids": unresolved})
            if low_conf:
                issues.append({"kind": "low_confidence", "ids": low_conf})
            checks.append(MeasureCheck(m.number, m.id, status, expected, used, issues))
            for e in m.events:
                if e.type == "unknown":
                    export_warnings.append({"kind": "unknown", "measure": m.number,
                                            "token": e.unknownText, "eventId": e.id})
                if e.durationStatus == "unknown":
                    export_warnings.append({"kind": "unknown_duration", "measure": m.number,
                                            "eventId": e.id})
            for c in bad_chord:
                export_warnings.append({"kind": "unparsed_chord", "measure": m.number,
                                        "rawText": c["chord"], "eventId": c["eventId"]})
            for i in m.events:
                for lr in i.lyrics:
                    if lr.provenance.reviewReason == "lyric_alignment":
                        export_warnings.append({"kind": "lyric_alignment",
                                                "measure": m.number, "eventId": i.id})
    ok = all(c.status == "valid" for c in checks)
    return ValidationReport(ok=ok, checks=checks, exportWarnings=export_warnings)
