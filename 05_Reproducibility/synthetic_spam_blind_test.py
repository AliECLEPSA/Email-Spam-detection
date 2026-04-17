from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import joblib
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)


ROOT = Path(__file__).resolve().parent
PACKAGE_ROOT = ROOT.parent
ARTIFACTS_DIR = PACKAGE_ROOT / "04_App" / "SpamShield_App" / "artifacts"
SPAM_PIPELINE_PATH = ARTIFACTS_DIR / "spam_pipeline.joblib"
METADATA_PATH = ARTIFACTS_DIR / "pipeline_metadata.json"
OUTPUT_DIR = PACKAGE_ROOT / "03_Datasets" / "generated_datasets"

SEED = 20260413
COUNT_PER_FAMILY = 60

RECIPIENT_EMAIL = "john.doe@contoso.com"
BUSINESS_DOMAINS = [
    "contoso.com",
    "northwind.com",
    "adatum.net",
    "globalbank.com",
    "mycompany.com",
    "fabrikam.io",
    "bizsupport.co",
    "devops.local",
    "hr-mail.net",
    "notifications.net",
    "example.com",
]
FREE_MAIL_DOMAINS = ["gmail.com", "outlook.com", "yahoo.com", "proton.me", "icloud.com"]
SPOOFISH_DOMAINS = ["accounts-mail.com", "portal-review.net", "secure-auth-notice.com"]

LEGIT_USER_AGENTS = [
    "Microsoft Outlook",
    "Apple Mail",
    "Thunderbird",
    "Spark",
    "Outlook-iOS",
    "Outlook-Android",
    "Gmail",
]
SPAM_USER_AGENTS = [
    "sendgrid",
    "aws-ses",
    "nodemailer",
    "Gmail",
    "Microsoft Outlook",
    "Spark",
]
LANGUAGES = ["en"]

FIRST_NAMES = [
    "Alex",
    "Jordan",
    "Taylor",
    "Sam",
    "Morgan",
    "Casey",
    "Riley",
    "Jamie",
    "Avery",
    "Cameron",
    "Drew",
    "Logan",
]
LAST_NAMES = [
    "Wright",
    "Turner",
    "Brooks",
    "Miller",
    "Ellis",
    "Grant",
    "Cooper",
    "Parker",
    "Reed",
    "Carter",
    "Bennett",
    "Moore",
]
PROJECTS = [
    "Mercury",
    "Atlas",
    "Nova",
    "Delta",
    "Beacon",
    "Apollo",
    "Orion",
    "Compass",
]
PRODUCTS = [
    "workspace portal",
    "finance dashboard",
    "support center",
    "analytics suite",
    "admin console",
    "customer portal",
]
NEWSLETTER_TOPICS = [
    "April product updates",
    "New analytics widgets",
    "Dashboard performance improvements",
    "Workflow automation launch",
    "Security controls now available",
]
SHIPPING_CARRIERS = ["DHL", "FedEx", "UPS", "GLS"]
PASSWORD_RESET_BRANDS = ["Microsoft 365", "Okta", "Dropbox", "Atlassian", "Notion"]
SUBSCRIPTION_BRANDS = ["Norton", "McAfee", "Webroot", "Avast"]
CRYPTO_BRANDS = ["BitVault", "CoinLance", "TradeMoon"]
PAYROLL_TERMS = ["compensation review", "salary adjustment", "payroll validation"]
DOCUMENT_TYPES = ["board deck", "Q3 budget", "vendor agreement", "staffing plan"]


@dataclass(frozen=True)
class FamilyConfig:
    family: str
    label: int
    coarse_type: str
    difficulty: str
    description: str


FAMILIES = [
    FamilyConfig(
        family="legit_internal_project",
        label=0,
        coarse_type="legitimate",
        difficulty="easy",
        description="Clean internal project or meeting follow-up with strong business signals and no links.",
    ),
    FamilyConfig(
        family="legit_calendar_invite",
        label=0,
        coarse_type="legitimate",
        difficulty="medium",
        description="Legitimate calendar invite, often with ICS attachment and sometimes a meeting link.",
    ),
    FamilyConfig(
        family="legit_invoice_notice",
        label=0,
        coarse_type="legitimate",
        difficulty="medium",
        description="Legitimate finance or accounts payable note using invoice vocabulary.",
    ),
    FamilyConfig(
        family="legit_shipping_confirmation",
        label=0,
        coarse_type="legitimate",
        difficulty="hard",
        description="Legitimate transactional shipping email with tracking links and HTML.",
    ),
    FamilyConfig(
        family="legit_newsletter_marketing",
        label=0,
        coarse_type="legitimate",
        difficulty="hard",
        description="Legitimate newsletter with HTML, tracking token and unsubscribe link.",
    ),
    FamilyConfig(
        family="legit_security_notice",
        label=0,
        coarse_type="legitimate",
        difficulty="hard",
        description="Legitimate security or password reset notice with a real login-review link.",
    ),
    FamilyConfig(
        family="spam_prize_lottery",
        label=1,
        coarse_type="spam",
        difficulty="easy",
        description="Obvious prize or reward scam with urgent promotional language.",
    ),
    FamilyConfig(
        family="spam_parcel_fee",
        label=1,
        coarse_type="spam",
        difficulty="medium",
        description="Parcel fee scam asking for payment to release a package.",
    ),
    FamilyConfig(
        family="spam_subscription_renewal",
        label=1,
        coarse_type="spam",
        difficulty="medium",
        description="Fake subscription or antivirus renewal notice pushing a payment link.",
    ),
    FamilyConfig(
        family="phishing_payroll_update",
        label=1,
        coarse_type="phishing",
        difficulty="hard",
        description="Professional-looking payroll or compensation phishing email.",
    ),
    FamilyConfig(
        family="phishing_document_share",
        label=1,
        coarse_type="phishing",
        difficulty="hard",
        description="Fake shared-document notification designed to harvest credentials.",
    ),
    FamilyConfig(
        family="phishing_ceo_wire",
        label=1,
        coarse_type="phishing",
        difficulty="hard",
        description="CEO-style urgent payment or gift-card fraud, often with no direct link.",
    ),
]


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def person_name(rng: random.Random) -> str:
    return f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"


