# Alpha Deployment Log

This file records backend redeploys that are intentionally created to align the
Cloud Run image tag with the current `develop` commit before alpha live
verification.

## 2026-05-02

- Purpose: redeploy the backend after frontend-only alpha gate fixes so
  `alpha-live-verification` can run with `require_deployed_sha_match=true`.
- Expected validation: `backend-deploy-staging` builds and deploys an image
  tagged with the merge commit SHA, then Cloud Run health and alpha suites can
  be verified against that exact commit.
