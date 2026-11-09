# Add guarded STOXRA daily Instagram publishing worker

The existing app automates Instagram conversations but has no daily feed-content pipeline. This change adds an isolated Python worker that rotates educational topics, generates structured captions/alt text, renders branded JPEG carousels, stores reviewable drafts in Supabase and publishes through the official Instagram Login API.

Live mode defaults off. Human approval defaults on and binds text, account, evidence, media URLs and JPEG hashes. Durable per-account locks and saved container IDs support recovery; an uncertain publish response requires operator reconciliation instead of a second publish call. GitHub Actions schedules 10:00 IST execution, provides manual dispatch and creates failure-alert issues with narrowly scoped permissions.

Validation: 30 tests passed; credential-free two-slide example rendered at 1080×1350; Python compilation and git whitespace checks passed. Existing Next.js code is unchanged apart from a README link and was not regression-tested. No Supabase migration, OpenAI live request, Meta contract test or real Instagram post has been executed.

Before enabling: configure a dedicated Supabase project/schema and Actions secrets, add the official STOXRA logo, approve editorial sources, select supported OpenAI/Meta versions, confirm professional-account/app permissions, configure environment protection and complete the real-account acceptance checklist in automation/README.md. Meta docs retrieval was rate-limited during development; verify the adapter against the selected API version. This is a release candidate, not a verified live deployment.
