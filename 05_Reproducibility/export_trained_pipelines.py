from __future__ import annotations

import json
from pathlib import Path

import joblib
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, f1_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from email_modeling import EmailFeatureBuilder, build_importance_proxy


ROOT = Path(__file__).resolve().parent
PACKAGE_ROOT = ROOT.parent
DATA_PATH = PACKAGE_ROOT / "03_Datasets" / "base_datasets" / "email_dataset_30k.csv"
ARTIFACTS_DIR = PACKAGE_ROOT / "04_App" / "SpamShield_App" / "artifacts"
RANDOM_STATE = 42


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def rounded_report_dict(report: dict, digits: int = 4) -> dict:
    out = {}
    for key, value in report.items():
        if isinstance(value, dict):
            out[key] = {sub_key: round(float(sub_value), digits) for sub_key, sub_value in value.items()}
        elif isinstance(value, (float, int)):
            out[key] = round(float(value), digits)
        else:
            out[key] = value
    return out


def train_spam_pipeline(df: pd.DataFrame) -> tuple[Pipeline, dict]:
    numeric_cols = [
        "hour_of_day",
        "num_received_headers",
        "num_urls",
        "num_emails_in_body",
        "num_phone_numbers",
        "to_count",
        "cc_count",
        "attachment_count",
        "subject_len",
        "body_len",
        "raw_len",
        "auth_pass_count",
        "subject_exclamation_count",
        "subject_question_count",
        "subject_upper_ratio",
        "body_digit_ratio",
        "month",
    ]
    boolean_cols = [
        "has_attachments",
        "has_html",
        "contains_tracking_token",
        "is_free_mail",
        "reply_to_missing",
        "has_reply_thread",
        "is_weekend",
        "is_business_hours",
    ]
    categorical_cols = [
        "from_domain",
        "spf_result",
        "dkim_result",
        "dmarc_result",
        "user_agent",
        "language",
        "day_of_week",
    ]

    preprocessor = ColumnTransformer(
        transformers=[
            (
                "text",
                TfidfVectorizer(max_features=8000, ngram_range=(1, 2), min_df=3, sublinear_tf=True),
                "combined_text",
            ),
            ("cat", OneHotEncoder(handle_unknown="ignore"), categorical_cols),
            (
                "num",
                Pipeline(
                    [
                        ("imputer", SimpleImputer(strategy="median")),
                        ("scaler", StandardScaler(with_mean=False)),
                    ]
                ),
                numeric_cols,
            ),
            ("bool", "passthrough", boolean_cols),
        ]
    )

    model = Pipeline(
        steps=[
            ("features", EmailFeatureBuilder()),
            ("preprocessor", preprocessor),
            ("classifier", LogisticRegression(max_iter=2500, solver="saga", class_weight="balanced")),
        ]
    )

    dedup = df.drop_duplicates(subset="raw_text").reset_index(drop=True)
    X_train, X_test, y_train, y_test = train_test_split(
        dedup,
        dedup["label"].astype(int),
        test_size=0.20,
        stratify=dedup["label"].astype(int),
        random_state=RANDOM_STATE,
    )

    model.fit(X_train, y_train)
    pred = model.predict(X_test)
    proba = model.predict_proba(X_test)[:, 1]

    metrics = {
        "accuracy": round(float(accuracy_score(y_test, pred)), 4),
        "f1": round(float(f1_score(y_test, pred)), 4),
        "roc_auc": round(float(roc_auc_score(y_test, proba)), 4),
        "classification_report": rounded_report_dict(classification_report(y_test, pred, output_dict=True)),
        "train_rows": int(len(X_train)),
        "test_rows": int(len(X_test)),
    }
    return model, metrics


