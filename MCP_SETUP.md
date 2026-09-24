# Integração MCP — Legal Research API

Implementação preparada para as seis operações REST existentes via MCP Streamable HTTP em `/mcp`. A API REST continua com Bearer e o mesmo contrato. O adaptador reutiliza a `API_KEY` somente dentro do processo; nenhum valor de credencial integra código, plugin ou documentação.

## Estado

Código testado localmente. Não ativado em produção: falta configurar um emissor OAuth 2.1 para a conexão privada. Sem configuração completa, `/mcp` responde 503 e não libera ferramentas. A chave REST não é aceita como token OAuth.

## Autenticação necessária

Usar um provedor estabelecido compatível com MCP (por exemplo, Auth0), com autorização por código, PKCE S256, discovery OAuth, registro de cliente compatível com o ChatGPT (DCR ou CIMD), tokens RS256 e escopo `legal:read`. Configurar o callback exato exibido pela interface do ChatGPT. A emissão deve preservar o parâmetro `resource` como audiência do token. Não usar cadastro aberto como autorização: somente o `sub` do proprietário é aceito pelo servidor.

Definir no Render, sem inserir valores em commits ou chats:

| Nome | Conteúdo esperado |
| --- | --- |
| `API_KEY` | Manter a credencial REST já existente |
| `MCP_OAUTH_ISSUER` | Issuer HTTPS exato do provedor, incluindo barra final se houver |
| `MCP_OAUTH_JWKS_URL` | URL HTTPS das chaves públicas oficiais do emissor |
| `MCP_RESOURCE_URL` | `https://legal-research-api-i2s4.onrender.com/mcp` |
| `MCP_OWNER_SUBJECT` | Identificador `sub` da conta do proprietário no provedor |

Apenas URLs e identificador público são exigidos pelo resource server. Segredos de cliente, se necessários, ficam na configuração segura do provedor/ChatGPT, nunca no plugin.

## Deploy e validação

1. Configurar o provedor e o cliente de login.
2. Executar `python -m pip install -r requirements.txt` e `python -m pip install pytest==9.1.1`, depois `python -m pytest -q`.
3. Definir as variáveis acima no Render. Não alterar seu start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`.
4. Integrar a branch revisada à main (Render faz deploy automático).
5. Confirmar que as rotas REST continuam autenticadas; `/mcp` sem token deve responder 401 e indicar os metadados OAuth.
6. Verificar `/.well-known/oauth-protected-resource/mcp`, completar login como proprietário e testar initialize, tools/list e tools/call para as seis operações.
7. Somente após o endpoint existir e o login funcionar, atualizar o plugin privado adicionando o servidor Streamable HTTP real em `mcp.json`. Preservar documentos, habilidades e prompts.

O provedor valida identidade; o adaptador valida assinatura, algoritmo RS256 fixo, issuer, audiência, expiração, emissão, escopo e sujeito autorizado. Chaves públicas são obtidas somente da URL configurada, nunca de URL fornecida no token. Tokens e cabeçalhos não são registrados pelo adaptador.

## Compatibilidade e limites

getHealth, listSources, listAreas, searchLegalContent, searchLegislation e searchJurisprudence preservam parâmetros e limites existentes. Testes usam exclusivamente chaves sintéticas. As datas dinâmicas de resposta podem variar entre chamadas.

A integração não transforma o catálogo estático em pesquisa atualizada. A API mantém 14 normas cadastradas e links de portais de jurisprudência; não contém base de acórdãos. Filtros e limitações originais estão preservados. Os documentos privados do plugin não são enviados ao repositório.

## Reversão

Reverter o commit de integração e redeploy mantém a versão REST anterior. Remover apenas a configuração OAuth desativa MCP com resposta 503, preservando REST. Não remover nem alterar API_KEY durante a transição.

## Referências

- https://developers.openai.com/plugins/build/auth
- https://github.com/modelcontextprotocol/python-sdk
