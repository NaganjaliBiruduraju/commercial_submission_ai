# Insight AI - Frontend

Modern React + TypeScript + Vite frontend for the Commercial Insurance Document Intelligence platform.

## Features

- 🎨 **Modern UI**: Built with React 18, TypeScript, and Tailwind CSS
- 🔐 **Authentication**: JWT-based auth with protected routes
- 📄 **Document Management**: Upload, process, and view insurance documents
- 🤖 **AI-Powered**: Real-time extraction, validation, and risk assessment
- 🔍 **RAG Search**: Semantic knowledge base search with similarity scoring
- 📱 **Responsive**: Mobile-friendly design with dark mode support
- ⚡ **Fast**: Vite for instant HMR and optimized builds

## Tech Stack

- **Framework**: React 18 with TypeScript
- **Build Tool**: Vite
- **Styling**: Tailwind CSS
- **Routing**: React Router v6
- **HTTP Client**: Axios with interceptors
- **State Management**: React Context API
- **UI Components**: Custom components with Tailwind

## Project Structure

```
frontend/
├── src/
│   ├── components/       # Reusable UI components
│   │   └── Navbar.tsx
│   ├── pages/           # Page components
│   │   ├── Login.tsx
│   │   ├── Dashboard.tsx
│   │   ├── Submissions.tsx
│   │   ├── SubmissionDetail.tsx
│   │   └── KnowledgeBase.tsx
│   ├── lib/             # Core utilities
│   │   ├── api.ts       # API client with Axios
│   │   └── auth.tsx     # Auth context and hooks
│   ├── App.tsx          # Main app component
│   ├── main.tsx         # Entry point
│   └── index.css        # Global styles
├── public/              # Static assets
├── Dockerfile           # Production Docker build
├── nginx.conf           # Nginx config for production
└── package.json         # Dependencies
```

## Getting Started

### Prerequisites

- Node.js 18+ and npm
- Backend API running on http://localhost:8000

### Installation

1. Install dependencies:
```bash
npm install
```

2. Create `.env` file:
```bash
cp .env.example .env
```

3. Configure environment variables in `.env`:
```
VITE_API_BASE_URL=http://localhost:8000/api/v1
```

### Development

Start the development server:
```bash
npm run dev
```

The app will be available at http://localhost:5173

### Build for Production

```bash
npm run build
```

Preview production build:
```bash
npm run preview
```

## Docker Deployment

### Build Docker Image

```bash
docker build -t insight-ai-frontend .
```

### Run Container

```bash
docker run -p 3000:80 insight-ai-frontend
```

### Docker Compose

The frontend is included in the main docker-compose.yml:

```bash
# From project root
docker-compose up -d frontend
```

Access at http://localhost:3000

## Features Overview

### Authentication
- Login and registration
- JWT token management
- Protected routes
- Auto redirect on token expiration

### Dashboard
- Overview of recent submissions
- Quick stats and metrics
- Quick actions for common tasks

### Submissions
- Create new submissions
- Upload documents (PDF, DOC, DOCX)
- Process documents with AI
- View processing status
- Filter and search

### Submission Details
- Document list with status
- Extracted data viewer
- Validation results with errors/warnings
- Risk assessment with scoring
- Multi-tab interface

### Knowledge Base
- Semantic search with RAG
- Create and manage articles
- Category and tag organization
- Similarity scoring for search results

## API Integration

The frontend communicates with the backend via REST API:

- **Base URL**: Configured via `VITE_API_BASE_URL`
- **Authentication**: Bearer token in Authorization header
- **Auto Retry**: Axios interceptors for token refresh
- **Error Handling**: Global error handling with user feedback

### API Endpoints Used

- `POST /auth/login` - User login
- `POST /auth/register` - User registration
- `GET /users/me` - Get current user
- `GET /submissions/` - List submissions
- `POST /submissions/` - Create submission
- `POST /submissions/{id}/documents` - Upload document
- `POST /submissions/{id}/process` - Process submission
- `GET /submissions/{id}/extracted` - Get extracted data
- `GET /submissions/{id}/validation` - Get validation results
- `GET /submissions/{id}/risk` - Get risk assessment
- `GET /knowledge/` - List knowledge articles
- `POST /knowledge/search` - Search knowledge base
- `POST /knowledge/` - Create article

## Customization

### Styling

Tailwind CSS is configured with custom utility classes in `index.css`:

- `.btn-primary` - Primary action buttons
- `.btn-secondary` - Secondary buttons
- `.btn-danger` - Destructive actions
- `.card` - Card container
- `.input-field` - Form inputs
- `.label` - Form labels

Customize in `tailwind.config.js` and `src/index.css`.

### Theme

Dark mode is supported via Tailwind's `dark:` classes. Toggle implementation can be added to `Navbar.tsx`.

## Browser Support

- Chrome/Edge (latest)
- Firefox (latest)
- Safari (latest)

## Performance

- Code splitting with React.lazy (can be added)
- Optimized builds with Vite
- Nginx gzip compression in production
- Asset caching with proper headers

## Security

- XSS protection headers
- CORS configuration
- Secure token storage
- Input sanitization (client-side)
- Protected routes

## Troubleshooting

### Port Already in Use

Change the port in `vite.config.ts`:
```typescript
export default defineConfig({
  server: {
    port: 5174, // Change port
  },
})
```

### API Connection Issues

1. Check backend is running: http://localhost:8000/docs
2. Verify CORS settings in backend allow frontend origin
3. Check `.env` has correct `VITE_API_BASE_URL`

### Build Errors

Clear node_modules and reinstall:
```bash
rm -rf node_modules package-lock.json
npm install
```

## Contributing

1. Create feature branch
2. Make changes
3. Test locally
4. Submit pull request

## License

Proprietary - INFOLOB Global, Inc.
