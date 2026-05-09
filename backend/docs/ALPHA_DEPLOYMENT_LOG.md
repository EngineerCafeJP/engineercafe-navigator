# Alpha Deployment Log

This file records backend redeploys that are intentionally created to align the
Cloud Run image tag with the current `develop` commit before alpha live
verification.

## 2026-05-09

- Purpose: redeploy the backend after post-alpha RAG ingestion/mutation
  hardening and Node.js 24 workflow cleanup so production verification runs
  against the current `develop` commit.
- Expected validation: `backend-deploy-staging` builds and deploys an image
  tagged with the merge commit SHA, Cloud Run serves 100% traffic from that
  revision, `/health` is OK, and live Knowledge CRUD/RAG plus voice smoke
  checks pass before the related issues are updated.

## 2026-05-02

- Purpose: redeploy the backend after frontend-only alpha gate fixes so
  `alpha-live-verification` can run with `require_deployed_sha_match=true`.
- Expected validation: `backend-deploy-staging` builds and deploys an image
  tagged with the merge commit SHA, then Cloud Run health and alpha suites can
  be verified against that exact commit.
- Result:
  - PR #667 merged to `develop`.
  - Cloud Run revision `engineer-cafe-backend-00144-q85` deployed.
  - Image tag matched `fa7745b7420c0709fcff950ed3bf4c090f0dfc55`.
  - Full alpha run `25244933308` executed and ended failure.
  - Targeted C/RAGAS run `25247945549` verified direct OpenAI after syncing
    GitHub Actions `OPENAI_API_KEY`.