def email_from_name(name: str, domain: str) -> str:
    local = name.lower().replace(" ", ".")
    return f"{local}@{domain}"


def random_ip(rng: random.Random) -> str:
    return ".".join(str(rng.randint(11, 223)) for _ in range(4))


def maybe_cc(rng: random.Random, max_count: int = 2) -> str:
    count = rng.randint(0, max_count)
    if count == 0:
        return ""
    names = [person_name(rng) for _ in range(count)]
    domain = rng.choice(BUSINESS_DOMAINS)
    return ";".join(email_from_name(name, domain) for name in names)


def random_date(rng: random.Random, business_like: bool) -> datetime:
    start = datetime(2024, 1, 15, 8, 0)
    day_offset = rng.randint(0, 570)
    dt = start + timedelta(days=day_offset)
    if business_like:
        hour = rng.randint(8, 18)
        minute = rng.choice([0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55])
    else:
        hour = rng.randint(0, 23)
        minute = rng.choice([0, 7, 12, 18, 23, 29, 36, 41, 48, 54])
    return dt.replace(hour=hour, minute=minute)


def format_body(lines: list[str]) -> str:
    return "\n".join(lines).strip()


def format_html_body(lines: list[str]) -> str:
    html_lines = "".join(f"<p>{line}</p>" for line in lines)
    return f"<html><body>{html_lines}</body></html>"


def make_message_id(prefix: str, idx: int, domain: str) -> str:
    return f"<{prefix}-{idx:05d}@{domain}>"


def render_row(
    *,
    rng: random.Random,
    idx: int,
    family: FamilyConfig,
    subject: str,
    lines: list[str],
    from_name: str,
    from_domain: str,
    spf_result: str,
    dkim_result: str,
    dmarc_result: str,
    has_html: bool,
    urls: list[str],
    attachment_types: list[str],
    tracking_token: bool,
    user_agent: str,
    date: datetime,
    reply_to: str = "",
    in_reply_to: str = "",
    list_unsubscribe: str = "",
    cc_addresses: str = "",
    extra_emails_in_body: list[str] | None = None,
    phone_numbers: list[str] | None = None,
    x_spam_score: float = 0.0,
) -> dict:
    extra_emails_in_body = extra_emails_in_body or []
    phone_numbers = phone_numbers or []
    plain_body = format_body(lines)
    html_body = format_html_body(lines) if has_html else ""
    raw_text = f"Subject: {subject}\n{plain_body}".strip()
    message_id = make_message_id(family.family, idx, from_domain)
    to_addresses = RECIPIENT_EMAIL
    attachment_string = ";".join(attachment_types)
    return {
        "raw_text": raw_text,
        "subject": subject,
        "body_plain": plain_body,
        "body_html": html_body,
        "from_address": email_from_name(from_name, from_domain),
        "from_domain": from_domain,
        "reply_to": reply_to,
        "to_addresses": to_addresses,
        "cc_addresses": cc_addresses,
        "date": date.isoformat(timespec="seconds"),
        "hour_of_day": date.hour,
        "message_id": message_id,
        "in_reply_to": in_reply_to,
        "num_received_headers": rng.randint(3, 8) if family.label == 0 else rng.randint(2, 6),
        "received_origin_ip": random_ip(rng),
        "spf_result": spf_result,
        "dkim_result": dkim_result,
        "dmarc_result": dmarc_result,
        "has_attachments": bool(attachment_types),
        "attachment_types": attachment_string,
        "has_html": has_html,
        "num_urls": len(urls),
        "num_emails_in_body": len(extra_emails_in_body),
        "num_phone_numbers": len(phone_numbers),
        "contains_tracking_token": tracking_token,
        "x_spam_score": x_spam_score,
        "user_agent": user_agent,
        "list_unsubscribe": list_unsubscribe,
        "language": rng.choice(LANGUAGES),
        "label": family.label,
        "family": family.family,
        "coarse_type": family.coarse_type,
        "difficulty": family.difficulty,
        "description": family.description,
    }


