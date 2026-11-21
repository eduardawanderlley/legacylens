# Arquitetura

## Visão geral

Um único índice alimenta os dois módulos. Isso evita duplicar ingestão e deixa a avaliação de recuperação valer para ambos: se a busca traz a função certa, tanto a resposta quanto o teste melhoram.

| Camada | Arquivo | Responsabilidade |
|---|---|---|
| Ingestão | `ingest/chunker.py`, `ingest/walker.py` | Percorre o repositório e divide cada arquivo em chunks por AST |
| Índice | `store.py` | SQLite: tabela de chunks, FTS5 (BM25), vetores em BLOB, tabela de chamadas |
| Recuperação | `retrieval/hybrid.py` | BM25 + vetor, fusão RRF, reranker, expansão por grafo |
| Perguntas | `qa.py` | Monta o prompt, chama o LLM, valida as citações |
| Testes | `testgen/` | Loop gerar, executar, corrigir; mutation score |
| Avaliação | `evaluation/metrics.py` | recall@k, MRR, citação correta, abstenção |
| Observabilidade | `telemetry.py` | JSONL com latência, tokens e custo por operação |

## Fluxo de uma pergunta

1. A pergunta vira consulta BM25 (termos sem stopwords, identificadores quebrados em partes) e um embedding.
2. Cada ranking traz até 30 candidatos. A fusão RRF soma `1/(60+posição)` por ranking.
3. O reranker de identificadores soma um bônus a quem tem o nome da função ou do arquivo na pergunta.
4. Os `k` melhores seguem. Para os três primeiros que são funções, entram até alguns vizinhos do grafo (quem chamam e quem os chama), marcados como `graph`.
5. O prompt recebe os trechos com a referência `caminho:início-fim` no cabeçalho de cada um.
6. A resposta é lida em busca de citações `[caminho:início-fim]`. Uma citação é válida se coincide com um chunk enviado ou está contida em um deles.

## Fluxo de geração de testes

1. Resolve o alvo (`caminho::Classe.método`) no índice. Alvo ambíguo ou inexistente gera erro explícito.
2. O prompt inclui o código alvo e até três funções internas que ele chama, só como contexto.
3. A resposta passa por `check_test_quality`: precisa compilar, ter funções `test_*` e cada uma precisa verificar algo.
4. O `pytest` roda em subprocesso, com `PYTHONPATH` apontando para a raiz e para `src/`.
5. Se falhar, a saída (últimos 4000 caracteres) volta ao modelo com a instrução de ajustar o teste ao comportamento real. Repete até `--attempts`.
6. Esgotadas as tentativas, o arquivo é apagado. O que fica no repositório sempre passou.

Um ponto de atenção: pedir ao modelo para "ajustar a expectativa ao comportamento real" produz testes que fixam o comportamento atual, bugs inclusos. Para código legado isso é o que se quer (teste de caracterização), mas é o motivo de eu medir mutation score em vez de confiar só em "passou".

## Execução isolada

O `PytestRunner` não isola nada além de um timeout. Para rodar código gerado com segurança, use o `Dockerfile` deste repositório sem montar credenciais além do necessário, e monte o repositório alvo como somente leitura quando só for indexar.
