# STOXRA Instagram publisher

An isolated Python worker for this Next.js/Supabase repository. It adds daily feed publishing without changing the existing inbox, comment automations, OAuth routes or database tables. This is a tested implementation candidate, **not a verified live deployment**. No real account has been published to during development.

## Architecture and delivery checklist

- [x] Stage 1: reproducible local fixture → policy checks → Pillow JPEG carousel → review manifest.
- [x] Stage 2: structured OpenAI generation, independent evidence check, rotating topics and duplication checks.
- [x] Stage 3: Supabase public media, private durable post state, official Instagram Login publishing adapter.
- [x] Stage 4: approval digests, concurrency locks, bounded retries, quota/token checks, failure alerts and tests.
- [ ] Add approved official logo and confirm typography/brand baseline.
- [ ] Apply SQL and configure GitHub Secrets/environment protection in a writable STOXRA fork.
- [ ] Confirm Meta version, account permissions, app access/review and token expiry.
- [ ] Run a controlled real-account test; check caption, slide ordering, alt text and persisted IDs.
- [ ] Review first posts, then deliberately enable unattended publication if desired.

Flow: daily Actions run → account lock → existing post lookup → topic/evidence → OpenAI generation → deterministic validation → independent model evidence check → template render → public JPEG preflight → durable draft → optional approval → token/account/quota check → container creation/readiness → persisted publish intent → one publish call → persisted Instagram ID.

The calendar rotates financial education, trading psychology, risk management, paper trading, AI mentor, STOXRA product education and algo trading using the IST calendar date. Recent captions/slide text are provided to the generator; exact hashes and normalized near-duplicate matching block repetition against the latest two hundred records. A duplicate blocks the run and alerts; it does not silently publish a replacement.

## Run the working example (no credentials, no remote writes)

From the repository root, with Python 3.12:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r automation/requirements.txt
PYTHONPATH=automation python -m pytest automation/tests -q
PYTHONPATH=automation python -m stoxra --mode dry-run --example automation/examples/post.json --date 2026-01-03
```

The fixture date maps to risk management. Output is `automation/output/manifest.json` and two **1080×1350 JPEGs**. Preview branding is explicitly marked until an official logo is supplied. No image generation model is used. Without `--example`, dry-run calls OpenAI and needs its key/model, but still performs no storage or Instagram writes. Dry-run has no persistent history; live runs use Supabase.

## Brand and factual evidence

Edit `automation/config/brand.json`. Add the official transparent PNG at `automation/assets/stoxra-official.png`; do not substitute an invented logo. Live generation refuses a missing logo. The default DejaVu Sans font is available on Ubuntu Actions runners; for other systems configure an installed font or commit a properly licensed font and attribution. Layouts use restrained white, black, purple and orange. Text overflow fails rather than clipping.

`config/facts.json` is an **editorial baseline**, not independently retrieved market research. An owner must review its statements and sources, add approved product facts and their source records, and set `STOXRA_EDITORIAL_BASELINE_APPROVED=true`. Each record has an expiry date. Product-topic posts stay generic until real product capabilities have approved evidence. Update evidence before it expires; expired/unknown evidence blocks publication.

The worker intentionally blocks numbers, currency/percent claims, links, mentions, stock calls and common guaranteed-return language. This first version does not automate live market commentary, investment recommendations or quantitative claims. OpenAI's separate evidence check can still make mistakes; regex checks and source IDs do not prove truth. Human approval defaults to on. No feature availability, subscriber count, pricing or return claims are inferred from memory.

## Set up durable state and public media

Use a hosted Supabase project (`https://PROJECT.supabase.co`). Apply `automation/schema.sql` manually in its SQL editor. It creates isolated RLS-protected records accessible only to the backend service role and a public JPEG-only `stoxra-media` bucket. If a bucket with that name already exists, verify it is public and restricted to JPEGs; `ON CONFLICT` does not change existing bucket settings.

Public media contains only rendered educational graphics. Drafts, account IDs, approval records and tokens must never be uploaded there. Keep media publicly available through publishing and recovery. The service-role secret bypasses RLS: prefer a dedicated project for this worker, restrict access to the GitHub environment, and never expose it to frontend variables. This adapter intentionally accepts hosted Supabase origins only; custom domains/self-hosted storage need a reviewed adapter change.

