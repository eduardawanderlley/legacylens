# Limitações conhecidas

- **Apenas Python.** Outras linguagens exigem um chunker novo (a interface está em `ingest/chunker.py`). Arquivos que não compilam, como Python 2, são ignorados e contados como "ignorados" na indexação.
- **Funções longas viram chunks longos.** Não há divisão interna; ver ADR-001.
- **Grafo por nome.** Sem resolução de tipos, herança ou chamadas dinâmicas (`getattr`, callbacks registrados em tempo de execução).
- **Embedder padrão não é semântico.** O de hashing só vê tokens em comum, não relaciona "validação" com `validate`. Use `st:<modelo>` para perguntas em linguagem natural. Para consultas em português sobre código em inglês, um modelo multilíngue é a escolha adequada, e isso deve ser medido no gabarito.
- **Filtro de abstenção lexical desligado por padrão**; ver ADR-005.
- **Citações verificam a origem, não a verdade.** Confirmo que a citação aponta para um trecho que foi enviado ao modelo. Não confirmo que o trecho sustenta a frase.
- **Executor sem sandbox.** `subprocess` e timeout, sem isolamento de rede, sistema de arquivos ou recursos.
- **Testes de caracterização.** Testes gerados fixam o comportamento atual, incluindo defeitos.
- **Mutation score** via `mutmut` 2.x; a leitura do `junitxml` foi escrita para essa série e deve ser conferida na sua versão.
- **Reindexação completa.** Cada `index` refaz tudo; não há indexação incremental.
- **Sem servidor MCP** nesta versão. O bot de PR (`pr-suggest` e o workflow) existe, mas está pouco exercitado em CI real.
