# Orca Frontend

React-based chat UI inspired by Gemini, for the Orca AI assistant.

Located at `buildandbreak/frontend/`.

## Setup

```bash
cd buildandbreak/frontend
npm install
```

## Environment

Create a `.env` file (or copy from `.env.example`):

```
VITE_API_BASE_URL=http://localhost:8000
VITE_API_AUTH_TOKEN=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ0ZXN0LXVzZXIiLCJpYXQiOjE3MzU2ODk2MDAsImV4cCI6NDA3MDkwODgwMH0.49JDWZ45SFFkBSQUV9aiy682SvKMcOpfhTRF1rhMNy4
```

- `VITE_API_BASE_URL` — Backend base URL. The frontend calls `POST {VITE_API_BASE_URL}/chat`.
- `VITE_API_AUTH_TOKEN` — JWT Bearer token (optional; hardcoded fallback for testing). No expiration (valid until 2099).

## Development

```bash
npm run dev
```

## Build

```bash
npm run build
```

## Features

- **Welcome Screen** — Orca branding with pulse animation; auto-transitions to chat after 3 seconds
- **Chat UI** — Centered message stream; user messages right, bot left; pill-shaped input
- **Upload Datasources** — JSON files for Trinity (datadrift + observability)
- **Trinity Validation** — ML performance queries require both datadrift and observability files

## Structure

- `src/components/` — `WelcomeScreen`, `Header`, `ChatMessage`, `ChatInput`, `UploadModal`, `TypingIndicator`
- `src/api/chat.ts` — Chat API client
- `src/utils/parseMLData.ts` — Parses Trinity JSON files (refine with sample schemas)
- `src/hooks/useMLQueryDetection.ts` — ML query detection for Trinity validation
