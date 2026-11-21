# Contribuindo

```bash
pip install -e ".[dev]"
pytest -q
ruff check src tests
```

- Testes usam um LLM e um runner simulados (`tests/helpers.py`, `tests/test_testgen.py`); nenhum teste chama a API.
- Mudanças que afetam a recuperação ou as respostas devem vir com o resultado de `legacylens eval` antes e depois.
- Decisões que mudam a arquitetura entram como um novo ADR em `docs/decisions.md`.
