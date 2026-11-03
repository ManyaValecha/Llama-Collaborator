# Devpost submission draft

## Llama-Collaborator — An Adaptive AI Engineering Partner

**Tagline:** A coding partner that remembers engineering decisions, adapts to the developer, and shows what it actually checked.

## Inspiration

Engineering copilots usually treat each prompt as a fresh chat and explain every answer at one fixed level. Llama-Collaborator brings together three ideas from the references: lifecycle memory for engineering decisions, adaptive knowledge support, and multimodal, approval-gated action. It uses an original implementation and interface.

## What it does

Llama-Collaborator turns an engineering request into a visible workflow. A small intent-and-context router selects specialist roles. The specialists pass notes forward, consult matching active decisions stored in SQLite, and return an evidence packet with their outputs and any provider citations.

The explanation coach adjusts to an explicit comfort setting, beginner/expert cues in the current request, and user feedback on whether the explanation was too complex, too simple, or helpful. A live decision ledger stores rationale, affected files, confidence, security relevance, review dates, dependencies, and supersession links. The UI renders saved decisions as a graph and flags broken references, cycles, and stale reviews.

Developers can attach source code or screenshots, use browser speech recognition for voice input, and ask for current technical research. Patch generation is a separate review flow: selected files are shown before they are sent to the provider, the exact diff is previewed, and applying it requires a second, single-use approval. A stale-file hash check prevents applying a diff after the source changes.

Verification is intentionally bounded. The current built-in check parses Python syntax. It uses Docker with a read-only, network-disabled workspace when available, and otherwise runs Python's AST parser locally without importing or executing project code. The interface never labels model critique as a test run.

## How we built it

- **Interface:** responsive HTML, CSS, and JavaScript engineering workspace.
- **Backend:** FastAPI with an inspectable Python router and role-specific handoffs.
- **Memory:** SQLite conversations, comfort profiles, structured project decisions, feedback, and validation.
- **Model:** OpenAI-compatible Responses API. The prepared configuration uses OpenRouter with Meta Llama 4 Maverick for text and image inputs, plus OpenRouter's search tool for research and security-review routes.
- **Action safety:** selected-file patch proposals, exact diff review, expiring one-time approval, hash checks, and bounded syntax evidence.
- **Continuous integration:** GitHub Actions runs the core tests and checks browser-script syntax.

The supplied credential is an OpenRouter key. It accesses a Meta Llama model through OpenRouter; it is not a Meta-hosted Model API key. If the event requires the Meta-hosted endpoint specifically, configure the corresponding Meta credential before submission.

## Signature demo

Click **Run guided demo**. The app loads a bundled Python fixture with two intentional token-claim defects, seeds a clearly labeled security invariant, routes the request through specialists, adapts to the user's beginner cue, and displays its real memory and verification state. The button sends the sample request and source code to the configured provider and may incur usage charges.

See [the complete three-minute demo script](demo-script.md) and [the architecture and trust boundaries](architecture.md).

## What is intentionally out of scope

This submission is a local MVP, not a hosted production service. It does not control arbitrary browser pages, run arbitrary shell commands, or provide multi-user access controls. The included verifier does not run unit or integration tests. These boundaries keep the demo's action and verification claims precise.