## Meta setup (Instagram Login only)

Use an Instagram Business or Creator account and a Meta app configured for **Instagram API with Instagram Login**. Grant `instagram_business_basic` and **`instagram_business_content_publish`** through the official OAuth flow. The existing app's messaging/comment scopes alone are insufficient for publishing. This worker takes a separately provisioned token and does not modify the existing OAuth implementation.

Follow official Meta docs for account eligibility, tester roles, Standard/Advanced Access, App Review and Business Verification as applicable. Obtain the professional account `user_id` and a valid long-lived Instagram user token. Do not use a personal-account password, browser cookies, Facebook Login token or unofficial endpoint. Select a supported Graph version for your Meta app and put it in `META_API_VERSION`; the worker never guesses an unversioned endpoint.

Before publishing, the worker checks `/me` against the account ID and queries `/content_publishing_limit`. Images use public JPEG URLs and per-slide `alt_text`. Carousels use child containers followed by a parent. Every container must reach `FINISHED` before publication. Scope and entitlement errors are rejected by Meta and fail closed.

Set `INSTAGRAM_TOKEN_EXPIRES_AT` from the real official token-exchange response (UTC ISO-8601). A token within seven days of expiry blocks publishing. The `/me` call also catches revoked tokens. Token refresh is intentionally operator-managed: use Meta's official refresh/exchange flow, rotate the GitHub secret and update expiry together. The system never invents an expiry or writes a refreshed token to artifacts. An inaccurate configured expiry is not a substitute for valid Meta authorization.

Official references (verify account/version details during setup):

- https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login
- https://developers.facebook.com/docs/instagram-platform/content-publishing
- https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/business-login
- https://developers.openai.com/api/docs/guides/structured-outputs

Meta documentation retrieval returned HTTP 429 during implementation; the API adapter still needs a real account contract test before release.

## GitHub setup

Use a writable STOXRA fork/branch. The original upstream repository was readable but not writable by the connected account during development. Do not put STOXRA secrets into an upstream maintainer's repository.

Create a GitHub environment named `stoxra-publishing`. Restrict deployment branches and optionally require trusted reviewers (availability depends on GitHub plan/repository visibility). Protect the default branch and workflow files. Never enable credential-bearing jobs for untrusted code. Pull request checks use no secrets; workflows do not use `pull_request_target`. Scheduled workflows execute from the default branch after merge.

Configure secrets from `automation/.env.example`:

| Actions Secret | Purpose |
| --- | --- |
| `OPENAI_API_KEY` | Project-scoped OpenAI key with budget/rate limits |
| `PUBLISH_SUPABASE_URL` | Dedicated hosted Supabase origin |
| `PUBLISH_SUPABASE_KEY` | Backend service-role key; keep private |
| `INSTAGRAM_ACCOUNT_ID` | Target professional account's `user_id` |
| `INSTAGRAM_ACCESS_TOKEN` | Official Instagram Login publishing token |
| `INSTAGRAM_TOKEN_EXPIRES_AT` | Actual UTC token expiry |

Configure repository/environment variables:

| Variable | Default / meaning |
| --- | --- |
| `OPENAI_MODEL` | Required: your supported structured-output model |
| `META_API_VERSION` | Required: supported explicit version, e.g. `v24.0` |
| `STOXRA_ENABLE_LIVE` | `false`; enable only after reviewing setup |
| `STOXRA_REQUIRE_APPROVAL` | `true`; set explicitly to `false` for unattended publication |
| `STOXRA_EDITORIAL_BASELINE_APPROVED` | `false`; owner must review evidence first |

Daily cron is `30 4 * * *`, corresponding to **10:00 AM Asia/Kolkata**. GitHub scheduling is best-effort and can be delayed or disabled under GitHub's inactivity policies. If exact-minute execution is essential, use an external scheduler dispatching the same guarded worker. Repository workflow provides manual dry-run, prepare, publish and auto modes, with optional original IST date for recovery. With live disabled, scheduled runs use the deterministic no-credential example. Manual prepare/publish requests fail if live is disabled.

