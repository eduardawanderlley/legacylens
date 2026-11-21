# Avaliação

O projeto vale tanto quanto os números que sustentam. Esta página descreve como medir e o que registrar.

## 1. Escolha do repositório

Use um projeto open source real, antigo e conhecido, em Python. Fixe o **commit** e anote na tabela do README. Evite repositórios que o modelo provavelmente memorizou por inteiro se quiser medir compreensão e não lembrança; registre essa ressalva se não puder evitar.

## 2. Gabarito de perguntas

Crie `eval/gold.jsonl` (formato em `eval/gold.example.jsonl`) com 30 a 50 perguntas:

- Perguntas de localização ("onde...") e de comportamento ("o que acontece se...").
- Perguntas **sem resposta** no código, cerca de 20% do total, para medir abstenção.
- Trechos de gabarito indicados como `path` e intervalo de linhas.

Escreva as perguntas e o gabarito **antes** de ver o que o sistema responde. Ajustar o gabarito ao que o sistema acerta invalida a medição. Se houver mais de uma pessoa disponível, peça a uma segunda que revise os trechos.

## 3. Recuperação (sem LLM, roda em CI)

```bash
TARGET_REPO=repos/<projeto> scripts/run_retrieval_eval.sh
```

Reporta recall@k e MRR para BM25, vetor, híbrido e híbrido + grafo. Um acerto é qualquer chunk recuperado que **sobrepõe** o trecho do gabarito. Use isso para justificar (ou revisar) as decisões do ADR-002.

## 4. Respostas

```bash
legacylens eval eval/gold.jsonl --answers
```

| Métrica | Significado |
|---|---|
| `citation_correct` | Alguma citação válida cai sobre o trecho do gabarito |
| `invalid_citation_rate` | Respostas com citação fora da evidência enviada |
| `abstention_correct` | Perguntas sem resposta em que o sistema disse que não sabe |
| `false_abstention` | Perguntas com resposta em que o sistema se recusou |

O que `citation_correct` **não** mede: se o texto da resposta está certo. Para isso, avalie uma amostra manualmente e reporte o tamanho dela. Se usar um LLM como juiz, informe o modelo e confira uma parte à mão.

## 5. Geração de testes

Escolha de 15 a 30 funções do módulo e, para cada uma, registre:

- passou de primeira (sim/não) e número de tentativas;
- cobertura e mutation score do teste gerado;
- os mesmos dois números para os testes humanos que já existem no módulo, se existirem.

Pontos de cuidado: o modelo pode ter visto os testes humanos do projeto no treinamento, e testes gerados por "ajuste ao comportamento real" fixam bugs existentes. Reporte os dois fatos.

## 6. Onboarding (com e sem o assistente)

Com 10 perguntas típicas de quem chega ao projeto, meça o tempo para responder e a taxa de acerto com citação correta, com e sem a ferramenta. É um estudo pequeno: informe quantas pessoas participaram, e não generalize além disso.

## 7. Custo e latência

`LEGACYLENS_PRICE_IN` e `LEGACYLENS_PRICE_OUT` (USD por milhão de tokens) fazem o `telemetry.jsonl` incluir `cost_usd`. Sem preços, o campo fica nulo. Reporte mediana e p95 de latência.