def generate_legit_internal_project(rng: random.Random, idx: int, family: FamilyConfig) -> dict:
    from_name = person_name(rng)
    recipient_first = RECIPIENT_EMAIL.split("@", 1)[0].split(".", 1)[0].title()
    domain = rng.choice(["contoso.com", "northwind.com", "adatum.net", "devops.local", "mycompany.com"])
    project = rng.choice(PROJECTS)
    subject = rng.choice(
        [
            f"Re: {project} sprint review action items",
            f"{project} release notes v{rng.randint(2,9)}.{rng.randint(0,9)}.{rng.randint(0,9)}",
            f"Follow-up: {project} onboarding tasks",
            f"{project} weekly update and next steps",
        ]
    )
    attachment_types = []
    if rng.random() < 0.35:
        attachment_types.append(f"{project.lower()}_notes_{rng.randint(1000,9999)}.pdf")
    reply_id = ""
    if rng.random() < 0.7:
        reply_id = f"<thread-{rng.randint(1000,9999)}@{domain}>"
    lines = [
        f"Hi {recipient_first},",
        f"Here are the notes from our {project} review.",
        rng.choice(
            [
                "Please add your comments to the attached document before tomorrow afternoon.",
                "Can you confirm the open items before the release window starts?",
                "I captured the blockers and owners below for the engineering sync.",
            ]
        ),
        "Thanks,",
        from_name.split()[0],
    ]
    return render_row(
        rng=rng,
        idx=idx,
        family=family,
        subject=subject,
        lines=lines,
        from_name=from_name,
        from_domain=domain,
        spf_result="pass",
        dkim_result="pass",
        dmarc_result="pass",
        has_html=rng.random() < 0.1,
        urls=[],
        attachment_types=attachment_types,
        tracking_token=False,
        user_agent=rng.choice(LEGIT_USER_AGENTS),
        date=random_date(rng, business_like=True),
        in_reply_to=reply_id,
        cc_addresses=maybe_cc(rng, max_count=2),
        x_spam_score=0.1,
    )


def generate_legit_calendar_invite(rng: random.Random, idx: int, family: FamilyConfig) -> dict:
    from_name = person_name(rng)
    recipient_first = RECIPIENT_EMAIL.split("@", 1)[0].split(".", 1)[0].title()
    domain = rng.choice(["contoso.com", "adatum.net", "northwind.com", "gmail.com", "outlook.com"])
    project = rng.choice(PROJECTS)
    meeting_dt = random_date(rng, business_like=True) + timedelta(days=rng.randint(1, 14))
    meeting_link = f"https://meet.{domain.replace('.local', '.com')}/join/{rng.randint(100000,999999)}"
    include_link = rng.random() < 0.45
    lines = [
        f"Hi {recipient_first},",
        f"This is a confirmation for the {project} planning session on {meeting_dt.strftime('%d/%m/%Y')} at {meeting_dt.strftime('%H:%M')}.",
        "The calendar invitation is attached.",
    ]
    urls = []
    if include_link:
        lines.append(f"You can also join with this meeting link: {meeting_link}")
        urls.append(meeting_link)
    lines.extend(["Best,", from_name.split()[0]])
    return render_row(
        rng=rng,
        idx=idx,
        family=family,
        subject=f"Calendar invite: {project} planning on {meeting_dt.strftime('%d/%m/%Y')}",
        lines=lines,
        from_name=from_name,
        from_domain=domain,
        spf_result="pass",
        dkim_result="pass",
        dmarc_result="pass" if domain not in FREE_MAIL_DOMAINS else "none",
        has_html=include_link,
        urls=urls,
        attachment_types=[f"invite_{rng.randint(100000,999999)}.ics", f"agenda_{rng.randint(1000,9999)}.pdf"],
        tracking_token=False,
        user_agent=rng.choice(LEGIT_USER_AGENTS),
        date=random_date(rng, business_like=True),
        cc_addresses=maybe_cc(rng, max_count=1),
        x_spam_score=0.2,
    )


def generate_legit_invoice_notice(rng: random.Random, idx: int, family: FamilyConfig) -> dict:
    from_name = person_name(rng)
    recipient_first = RECIPIENT_EMAIL.split("@", 1)[0].split(".", 1)[0].title()
    domain = rng.choice(["globalbank.com", "mycompany.com", "adatum.net", "bizsupport.co"])
    invoice_id = rng.randint(100000, 999999)
    include_link = rng.random() < 0.2
    portal_url = f"https://billing.{domain.replace('.local', '.com')}/invoice/{invoice_id}"
    lines = [
        f"Dear {recipient_first},",
        f"We received invoice {invoice_id} and it is now queued for Accounts Payable processing.",
        "The PDF copy is attached for your records.",
    ]
    urls = []
    if include_link:
        lines.append(f"You can review the same invoice in the billing portal here: {portal_url}")
        urls.append(portal_url)
    lines.extend(["Best regards,", from_name])
    return render_row(
        rng=rng,
        idx=idx,
        family=family,
        subject=f"Invoice {invoice_id} processed for April services",
        lines=lines,
        from_name=from_name,
        from_domain=domain,
        spf_result="pass",
        dkim_result="pass",
        dmarc_result="pass",
        has_html=include_link,
        urls=urls,
        attachment_types=[f"invoice_{invoice_id}.pdf"],
        tracking_token=False,
        user_agent=rng.choice(LEGIT_USER_AGENTS),
        date=random_date(rng, business_like=True),
        cc_addresses=maybe_cc(rng, max_count=1),
        x_spam_score=0.2,
    )