def train_importance_pipeline(df: pd.DataFrame) -> tuple[Pipeline, dict, dict]:
    numeric_cols = [
        "hour_of_day",
        "num_received_headers",
        "num_urls",
        "num_emails_in_body",
        "num_phone_numbers",
        "to_count",
        "cc_count",
        "attachment_count",
        "subject_len",
        "body_len",
        "raw_len",
        "auth_pass_count",
        "subject_exclamation_count",
        "subject_question_count",
        "subject_upper_ratio",
        "body_digit_ratio",
        "month",
    ]
    boolean_cols = [
        "has_attachments",
        "has_html",
        "contains_tracking_token",
        "is_free_mail",
        "reply_to_missing",
        "has_reply_thread",
        "is_weekend",
        "is_business_hours",
    ]
    categorical_cols = [
        "from_domain",
        "spf_result",
        "dkim_result",
        "dmarc_result",
        "user_agent",
        "language",
        "day_of_week",
    ]

    preprocessor = ColumnTransformer(
        transformers=[
            (
                "text",
                TfidfVectorizer(max_features=8000, ngram_range=(1, 2), min_df=3, sublinear_tf=True),
                "combined_text",
            ),
            ("cat", OneHotEncoder(handle_unknown="ignore"), categorical_cols),
            (
                "num",
                Pipeline(
                    [
                        ("imputer", SimpleImputer(strategy="median")),
                        ("scaler", StandardScaler(with_mean=False)),
                    ]
                ),
                numeric_cols,
            ),
            ("bool", "passthrough", boolean_cols),
        ]
    )

    model = Pipeline(
        steps=[
            ("features", EmailFeatureBuilder()),
            ("preprocessor", preprocessor),
            ("classifier", LogisticRegression(max_iter=2500, solver="saga")),
        ]
    )

    dedup = df.drop_duplicates(subset="raw_text").reset_index(drop=True)
    ham = dedup.loc[dedup["label"] == 0].copy().reset_index(drop=True)

    engineered_ham = EmailFeatureBuilder().fit_transform(ham)
    ham_with_proxy, thresholds = build_importance_proxy(engineered_ham)

    X_train, X_test, y_train, y_test = train_test_split(
        ham,
        ham_with_proxy["importance_level"],
        test_size=0.20,
        stratify=ham_with_proxy["importance_level"],
        random_state=RANDOM_STATE,
    )

    model.fit(X_train, y_train)
    pred = model.predict(X_test)

    metrics = {
        "accuracy": round(float(accuracy_score(y_test, pred)), 4),
        "macro_f1": round(float(f1_score(y_test, pred, average="macro")), 4),
        "classification_report": rounded_report_dict(classification_report(y_test, pred, output_dict=True)),
        "train_rows": int(len(X_train)),
        "test_rows": int(len(X_test)),
    }
    thresholds_dict = {"q33": round(thresholds.q33, 4), "q66": round(thresholds.q66, 4)}
    return model, metrics, thresholds_dict


def main() -> None:
    ensure_dir(ARTIFACTS_DIR)
    data = pd.read_csv(DATA_PATH)

    spam_pipeline, spam_metrics = train_spam_pipeline(data)
    importance_pipeline, importance_metrics, importance_thresholds = train_importance_pipeline(data)

    spam_path = ARTIFACTS_DIR / "spam_pipeline.joblib"
    importance_path = ARTIFACTS_DIR / "importance_pipeline.joblib"
    metadata_path = ARTIFACTS_DIR / "pipeline_metadata.json"

    joblib.dump(spam_pipeline, spam_path)
    joblib.dump(importance_pipeline, importance_path)

    metadata = {
        "dataset": DATA_PATH.name,
        "artifacts": {
            "spam_pipeline": spam_path.name,
            "importance_pipeline": importance_path.name,
        },
        "spam_model": {
            "type": "hybrid_strict",
            "notes": "Uses raw CSV columns directly and performs internal feature engineering before TF-IDF plus metadata classification.",
            "metrics": spam_metrics,
            "recommended_threshold": 0.5,
        },
        "importance_model": {
            "type": "hybrid_proxy_target",
            "notes": "Predicts low/medium/high importance on non-spam emails. Proxy labels are built from transparent business rules.",
            "metrics": importance_metrics,
            "proxy_thresholds": importance_thresholds,
            "classes": ["low", "medium", "high"],
        },
    }

    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    print(f"Exported: {spam_path}")
    print(f"Exported: {importance_path}")
    print(f"Exported: {metadata_path}")
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