GitHub token permissions are `contents: read` for the worker; only the separate failure-alert job has `issues: write`. Alerts create an issue linking the failed run. Enable GitHub notifications for those issues. The alert job itself can fail if issues/permissions are disabled; also enable Actions failure notifications. Logs omit request bodies, headers, query strings and raw exceptions; review artifacts contain only public post metadata/media URLs. Actions are pinned by commit; review dependency/action updates periodically. Direct Python versions are pinned; resolve/hash transitive dependencies against your organization's package registry before regulated deployment.

## Human approval

With approval enabled, `auto` prepares and stores the draft and then exits without publishing. Review the manifest, caption, every image URL, alt text, policy evidence and the exact `review_digest` in Supabase. The digest binds account, post key, text, approved evidence, URLs and JPEG hashes. Evidence edits invalidate the draft. Approve only the reviewed bundle using a parameterized administrative operation or the SQL editor:

```sql
update public.stoxra_posts
set approved_digest = review_digest
where post_key = 'ACCOUNT_ID-YYYY-MM-DD'
  and review_digest = 'PASTE_REVIEWED_DIGEST_HERE'
  and status = 'prepared';
```

Then manually dispatch `publish` with the **same original date**. Approval does not expire automatically, but evidence expiry is rechecked. Public bytes are re-hashed before publication to detect changed media. For unattended operation, explicitly set `STOXRA_REQUIRE_APPROVAL=false`; editorial approval and all technical guards still apply. Environment required reviewers are a separate gate, before the job, not a replacement for reviewing the generated bundle.

## Idempotency and recovery

A unique account/date key prevents reruns from regenerating that day's stored content. A unique account/content hash prevents exact duplicate records. A durable per-account lock serializes runs across hosts; GitHub concurrency also prevents overlapping workflow runs. Do not bypass either guard.

States are `prepared` → `container_ready` → `publishing` → `published`. Child IDs and the parent container ID are checkpointed. A completed post is a no-op on rerun. GET requests and idempotent storage/state writes have bounded backoff; Retry-After seconds are respected up to sixty seconds. OpenAI generation and Meta container creation are not automatically retried because they can create billable/remote resources. An interrupted container creation can leave an orphan container, but cannot publish by itself. Publish mutations are **never automatically retried**.

The publish intent is committed before sending `/media_publish`. If its response or the following database save fails, state stays `publishing`. The next attempt stops for operator reconciliation. Inspect the saved container status and account media in Meta; if publication succeeded, persist its real media ID and mark `published`. If the container is still `FINISHED` and you have independently confirmed no published post exists, an operator may restore `container_ready` and rerun with the same date. Never reset a `PUBLISHED` container for republishing. Expired/error containers need deliberate operator replacement, not an automatic second post.

If a runner is killed before its `finally` cleanup, the lock remains. First ensure all publisher processes have stopped, inspect post/container state, reconcile any ambiguous publication, then remove only that account's stale lock:

```sql
delete from public.stoxra_publish_locks where account_id = 'ACCOUNT_ID';
```

No lock lease auto-expiry is intentional: stopping for an operator is safer than a second active publisher. Monitor stale locks and investigate failure alerts. Keep Supabase backups and audit administrative approval/recovery changes.

## Validation and release acceptance

Tests cover rotation, invalid/expired claims, near duplicates, rendering, missing logos, overflow, approval binding, successful carousel persistence, saved-container resume, timeout safety, retries, storage-origin restrictions and token expiry. These mocks establish worker behavior, not Meta acceptance. Existing Next.js application behavior was not changed or regression-tested.

Before calling the system production-ready: execute SQL in staging; prove concurrent lock conflict and RLS denial for anon/authenticated; verify public bytes without authentication; run OpenAI generation against the selected model; test token/account/quota responses; approve and publish one controlled carousel, then a single image; inspect alt text and ordering in Instagram; rerun to prove no duplicate; simulate a response loss and reconcile; verify alert delivery. Save real post/container IDs and run URLs as release evidence. **No successful live posting is claimed until those checks pass.**