def generate_legit_shipping_confirmation(rng: random.Random, idx: int, family: FamilyConfig) -> dict:
    from_name = "Order Update"
    recipient_first = RECIPIENT_EMAIL.split("@", 1)[0].split(".", 1)[0].title()
    domain = rng.choice(["notifications.net", "example.com", "mycompany.com"])
    carrier = rng.choice(SHIPPING_CARRIERS)
    order_id = rng.randint(100000, 999999)
    tracking_id = f"{carrier[:2].upper()}{rng.randint(10000000,99999999)}"
    url_one = f"https://track.{domain}/order/{order_id}?ref={rng.randint(1000,9999)}"
    url_two = f"https://track.{domain}/carrier/{tracking_id}?utm={rng.randint(10000,99999)}"
    lines = [
        f"Hi {recipient_first},",
        f"Your order {order_id} shipped today with {carrier}.",
        f"Tracking page: {url_one}",
        f"Carrier detail page: {url_two}",
        "This message was sent automatically by the order system.",
        "Thanks,",
        "Customer notifications",
    ]
    return render_row(
        rng=rng,
        idx=idx,
        family=family,
        subject=f"Your order {order_id} has shipped",
        lines=lines,
        from_name=from_name,
        from_domain=domain,
        spf_result="pass",
        dkim_result="pass",
        dmarc_result="pass",
        has_html=True,
        urls=[url_one, url_two],
        attachment_types=[],
        tracking_token=True,
        user_agent=rng.choice(LEGIT_USER_AGENTS),
        date=random_date(rng, business_like=True),
        list_unsubscribe="mailto:unsubscribe@notifications.net",
        x_spam_score=0.4,
    )


def generate_legit_newsletter_marketing(rng: random.Random, idx: int, family: FamilyConfig) -> dict:
    from_name = "Product News"
    domain = rng.choice(["notifications.net", "example.com", "adatum.net"])
    topic = rng.choice(NEWSLETTER_TOPICS)
    url_one = f"https://updates.{domain}/release/{rng.randint(1000,9999)}?utm_source=email&utm_campaign={rng.randint(100,999)}"
    url_two = f"https://help.{domain}/article/{rng.randint(1000,9999)}?trk={rng.randint(10000,99999)}"
    lines = [
        "Hello,",
        f"Here is this week's update: {topic}.",
        f"Release note: {url_one}",
        f"Help article: {url_two}",
        "You receive this service newsletter because your workspace notifications are enabled.",
        "Regards,",
        "The product team",
    ]
    return render_row(
        rng=rng,
        idx=idx,
        family=family,
        subject=topic,
        lines=lines,
        from_name=from_name,
        from_domain=domain,
        spf_result="pass",
        dkim_result="pass",
        dmarc_result="pass",
        has_html=True,
        urls=[url_one, url_two],
        attachment_types=[],
        tracking_token=True,
        user_agent=rng.choice(LEGIT_USER_AGENTS),
        date=random_date(rng, business_like=True),
        list_unsubscribe=f"https://updates.{domain}/unsubscribe/{rng.randint(100000,999999)}",
        x_spam_score=0.8,
    )


def generate_legit_security_notice(rng: random.Random, idx: int, family: FamilyConfig) -> dict:
    from_name = "Security Team"
    brand = rng.choice(PASSWORD_RESET_BRANDS)
    domain = rng.choice(["bizsupport.co", "contoso.com", "northwind.com", "example.com"])
    recipient_first = RECIPIENT_EMAIL.split("@", 1)[0].split(".", 1)[0].title()
    review_url = f"https://account.{domain}/review-session/{rng.randint(100000,999999)}"
    lines = [
        f"Hi {recipient_first},",
        f"We detected a new sign-in to your {brand} workspace from an unrecognized device.",
        f"Review the sign-in activity here: {review_url}",
        "If this was you, no further action is required.",
        "Security operations",
    ]
    return render_row(
        rng=rng,
        idx=idx,
        family=family,
        subject=f"Security notice: new sign-in to your {brand} account",
        lines=lines,
        from_name=from_name,
        from_domain=domain,
        spf_result="pass",
        dkim_result="pass",
        dmarc_result="pass",
        has_html=True,
        urls=[review_url],
        attachment_types=[],
        tracking_token=False,
        user_agent=rng.choice(LEGIT_USER_AGENTS),
        date=random_date(rng, business_like=True),
        x_spam_score=0.6,
    )


