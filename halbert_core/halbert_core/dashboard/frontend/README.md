# Halbert Dashboard Frontend

Modern React dashboard for Halbert autonomous IT management.

## Tech Stack

- **React 18** + **TypeScript**
- **Vite** - Fast build tool
- **Tailwind CSS** - Utility-first styling
- **shadcn/ui** - Modern component library
- **Lucide React** - Beautiful icons
- **React Router** - Client-side routing

## Development

```bash
# Install dependencies
npm install

# Start dev server (http://localhost:5173)
npm run dev

# Build for production
npm run build
```

## Project Structure

```
src/
├── components/
│   ├── ui/           # shadcn/ui components
│   └── Layout.tsx    # Main layout with sidebar
├── pages/
│   ├── Dashboard.tsx
│   ├── Approvals.tsx
│   ├── Jobs.tsx
│   ├── Memory.tsx
│   └── Settings.tsx
├── hooks/
│   └── useWebSocket.ts
├── lib/
│   ├── api.ts        # API client
│   └── utils.ts      # Utilities
├── App.tsx
└── main.tsx
```

## Features

- **Real-time Updates** - WebSocket connection for live data
- **System Monitoring** - CPU, memory, disk usage
- **Approval Management** - Interactive approval/rejection
- **Professional UI** - Clean, accessible design
- **Dark Mode Ready** - Built-in dark mode support

## API Integration

The dashboard connects to the FastAPI backend at `http://localhost:8000`.

Endpoints:
- `GET /api/status` - System status
- `GET /api/approvals` - Pending approvals
- `POST /api/approvals/{id}/approve` - Approve request
- `WS /ws` - WebSocket connection
