#!/usr/bin/env sh
# Indexa o repositório alvo e roda a avaliação de recuperação (sem LLM).
# Uso: TARGET_REPO=repos/flask scripts/run_retrieval_eval.sh
set -eu
TARGET_REPO="${TARGET_REPO:-.}"
legacylens index "$TARGET_REPO"
legacylens eval eval/gold.jsonl -k 5 > eval/results.json
cat eval/results.json
