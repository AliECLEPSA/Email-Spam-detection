from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin


FREE_MAIL_PROVIDERS = {
    "gmail.com",
    "googlemail.com",
    "outlook.com",
    "hotmail.com",
    "live.com",
    "icloud.com",
    "me.com",
    "yahoo.com",
    "proton.me",
    "protonmail.com",
    "aol.com",
    "gmx.com",
    "mail.com",
}


def count_addresses(value) -> int:
    if pd.isna(value) or str(value).strip() == "":
        return 0
    return len([item for item in re.split(r"[;,]", str(value)) if item.strip()])


def count_attachments(value) -> int:
    if pd.isna(value) or str(value).strip() == "":
        return 0
    return len([item for item in str(value).split(";") if item.strip()])


def upper_ratio(text) -> float:
    text = "" if pd.isna(text) else str(text)
    letters = [char for char in text if char.isalpha()]
    if not letters:
        return 0.0
    return sum(char.isupper() for char in letters) / len(letters)


def digit_ratio(text) -> float:
    text = "" if pd.isna(text) else str(text)
    if len(text) == 0:
        return 0.0
    return sum(char.isdigit() for char in text) / len(text)


class EmailFeatureBuilder(BaseEstimator, TransformerMixin):
    def fit(self, X, y=None):
        return self

    def transform(self, X):
        out = X.copy()

        out["date"] = pd.to_datetime(out["date"], errors="coerce")
        out["combined_text"] = (
            out["subject"].fillna("")
            + " "
            + out["body_plain"].fillna("")
            + " "
            + out["body_html"].fillna("")
        ).str.strip()

        out["to_count"] = out["to_addresses"].apply(count_addresses)
        out["cc_count"] = out["cc_addresses"].apply(count_addresses)
        out["attachment_count"] = out["attachment_types"].apply(count_attachments)

        out["day_of_week"] = out["date"].dt.day_name().fillna("Unknown")
        out["month"] = out["date"].dt.month.fillna(-1).astype(int)
        out["is_weekend"] = out["day_of_week"].isin(["Saturday", "Sunday"])
        out["is_business_hours"] = out["hour_of_day"].between(8, 18)

        out["has_reply_thread"] = out["in_reply_to"].notna() & out["in_reply_to"].astype(str).ne("")
        out["reply_to_missing"] = out["reply_to"].isna() | out["reply_to"].astype(str).eq("")

        out["is_free_mail"] = out["from_domain"].isin(FREE_MAIL_PROVIDERS)
        out["auth_pass_count"] = (
            out["spf_result"].eq("pass").astype(int)
            + out["dkim_result"].eq("pass").astype(int)
            + out["dmarc_result"].eq("pass").astype(int)
        )

        out["subject_len"] = out["subject"].fillna("").str.len()
        out["body_len"] = out["body_plain"].fillna("").str.len()
        out["raw_len"] = out["raw_text"].fillna("").str.len()
        out["subject_exclamation_count"] = out["subject"].fillna("").str.count("!")
        out["subject_question_count"] = out["subject"].fillna("").str.count(r"\?")
        out["subject_upper_ratio"] = out["subject"].apply(upper_ratio)
        out["body_digit_ratio"] = out["body_plain"].apply(digit_ratio)

        return out


@dataclass(frozen=True)
class ImportanceRuleThresholds:
    q33: float
    q66: float


def build_importance_proxy(df: pd.DataFrame) -> tuple[pd.DataFrame, ImportanceRuleThresholds]:
    out = df.copy()
    text_lower = out["combined_text"].str.lower()

    out["score_reply_thread"] = 2.2 * out["has_reply_thread"].astype(int)
    out["score_attachment"] = 1.8 * out["has_attachments"].astype(int)
    out["score_schedule_keywords"] = 1.5 * text_lower.str.contains(
        r"meeting|agenda|call|appointment|schedule|calendar|deadline|due date|review|follow-up|follow up|reminder",
        regex=True,
        na=False,
    ).astype(int)
    out["score_finance_keywords"] = 1.2 * text_lower.str.contains(
        r"invoice|payment|billing|statement|accounts payable|budget|contract|legal|approval",
        regex=True,
        na=False,
    ).astype(int)
    out["score_project_keywords"] = 1.0 * text_lower.str.contains(
        r"release notes|report|weekly update|project|onboarding|it|legal",
        regex=True,
        na=False,
    ).astype(int)
    out["score_business_domain"] = 0.8 * (~out["is_free_mail"]).astype(int)
    out["score_authentication"] = 0.6 * (out["auth_pass_count"] >= 2).astype(int)
    out["score_cc"] = 0.4 * (out["cc_count"] > 0).astype(int)
    out["score_business_hours"] = 0.3 * out["is_business_hours"].astype(int)

    out["penalty_unsubscribe"] = -0.8 * out["list_unsubscribe"].notna().astype(int)
    out["penalty_urls"] = -0.8 * (out["num_urls"] >= 1).astype(int)
    out["penalty_tracking"] = -0.5 * out["contains_tracking_token"].astype(int)

    components = [
        "score_reply_thread",
        "score_attachment",
        "score_schedule_keywords",
        "score_finance_keywords",
        "score_project_keywords",
        "score_business_domain",
        "score_authentication",
        "score_cc",
        "score_business_hours",
        "penalty_unsubscribe",
        "penalty_urls",
        "penalty_tracking",
    ]

    out["importance_score"] = out[components].sum(axis=1)
    q33, q66 = out["importance_score"].quantile([0.33, 0.66]).tolist()
    out["importance_level"] = pd.cut(
        out["importance_score"],
        bins=[-np.inf, q33, q66, np.inf],
        labels=["low", "medium", "high"],
    )
    return out, ImportanceRuleThresholds(q33=float(q33), q66=float(q66))
