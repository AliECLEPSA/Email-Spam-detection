#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

if [ -x /opt/miniconda3/bin/python3 ] && /opt/miniconda3/bin/python3 -c "import joblib, pandas, sklearn, matplotlib" >/dev/null 2>&1; then
  PYTHON_BIN=/opt/miniconda3/bin/python3
elif python3 -c "import joblib, pandas, sklearn, matplotlib" >/dev/null 2>&1; then
  PYTHON_BIN=python3
else
  echo "Missing Python dependencies."
  echo "Run: python3 -m pip install -r ../04_App/requirements.txt"
  exit 1
fi

"$PYTHON_BIN" synthetic_spam_blind_test.py
