# AWS Cost Analyzer — Frontend

Next.js (React 19, Tailwind CSS) UI for the FastAPI backend.

## Setup

```bash
npm ci
```

## Development

```bash
npm run dev
```

Opens <http://localhost:3000>. The UI calls the backend's `/ask` and
`/upload` endpoints.

## Backend URL

The backend base URL defaults to `http://localhost:8000`. To deploy the
frontend separately from the API (e.g. static hosting in front of a
remote FastAPI service), set `NEXT_PUBLIC_API_BASE_URL` at build time:

```bash
NEXT_PUBLIC_API_BASE_URL=https://api.example.com npm run build
```

`NEXT_PUBLIC_*` variables are inlined at build time, so setting it at
runtime has no effect.

## Tests & build

```bash
npm test        # vitest unit tests (lib/api, lib/chartData)
npm run build   # production build + type check
```
