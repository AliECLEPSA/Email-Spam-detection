from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen
from urllib.parse import urlparse

import joblib
import pandas as pd
from sklearn.model_selection import train_test_split


ROOT = Path(__file__).resolve().parent
HTML_PATH = ROOT / "SpamShield_Gmail_App.html"
JS_PATH = ROOT / "spamshield_app.js"
PACKAGE_ROOT = ROOT.parent.parent
REPRO_ROOT = PACKAGE_ROOT / "05_Reproducibility"
if str(REPRO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPRO_ROOT))
DATA_PATH = PACKAGE_ROOT / "03_Datasets" / "base_datasets" / "email_dataset_30k.csv"
GENERATED_PREDICTIONS_PATH = (
    PACKAGE_ROOT / "03_Datasets" / "generated_datasets" / "synthetic_spam_stress_test_predictions.csv"
)
ARTIFACTS_DIR = ROOT / "artifacts"
SPAM_PIPELINE_PATH = ARTIFACTS_DIR / "spam_pipeline.joblib"
IMPORTANCE_PIPELINE_PATH = ARTIFACTS_DIR / "importance_pipeline.joblib"
METADATA_PATH = ARTIFACTS_DIR / "pipeline_metadata.json"

HOST = "127.0.0.1"
PORT = 8765
RANDOM_STATE = 42
DEFAULT_SPAM_THRESHOLD = 0.50
LMSTUDIO_BASE_URL = "http://127.0.0.1:1234/v1"
LMSTUDIO_TIMEOUT_SECONDS = 180
LMSTUDIO_MAX_RESPONSE_TOKENS = 260
LMSTUDIO_HISTORY_TURNS = 4
LMSTUDIO_HISTORY_CHARS = 220
LMSTUDIO_SUMMARY_CHARS = 170
LMSTUDIO_REASON_CHARS = 210
LMSTUDIO_BODY_CHARS = 1100
LMSTUDIO_EVENT_SOURCE_CHARS = 110
LMSTUDIO_MAX_EVENT_ITEMS = 4
LMSTUDIO_MAX_RELEVANT_EMAILS = 3
LMSTUDIO_MAX_PRIORITY_EMAILS = 3
FR_TO_EN_WEEKDAY = {
    "lundi": "monday",
    "mardi": "tuesday",
    "mercredi": "wednesday",
    "jeudi": "thursday",
    "vendredi": "friday",
    "samedi": "saturday",
    "dimanche": "sunday",
}
EN_TO_FR_WEEKDAY = {value: key for key, value in FR_TO_EN_WEEKDAY.items()}
STOPWORDS = {
    "le", "la", "les", "de", "des", "du", "un", "une", "et", "ou", "pour", "sur", "avec", "dans", "que", "qui",
    "je", "tu", "il", "elle", "nous", "vous", "ils", "elles", "mail", "email", "mails", "emails", "message",
    "messages", "quel", "quelle", "quels", "quelles", "j", "ai", "a", "est", "ce", "cet", "cette", "mes", "mon",
    "ma", "the", "and", "for", "with", "about", "what", "which", "mailbox", "current", "email", "this", "that",
}
EN_WEEKDAYS = tuple(EN_TO_FR_WEEKDAY.keys())
EVENT_STRONG_SIGNALS = (
    "meeting",
    "appointment",
    "calendar invite",
    "calendar invitation",
    "invite to join",
    "join the meeting",
    "join via",
    "microsoft teams",
    "teams session",
    "google meet",
    "zoom",
    "webex",
    "conference call",
    "session is confirmed",
    "confirmed for",
    "scheduled for",
    "reschedule",
    "interview",
    "workshop",
    "webinar",
    "town hall",
    "kickoff",
    "standup",
    "1:1",
)
EVENT_WEAK_SIGNALS = (
    "agenda",
    "review",
    "sprint review",
    "retro",
    "sync",
    "call",
    "reminder",
    "office hours",
)
EVENT_NEGATIVE_SIGNALS = (
    "invoice",
    "accounts payable",
    "payment",
    "parcel",
    "claim your reward",
    "billing",
    "renew now",
    "subscription expired",
    "winner",
)
ACTION_REQUIRED_SIGNALS = (
    "action required",
    "please review",
    "review needed",
    "please confirm",
    "confirm receipt",
    "follow-up",
    "follow up",
    "next steps",
    "respond by",
    "approval",
    "approve",
    "deadline",
    "due",
    "need your help",
    "required by",
    "please complete",
)
FINANCE_SIGNALS = (
    "invoice",
    "payment",
    "billing",
    "budget",
    "accounts payable",
    "statement",
    "expense",
    "purchase order",
    "contract",
    "remittance",
    "quote",
)
SHIPPING_SIGNALS = (
    "shipping",
    "shipment",
    "tracking",
    "delivery",
    "parcel",
    "package",
    "dispatch",
    "courier",
    "order status",
    "arriving",
)
NEWSLETTER_SIGNALS = (
    "newsletter",
    "digest",
    "product updates",
    "product update",
    "announcing",
    "launch",
    "release notes",
    "roundup",
    "weekly update",
    "new analytics",
    "unsubscribe",
)
SECURITY_SIGNALS = (
    "security alert",
    "security notice",
    "unusual login",
    "login detected",
    "password",
    "verify your",
    "verification",
    "mfa",
    "two-factor",
    "multi-factor",
    "access review",
    "suspicious",
)


def split_attachments(value: str) -> list[str]:
    if pd.isna(value) or str(value).strip() == "":
        return []
    return [item.strip() for item in str(value).split(";") if item.strip()]


