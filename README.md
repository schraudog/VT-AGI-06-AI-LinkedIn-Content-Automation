# FinEdge LinkedIn content automation

This prototype combines an AutoGen-inspired FastAPI service with an n8n workflow.
Three sequential model roles generate ideas, select and draft a post with a
confidence estimate, and suggest hashtags. This is role-based orchestration,
not the AutoGen framework. The workflow composes the post, records the decision,
and routes it to Slack for review or to LinkedIn.

## Architecture and safeguards

`Schedule → Brand Config → AutoGen Microservice → Compose Final → Log Run → Approval Gate`

The gate routes to LinkedIn **only** when `dryRun` is the boolean `false` and the
numeric confidence is at least the numeric threshold (both in the range 0–1).
Otherwise it routes to Slack. The imported workflow is inactive and `dryRun`
defaults to `true`. Slack is a notification for manual review; it does not
provide an approval button or automatically publish reviewed posts. Review,
edit, and publish those posts separately. The live path is an automated
threshold decision, not human approval.

The model's self-assessed confidence is not calibrated and cannot verify facts,
regulatory compliance, or brand safety. For a fintech organization, keep
`dryRun` enabled and have a qualified human check every post, particularly
claims, financial advice, privacy, and regulatory requirements. Only enable
automatic publishing if the organization explicitly accepts that risk and
adds its own review/compliance controls. Inputs and generated output are sent to
the configured OpenAI model; do not include sensitive or customer data.

## Ubuntu setup

