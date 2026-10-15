# Verificação de 15/10/2026

Produção: Legal Research API 4.1.1, commit 36d8942b0052063e25f5e840fc32fce68b89a802. Chamadas autenticadas pelo MCP, entre 10:05 e 10:09 (America/Sao_Paulo).

## Resultados efetivos

- As seis operações MCP responderam após a reconexão OAuth. Antes dela, o Render registrou HTTP 401; isso não era falha da Câmara ou do STJ.
- Câmara: Lei 13.019/2014 recuperada em HTML, com 93.003 caracteres e SHA-256 10d75f8be0ebb087a6f8ef8c8184bbc5e53f33207e235f0066c29fff04ae5668. Primeira chamada sem cache; consultas 13.019 e 13019 reutilizaram cache declarado.
- Câmara: Lei 14.133/2021 recuperada em PDF oficial, 271.202 caracteres, sem cache na chamada.
- STJ: índice ready, 20 lotes, soma de 14268 registros por lote (não equivale à contagem de processos únicos). Busca por imunidade tributária entidades beneficentes retornou AgInt no REsp 2268006 (record_id 1456956) e AgInt no REsp 2209237 (record_id 1451433), com ementa e decisão. Inteiro teor não recuperado; cobertura histórica parcial.
- Consulta aleatória sem correspondência retornou vazio. precedent_only=true para tributário retornou vazio dentro da cobertura; não houve atribuição fictícia de precedente.
- STF, CNJ e TCU retornaram source_unavailable. A implementação atual não faz busca documental nessas três fontes; a mensagem de 403 do STF representa uma validação anterior, e não uma nova requisição desta chamada MCP.

## Logs do Render e limites

Foi acessado o serviço srv-d7h8sm37uimc73d7kif0 e confirmada a implantação 36d8942. O plano disponível oferece sete dias de logs; o deploy foi indicado como ocorrido nove dias antes. A busca por camara nos sete dias não mostrou registros. O código publicado reduz falhas de DNS, conexão, tempo e formato à mesma mensagem e não registra a exceção de origem. Portanto, não é possível atribuir retrospectivamente a causa da falha da rodada anterior. Os testes atuais passaram sem mudança de rede ou de autenticação do servidor.

## Acesso oficial e integrações pendentes

- STJ: https://dadosabertos.web.stj.jus.br/ informa expressamente acesso automatizado pela API CKAN. O catálogo e um lote JSON também foram baixados diretamente na máquina do usuário, sem credenciais e sem contornar controles.
- TCU: https://sites.tcu.gov.br/dados-abertos/jurisprudencia/ disponibiliza CSVs oficiais e dicionário de dados, com atualização exibida de 02/10/2026. CSV de acórdãos de 2026: 308,50 MB; jurisprudência selecionada: 112,35 MB. Esse canal foi identificado, mas não foi indexado nem integrado à API. A carga integral exige planejamento de ingestão e armazenamento limitado; os CSVs de resumos de IA não substituem os documentos oficiais.
- STF: a consulta web a https://jurisprudencia.stf.jus.br/pages/search retornou HTTP 403 nesta rodada. Não foi contornado.
- CNJ: a consulta web à carta de serviços retornou HTTP 403 nesta rodada. Não foi validado endpoint público de recuperação documental de decisões do Conselho. DataJud não deve ser anunciado como substituto de acórdãos recuperados.

## Alteração proposta

official_http.py registra host, categoria controlada, classe da exceção e duração da falha, ou status HTTP. Não registra URL completa, parâmetros, corpo, token, cabeçalhos ou texto arbitrário da exceção. O cliente recebe categoria de erro adicional. Não há mudança de OAuth, lista de destinos permitidos, controle TLS ou política de acesso dos tribunais.

Validação isolada: 47 testes passaram, incluindo cinco novos casos de diagnóstico e sigilo dos registros. Execução em Windows com dependências da API instaladas em diretório isolado. Isso não substitui homologação das integrações pendentes.

Alteração preparada em branch própria; sem merge nem nova publicação em produção nesta rodada.
