"""Deduplication, corroboration, risk classification, and exact-version reviews."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Set, Tuple

from publishing import (
    PublishingError, Story, canonicalize_url, revision_fingerprint, utc_iso,
)

TOKEN_RX = re.compile(r"[\w\u0600-\u06ff]+", re.UNICODE)
CASUALTY_RX = re.compile(
    r"\b(?:kill(?:ed|ing|s)?|die[ds]?|dying|dead|death(?:s| toll)?|fatalit\w*|"
    r"slain|slay(?:s|ing)?|"
    r"casualt\w*|wound\w*|injur\w*|martyr\w*)\b|"
    r"شهيد|شهداء|استشهد|استشهاد|قتل|مقتل|قتلى|مصرع|جرحى|إصاب|"
    r"وفاة|وفيات|توفي|يتوفى|ضحايا|لقي حتفه|قضى نحبه", re.I)
ACCUSATION_RX = re.compile(
    r"\b(?:accus\w*|alleg\w*|corrupt\w*|brib\w*|embezzl\w*|fraud\w*|"
    r"war crime\w*|genocide|tortur\w*|abuse\w*)\b|"
    r"اتهام|يتهم|متهم|مزاعم|ادعاء|فساد|رشوة|اختلاس|احتيال|جريمة حرب|إبادة|تعذيب|انتهاك", re.I)
SECURITY_RX = re.compile(
    r"\b(?:army|military|soldier|commander|general|colonel|officer|security forces?|"
    r"intelligence|police|idf|shin bet|mossad|brigades?|armed wing)\b|"
    r"جيش|عسكري|جندي|قائد|لواء|عقيد|ضابط|قوات الأمن|أجهزة الأمن|مخابرات|شرطة|"
    r"جيش الاحتلال|الشاباك|الموساد|كتائب|الجناح المسلح", re.I)
BREAKING_RX = re.compile(
    r"\b(?:breaking|urgent|strike|airstrike|bomb|shell|raid|assassinat|"
    r"ceasefire|truce|explosion|evacuat)\w*\b|عاجل|غارة|قصف|اقتحام|اغتيال|"
    r"وقف إطلاق النار|هدنة|انفجار|إخلاء", re.I)
NAMED_SUBJECT_RX = re.compile(
    r"(?:\b[A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,}){1,3}\b|"
    r"(?:اللواء|العقيد|العميد|الرئيس|الوزير|القائد)\s+[\u0600-\u06ff]{3,}"
    r"(?:\s+[\u0600-\u06ff]{3,}){0,2})")
NEGATION_TOKENS = {
    "not", "no", "never", "denied", "denies", "deny", "false", "without",
    "لا", "لم", "لن", "ليس", "ليست", "ينفي", "نفت", "نفى", "دون", "غير",
}
NUMBER_RX = re.compile(r"\d+|[٠-٩]+")


def normalized_tokens(text: str) -> List[str]:
    return TOKEN_RX.findall((text or "").casefold())


def title_similarity(left: Story, right: Story) -> float:
    a, b = normalized_tokens(left.get("title", "")), normalized_tokens(right.get("title", ""))
    if not a or not b:
        return 0.0
    sequence = SequenceMatcher(None, " ".join(a), " ".join(b)).ratio()
    aset, bset = set(a), set(b)
    jaccard = len(aset & bset) / max(1, len(aset | bset))
    return max(sequence, jaccard)


def materially_conflicts(left: Story, right: Story) -> bool:
    """Keep contradictory or numerically different claims out of one cluster."""
    left_title = left.get("title", "")
    right_title = right.get("title", "")
    left_tokens = set(normalized_tokens(left_title))
    right_tokens = set(normalized_tokens(right_title))
    if bool(left_tokens & NEGATION_TOKENS) != bool(right_tokens & NEGATION_TOKENS):
        return True
    left_numbers = set(NUMBER_RX.findall(left_title))
    right_numbers = set(NUMBER_RX.findall(right_title))
    return bool(left_numbers and right_numbers and left_numbers != right_numbers)


def cluster_duplicates(items: Sequence[Story], threshold: float = 0.84
                       ) -> Tuple[List[Story], int]:
    """Cluster near-duplicates while retaining independent source provenance."""
    clusters: List[List[Story]] = []
    for item in sorted(items, key=lambda x: x["date"], reverse=True):
        url = canonicalize_url(item.get("link", ""))
        target = None
        for cluster in clusters:
            head = cluster[0]
            same_url = url and url == canonicalize_url(head.get("link", ""))
            close_time = abs((head["date"] - item["date"]).total_seconds()) <= 48 * 3600
            same_origin = bool(head.get("original")) == bool(item.get("original"))
            same_normalized_title = (
                normalized_tokens(head.get("title", ""))
                == normalized_tokens(item.get("title", "")))
            if same_origin and (same_url or (
                close_time
                and same_normalized_title
                and not materially_conflicts(head, item)
            )):
                target = cluster
                break
        if target is None:
            clusters.append([item])
        else:
            target.append(item)

    output: List[Story] = []
    removed = 0
    for cluster in clusters:
        # Prefer a record with a summary, then the newest deterministic source ID.
        cluster.sort(
            key=lambda x: (bool(x.get("dek")), x["date"], x.get("source_id", "")),
            reverse=True,
        )
        representative = cluster[0]
        seen: Set[Tuple[str, str]] = set()
        sources: List[Dict[str, str]] = []
        for item in cluster:
            key = (item.get("source", ""), item.get("source_url", ""))
            if key in seen:
                continue
            seen.add(key)
            sources.append({
                "name": key[0],
                "url": key[1],
                "article": item.get("link", ""),
                # Similar headlines are related reporting, not proof of corroboration.
                "verified": False,
            })
        representative["corroborating_sources"] = sources
        output.append(representative)
        removed += len(cluster) - 1
    output.sort(key=lambda x: x["date"], reverse=True)
    return output, removed


def classify_risk(story: Story) -> List[str]:
    hay = f"{story.get('title', '')}\n{story.get('dek', '')}\n{story.get('brief', '')}"
    reasons: List[str] = []
    if story.get("source_type") == "telegram":
        reasons.append("citizen_or_social_source")
    if story.get("original"):
        reasons.append("repository_original")
    if CASUALTY_RX.search(hay):
        reasons.append("casualty_claim")
    if ACCUSATION_RX.search(hay):
        reasons.append("accusation_or_serious_allegation")
    if SECURITY_RX.search(hay) and (
        NAMED_SUBJECT_RX.search(hay) or story.get("lang") == "ar"
    ):
        reasons.append("named_security_or_military_subject")
    independent = len({
        (source.get("name"), source.get("url"))
        for source in story.get("corroborating_sources", [])
        if source.get("name") and source.get("url") and source.get("verified") is True
    })
    if BREAKING_RX.search(hay) and independent < 2:
        reasons.append("low_corroboration_breaking_claim")
    # Preserve declaration order but never duplicate a reason.
    return list(dict.fromkeys(reasons))


def load_reviews(path: Path) -> Dict[str, Dict[str, Any]]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PublishingError(f"invalid review ledger: {exc}") from exc
    if raw.get("version") != 1 or not isinstance(raw.get("approvals"), dict):
        raise PublishingError("review ledger must have version 1 and approvals object")
    approvals = raw["approvals"]
    for fingerprint, approval in approvals.items():
        if not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
            raise PublishingError("review ledger contains an invalid fingerprint")
        if not isinstance(approval, dict) or not approval.get("reviewer") or not approval.get("at"):
            raise PublishingError(f"review {fingerprint[:12]} lacks reviewer/at")
        try:
            approved_at = datetime.fromisoformat(approval["at"].replace("Z", "+00:00"))
            if approved_at.tzinfo is None or approved_at.utcoffset() != timezone.utc.utcoffset(approved_at):
                raise ValueError("approval time is not UTC")
        except (TypeError, ValueError) as exc:
            raise PublishingError(
                f"review {fingerprint[:12]} has invalid timestamp") from exc
        if approval.get("expires"):
            try:
                expires = datetime.fromisoformat(
                    approval["expires"].replace("Z", "+00:00"))
                if expires.tzinfo is None or expires.utcoffset() != timezone.utc.utcoffset(expires):
                    raise ValueError("expiry is not UTC")
            except (TypeError, ValueError) as exc:
                raise PublishingError(
                    f"review {fingerprint[:12]} has invalid expiry") from exc
    return approvals


def apply_review_gate(stories: Sequence[Story], approvals: Dict[str, Dict[str, Any]]
                      ) -> Tuple[List[Story], List[Story]]:
    publishable, held = [], []
    now = datetime.now(timezone.utc)
    for story in stories:
        reasons = classify_risk(story)
        story["risk_reasons"] = reasons
        fingerprint = revision_fingerprint(story)
        story["review_fingerprint"] = fingerprint
        approval = approvals.get(fingerprint)
        approved = False
        if approval:
            expires = approval.get("expires")
            if not expires:
                approved = True
            else:
                try:
                    approved = datetime.fromisoformat(
                        expires.replace("Z", "+00:00")).astimezone(timezone.utc) > now
                except (TypeError, ValueError):
                    raise PublishingError(
                        f"review {fingerprint[:12]} has invalid expiry")
        story["review_approved"] = approved
        if reasons and not approved:
            held.append(story)
        else:
            publishable.append(story)
    return publishable, held


def sanitized_review_queue(held: Iterable[Story]) -> Dict[str, Any]:
    rows = [{
        "fingerprint": item["review_fingerprint"],
        "reasonCodes": item["risk_reasons"],
        "language": item["lang"],
    } for item in held]
    return {
        "schemaVersion": 1,
        "generatedAt": utc_iso(datetime.now(timezone.utc)),
        "count": len(rows),
        "items": rows,
    }
