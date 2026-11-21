# Decisões técnicas

Formato curto: contexto, decisão, o que se perde.

## ADR-001: chunking por AST, não por tamanho de texto

**Contexto.** Cortar código a cada N tokens separa assinatura de corpo e mistura funções vizinhas, o que prejudica tanto a busca quanto a citação de linhas.
**Decisão.** Um chunk por função ou método; a classe vira um cabeçalho até o primeiro método. Decoradores entram no chunk. O intervalo de linhas do chunk é o que aparece na citação.
**Custo.** Tamanhos muito desiguais: uma função de 400 linhas vira um chunk enorme. Aceito por ora, porque cortar no meio quebraria a citação. Um próximo passo é dividir funções longas por blocos de AST.
**Escolha de ferramenta.** Usei o módulo `ast` da biblioteca padrão. Para Python ele é exato e sem dependências. Para suportar outras linguagens, a interface `chunk_*_source(path, source) -> list[Chunk]` é pequena o bastante para ganhar uma implementação com tree-sitter.

## ADR-002: busca híbrida com RRF

**Contexto.** Perguntas de código citam identificadores exatos (`validate_payment`), onde BM25 é forte e embeddings falham. Perguntas por intenção ("onde se trata falha de rede?") são o oposto.
**Decisão.** Rodar os dois e fundir por Reciprocal Rank Fusion, que combina posições e dispensa calibrar escalas de score diferentes.
**Custo.** Duas buscas por consulta. O reranker padrão é uma heurística de identificadores, não um modelo; há um `CrossEncoderReranker` opcional.
**Verificação.** O `legacylens eval` roda os quatro modos (BM25, vetor, híbrido, híbrido + grafo) sobre o mesmo gabarito. Isso é a ablação que sustenta ou derruba esta decisão com dados.

## ADR-003: SQLite no lugar de Postgres/Qdrant

**Contexto.** O projeto precisa rodar com um comando e ser reproduzível por quem avalia.
**Decisão.** SQLite com FTS5 para BM25 e vetores em BLOB com busca por produto escalar em memória (numpy).
**Custo.** Não escala para milhões de chunks e não tem índice aproximado de vizinhos. A interface do `Store` é pequena; migrar para pgvector ou Qdrant significa reimplementar `search_bm25` e `search_vector`.

## ADR-004: grafo de chamadas por nome

**Decisão.** Registrar os nomes chamados em cada função e ligar por nome simples.
**Custo.** Sem resolução de tipos, nomes iguais em classes diferentes se confundem. O ganho é custo zero de análise e contexto útil na maioria dos casos. Vizinhos do grafo ficam sempre marcados (`via="graph"`) e abaixo dos resultados diretos.

## ADR-005: abstenção em duas camadas

**Contexto.** Responder com confiança sem evidência é a pior falha de um assistente de código.
**Decisão.** (1) O prompt manda dizer quando os trechos não bastam. (2) Um filtro lexical opcional (`LEGACYLENS_MIN_OVERLAP`) recusa antes de chamar o LLM se pouca coisa da pergunta aparece na evidência.
**Por que o filtro vem desligado.** Perguntas em português sobre identificadores em inglês quase não compartilham vocabulário, e o filtro recusaria perguntas boas. Ligue-o quando pergunta e código estiverem no mesmo idioma. Medir a taxa de abstenção correta e de falsa abstenção no gabarito é o que deve guiar esse ajuste.

## ADR-006: só entregar testes que passam e que verificam algo

**Decisão.** Rejeitar antes de executar testes sem `assert` ou `pytest.raises`, limitar tentativas e apagar o que falha.
**Motivo.** Um teste vazio passa e infla cobertura. Mutation score é a métrica de qualidade; cobertura é só informação auxiliar.