1. Install Python 3.11+ and its venv package, and a Node.js version supported by
   the current [n8n installation instructions](https://docs.n8n.io/hosting/installation/npm/).
   For example, install `python3`, `python3-venv`, and `python3-pip` using apt,
   and install a supported Node.js release using your organization's approved
   method. Install a current, patched n8n: `npm install -g n8n`.
2. From the repository directory:

   ```sh
   python3 -m venv .venv
   . .venv/bin/activate
   pip install -r requirements.txt
   cp .env.example .env
   ```

3. Set `OPENAI_API_KEY` in `.env`, optionally set `OPENAI_MODEL` and
   `RUNS_DB_PATH`, then load it into the service process and start the API:

   ```sh
   set -a; . ./.env; set +a
   uvicorn main:app --host 127.0.0.1 --port 8000
   ```

   `/linkedin` uses OpenAI's chat completions API with JSON mode. The configured
   model must support that API and JSON mode. The API key remains on the service;
   it is never included in the workflow export.
4. In a separate shell, start `n8n`, open its local dashboard, and import
   `workflow.json` using **Import from File**. This assumes n8n and the service
   run on the same host. If n8n runs in a container, `127.0.0.1` refers to that
   container: update both HTTP node URLs to a private, reachable service address.
   The service has no authentication; bind it to loopback or protect it with
   network isolation and an authenticated TLS reverse proxy. Do not expose it
   directly to the internet.

## Configure the workflow

1. Set the schedule and workflow timezone as needed (the export uses 10:00
   daily, Asia/Kolkata). Edit Brand Config's `name`, `voice`, `audience`,
   `context`, `threshold`, and `dryRun`. Provide current, verified context
   yourself; the service does not browse for trends. Start with `dryRun=true`.
2. Create a Slack incoming webhook for a private review channel. Replace the
   placeholder URL in **Send to Slack Review** in your private n8n instance.
   The webhook URL is a secret: do not commit or share an export containing it.
   Restrict access to n8n, its execution data, and the Slack channel.
3. For live posting, configure **Publish to LinkedIn** with n8n LinkedIn OAuth
   credentials and the authorized person or organization identifier. Select
   the appropriate **Post As** option and confirm the account has permission
   to post. See [n8n's LinkedIn node documentation](https://docs.n8n.io/integrations/builtin/app-nodes/n8n-nodes-base.linkedin/).
   Never export credentials or tokens. The node is deliberately unconfigured
   and disabled in the supplied export so that dry runs do not require LinkedIn
   credentials. Enable it only when the live branch is ready and authorized.
4. Save the workflow. Use manual executions before activating the schedule.
   Set `dryRun=false` only after review and explicit authorization for the
   automated live path. The default threshold of 0.85 is illustrative, not a
   measured or validated safety threshold.

## Test and operate

With the service running and an API key configured, exercise the endpoint:

```sh
curl -sS -X POST http://127.0.0.1:8000/linkedin \
  -H 'Content-Type: application/json' \
  -d '{"brand":{"name":"FinEdge Mumbai","voice":"clear and professional","audience":"fintech leaders"},"context":"Digital payments education; avoid unsupported claims."}'
```

The response contains `ideas` (3–5 strings), `draft`, `confidence` (0–1), and
`hashtags` (1–8 strings). `/docs` provides the full API schema. A missing key
returns 503; an unavailable provider or invalid model output returns 502. An
invalid request returns 422. Calls are bounded by a 45-second per-agent timeout
and fail rather than publishing partial output.

For automated service tests (the test client needs httpx):

```sh
pip install httpx==0.28.1
python -m unittest discover -s tests -v
```

In n8n, execute Brand Config and the HTTP node, then execute Compose Final and
inspect the text and score. Execute the whole workflow with `dryRun=true` and
verify that Slack receives the draft and LinkedIn is not called. Also test a
score below the threshold with `dryRun=false`: it must go to Slack. Test the
high-confidence live branch only with an authorized test account and explicit
permission to publish. Inspect each node's input/output and the execution
history; never infer delivery solely from the generated score.

**Log Run** appends the server timestamp, n8n execution ID, final text,
confidence, and selected route to the SQLite `runs` table at `RUNS_DB_PATH`.
Inspect it, for example:

```sh
sqlite3 runs.sqlite3 'SELECT timestamp, execution_id, confidence, route FROM runs ORDER BY id DESC LIMIT 10;'
```

The record describes the *intended* route, not delivery success. Check n8n
execution history and Slack/LinkedIn for delivery results. The HTTP and delivery
nodes stop the execution on errors; a logging failure prevents either branch.
Use n8n error workflows/alerts in production, protect and back up the database,
and set an appropriate retention policy for the database and n8n execution
history. Do not retry a failed or uncertain LinkedIn delivery blindly: it may
have succeeded and a retry could create a duplicate post.

### Troubleshooting and verification record

* **503**: set the API key in the shell that starts uvicorn.
* **502**: check provider availability, model access, and service logs; invalid
  model JSON is deliberately rejected. No model response or key is logged.
* **Connection refused**: check both processes and the two service URLs; in a
  container, use the service's reachable private address instead of localhost.
* **Slack/LinkedIn node error**: check the webhook or OAuth permissions, account
  identifier, and n8n execution details. Review delivery before retrying.
* **Database error**: ensure the service can write to the database directory.

The automated tests use a mocked model provider and a temporary SQLite database;
they verify response composition, validation, provider failure, and logging.
The workflow was imported into n8n 2.48.7. For a CLI smoke test, a temporary
copy used an Execute Workflow trigger and local mock endpoints: the dry run
completed, logged `review`, and delivered the composed text to mock Slack.
With the real local service and no API key, execution stopped at the service
with 503 before logging or delivery. These are not live integration tests.
Live OpenAI generation and Slack/LinkedIn delivery require credentials and an
operator's environment. Capture screenshots of the successful service response,
n8n execution, and Slack review in that environment for submission; no successful
external integration or screenshots are claimed by this repository.

## Design trade-offs

Separate model roles make each stage inspectable, but require three provider
calls and increase latency and cost. Structured validation and fail-closed
errors prevent malformed results from reaching the gate, but cannot eliminate
hallucinations or prompt injection. SQLite gives a simple local audit trail but
is not a delivery ledger or a replacement for centralized monitoring. Dry-run
review favors oversight over hands-off publishing; confidence thresholds should
only be tuned against reviewed outcomes, not assumed to guarantee quality.
