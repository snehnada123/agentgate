# AgentGate MCP

The local stdio server exposes 12 shopping research tools. Run the gateway first with `start.ps1`, then configure an MCP client to launch `mcp_server.py` with your Python environment as shown in `mcp-config.example.json`. Refresh the client's tool list after an update; Claude can cache an older schema.

`search_web_products` searches three public electronics retailers. `preview_public_product` handles an individual public HTTPS URL. `save_external_reference` adds a reviewed draft to your private shortlist. `browse_catalog` reads only the saved shortlist. `compare_product_shortlist` checks listed price, currency, product identity evidence and missing totals. Profile, remove, restore, refresh, and export tools complete the research flow. No reservation, checkout, payment or seller operation is exposed.

A local account can create a revocable 90-day token from the Account panel. Set `AGENTGATE_PERSONAL_TOKEN` in a private `.env` file for the stdio server; the server sends it as a bearer header. Without that token, it uses the shared local demo key. Tokens should never be placed in a connector URL.

The separate `mcp_http.py` is a temporary **shared local demo** adapter. It uses `AGENTGATE_REMOTE_TOKEN` and is not a deployed per-user connector. Do not submit its credential URL publicly. Hosted personal-token MCP transport has not been validated.