def generate_spam_prize_lottery(rng: random.Random, idx: int, family: FamilyConfig) -> dict:
    from_name = "Claim Center"
    domain = rng.choice(["gmail.com", "outlook.com", "yahoo.com", "proton.me"])
    url_one = f"https://claim-prize-now.net/reward/{rng.randint(100000,999999)}"
    url_two = f"https://secure-payout.net/confirm/{rng.randint(100000,999999)}"
    lines = [
        "Dear user,",
        "WINNER! You have been selected for an instant loyalty reward.",
        f"Claim your payout here: {url_one}",
        f"Complete confirmation here: {url_two}",
        f"Support line: +1-{rng.randint(200,999)}-{rng.randint(200,999)}-{rng.randint(1000,9999)}",
        "Failure to respond today may lead to account closure.",
        "Rewards team",
    ]
    return render_row(
        rng=rng,
        idx=idx,
        family=family,
        subject="WINNER! Claim your reward now",
        lines=lines,
        from_name=from_name,
        from_domain=domain,
        spf_result="fail",
        dkim_result="fail",
        dmarc_result="none",
        has_html=False,
        urls=[url_one, url_two],
        attachment_types=[],
        tracking_token=False,
        user_agent=rng.choice(SPAM_USER_AGENTS),
        date=random_date(rng, business_like=False),
        phone_numbers=["support"],
        x_spam_score=8.6,
    )


def generate_spam_parcel_fee(rng: random.Random, idx: int, family: FamilyConfig) -> dict:
    from_name = "Parcel Desk"
    domain = rng.choice(["icloud.com", "accounts-mail.com", "outlook.com"])
    fee_url = f"https://parcel-release-pay.net/fee/{rng.randint(100000,999999)}"
    lines = [
        "Dear customer,",
        "Your parcel is on hold pending a customs handling fee.",
        f"Pay the fee here to release delivery: {fee_url}",
        "If you do not act within 12 hours the package will be returned.",
        "Parcel support",
    ]
    return render_row(
        rng=rng,
        idx=idx,
        family=family,
        subject="Parcel hold: customs payment required",
        lines=lines,
        from_name=from_name,
        from_domain=domain,
        spf_result=rng.choice(["fail", "neutral"]),
        dkim_result="fail",
        dmarc_result="none",
        has_html=True,
        urls=[fee_url],
        attachment_types=[],
        tracking_token=True,
        user_agent=rng.choice(SPAM_USER_AGENTS),
        date=random_date(rng, business_like=False),
        x_spam_score=7.4,
    )


def generate_spam_subscription_renewal(rng: random.Random, idx: int, family: FamilyConfig) -> dict:
    from_name = "Billing Center"
    domain = rng.choice(["gmail.com", "proton.me", "accounts-mail.com"])
    brand = rng.choice(SUBSCRIPTION_BRANDS)
    url_one = f"https://renew-now-pay.net/invoice/{rng.randint(100000,999999)}"
    url_two = f"https://billing-review-now.net/cancel/{rng.randint(100000,999999)}"
    lines = [
        "Hello,",
        f"Your {brand} protection plan has renewed automatically for USD {rng.randint(199,699)}.",
        f"Review or cancel here: {url_one}",
        f"Billing support portal: {url_two}",
        f"Help desk: +1-{rng.randint(200,999)}-{rng.randint(200,999)}-{rng.randint(1000,9999)}",
        "Please act immediately if you did not authorize this charge.",
    ]
    return render_row(
        rng=rng,
        idx=idx,
        family=family,
        subject=f"{brand} subscription renewed successfully",
        lines=lines,
        from_name=from_name,
        from_domain=domain,
        spf_result=rng.choice(["fail", "neutral"]),
        dkim_result=rng.choice(["fail", "neutral"]),
        dmarc_result="none",
        has_html=True,
        urls=[url_one, url_two],
        attachment_types=[],
        tracking_token=True,
        user_agent=rng.choice(SPAM_USER_AGENTS),
        date=random_date(rng, business_like=False),
        phone_numbers=["billing"],
        x_spam_score=7.9,
    )


def generate_phishing_payroll_update(rng: random.Random, idx: int, family: FamilyConfig) -> dict:
    from_name = person_name(rng)
    recipient_first = RECIPIENT_EMAIL.split("@", 1)[0].split(".", 1)[0].title()
    domain = rng.choice(["accounts-mail.com", "mycompany.com", "hr-mail.net"])
    term = rng.choice(PAYROLL_TERMS)
    review_url = f"https://secure-payroll-review.net/document/{rng.randint(100000,999999)}"
    lines = [
        f"Hi {recipient_first},",
        f"The HR team published an updated {term} document for your profile.",
        f"Please review it here before today's payroll close: {review_url}",
        "You may need to sign in with your company credentials to continue.",
        "Thanks,",
        "Payroll operations",
    ]
    return render_row(
        rng=rng,
        idx=idx,
        family=family,
        subject=f"Updated {term} available",
        lines=lines,
        from_name=from_name,
        from_domain=domain,
        spf_result=rng.choice(["neutral", "fail"]),
        dkim_result=rng.choice(["pass", "neutral", "fail"]),
        dmarc_result=rng.choice(["none", "fail"]),
        has_html=True,
        urls=[review_url],
        attachment_types=[],
        tracking_token=False,
        user_agent=rng.choice(["Microsoft Outlook", "Outlook-iOS", "Gmail", "sendgrid"]),
        date=random_date(rng, business_like=True),
        x_spam_score=6.8,
    )


