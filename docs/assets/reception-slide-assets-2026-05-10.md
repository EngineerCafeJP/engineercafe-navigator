# Reception Slide Asset Provenance, 2026-05-10

## Status

Working evidence for #810. This record covers the 2026-05-10 refresh of the
checked-in reception slide PDFs and their QR source images.

This is an operational provenance record, not legal advice. Do not describe the
asset set as OSS-ready unless the owner / permission fields below are confirmed.

## Runtime Path

Reception slide PDFs are shipped as frontend static assets:

- `frontend/public/reception/engineer-cafe-ja.pdf`
- `frontend/public/reception/engineer-cafe-en.pdf`

The kiosk reads them through `/reception/engineer-cafe-ja.pdf` and
`/reception/engineer-cafe-en.pdf`. The live runtime does not read these PDFs
from Google Cloud Storage. A merge to `develop` must therefore be verified on
the frontend deployment, not only on Cloud Run.

## Asset Inventory

| Asset | Size | SHA256 |
| --- | ---: | --- |
| `frontend/public/reception/engineer-cafe-ja.pdf` | 750005 bytes | `643194ac19f3bc69436e17adaeb8f5f4dfbcc507bb7bd4d4bcb42bb2a03d50b9` |
| `frontend/public/reception/engineer-cafe-en.pdf` | 644486 bytes | `c3c759f2fe6f76f108ffc298f9e7f0e835a458878f5757df889b49ee87506858` |
| `frontend/public/assets/images/qrcode_engineercafe-reception-JA.herokuapp.com.png` | 6077 bytes | `5cabe703704e83656b35f783da4e4d7beb086955688b75854938959067e518e5` |
| `frontend/public/assets/images/qrcode_engineercafe-reception-EN.herokuapp.com.png` | 5952 bytes | `82b0b5a2c34255ceeee41dd961e8e866436040693da186e3af5df0edc0f85d5a` |

## PDF Inspection

Both refreshed PDFs:

- were exported by LibreOffice Impress 26.2.2.2;
- are PDF 1.7;
- contain 5 pages;
- use 720 x 405.014 pt pages;
- preserve the previous extracted text exactly when compared with `pdftotext`
  output from `HEAD`.

Because the extracted text is unchanged and the page count is unchanged, this
refresh does not require updates to:

- `frontend/public/reception/engineer-cafe-narration-ja.md`
- `frontend/public/reception/engineer-cafe-narration-en.md`
- `backend/slides/narration/engineer-cafe-ja.json`
- `backend/slides/narration/engineer-cafe-en.json`
- `frontend/public/reception/audio/{ja,en}/01.mp3` through `05.mp3`

If a future deck refresh changes extracted text, the narration Markdown,
backend narration JSON, and PiperPlus MP3 set must be regenerated in the same
PR.

## Provenance Fields

| Field | Current evidence | Release requirement |
| --- | --- | --- |
| Owner | Engineer Cafe / operator-provided reception deck | Confirm operator ownership or redistribution permission before release |
| Source application | LibreOffice Impress export metadata | Keep source deck or export note outside this repo if it cannot be redistributed |
| Generated at | PDF metadata shows 2026-04-30 JST | Confirm the actual deck refresh date in PR notes |
| License / permission | Not encoded in the PDFs or PNGs | Record permission / terms before calling the binary assets OSS-cleared |
| Attribution | None detected in metadata | Confirm whether attribution is required |
| QR destination | Filenames indicate Engineer Cafe reception JA/EN Heroku app URLs | Verify QR scan destinations before production acceptance |

## Verification Commands

```bash
pdfinfo frontend/public/reception/engineer-cafe-ja.pdf
pdfinfo frontend/public/reception/engineer-cafe-en.pdf
pdftotext -layout frontend/public/reception/engineer-cafe-ja.pdf -
pdftotext -layout frontend/public/reception/engineer-cafe-en.pdf -
corepack pnpm --dir frontend exec tsx src/__tests__/reception-narration-assets.test.ts
```

After deploy, verify the production frontend:

```bash
curl -I https://frontend-delta-six-20.vercel.app/reception/engineer-cafe-ja.pdf
curl -I https://frontend-delta-six-20.vercel.app/reception/engineer-cafe-en.pdf
```
