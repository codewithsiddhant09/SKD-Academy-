# BOOKLY AI Appointment Agent Frontend

## Overview
This frontend is a responsive Next.js dashboard for the BOOKLY AI salon booking assistant.
It is built with Tailwind CSS and a component-based architecture.

## Folder structure
- `app/page.tsx` - main dashboard layout and page composition
- `app/layout.tsx` - global metadata and root layout
- `app/globals.css` - Tailwind directives, global styling, and dark mode variables
- `components/` - reusable dashboard UI sections
- `lib/dashboard-data.ts` - static wireframe data for the dashboard UI

## Components
- `Sidebar` - primary app navigation and conversation history
- `ChatPanel` - conversation preview and prompt actions
- `DebugPanel` - AI reasoning and state preview
- `BookingPanel` - booking details and CTA
- `CategoryGrid` - service category cards
- `ApiMonitorPanel` - mock backend health and request overview
- `AgentFlowPanel` - multi-agent flow visualization
- `RecommendationPanel` - salon recommendation cards
- `FaqPolicyPanel` - knowledge & policy answer blocks
- `AnalyticsPanel` - metrics and performance cards

## Features
- Modern SaaS dashboard layout
- Responsive grid-based sections
- Dark mode support via `html.dark`
- Clean separation of UI concerns for future data integration
- Static data can be replaced with live backend props or API responses