def generate_phishing_document_share(rng: random.Random, idx: int, family: FamilyConfig) -> dict:
    from_name = person_name(rng)
    document_type = rng.choice(DOCUMENT_TYPES)
    domain = rng.choice(["accounts-mail.com", "example.com", "notifications.net", "adatum.net"])
    access_url = f"https://document-access-secure.net/open/{rng.randint(100000,999999)}"
    lines = [
        "Hello,",
        f"{from_name} shared a {document_type} with you and added a short comment.",
        f"Open the file here: {access_url}",
        "If the preview does not load, sign in again to refresh access.",
        "Microsoft SharePoint notifications",
    ]
    return render_row(
        rng=rng,
        idx=idx,
        family=family,
        subject=f"Re: {document_type} shared with you",
        lines=lines,
        from_name=from_name,
        from_domain=domain,
        spf_result=rng.choice(["neutral", "fail"]),
        dkim_result=rng.choice(["neutral", "fail", "pass"]),
        dmarc_result="none",
        has_html=True,
        urls=[access_url],
        attachment_types=[],
        tracking_token=False,
        user_agent=rng.choice(["Gmail", "Outlook-Android", "sendgrid"]),
        date=random_date(rng, business_like=True),
        x_spam_score=6.5,
    )


def generate_phishing_ceo_wire(rng: random.Random, idx: int, family: FamilyConfig) -> dict:
    sender_first = rng.choice(FIRST_NAMES)
    sender_last = rng.choice(LAST_NAMES)
    from_name = f"{sender_first} {sender_last}"
    domain = rng.choice(["gmail.com", "outlook.com", "mycompany.com"])
    recipient_first = RECIPIENT_EMAIL.split("@", 1)[0].split(".", 1)[0].title()
    request_amount = rng.randint(3200, 18750)
    phone = f"+1-{rng.randint(200,999)}-{rng.randint(200,999)}-{rng.randint(1000,9999)}"
    lines = [
        f"Hi {recipient_first},",
        "Are you available right now?",
        f"I need you to help with an urgent vendor transfer for USD {request_amount}.",
        "Reply as soon as you see this and keep the matter confidential until I confirm the details.",
        f"If I miss your response here, text me at {phone}.",
        sender_first,
    ]
    return render_row(
        rng=rng,
        idx=idx,
        family=family,
        subject="Need your help with a payment today",
        lines=lines,
        from_name=from_name,
        from_domain=domain,
        spf_result=rng.choice(["fail", "neutral"]),
        dkim_result=rng.choice(["neutral", "fail"]),
        dmarc_result="none",
        has_html=False,
        urls=[],
        attachment_types=[],
        tracking_token=False,
        user_agent=rng.choice(["Microsoft Outlook", "Apple Mail", "Gmail"]),
        date=random_date(rng, business_like=True),
        phone_numbers=[phone],
        x_spam_score=5.7,
    )


GENERATOR_MAP = {
    "legit_internal_project": generate_legit_internal_project,
    "legit_calendar_invite": generate_legit_calendar_invite,
    "legit_invoice_notice": generate_legit_invoice_notice,
    "legit_shipping_confirmation": generate_legit_shipping_confirmation,
    "legit_newsletter_marketing": generate_legit_newsletter_marketing,
    "legit_security_notice": generate_legit_security_notice,
    "spam_prize_lottery": generate_spam_prize_lottery,
    "spam_parcel_fee": generate_spam_parcel_fee,
    "spam_subscription_renewal": generate_spam_subscription_renewal,
    "phishing_payroll_update": generate_phishing_payroll_update,
    "phishing_document_share": generate_phishing_document_share,
    "phishing_ceo_wire": generate_phishing_ceo_wire,
}


def rounded_metrics(y_true: pd.Series, y_pred: pd.Series) -> dict[str, float]:
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
    specificity = tn / (tn + fp) if (tn + fp) else 0.0
    return {
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
        "precision": round(float(precision_score(y_true, y_pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y_true, y_pred, zero_division=0)), 4),
        "f1": round(float(f1_score(y_true, y_pred, zero_division=0)), 4),
        "specificity": round(float(specificity), 4),
        "false_positive_rate": round(float(fp / (fp + tn)) if (fp + tn) else 0.0, 4),
        "false_negative_rate": round(float(fn / (fn + tp)) if (fn + tp) else 0.0, 4),
        "tn": int(tn),
        "fp": int(fp),
        "fn": int(fn),
        "tp": int(tp),
    }


