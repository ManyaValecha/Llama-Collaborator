# Three-minute demo: Build, Debug & Learn

## Before recording

- Start the backend from `backend/` and open `http://127.0.0.1:8000`.
- Confirm the provider badge says configured. A live run sends the bundled sample source and prompt to OpenRouter and may incur usage charges; it makes several specialist calls.
- Keep the model key in local `backend/.env`. Never show the key, environment file, or terminal environment in the recording.
- Use a fresh browser session or clear only the demo conversation if you want a clean opening state. The guided decision remains in local SQLite after the first run.

## Talk track

**0:00–0:20 — The problem**

“A normal coding chatbot forgets why a team chose an approach and explains every answer at the same level. Llama-Collaborator routes an engineering task through specialists, checks active project decisions, and changes explanation depth based on the developer.”

**0:20–0:40 — Start the reproducible scenario**

Click **Run guided demo**. Point out that it loads an intentionally flawed local Python fixture and seeds a labeled security invariant. The task says the developer is new to backend development. This sample and request are sent to the configured provider; no workspace changes happen at this step.

**0:40–1:20 — Show collaboration and memory**

Walk through the live workflow card and agent control room. The route, context signals, role outputs, matching decision, and citations are rendered from the API response. Show the decision graph and validator summary. Explain that a role's critique is not a test result.

**1:20–1:45 — Show adaptation**

Point out that “I am new” lowers the effective explanation level for this turn without silently rewriting the saved preference. Click **Too complex** on the response; the saved setting adjusts for later tasks. The slider remains directly editable.

**1:45–2:25 — Show a controlled code action**

Use the selected fixture's **Draft an approved code patch** button. Confirm that the selected file and task will go to the provider. Review the full diff before showing the separate **Approve & apply patch** action. If recording a live application, restore the intentional fixture afterward.

**2:25–2:45 — Show evidence boundaries**

Run the approved Python syntax check. Read out the exact status, number of files parsed, and scope. Say explicitly that this is a syntax parse, not a unit test or runtime test. Docker provides network-disabled read-only isolation when available; otherwise the app uses a clearly labeled non-executing local AST parse.

**2:45–3:00 — Close**

“The differentiator is the connected loop: a routed task uses durable engineering memory, adapts to the developer, proposes a reviewable action, and reports only evidence it actually collected. The current MVP is local-first; full browser control, hosted multi-user access, and general-purpose code execution are future work.”
