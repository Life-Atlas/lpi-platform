# LPI Platform — React Frontend Client

**Author:** Jahanvi Gupta

This directory contains the React + Vite frontend client for the LPI Platform, integrated with backend services.

## Setup & Run Instructions

### Prerequisites

Make sure you have [Node.js](https://nodejs.org/) installed.

### 1. Install Dependencies

Navigate to this directory and install the package dependencies:

```bash
cd frontend-js
npm install
```

### 2. Run the Development Server

Start the local Vite development server:

```bash
npm run dev
```

Open the provided local address (typically `http://localhost:5173`) in your browser to view the application.

### 3. Build for Production

To generate a production-ready optimized build:

```bash
npm run build
```

---

## Backend Connection & Changes

The frontend connects to the FastAPI backend API running at `http://localhost:8000`. Ensure your backend server is running concurrently by running the following command in the root folder of the project:

```bash
make run
```

### Configuration (`.env` file)

Inside the frontend-js folder make sure you have .env folder containing
VITE_SUPABASE_URL=http://127.0.0.1:54321
VITE_SUPABASE_ANON_KEY=your-key-here

### Configuration (`.env` file)

In the root directory of the project, make sure you have a `.env` file set up with the following configuration:

```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-key
LLM_PROVIDER=anthropic
LLM_MODEL=claude-sonnet-4-20250514
ANTHROPIC_API_KEY=sk-ant-...
DAILY_COST_CAP_USD=10.0
ADMIN_USER_IDS=your-admin-user-id
```

> [!NOTE]
> To configure multiple administrators, you can add their user UUIDs in `ADMIN_USER_IDS` separated by a comma (e.g., `ADMIN_USER_IDS=uuid1,uuid2,uuid3`).

### Changing the GitHub Repository for Activity Signals

If you want to add another demo repository in the activity signals feature, replace the default repository name with your GitHub repository name in [SignalsView.jsx](file:///Users/jahanvi/lpi%20jahanvi/lpi-platform/frontend-js/src/components/SignalsView.jsx) at lines **216** (in the auto-sync fetch function) and **305** (in the timeline display filter).

### Summary of Backend Changes

The following backend files were created or modified to support user authentication, goal management, and activity signal ingestion:

1. **`src/lpi/config.py`**: Added configuration settings for user verification, database connections, and auth tokens.
2. **`src/lpi/main.py`**: Registered new routes for user profiles, `/me` current user context, goals, and activity signal polling.
3. **`src/lpi/middleware/auth.py`**: Modified user authentication middleware to authenticate requests and map incoming requests to user sessions.
4. **`src/lpi/routers/goals.py`**: Updated goal endpoints to filter, create, transition, and delete goals under active user sessions.
5. **`src/lpi/routers/me.py`** _(New)_: Created endpoints to return user profile data for the active logged-in user context.
6. **`src/lpi/routers/signals.py`**: Modified signals endpoints to support ingestion, deduplication, chronological sorting, and fetching of activity streams from `Jahanvi3005/demo4`.
7. **`src/lpi/routers/users.py`** _(New)_: Created endpoints for user registration, user map querying, and profile updates.

## folder structure

frontend-js/
├── README.md # Setup and running instructions
├── index.html # HTML entry point for the React app
├── package.json # Project dependencies and script runner (Vite)
├── vite.config.js # Vite build tool configuration
├── eslint.config.js # JavaScript formatting/linting rules

├── public/ # Static assets (favicons, SVG assets)

└── src/ # Main React source code
├── main.jsx # React root injection point
├── App.jsx # Main App layout, tab navigation, auth session listener
├── App.css # Base application layout styles
├── api.js # Fetch connection layer to FastAPI endpoints
├── index.css # Global theme styling tokens (dark mode, glassmorphism)
├── supabaseClient.js # Supabase Authentication client initialization

├── src/assets/ # Images and design assets

└── src/components/ # Modular React components and their CSS files
├── LoginPage.jsx / .css # Portal landing / Login / Sign-up layout
├── UserProfile.jsx / .css # Settings page, profile image avatar, display name sync
├── GoalsList.jsx / .css # Dashboard grid wrapper for GoalCards
├── GoalCard.jsx / .css # Individual SMILE phase steppers, transitions, delete panel
├── GoalCreateModal.jsx / .css # Overlay popup wrapper for new goal creation
├── GoalCreateForm.jsx / .css # Fields for Title, Priority, Urgency and SMILE phase select
└── SignalsView.jsx / .css # Chronological timeline polling activity stream from GitHub