def sender_name(address: str) -> str:
    if not address:
        return "Unknown Sender"
    local = address.split("@", 1)[0]
    local = re.sub(r"[_\-.]+", " ", local)
    local = re.sub(r"\d+", " ", local)
    words = [word.capitalize() for word in local.split() if word]
    return " ".join(words[:3]) or address


def preview_text(text: str, limit: int = 110) -> str:
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def safe_text(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value)


def titleize_identifier(value: str) -> str:
    return " ".join(part.capitalize() for part in str(value or "").replace("-", "_").split("_") if part)


def text_has_any(text: str, signals: tuple[str, ...]) -> bool:
    return any(signal in text for signal in signals)


def compact_text(text: str, limit: int) -> str:
    return preview_text(re.sub(r"<[^>]+>", " ", text or ""), limit)


def stable_unread(seed_text: str) -> bool:
    digest = hashlib.md5(seed_text.encode("utf-8")).hexdigest()
    return int(digest[:2], 16) % 100 < 42


def format_time_label(dt: datetime) -> str:
    return dt.strftime("%d %b %H:%M")


def count_auth_failures(row: pd.Series) -> int:
    return int(row["spf_result"] == "fail") + int(row["dkim_result"] == "fail") + int(row["dmarc_result"] == "fail")


def phishing_score(row: pd.Series) -> int:
    text = f"{row.get('subject', '')} {row.get('body_plain', '')}".lower()
    auth_fails = count_auth_failures(row)
    phish_keywords = [
        "verify",
        "password",
        "suspended",
        "login",
        "billing",
        "account",
        "restore access",
        "closure",
        "urgent",
        "immediately",
    ]
    keyword_hits = sum(keyword in text for keyword in phish_keywords)
    score = auth_fails + int(row.get("num_urls", 0) > 0) + int(row.get("contains_tracking_token", False)) + keyword_hits
    return score


def infer_threat_type(row: pd.Series, spam_probability: float) -> str:
    if spam_probability < DEFAULT_SPAM_THRESHOLD:
        return "legitimate"
    score = phishing_score(row)
    return "phishing" if score >= 4 else "spam"


def importance_rank(label: str, probability_map: dict[str, float]) -> int:
    confidence = probability_map.get(label, 0.0)
    if label == "low":
        return 1 if confidence >= 0.80 else 2
    if label == "medium":
        return 3
    return 5 if confidence >= 0.80 else 4


def importance_color(rank: int) -> str:
    return {
        1: "#9aa0a6",
        2: "#5f6368",
        3: "#1a73e8",
        4: "#e8710a",
        5: "#c5221f",
    }[rank]


def compute_severity(threat_type: str, spam_probability: float, row: pd.Series) -> float:
    base = {"legitimate": 1.0, "spam": 5.0, "phishing": 8.0}[threat_type]
    auth_fails = count_auth_failures(row)
    url_factor = min(float(row.get("num_urls", 0)) * 0.7, 1.5)
    track_factor = 0.7 if bool(row.get("contains_tracking_token", False)) else 0.0
    prob_factor = min(spam_probability * 1.5, 1.5)
    return round(min(10.0, base + auth_fails * 0.35 + url_factor + track_factor + prob_factor), 2)


def summarize_email(subject: str, body: str) -> str:
    subject = (subject or "").strip()
    body = (body or "").strip()
    if not body:
        return subject or "Empty email."
    sentences = re.split(r"(?<=[.!?])\s+|\n+", body)
    sentences = [sentence.strip() for sentence in sentences if sentence.strip()]
    picked = sentences[:2] if sentences else [body]
    summary = " ".join(picked)
    return preview_text(f"{subject}. {summary}" if subject else summary, limit=220)


def parse_event_date_token(token: str) -> tuple[str | None, str | None, str | None]:
    token = (token or "").strip()
    if not token:
        return None, None, None

    formats = ("%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%d-%m-%y")
    for fmt in formats:
        try:
            parsed = datetime.strptime(token, fmt)
            weekday_en = parsed.strftime("%A").lower()
            return parsed.date().isoformat(), weekday_en, EN_TO_FR_WEEKDAY.get(weekday_en)
        except ValueError:
            continue
    return None, None, None


def strip_subject_prefixes(subject: str) -> str:
    return re.sub(r"^(?:(?:re|fw|fwd)\s*:\s*)+", "", (subject or "").strip(), flags=re.IGNORECASE)


def detect_weekday_token(text: str) -> tuple[str | None, str | None]:
    lower = text.lower()
    for fr, en in FR_TO_EN_WEEKDAY.items():
        if re.search(rf"\b{re.escape(fr)}\b", lower):
            return en, fr
    for en in EN_WEEKDAYS:
        if re.search(rf"\b{re.escape(en)}\b", lower):
            return en, EN_TO_FR_WEEKDAY[en]
    return None, None


def extract_time_tokens(text: str) -> list[str]:
    seen: list[str] = []
    for pattern in (r"\b(?:[01]?\d|2[0-3]):[0-5]\d\b", r"\b\d{1,2}(?::\d{2})?\s?(?:am|pm)\b"):
        for token in re.findall(pattern, text, flags=re.IGNORECASE):
            normalized = token.upper().replace(" ", "")
            if normalized not in seen:
                seen.append(normalized)
    return seen


def has_calendar_attachment(attachments: list[str]) -> bool:
    for item in attachments:
        lower = item.lower()
        if lower.endswith(".ics") or "calendar" in lower or "invite" in lower:
            return True
    return False


