# AgentDesk Frontend

Minimal React and TypeScript frontend foundation for AgentDesk. It contains no
business logic, API keys, or external-service integration.

## Requirements

- Node.js 24.15 or later, below Node.js 25
- npm 11 or later

## Local development

```sh
npm ci
npm run dev
```

The development server listens on `http://localhost:5173`.

## Tests

```sh
npm test
```

## Production build

```sh
npm run build
```

## Docker Compose

From the repository root:

```sh
docker compose up --build frontend
```

The containerized frontend is available at `http://localhost:5173`.