def grouped_metrics(df: pd.DataFrame, group_col: str) -> pd.DataFrame:
    rows = []
    for group_value, chunk in df.groupby(group_col, sort=True):
        metrics = rounded_metrics(chunk["label"], chunk["pred_label"])
        metrics.update(
            {
                group_col: group_value,
                "n_rows": int(len(chunk)),
                "avg_spam_probability": round(float(chunk["spam_probability"].mean()), 4),
            }
        )
        rows.append(metrics)
    columns = [
        group_col,
        "n_rows",
        "accuracy",
        "precision",
        "recall",
        "f1",
        "specificity",
        "false_positive_rate",
        "false_negative_rate",
        "avg_spam_probability",
        "tn",
        "fp",
        "fn",
        "tp",
    ]
    return pd.DataFrame(rows)[columns].sort_values(group_col).reset_index(drop=True)


def build_dataset(seed: int = SEED, count_per_family: int = COUNT_PER_FAMILY) -> pd.DataFrame:
    rng = random.Random(seed)
    rows = []
    idx = 1
    for family in FAMILIES:
        generator = GENERATOR_MAP[family.family]
        for _ in range(count_per_family):
            rows.append(generator(rng, idx, family))
            idx += 1
    return pd.DataFrame(rows)


def render_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_None_"
    return "```text\n" + df.to_string(index=False) + "\n```"


