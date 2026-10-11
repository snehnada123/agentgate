# Verification record

- Pure local tests: 28 passed (`test_core`, `test_comparison`, `test_importer`, `test_marketplace`, `test_search`, `test_research`). These include owner isolation, token revocation, source deduplication, removal and restore, price refresh history, source-reported stock labeling, manufacturer identifier matching, and uncertain variant price handling.
- Python compilation of application/MCP/search modules: passed.
- Browser JavaScript syntax check: passed.
- Earlier live public-page checks read Arduino Uno Rev3 and SparkFun Arduino Uno R3 listings. Their EUR and USD prices were kept separate and must be refreshed before use.
- Earlier Claude test successfully invoked AgentGate `search_web_products` after the connector's tool list was refreshed. This was before the current 12-tool update; revalidation is required.
- API/MCP integration tests and a fresh browser walkthrough remain unverified for the latest changes because the restricted Windows environment cannot create the asyncio socket required by the test runner. An unsandboxed retry was rejected by automatic approval review due to a usage limit.
- Vercel project `snehnada123s-projects/agentgate-research` exists and is linked. Team storage is empty. Neon still returns `integration_terms_acceptance_required`; no deployment or hosted URL is available.

- Render Blueprint (`render.yaml`) prepared with free Python service and free PostgreSQL. Not deployed: Render browser session is signed out, and no AgentGate GitHub repo is available.