def pick_event_source_sentence(subject: str, body: str) -> str:
    pieces = [strip_subject_prefixes(subject)]
    pieces.extend(re.split(r"(?<=[.!?])\s+|\n+", body or ""))
    candidates = [piece.strip() for piece in pieces if piece.strip()]

    def score(piece: str) -> tuple[int, int, int]:
        lower = piece.lower()
        strong = sum(signal in lower for signal in EVENT_STRONG_SIGNALS)
        weak = sum(signal in lower for signal in EVENT_WEAK_SIGNALS)
        when = int(bool(re.search(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", piece))) + int(bool(extract_time_tokens(piece)))
        return (strong, weak, when)

    ranked = sorted(candidates, key=score, reverse=True)
    return ranked[0] if ranked else strip_subject_prefixes(subject) or "Scheduled event"


def extract_events(subject: str, body: str, attachments: list[str] | None = None) -> list[dict[str, str]]:
    attachments = attachments or []
    text = f"{subject}\n{body}"
    lower = text.lower()
    strong_signal = any(keyword in lower for keyword in EVENT_STRONG_SIGNALS)
    weak_signal = any(keyword in lower for keyword in EVENT_WEAK_SIGNALS)
    negative_signal = any(keyword in lower for keyword in EVENT_NEGATIVE_SIGNALS)
    date_patterns = re.findall(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", text)
    time_patterns = extract_time_tokens(text)
    detected_weekday_en, detected_weekday_fr = detect_weekday_token(text)
    calendar_attachment = has_calendar_attachment(attachments)
    has_when_signal = bool(date_patterns or time_patterns or detected_weekday_en)

    if not ((strong_signal and (has_when_signal or calendar_attachment)) or (weak_signal and (date_patterns or calendar_attachment or (detected_weekday_en and time_patterns)))):
        return []
    if negative_signal and not (calendar_attachment or strong_signal):
        return []

    title = preview_text(strip_subject_prefixes(subject) or "Meeting / event", 90)
    when_bits = []
    if date_patterns:
        when_bits.append(date_patterns[0])
    if time_patterns:
        when_bits.append(time_patterns[0])
    if not when_bits and detected_weekday_fr:
        when_bits.append(detected_weekday_fr.capitalize())
    date_iso, parsed_weekday_en, parsed_weekday_fr = parse_event_date_token(date_patterns[0] if date_patterns else "")
    weekday_en = parsed_weekday_en or detected_weekday_en
    weekday_fr = parsed_weekday_fr or detected_weekday_fr
    source_sentence = pick_event_source_sentence(subject, body)
    if calendar_attachment and not when_bits:
        when_bits.append("Calendar invite attached")

    return [
        {
            "title": title,
            "when": " ".join(when_bits) if when_bits else "Date to confirm",
            "source": preview_text(source_sentence, 130),
            "date_iso": date_iso,
            "weekday_en": weekday_en,
            "weekday_fr": weekday_fr,
        }
    ]


def derive_folder_tags(
    row: pd.Series,
    subject: str,
    body: str,
    events: list[dict[str, str]],
    importance_rank_value: int | None,
    source_kind: str,
) -> list[str]:
    text = f"{subject}\n{body}".lower()
    tags: list[str] = []

    def add(tag: str) -> None:
        if tag not in tags:
            tags.append(tag)

    if source_kind == "generated_demo":
        add("generated")

    has_unsubscribe = bool(safe_text(row.get("list_unsubscribe")).strip())
    has_meeting_signal = bool(events) or text_has_any(text, EVENT_STRONG_SIGNALS + EVENT_WEAK_SIGNALS)
    has_finance_signal = text_has_any(text, FINANCE_SIGNALS)
    has_shipping_signal = text_has_any(text, SHIPPING_SIGNALS)
    has_newsletter_signal = has_unsubscribe or text_has_any(text, NEWSLETTER_SIGNALS)
    has_security_signal = text_has_any(text, SECURITY_SIGNALS)

    if has_meeting_signal:
        add("meetings")
    if has_finance_signal:
        add("finance")
    if has_shipping_signal:
        add("shipping")
    if has_newsletter_signal:
        add("newsletters")
    if has_security_signal:
        add("security")

    action_score = 0
    if text_has_any(text, ACTION_REQUIRED_SIGNALS):
        action_score += 2
    if importance_rank_value and importance_rank_value >= 4:
        action_score += 1
    if has_meeting_signal and any(event.get("date_iso") or event.get("when") for event in events):
        action_score += 1
    if (has_finance_signal or has_shipping_signal or has_security_signal) and text_has_any(
        text,
        ("please", "confirm", "review", "respond", "complete", "needed"),
    ):
        action_score += 1
    if action_score >= 2:
        add("action_required")

    return tags


def load_generated_demo_rows() -> pd.DataFrame:
    if not GENERATED_PREDICTIONS_PATH.exists():
        return pd.DataFrame()

    generated_df = pd.read_csv(GENERATED_PREDICTIONS_PATH)
    if generated_df.empty:
        return generated_df

    curated = (
        generated_df.sort_values(["family", "date"], ascending=[True, False])
        .groupby("family", group_keys=False)
        .head(3)
        .sort_values("date", ascending=False)
        .reset_index(drop=True)
    )
    return curated


def build_email_records(
    df: pd.DataFrame,
    spam_pipeline,
    importance_pipeline,
    *,
    source_kind: str,
    source_label: str,
    starting_id: int,
) -> tuple[list[dict], int]:
    if df.empty:
        return [], starting_id

    rows_df = df.reset_index(drop=True).copy()
    model_input = rows_df.drop(
        columns=[
            "label",
            "spam_probability",
            "pred_label",
            "predicted_bucket",
            "actual_bucket",
            "label_type",
        ],
        errors="ignore",
    ).copy()

    spam_probabilities = spam_pipeline.predict_proba(model_input)[:, 1]
    importance_predictions = importance_pipeline.predict(model_input)
    importance_proba = importance_pipeline.predict_proba(model_input)
    importance_classes = list(importance_pipeline.named_steps["classifier"].classes_)

    emails: list[dict] = []
    next_id = starting_id
    for idx, row in rows_df.iterrows():
        dt = datetime.fromisoformat(safe_text(row.get("date")))
        from_address = safe_text(row.get("from_address"))
        from_display = sender_name(from_address)
        subject = safe_text(row.get("subject")) or "(No subject)"
        body = safe_text(row.get("body_plain")) or safe_text(row.get("raw_text"))
        summary = summarize_email(subject, body)
        spam_probability = float(spam_probabilities[idx])
        threat_type = infer_threat_type(row, spam_probability)
        phish_score = phishing_score(row)
        attachments = split_attachments(row.get("attachment_types"))
        importance_label = None
        importance_rank_value = None
        importance_probability_map = None
        if threat_type == "legitimate":
            predicted_label = str(importance_predictions[idx])
            probability_map = {
                label: float(prob)
                for label, prob in zip(importance_classes, importance_proba[idx])
            }
            importance_label = predicted_label
            importance_probability_map = probability_map
            importance_rank_value = importance_rank(predicted_label, probability_map)

        events = extract_events(subject, body, attachments=attachments)
        severity = compute_severity(threat_type, spam_probability, row)
        reasoning = local_reasoning(threat_type, spam_probability, importance_label, importance_rank_value, row)
        folder_tags = derive_folder_tags(row, subject, body, events, importance_rank_value, source_kind)
        family_identifier = safe_text(row.get("family"))

        email_record = {
            "id": int(next_id),
            "message_id": safe_text(row.get("message_id")),
            "from": from_display,
            "from_addr": from_address,
            "from_domain": safe_text(row.get("from_domain")),
            "subject": subject,
            "snippet": preview_text(body, 120),
            "summary": summary,
            "body": body,
            "time": format_time_label(dt),
            "date_iso": safe_text(row.get("date")),
            "hour": int(row.get("hour_of_day", 0) or 0),
            "spf": safe_text(row.get("spf_result")),
            "dkim": safe_text(row.get("dkim_result")),
            "dmarc": safe_text(row.get("dmarc_result")),
            "attachments": attachments,
            "has_attachments": bool(row.get("has_attachments")),
            "has_html": bool(row.get("has_html")),
            "urls": int(row.get("num_urls", 0) or 0),
            "tracking_token": bool(row.get("contains_tracking_token")),
            "language": safe_text(row.get("language")) or "en",
            "user_agent": safe_text(row.get("user_agent")),
            "reply_to": safe_text(row.get("reply_to")),
            "in_reply_to": safe_text(row.get("in_reply_to")),
            "unread": stable_unread(safe_text(row.get("message_id")) or f"{source_kind}-{next_id}"),
            "spam_probability": round(spam_probability, 4),
            "default_is_spam": spam_probability >= DEFAULT_SPAM_THRESHOLD,
            "threat_type": threat_type,
            "phishing_score": phish_score,
            "severity_score": severity,
            "importance_label": importance_label,
            "importance_rank": importance_rank_value,
            "importance_color": importance_color(importance_rank_value) if importance_rank_value else None,
            "importance_probabilities": importance_probability_map,
            "events": events,
            "classification_reason": reasoning["classification_reason"],
            "importance_reason": reasoning["importance_reason"],
            "source_kind": source_kind,
            "source_label": source_label,
            "is_generated": source_kind == "generated_demo",
            "folder_tags": folder_tags,
            "generated_family": family_identifier,
            "generated_family_label": titleize_identifier(family_identifier) if family_identifier else "",
            "generated_difficulty": safe_text(row.get("difficulty")),
            "generated_description": safe_text(row.get("description")),
        }
        emails.append(email_record)
        next_id += 1

    return emails, next_id


def extract_query_keywords(question: str) -> list[str]:
    words = re.findall(r"[a-zA-ZÀ-ÿ0-9]{3,}", question.lower())
    return [word for word in words if word not in STOPWORDS]


def detect_requested_weekday(question: str) -> tuple[str | None, str | None]:
    lower = question.lower()
    for fr, en in FR_TO_EN_WEEKDAY.items():
        if fr in lower:
            return en, fr
    for en, fr in EN_TO_FR_WEEKDAY.items():
        if en in lower:
            return en, fr
    return None, None


def score_email_for_query(email: dict, question: str, keywords: list[str], requested_weekday_en: str | None) -> float:
    text = " ".join(
        [
            email.get("subject", ""),
            email.get("summary", ""),
            email.get("body", ""),
            email.get("from", ""),
            email.get("classification_reason", ""),
        ]
    ).lower()

    score = 0.0
    if requested_weekday_en and any(event.get("weekday_en") == requested_weekday_en for event in email.get("events", [])):
        score += 8.0
    if "important" in question.lower() or "priorit" in question.lower() or "important" in question.lower():
        score += (email.get("importance_rank") or 0) * 1.4
    if "event" in question.lower() or "rendez" in question.lower() or "meeting" in question.lower():
        score += 3.0 if email.get("events") else 0.0
    for keyword in keywords:
        if keyword in text:
            score += 1.2
    return score


def build_context_bundle(question: str, current_email: dict | None) -> dict:
    keywords = extract_query_keywords(question)
    weekday_en, weekday_fr = detect_requested_weekday(question)
    lower = question.lower()
    event_question = any(token in lower for token in ["event", "meeting", "calendar", "agenda", "rendez", "vendredi", "lundi", "mardi", "mercredi", "jeudi", "samedi", "dimanche"])

    legitimate_emails = [email for email in EMAILS if email["threat_type"] == "legitimate"]
    scored = []
    for email in legitimate_emails:
        score = score_email_for_query(email, question, keywords, weekday_en)
        if current_email and email["id"] == current_email["id"]:
            score += 1.0
        if score > 0:
            scored.append((score, email))
    scored.sort(key=lambda item: (item[0], item[1].get("importance_rank") or 0, item[1]["spam_probability"]), reverse=True)

    relevant_emails = [email for _, email in scored[:8]]
    if not relevant_emails and current_email is not None:
        relevant_emails = [current_email]

    relevant_events = []
    for email in legitimate_emails:
        for event in email.get("events", []):
            event_score = 0.0
            if weekday_en and event.get("weekday_en") == weekday_en:
                event_score += 8.0
            if any(keyword in f"{event.get('title','')} {event.get('source','')}".lower() for keyword in keywords):
                event_score += 2.0
            if email.get("importance_rank"):
                event_score += min(email["importance_rank"] * 0.5, 2.5)
            if event_question and email.get("events"):
                event_score += 1.0
            if event_score > 0:
                relevant_events.append(
                    {
                        "score": event_score,
                        "email_id": email["id"],
                        "subject": email["subject"],
                        "from": email["from"],
                        "importance_rank": email.get("importance_rank"),
                        "event": event,
                    }
                )
    relevant_events.sort(key=lambda item: (item["score"], item.get("importance_rank") or 0), reverse=True)
    relevant_events = relevant_events[:10]

    top_priority = sorted(
        legitimate_emails,
        key=lambda email: ((email.get("importance_rank") or 0), 1 if email.get("events") else 0, -email["spam_probability"]),
        reverse=True,
    )[:8]

    return {
        "question_keywords": keywords,
        "requested_weekday_en": weekday_en,
        "requested_weekday_fr": weekday_fr,
        "is_event_question": event_question,
        "current_email": current_email,
        "relevant_emails": relevant_emails,
        "relevant_events": relevant_events,
        "top_priority_emails": top_priority,
        "mailbox_stats": {
            "total": STATS["total_emails"],
            "generated_demo": STATS["generated_email_count"],
            "legitimate": STATS["legitimate_count"],
            "spam": STATS["spam_count"],
            "phishing": STATS["phishing_count"],
            "high_priority": STATS["high_priority_count"],
            "events": STATS["event_count"],
        },
    }


def detect_question_intent(question: str) -> dict[str, bool]:
    lower = question.lower()
    return {
        "summary": any(token in lower for token in ["summary", "summar", "résum", "resume", "contenu", "what is this about"]),
        "classification": any(token in lower for token in [
            "spam", "phish", "safe", "legit", "pourquoi", "why", "explain", "threat",
            "probab", "probabilité", "probability", "signal", "signals", "raison", "reason",
            "spf", "dkim", "dmarc", "auth", "analy", "analyse", "analyze", "review", "check",
        ]),
        "event": any(token in lower for token in ["event", "meeting", "calendar", "agenda", "rendez", "friday", "monday", "tuesday", "wednesday", "thursday", "saturday", "sunday", "vendredi", "lundi", "mardi", "mercredi", "jeudi", "samedi", "dimanche"]),
        "importance": any(token in lower for token in ["important", "importance", "priority", "priorité", "priorite"]),
        "stats": any(token in lower for token in ["stat", "count", "combien", "how many", "numbers"]),
    }


def is_general_conversation(question: str) -> bool:
    lower = question.lower().strip()
    patterns = [
        r"\b(hey|hi|hello|salut|coucou)\b",
        r"\bhow are you\b",
        r"\band you\b",
        r"\band u\b",
        r"\bcomment vas[- ]?tu\b",
        r"\bça va\b",
        r"\bca va\b",
        r"\bet toi\b",
        r"\bwho are you\b",
        r"\bqui es[- ]?tu\b",
        r"\bthank(s| you)?\b",
        r"\bmerci\b",
        r"\btu peux m'aider\b",
        r"\bcan you help\b",
    ]
    return any(re.search(pattern, lower) for pattern in patterns)


def references_mailbox_or_current_email(question: str) -> bool:
    lower = question.lower()
    hints = [
        "mail",
        "email",
        "message",
        "this email",
        "current email",
        "current mail",
        "ce mail",
        "cet email",
        "mail courant",
        "message courant",
        "email courant",
        "inbox",
        "boîte",
        "boite",
        "spam",
        "calendar",
        "agenda",
        "meeting",
        "event",
        "priority",
        "importance",
    ]
    return any(hint in lower for hint in hints)


def should_include_history(question: str) -> bool:
    lower = question.lower().strip()
    tokens = re.findall(r"[a-zA-ZÀ-ÿ0-9]{1,}", lower)
    follow_up_starters = (
        "and ",
        "et ",
        "what about",
        "qu'en",
        "sinon",
        "then ",
        "also ",
    )
    vague_follow_ups = {
        "why",
        "why?",
        "pourquoi",
        "pourquoi?",
        "friday",
        "friday?",
        "vendredi",
        "vendredi?",
        "this one",
        "ce mail",
        "celui-ci",
    }
    return len(tokens) <= 4 or lower in vague_follow_ups or any(lower.startswith(prefix) for prefix in follow_up_starters)


def compact_email_view(
    email: dict,
    *,
    include_body: bool = False,
    include_reasons: bool = False,
    include_events: bool = False,
) -> dict:
    payload = {
        "id": email["id"],
        "subject": compact_text(email["subject"], 100),
        "from": email["from"],
        "time": email["time"],
        "summary": compact_text(email["summary"], LMSTUDIO_SUMMARY_CHARS),
        "threat_type": email["threat_type"],
        "spam_probability": email["spam_probability"],
        "importance_label": email.get("importance_label"),
        "importance_rank": email.get("importance_rank"),
    }
    if include_events and email.get("events"):
        payload["events"] = [
            {
                "title": compact_text(event.get("title", ""), 90),
                "when": compact_text(event.get("when", ""), 40),
                "date": event.get("date_iso"),
                "weekday": event.get("weekday_fr") or event.get("weekday_en"),
            }
            for event in email.get("events", [])[:2]
        ]
    if include_reasons:
        payload["classification_reason"] = compact_text(email.get("classification_reason", ""), LMSTUDIO_REASON_CHARS)
        payload["importance_reason"] = compact_text(email.get("importance_reason", ""), LMSTUDIO_REASON_CHARS)
    if include_body:
        payload["body"] = compact_text(email.get("body", ""), LMSTUDIO_BODY_CHARS)
    return payload


def compact_event_view(item: dict) -> dict:
    event = item.get("event", item)
    payload = {
        "title": compact_text(event.get("title", ""), 90),
        "when": compact_text(event.get("when", ""), 40),
        "date": event.get("date_iso"),
        "weekday": event.get("weekday_fr") or event.get("weekday_en"),
        "source": compact_text(event.get("source", ""), LMSTUDIO_EVENT_SOURCE_CHARS),
    }
    if "email_id" in item:
        payload["email_id"] = item.get("email_id")
        payload["from"] = item.get("from")
        payload["subject"] = compact_text(item.get("subject", ""), 100)
        payload["importance_rank"] = item.get("importance_rank")
    return payload


def format_event_for_prompt(item: dict) -> str:
    payload = compact_event_view(item)
    bits = []
    if payload.get("date"):
        bits.append(payload["date"])
    elif payload.get("weekday"):
        bits.append(payload["weekday"])
    time_tokens = extract_time_tokens(payload.get("when", ""))
    if time_tokens:
        bits.append(time_tokens[0])
    elif payload.get("when") and payload.get("when") not in {payload.get("date"), payload.get("weekday")}:
        bits.append(payload["when"])
    bits.append(payload["title"])
    if payload.get("from"):
        bits.append(f"from {payload['from']}")
    if payload.get("importance_rank"):
        bits.append(f"importance {payload['importance_rank']}/5")
    return "- " + " | ".join(str(bit) for bit in bits if bit)


def format_email_for_prompt(
    email: dict,
    *,
    include_body: bool = False,
    include_reasons: bool = False,
    include_events: bool = False,
) -> str:
    payload = compact_email_view(
        email,
        include_body=include_body,
        include_reasons=include_reasons,
        include_events=include_events,
    )
    lines = [
        f"id: {payload['id']}",
        f"from: {payload['from']}",
        f"subject: {payload['subject']}",
        f"time: {payload['time']}",
        f"summary: {payload['summary']}",
        f"threat: {payload['threat_type']} (spam_prob={payload['spam_probability']})",
    ]
    if payload.get("importance_rank"):
        lines.append(f"importance: {payload.get('importance_label')} ({payload['importance_rank']}/5)")
    if include_events and payload.get("events"):
        event_text = "; ".join(
            f"{event.get('title')} | {event.get('when')}"
            for event in payload.get("events", [])
        )
        lines.append(f"events: {event_text}")
    if include_reasons and payload.get("classification_reason"):
        lines.append(f"classification_reason: {payload['classification_reason']}")
    if include_reasons and payload.get("importance_reason"):
        lines.append(f"importance_reason: {payload['importance_reason']}")
    if include_body and payload.get("body"):
        lines.append(f"body: {payload['body']}")
    return "\n".join(lines)


def normalize_history(history: list[dict] | None) -> list[dict]:
    cleaned = []
    for item in history or []:
        role = item.get("role")
        content = compact_text((item.get("content") or "").strip(), LMSTUDIO_HISTORY_CHARS)
        if role in {"user", "assistant"} and content:
            cleaned.append({"role": role, "content": content})
    return cleaned[-LMSTUDIO_HISTORY_TURNS:]


def build_lmstudio_messages(question: str, email_record: dict | None, history: list[dict] | None = None) -> list[dict]:
    context = build_context_bundle(question, email_record)
    intent = detect_question_intent(question)
    attach_mailbox_context = (
        any(intent.values())
        or references_mailbox_or_current_email(question)
        or (email_record is not None and should_include_history(question) and not is_general_conversation(question))
    )

    if not attach_mailbox_context:
        system_prompt = (
            "You are SpamShield AI. Reply in natural English. "
            "Keep replies concise, usually 1 to 3 short sentences. "
            "No long preambles, no numbered menus unless the user asks for options. "
            "You can chat normally and answer general questions."
        )
        messages = [{"role": "system", "content": system_prompt}]
        if should_include_history(question) and not is_general_conversation(question):
            messages.extend(normalize_history(history))
        messages.append({"role": "user", "content": question})
        return messages

    include_current_email = email_record is not None and (
        intent["summary"] or intent["classification"] or (not intent["event"] and not intent["importance"])
    )
    if intent["event"] and email_record is not None and email_record.get("events"):
        include_current_email = True

    sections = [
        f"QUESTION: {question}",
        f"NOW: {datetime.now().isoformat(timespec='seconds')}",
    ]

    requested_day = context["requested_weekday_fr"] or context["requested_weekday_en"]
    if requested_day:
        sections.append(f"REQUESTED_DAY: {requested_day}")

    if intent["stats"]:
        sections.append(
            "MAILBOX_STATS:\n"
            + "\n".join(f"- {key}: {value}" for key, value in context["mailbox_stats"].items())
        )

    if include_current_email and email_record is not None:
        sections.append(
            "CURRENT_EMAIL:\n"
            + format_email_for_prompt(
                email_record,
                include_body=intent["summary"],
                include_reasons=intent["classification"],
                include_events=bool(email_record.get("events")),
            )
        )

    if intent["event"]:
        event_lines = [
            format_event_for_prompt(item)
            for item in context["relevant_events"][:LMSTUDIO_MAX_EVENT_ITEMS]
        ]
        if event_lines:
            sections.append("RELEVANT_EVENTS:\n" + "\n".join(event_lines))
        else:
            sections.append("RELEVANT_EVENTS: []")

    if intent["importance"]:
        priority_lines = [
            format_email_for_prompt(email, include_events=True)
            for email in context["top_priority_emails"][:LMSTUDIO_MAX_PRIORITY_EMAILS]
        ]
        if priority_lines:
            sections.append("TOP_PRIORITY_EMAILS:\n" + "\n\n".join(priority_lines))
    elif not intent["summary"] and not intent["classification"] and not intent["event"]:
        relevant_lines = [
            format_email_for_prompt(email, include_events=intent["event"])
            for email in context["relevant_emails"][:LMSTUDIO_MAX_RELEVANT_EMAILS]
        ]
        if relevant_lines:
            sections.append("RELEVANT_EMAILS:\n" + "\n\n".join(relevant_lines))

    system_prompt = (
        "You are SpamShield AI inside an email app. Reply in natural English. "
        "Be concise: usually 1 to 3 short sentences, or very short bullets when listing events. "
        "Answer directly and do not produce long menus or generic support scripts. "
        "If a current email is provided and the user asks to analyze, check, or help with the email, assume they mean that selected email. "
        "For email, spam, priority, or calendar questions, use the mailbox context below. "
        "Never invent mailbox facts, dates, senders, or events. If mailbox information is missing, say so plainly."
    )

    messages = [{"role": "system", "content": system_prompt}]
    if should_include_history(question):
        messages.extend(normalize_history(history))
    messages.append({"role": "user", "content": "\n".join(sections)})
    return messages


def local_reasoning(threat_type: str, spam_probability: float, importance_label: str | None, importance_rank_value: int | None, row: pd.Series) -> dict[str, str]:
    auth = f"SPF={row['spf_result']}, DKIM={row['dkim_result']}, DMARC={row['dmarc_result']}"
    if threat_type == "legitimate":
        reason = (
            f"Classified as legitimate because the spam probability is low ({spam_probability:.3f}), "
            f"the authentication signals look healthy ({auth}), and the content matches a normal email."
        )
    elif threat_type == "spam":
        reason = (
            f"Classified as spam because the spam probability is high ({spam_probability:.3f}), "
            f"with {row['num_urls']} URL(s), mixed authentication signals ({auth}), and suspicious promotional wording."
        )
    else:
        reason = (
            f"Classified as phishing because the spam probability is high ({spam_probability:.3f}) and the impersonation signals are strong "
            f"({auth}, urgent wording, links, or verification requests)."
        )

    if importance_label is None:
        priority = "No importance score is assigned because the email is treated as unwanted."
    else:
        priority = (
            f"Estimated importance: {importance_label.upper()} (rank {importance_rank_value}/5). "
            f"This score comes from the content, attachments, reply-thread cues, and professional context."
        )

    return {
        "classification_reason": reason,
        "importance_reason": priority,
    }


def lmstudio_available() -> tuple[bool, str | None]:
    try:
        with urlopen(f"{LMSTUDIO_BASE_URL}/models", timeout=1.5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        data = payload.get("data", [])
        if not data:
            return False, None
        return True, data[0]["id"]
    except Exception:
        return False, None


def call_lmstudio(question: str, email_record: dict | None, history: list[dict] | None = None) -> str:
    available, model_id = lmstudio_available()
    if not available or model_id is None:
        return (
            "LM Studio is not connected yet. Start the LM Studio server with a loaded model and this panel will use Gemma automatically."
        )
    messages = build_lmstudio_messages(question, email_record, history)

    payload = {
        "model": model_id,
        "temperature": 0.1,
        "top_p": 0.8,
        "max_tokens": LMSTUDIO_MAX_RESPONSE_TOKENS,
        "messages": messages,
    }

    request = Request(
        f"{LMSTUDIO_BASE_URL}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=LMSTUDIO_TIMEOUT_SECONDS) as response:
            result = json.loads(response.read().decode("utf-8"))
        return result["choices"][0]["message"]["content"].strip()
    except URLError:
        return "LM Studio is detected but the request failed. Check that the model is loaded and the local server is running."
    except Exception as exc:
        return f"LM Studio returned an error: {exc}"


def stream_lmstudio(question: str, email_record: dict | None, history: list[dict] | None = None):
    available, model_id = lmstudio_available()
    if not available or model_id is None:
        yield {
            "error": (
                "LM Studio is not connected yet. Start the LM Studio server with a loaded model and this panel will use Gemma automatically."
            )
        }
        return

    messages = build_lmstudio_messages(question, email_record, history)
    payload = {
        "model": model_id,
        "temperature": 0.1,
        "top_p": 0.8,
        "max_tokens": LMSTUDIO_MAX_RESPONSE_TOKENS,
        "stream": True,
        "messages": messages,
    }

    request = Request(
        f"{LMSTUDIO_BASE_URL}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=LMSTUDIO_TIMEOUT_SECONDS) as response:
            for raw_line in response:
                line = raw_line.decode("utf-8", errors="ignore").strip()
                if not line or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    yield {"done": True}
                    return
                try:
                    payload = json.loads(data)
                except json.JSONDecodeError:
                    continue

                delta = payload.get("choices", [{}])[0].get("delta", {}).get("content")
                if delta:
                    yield {"delta": delta}

            yield {"done": True}
    except URLError:
        yield {"error": "LM Studio is detected but the request failed. Check that the model is loaded and the local server is running."}
    except Exception as exc:
        yield {"error": f"LM Studio returned an error: {exc}"}


def build_app_dataset() -> tuple[list[dict], dict]:
    spam_pipeline = joblib.load(SPAM_PIPELINE_PATH)
    importance_pipeline = joblib.load(IMPORTANCE_PIPELINE_PATH)
    metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))

    df = pd.read_csv(DATA_PATH).drop_duplicates(subset="raw_text").reset_index(drop=True)
    _, test_df = train_test_split(
        df,
        test_size=0.20,
        stratify=df["label"].astype(int),
        random_state=RANDOM_STATE,
    )
    test_df = test_df.sort_values("date", ascending=False).reset_index(drop=True)

    base_emails, next_id = build_email_records(
        test_df,
        spam_pipeline,
        importance_pipeline,
        source_kind="held_out_test",
        source_label="Held-out test set",
        starting_id=1,
    )
    generated_df = load_generated_demo_rows()
    generated_emails, _ = build_email_records(
        generated_df,
        spam_pipeline,
        importance_pipeline,
        source_kind="generated_demo",
        source_label="Generated demo set",
        starting_id=next_id,
    )

    emails = base_emails + generated_emails
    emails.sort(key=lambda email: email["date_iso"], reverse=True)
    for idx, email in enumerate(emails, start=1):
        email["id"] = idx

    legitimate_count = sum(email["threat_type"] == "legitimate" for email in emails)
    spam_count = sum(email["threat_type"] == "spam" for email in emails)
    phishing_count = sum(email["threat_type"] == "phishing" for email in emails)
    high_priority_count = sum((email["importance_rank"] or 0) >= 4 for email in emails if email["threat_type"] == "legitimate")
    event_count = sum(len(email["events"]) > 0 for email in emails if email["threat_type"] == "legitimate")
    generated_email_count = sum(email["source_kind"] == "generated_demo" for email in emails)
    held_out_email_count = sum(email["source_kind"] == "held_out_test" for email in emails)

    stats = {
        "total_emails": len(emails),
        "held_out_email_count": held_out_email_count,
        "generated_email_count": generated_email_count,
        "legitimate_count": legitimate_count,
        "spam_count": spam_count,
        "phishing_count": phishing_count,
        "high_priority_count": high_priority_count,
        "event_count": event_count,
        "default_spam_threshold": DEFAULT_SPAM_THRESHOLD,
        "training_metadata": metadata,
    }
    return emails, stats


EMAILS, STATS = build_app_dataset()
EMAIL_BY_ID = {email["id"]: email for email in EMAILS}


class SpamShieldHandler(BaseHTTPRequestHandler):
    def _write_sse(self, payload: dict) -> None:
        body = f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode("utf-8")
        self.wfile.write(body)
        self.wfile.flush()

    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path, content_type: str) -> None:
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            return self._send_file(HTML_PATH, "text/html; charset=utf-8")
        if parsed.path == "/static/spamshield_app.js":
            return self._send_file(JS_PATH, "application/javascript; charset=utf-8")
        if parsed.path == "/api/bootstrap":
            available, model_id = lmstudio_available()
            return self._send_json(
                {
                    "emails": EMAILS,
                    "stats": STATS,
                    "lm_studio": {
                        "available": available,
                        "model_id": model_id,
                    },
                }
            )
        if parsed.path == "/api/status":
            available, model_id = lmstudio_available()
            return self._send_json(
                {
                    "lm_studio": {
                        "available": available,
                        "model_id": model_id,
                    }
                }
            )
        if parsed.path.startswith("/api/email/"):
            try:
                email_id = int(parsed.path.rsplit("/", 1)[-1])
            except ValueError:
                return self._send_json({"error": "Invalid email id"}, status=400)
            email = EMAIL_BY_ID.get(email_id)
            if email is None:
                return self._send_json({"error": "Email not found"}, status=404)
            return self._send_json({"email": email})

        return self._send_json({"error": "Not found"}, status=404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path not in {"/api/chat", "/api/chat/stream"}:
            return self._send_json({"error": "Not found"}, status=404)

        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8") if length else "{}"
        payload = json.loads(raw or "{}")
        question = (payload.get("question") or "").strip()
        email_id = payload.get("email_id")
        history = payload.get("history") or []
        email = EMAIL_BY_ID.get(int(email_id)) if email_id else None

        if not question:
            return self._send_json({"error": "Question is required"}, status=400)

        if parsed.path == "/api/chat/stream":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()

            for event in stream_lmstudio(question, email, history=history):
                self._write_sse(event)
            self.close_connection = True
            return

        reply = call_lmstudio(question, email, history=history)
        return self._send_json({"reply": reply})


def main() -> None:
    print(f"SpamShield server running on http://{HOST}:{PORT}")
    print(
        f"Loaded {STATS['total_emails']} emails for the demo "
        f"({STATS['held_out_email_count']} held-out + {STATS['generated_email_count']} generated)."
    )
    print("LM Studio chat support is optional and auto-detected at runtime.")
    server = ThreadingHTTPServer((HOST, PORT), SpamShieldHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()
