# Claude web demo status

The earlier Claude web connector used a temporary Cloudflare HTTPS tunnel to a local HTTP MCP service on port 4181. It used a separate shared demo token and was successfully tested with the earlier `search_web_products` tool. A tunnel address can change after restart. Do not publish the complete credential URL.

The current MCP server has 12 research tools and removes reservation actions. Claude caches tool schemas; in Claude Connectors, open AgentGate and choose **Refresh tools list** before testing. The tunnel and local gateway must be running. The current 12-tool version has not yet been validated in Claude, and the previous local server sessions are no longer confirmed running.

A stable hosted per-user Claude web connector remains unfinished. The prepared account API issues personal bearer tokens, but Claude web may require OAuth rather than a manually configured bearer header. Do not present the local tunnel as a production integration.