def build_report(
    *,
    summary: dict,
    family_metrics_df: pd.DataFrame,
    difficulty_metrics_df: pd.DataFrame,
    broad_metrics_df: pd.DataFrame,
    false_positives_df: pd.DataFrame,
    false_negatives_df: pd.DataFrame,
) -> str:
    overall = summary["overall_metrics"]
    hardest_legit = family_metrics_df[family_metrics_df["family"].str.startswith("legit_")].sort_values(
        ["false_positive_rate", "avg_spam_probability"], ascending=[False, False]
    )
    hardest_spam = family_metrics_df[family_metrics_df["label_type"] == "spam_like"].sort_values(
        ["false_negative_rate", "avg_spam_probability"], ascending=[False, True]
    )

    lines = [
        "# Synthetic Blind Stress Test for the Spam Pipeline",
        "",
        "## Setup",
        f"- Seed: `{summary['seed']}`",
        f"- Total emails: `{summary['n_rows']}`",
        f"- Families: `{summary['n_families']}`",
        f"- Threshold used: `{summary['threshold']}`",
        f"- Blind inference: the pipeline predicted on rows with the `label` column removed before scoring.",
        "",
        "## Overall results",
        f"- Accuracy: `{overall['accuracy']}`",
        f"- Precision: `{overall['precision']}`",
        f"- Recall: `{overall['recall']}`",
        f"- F1: `{overall['f1']}`",
        f"- Specificity: `{overall['specificity']}`",
        f"- False positive rate on legitimate mail: `{overall['false_positive_rate']}`",
        f"- False negative rate on spam/phishing mail: `{overall['false_negative_rate']}`",
        f"- Confusion matrix counts: `TN={overall['tn']}, FP={overall['fp']}, FN={overall['fn']}, TP={overall['tp']}`",
        "",
        "## Main readout",
        f"- The easiest legitimate family was `{summary['best_legit_family']}`.",
        f"- The hardest legitimate family was `{summary['worst_legit_family']}`.",
        f"- The easiest spam/phishing family was `{summary['best_spam_family']}`.",
        f"- The hardest spam/phishing family was `{summary['worst_spam_family']}`.",
        "",
        "## Metrics by family",
        render_table(family_metrics_df),
        "",
        "## Metrics by difficulty",
        render_table(difficulty_metrics_df),
        "",
        "## Metrics by broad type",
        render_table(broad_metrics_df),
        "",
        "## Sample false positives",
        render_table(false_positives_df),
        "",
        "## Sample false negatives",
        render_table(false_negatives_df),
        "",
        "## Interpretation",
        "- If false positives cluster around legitimate emails with URLs, HTML and tracking tokens, the model is likely overfitted to the original dataset pattern where legitimate emails almost never contain links.",
        "- If false negatives cluster around polished phishing or CEO-style fraud without links, the model is probably relying too much on easy metadata such as URL count and authentication failure.",
        "- This report is more realistic than the original hold-out score because every example here was generated after training and scored in blind mode.",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    ensure_dir(OUTPUT_DIR)
    metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    threshold = float(metadata["spam_model"]["recommended_threshold"])
    pipeline = joblib.load(SPAM_PIPELINE_PATH)

    df = build_dataset()
    model_input = df.drop(columns=["label"], errors="ignore").copy()

    classes = list(pipeline.named_steps["classifier"].classes_)
    spam_index = classes.index(1)
    spam_probability = pipeline.predict_proba(model_input)[:, spam_index]
    pred_label = (spam_probability >= threshold).astype(int)

    evaluated = df.copy()
    evaluated["spam_probability"] = spam_probability.round(6)
    evaluated["pred_label"] = pred_label
    evaluated["predicted_bucket"] = evaluated["pred_label"].map({0: "legitimate", 1: "spam_or_phishing"})
    evaluated["actual_bucket"] = evaluated["label"].map({0: "legitimate", 1: "spam_or_phishing"})
    evaluated["label_type"] = evaluated["label"].map({0: "legitimate", 1: "spam_like"})

    overall_metrics = rounded_metrics(evaluated["label"], evaluated["pred_label"])
    family_metrics_df = grouped_metrics(evaluated, "family")
    family_metrics_df["label_type"] = family_metrics_df["family"].map(
        {
            family.family: ("legitimate" if family.label == 0 else "spam_like")
            for family in FAMILIES
        }
    )
    family_metrics_df = family_metrics_df[
        [
            "family",
            "label_type",
            "n_rows",
            "accuracy",
            "precision",
            "recall",
            "f1",
            "specificity",
            "false_positive_rate",
            "false_negative_rate",
            "avg_spam_probability",
            "tn",
            "fp",
            "fn",
            "tp",
        ]
    ]
    difficulty_metrics_df = grouped_metrics(evaluated, "difficulty")
    broad_metrics_df = grouped_metrics(evaluated, "coarse_type")

    worst_legit_family = (
        family_metrics_df[family_metrics_df["label_type"] == "legitimate"]
        .sort_values(["false_positive_rate", "avg_spam_probability"], ascending=[False, False])
        .iloc[0]["family"]
    )
    best_legit_family = (
        family_metrics_df[family_metrics_df["label_type"] == "legitimate"]
        .sort_values(["false_positive_rate", "avg_spam_probability"], ascending=[True, True])
        .iloc[0]["family"]
    )
    worst_spam_family = (
        family_metrics_df[family_metrics_df["label_type"] == "spam_like"]
        .sort_values(["false_negative_rate", "avg_spam_probability"], ascending=[False, True])
        .iloc[0]["family"]
    )
    best_spam_family = (
        family_metrics_df[family_metrics_df["label_type"] == "spam_like"]
        .sort_values(["false_negative_rate", "avg_spam_probability"], ascending=[True, False])
        .iloc[0]["family"]
    )

    false_positives_df = (
        evaluated[(evaluated["label"] == 0) & (evaluated["pred_label"] == 1)][
            ["family", "difficulty", "subject", "from_domain", "num_urls", "contains_tracking_token", "spam_probability"]
        ]
        .sort_values("spam_probability", ascending=False)
        .head(15)
        .reset_index(drop=True)
    )
    false_negatives_df = (
        evaluated[(evaluated["label"] == 1) & (evaluated["pred_label"] == 0)][
            ["family", "difficulty", "subject", "from_domain", "num_urls", "contains_tracking_token", "spam_probability"]
        ]
        .sort_values("spam_probability", ascending=True)
        .head(15)
        .reset_index(drop=True)
    )

    summary = {
        "seed": SEED,
        "threshold": threshold,
        "n_rows": int(len(evaluated)),
        "n_families": len(FAMILIES),
        "overall_metrics": overall_metrics,
        "best_legit_family": best_legit_family,
        "worst_legit_family": worst_legit_family,
        "best_spam_family": best_spam_family,
        "worst_spam_family": worst_spam_family,
        "classification_report": classification_report(
            evaluated["label"],
            evaluated["pred_label"],
            output_dict=True,
            zero_division=0,
        ),
    }

    dataset_path = OUTPUT_DIR / "synthetic_spam_stress_test_dataset.csv"
    predictions_path = OUTPUT_DIR / "synthetic_spam_stress_test_predictions.csv"
    family_metrics_path = OUTPUT_DIR / "synthetic_spam_stress_test_family_metrics.csv"
    difficulty_metrics_path = OUTPUT_DIR / "synthetic_spam_stress_test_difficulty_metrics.csv"
    broad_metrics_path = OUTPUT_DIR / "synthetic_spam_stress_test_broad_metrics.csv"
    summary_path = OUTPUT_DIR / "synthetic_spam_stress_test_summary.json"
    report_path = OUTPUT_DIR / "synthetic_spam_stress_test_report.md"

    df.to_csv(dataset_path, index=False)
    evaluated.to_csv(predictions_path, index=False)
    family_metrics_df.to_csv(family_metrics_path, index=False)
    difficulty_metrics_df.to_csv(difficulty_metrics_path, index=False)
    broad_metrics_df.to_csv(broad_metrics_path, index=False)
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    report_path.write_text(
        build_report(
            summary=summary,
            family_metrics_df=family_metrics_df,
            difficulty_metrics_df=difficulty_metrics_df,
            broad_metrics_df=broad_metrics_df,
            false_positives_df=false_positives_df,
            false_negatives_df=false_negatives_df,
        ),
        encoding="utf-8",
    )

    print(f"Generated synthetic blind-test dataset at: {dataset_path}")
    print(f"Saved scored predictions at: {predictions_path}")
    print(f"Saved markdown report at: {report_path}")
    print(json.dumps(summary["overall_metrics"], indent=2))


if __name__ == "__main__":
    main()
