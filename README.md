# AgentGate — evidence-backed product research

AgentGate searches public product pages at Adafruit, Arduino and SparkFun, then builds a private shortlist with source links and captured prices. It remembers a budget, preferred brands, intended use, condition and requirements. It marks stock as a source-reported snapshot, leaves shipping/tax totals unknown unless explicitly evidenced, and refuses to convert currencies or call similar titles the same product.

## Run locally (Windows)

From this directory:

```powershell
powershell -ExecutionPolicy Bypass -File start.ps1
```

Open [http://localhost:4180](http://localhost:4180). Python 3.11+ is required. The first run creates a virtual environment and installs locked dependencies. The app works without an AI key. Ollama is optional legacy code and is not needed for product research. You may use the local demo identity or create a username/password account for a separate shortlist. Do not put real secrets in chat; edit `.env` on your machine if needed.

## Demo

1. Search **Arduino Uno Rev3**. The app reads available product pages from three retailers, displays each source and captured timestamp, and reports an unavailable source explicitly. Store behavior can change; if a search yields no pages, paste a public product URL into the preview field.
2. Set a EUR or USD budget and save preferences such as Arduino, learning electronics, and new condition. Save selected results to the shortlist. Search results start as drafts and are not saved automatically.
3. Compare the shortlist. Distinct currencies stay separate; a missing manufacturer identifier leaves cross-store identity unverified. The lowest listed price is a price observation, not a purchase recommendation. A “from” price is not treated as a definite variant price.
4. Refresh one source, remove it, use Undo, and export the JSON evidence report. The source link remains available for checking current stock, shipping, taxes and final checkout total.
5. If using MCP, refresh the tool list in the client after updating AgentGate. `search_web_products` discovers products; `browse_catalog` shows saved references only. The 12 current tools have no reservation or checkout action.

The extractor reads public HTTPS pages under robots.txt, enforces bounded fetches, and blocks private network addresses. Some sites block crawlers or render products with JavaScript. Search coverage is the three named retailers, not the whole web. No live stock feed, final checkout total, payment, or universal exact-match guarantee is claimed.

## MCP

Use `mcp-config.example.json` as a template for a local stdio client. A signed-in user can create a 90-day revocable personal token in the Account panel and put it in `AGENTGATE_PERSONAL_TOKEN` in their **local** `.env`. Set `AGENTGATE_URL` to localhost or the future HTTPS deployment. Never place that token in a URL or public repository. Existing Claude web demo uses a temporary tunnel with a separate shared demo token; it is not the hosted per-user configuration.

## Render free deployment alternative

`render.yaml` now defines one free Python web service and one free Render PostgreSQL database. Render reads `.python-version` to use Python 3.12. Put this folder at the root of a GitHub repository, sign in to Render, choose **New > Blueprint**, connect the repository and deploy the Blueprint. Render will provide the database URL to the web service. The Render account and GitHub repository are not connected here, so no Render deployment or URL has been verified. The free database expires after 30 days and the idle web service may take about a minute to wake. See [Render's free-tier documentation](https://render.com/docs/free).

## Hosting status

The app is prepared for Vercel FastAPI with Python 3.12 and requires a persistent PostgreSQL `DATABASE_URL` when `VERCEL` is present. It refuses to start a cloud instance without that database, so accounts and research are never silently stored in an ephemeral file. The Vercel project `snehnada123s-projects/agentgate-research` now exists and is linked to this folder. A free Neon install and deployment are **not complete**: Vercel continues to return `integration_terms_acceptance_required`, and the acceptance URL opens at a signed-out browser session. The owner must sign into Vercel and accept the Neon marketplace terms for this team. No hosted URL is verified. The HTTPS MCP path with personal tokens also needs a full hosted protocol test before release.

## Verification

`python -m unittest test_core test_comparison test_importer test_marketplace test_search test_research -v` runs the tests that do not need Windows local socket access. 28 passed in this environment. Python modules compile and `research.js` passes `node --check`. API and MCP protocol integration tests could not be run in the restricted sandbox because Windows asyncio could not create its local loop socket and automatic approval review rejected the unsandboxed retry. This limits the validation claim; run `python -m unittest discover -v` in a normal terminal before presenting a hosted demo.

