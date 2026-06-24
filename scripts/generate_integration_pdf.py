"""Generate Bookly AI Integration Audit PDF for Frontend handover."""
from __future__ import annotations

from pathlib import Path

from fpdf import FPDF

OUT = Path(__file__).resolve().parent.parent / "docs" / "Bookly_AI_Integration_Audit.pdf"


def clean(text: str) -> str:
    """Replace Unicode chars that break core fonts."""
    return (
        text.replace("\u2192", "->")
        .replace("\u00b7", " | ")
        .replace("\u2014", "-")
        .replace("\u2013", "-")
        .replace("\u2190", "<-")
        .replace("\u2022", "-")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u2018", "'")
        .replace("\u2019", "'")
    )


class AuditPDF(FPDF):
    def header(self) -> None:
        if self.page_no() == 1:
            return
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 8, "Bookly AI Agent - Integration Audit", align="L")
        self.ln(4)

    def footer(self) -> None:
        self.set_y(-12)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 8, f"Page {self.page_no()}", align="C")

    def title_page(self) -> None:
        self.add_page()
        self.set_font("Helvetica", "B", 22)
        self.set_text_color(30, 30, 30)
        self.ln(40)
        self.multi_cell(0, 12, "Bookly AI Appointment Agent", align="C")
        self.ln(4)
        self.set_font("Helvetica", "", 16)
        self.multi_cell(0, 10, "Integration Audit & Frontend Handover", align="C")
        self.ln(20)
        self.set_font("Helvetica", "", 11)
        self.set_text_color(80, 80, 80)
        self.multi_cell(
            0,
            7,
            clean(
                "Complete technical documentation covering REST APIs, Socket.IO events, "
                "conversation flows, state management, MongoDB schema, external integrations, "
                "AI agents, TypeScript contracts, and testing checklist."
            ),
            align="C",
        )
        self.ln(30)
        self.set_font("Helvetica", "I", 10)
        self.cell(0, 8, "Generated: June 2026  |  Audience: Frontend Team", align="C")

    def h1(self, text: str) -> None:
        self.ln(6)
        self.set_font("Helvetica", "B", 16)
        self.set_text_color(30, 30, 30)
        self.multi_cell(0, 10, clean(text))
        self.ln(2)
        self.set_draw_color(89, 156, 231)
        self.set_line_width(0.5)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(4)

    def h2(self, text: str) -> None:
        self.ln(4)
        self.set_font("Helvetica", "B", 12)
        self.set_text_color(50, 50, 50)
        self.multi_cell(0, 8, clean(text))
        self.ln(2)

    def h3(self, text: str) -> None:
        self.ln(2)
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(60, 60, 60)
        self.multi_cell(0, 7, clean(text))
        self.ln(1)

    def body(self, text: str) -> None:
        self.set_font("Helvetica", "", 9)
        self.set_text_color(40, 40, 40)
        self.multi_cell(0, 5, clean(text))
        self.ln(2)

    def mono(self, text: str) -> None:
        self.set_font("Courier", "", 8)
        self.set_text_color(50, 50, 50)
        self.set_fill_color(245, 245, 245)
        x, y = self.get_x(), self.get_y()
        self.multi_cell(0, 4.5, clean(text), fill=True)
        self.ln(2)

    def bullet(self, text: str) -> None:
        self.set_font("Helvetica", "", 9)
        self.set_text_color(40, 40, 40)
        self.multi_cell(0, 5, clean(f"  - {text}"))
        self.ln(1)

    def step(self, num: int, text: str) -> None:
        self.set_font("Helvetica", "", 9)
        self.multi_cell(0, 5, clean(f"  {num}. {text}"))
        self.ln(1)

    def table_row(self, cols: list[str], bold: bool = False) -> None:
        w = [45, 35, 55, 55]
        style = "B" if bold else ""
        self.set_font("Helvetica", style, 8)
        for i, col in enumerate(cols):
            self.cell(w[i], 6, clean(col)[:60], border=1)
        self.ln()


def build() -> None:
    pdf = AuditPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.title_page()

    # ── 1. Architecture ──────────────────────────────────────────────────────
    pdf.add_page()
    pdf.h1("1. System Architecture")
    pdf.body(
        "Stack: FastAPI + Socket.IO ASGI | LangGraph orchestration | OpenAI LLM + Embeddings | "
        "MongoDB Atlas | ChromaDB | Next.js frontend"
    )
    pdf.h2("Frontend Layer (port 3000)")
    for item in [
        "Next.js - ChatPanel.tsx uses REST POST /chat",
        "Socket.IO client - user_message, bot_response, salon_cards, typing_start/end",
        "Standalone index.html - socket-only alternative UI",
        "localStorage - conversation persistence across refreshes",
    ]:
        pdf.bullet(item)

    pdf.h2("Backend Layer (port 8000)")
    for item in [
        "FastAPI - 9 REST endpoints",
        "CORS: allow_origins=['*']",
        "Socket.IO ASGI mounted at /socket.io",
        "Lazy dependency init on first request",
    ]:
        pdf.bullet(item)

    pdf.h2("LangGraph Workflow Nodes")
    for item in [
        "detect_intent -> route_intent",
        "-> faq_policy (RAG flow)",
        "-> service_prepare -> service_check -> location_check -> discover",
        "-> booking (date/time extraction + confirmation)",
        "-> general (fallback / greeting)",
    ]:
        pdf.bullet(item)

    pdf.h2("Data Source Priority")
    for item in [
        "1. MongoDB Atlas (bookly) - vendor users.businessAddress",
        "2. Categories API - localhost:4006/user/allCategories",
        "3. mock_salons.json - fallback when MongoDB returns 0",
        "4. ChromaDB - FAQ + policy knowledge base (.chroma/)",
    ]:
        pdf.bullet(item)

    pdf.h2("Request Flow")
    for line in [
        "Frontend -> POST /chat OR socket user_message",
        "OrchestratorService.chat() / socketio_server.user_message()",
        "ensure_user_context(session_id, user_id) [MongoDB users lookup, cached per session]",
        "OrchestratorWorkflow.run(GraphState) [LangGraph nodes]",
        "detect_intent [OpenAI] -> route -> nodes -> reply + recommendations",
        "ChatResponse { session_id, reply, intent, structured, recommendations }",
        "[Socket only] emit bot_response -> emit salon_cards? -> emit typing_end",
    ]:
        pdf.mono(line)

    pdf.h2("Known Gaps (Before Production)")
    for sev, issue, detail in [
        ("HIGH", "BookingService is in-memory only", "Bookings lost on restart; MongoDB bookings not wired."),
        ("HIGH", "No availability check", "slots collection never queried before confirming booking."),
        ("MED", "No authentication", "All APIs open. Plan auth headers before production."),
        ("MED", "SALON_INFO_API_URL unused", "Declared in config but never called."),
        ("LOW", "mock_salons.json UAE bias", "Non-UAE locations with no MongoDB data return mock UAE salons."),
    ]:
        pdf.body(f"[{sev}] {issue}: {detail}")

    # ── 2. REST APIs ─────────────────────────────────────────────────────────
    pdf.add_page()
    pdf.h1("2. REST API Inventory")
    pdf.body(": http://localhost:8Base URL000 | Content-Type: application/json | No authentication required")

    apis = [
        ("POST", "/chat", "Core", "Send user message; runs full LangGraph workflow.",
         "{ session_id, message, user_id? }",
         "{ session_id, reply, intent, structured, recommendations[] }",
         "503 Service not initialized"),
        ("POST", "/session/start", "Core", "Load MongoDB user profile; return personalized greeting.",
         "{ session_id, user_id? }",
         "{ session_id, greeting, context: SessionContext }",
         "503 Service not initialized"),
        ("GET", "/health", "Infra", "Liveness probe - RAG + category cache status.",
         "-", "{ status, app, rag_ready, categories_cached }", "-"),
        ("GET", "/categories", "Data", "All service categories (TTL 1h cache).",
         "-", "Category[] { id, name }", "-"),
        ("GET", "/debug/salons", "Debug", "MongoDB discovery probe (diagnostic).",
         "Query: location?, category?, service?",
         "{ query, diagnosis, count, matches[] }", "-"),
        ("POST", "/book-appointment", "Booking", "Direct booking (bypasses chat).",
         "{ session_id, salon?, service?, date?, time? }",
         "{ booking_id, status: confirmed, payload }", "400 Missing fields | 503"),
        ("POST", "/debug-rag", "Debug", "Inspect RAG pipeline.",
         "{ question }", "{ question, retrieved_chunks[], answer, explanation }", "503"),
        ("POST", "/debug-intent", "Debug", "Test intent classification.",
         "{ message }", "{ message, intent, category, service, explanation }", "503"),
        ("POST", "/upload", "Utility", "Upload .docx knowledge document.",
         "multipart file: *.docx", "{ status, filename }", "400 Only .docx"),
    ]
    for method, path, tag, desc, req, resp, err in apis:
        pdf.h3(f"{method} {path}  [{tag}]")
        pdf.body(desc)
        pdf.mono(f"Request:  {req}")
        pdf.mono(f"Response: {resp}")
        if err != "-":
            pdf.body(f"Errors: {err}")
        pdf.ln(2)

    # ── 3. Socket Events ─────────────────────────────────────────────────────
    pdf.add_page()
    pdf.h1("3. Socket.IO Event Inventory")
    pdf.body("Path: /socket.io | Transport: async WebSocket | CORS: all origins")

    events = [
        ("connect", "S->C", "Client connects", "{ session_id, reply }", "Emits welcome greeting immediately."),
        ("disconnect", "C->S", "Client disconnects", "-", "Logged server-side only."),
        ("user_message", "C->S", "User sends message", "{ session_id, message, user_id? }",
         "Triggers typing_start -> workflow -> bot_response -> salon_cards? -> typing_end"),
        ("typing_start", "S->C", "After user_message received", "{ session_id }", "Show typing indicator."),
        ("bot_response", "S->C", "After workflow completes", "{ session_id, reply, intent?, structured? }",
         "Always emitted. structured.booking_payload on booking steps."),
        ("salon_cards", "S->C", "When recommendations exist",
         "{ salons: [{ salonId, salonName, rating, distance, location, services[], reason, redirectUrl }] }",
         "Only when salons found. Frontend renders clickable cards."),
        ("typing_end", "S->C", "After all events emitted", "{ session_id }", "Hide typing indicator."),
    ]
    for ev, direction, trigger, payload, notes in events:
        pdf.h3(f"{ev}  ({direction})")
        pdf.body(f"Trigger: {trigger}")
        pdf.mono(f"Payload: {payload}")
        pdf.body(f"Notes: {notes}")
        pdf.ln(1)

    # ── 4. Chat Flows ────────────────────────────────────────────────────────
    pdf.add_page()
    pdf.h1("4. Conversation Flow Analysis")

    flows = [
        ("Greeting / General", [
            "User sends hello or vague message",
            "IntentAgent -> general_conversation",
            "route_intent -> general node",
            "Check SessionContext for fullName (from MongoDB)",
            "Reply: Welcome back {name} OR generic welcome",
        ]),
        ("FAQ / Policy (RAG)", [
            "User asks knowledge question (e.g. What is Bookly?)",
            "IntentAgent -> faq | policy",
            "route_intent -> faq_policy node",
            "FaqAgent.answer() -> RagStore.retrieve_with_scores(top_k=8)",
            "GPT-4o-mini synthesises answer from retrieved chunks",
            "Reply: RAG-grounded answer only",
        ]),
        ("Salon Search (location only)", [
            "User: Show salons in Noida",
            "IntentAgent -> salon_search (no service, no category)",
            "service_prepare: salon_search=true; location extracted",
            "service_check: skipped",
            "discover: MongoDB users.businessAddress query",
            "ranking_agent.rank() -> top-5 cards",
            "Reply + salon_cards event",
        ]),
        ("Service Search -> Location -> Booking", [
            "User: Hair Smoothing",
            "IntentAgent -> service_search; category=Hair",
            "location_check: ask preferred location",
            "User: Noida -> discover MongoDB Hair+Noida",
            "BookingDraft auto-set; stage=awaiting_date",
            "User: date -> stage=awaiting_time",
            "User: time -> BookingService.create_booking()",
            "Reply: Confirmed + booking_id (no name/phone requested)",
        ]),
        ("Service + Location in One Message", [
            "User: Hair Smoothing in Noida",
            "service + location extracted in same turn",
            "discover runs immediately - no location prompt",
        ]),
        ("Appointment Cancellation", [
            "User: Cancel my appointment",
            "IntentAgent -> appointment_cancellation",
            "route_intent -> faq_policy (policy explanation)",
        ]),
    ]
    for name, steps in flows:
        pdf.h2(name)
        for i, step in enumerate(steps, 1):
            pdf.step(i, step)
        pdf.ln(2)

    # ── 5. State Management ──────────────────────────────────────────────────
    pdf.add_page()
    pdf.h1("5. State Management")
    pdf.body(
        "All state is server-side in ConversationStore (in-memory, keyed by session_id). "
        "GraphState (TypedDict) is the per-request envelope. No client-side session cookies."
    )
    pdf.h2("ConversationStore Fields")
    pdf.mono(
        "_messages: dict[session_id -> Message[]]  last 12 as LLM history\n"
        "_booking_drafts: dict[session_id -> BookingPayload]\n"
        "_booking_stages: dict[session_id -> awaiting_date | awaiting_time]\n"
        "_active_booking_sessions: set[session_id]\n"
        "_user_contexts: dict[session_id -> SessionContext]  loaded once from MongoDB\n"
        "_salon_lookup: dict[session_id -> {name: vendor_id}]"
    )
    pdf.h2("GraphState Fields")
    pdf.table_row(["Field", "Type", "Lifecycle", "Notes"], bold=True)
    state_rows = [
        ("session_id", "string", "Per request", "UUID from frontend"),
        ("intent_analysis", "IntentAnalysis", "detect_intent", "intent+service+category+location"),
        ("salon_search", "boolean", "service_prepare", "Skip service requirement"),
        ("service", "string|null", "service_prepare", "Null for salon_search"),
        ("category", "string|null", "service_prepare", "Never defaulted"),
        ("location", "string", "service_prepare", "Free-form city or UAE area"),
        ("recommendations", "SalonRec[]", "discover", "Max 5 cards"),
        ("booking_payload", "BookingPayload", "booking", "salon_id, date, time, user_id"),
        ("booking_stage", "string", "discover/booking", "awaiting_date|awaiting_time"),
        ("UserContext", "SessionContext", "ensure_user_context", "Cached per session"),
    ]
    for row in state_rows:
        pdf.table_row(list(row))

    # ── 6. Database ──────────────────────────────────────────────────────────
    pdf.add_page()
    pdf.h1("6. MongoDB Database Analysis")
    pdf.body(
        'Database: bookly. IMPORTANT: "addresses" collection stores CUSTOMER addresses, '
        "NOT vendor locations. Vendor location = users.businessAddress."
    )
    collections = [
        ("users", "Vendors AND customers (userType field)", "SalonRepository, UserService"),
        ("services", "Individual vendor services", "SalonRepository (category+service search)"),
        ("categories", "Service category taxonomy", "SalonRepository, CategoryService"),
        ("reviews", "Customer ratings for vendors", "SalonRepository (avg rating)"),
        ("addresses", "Customer saved addresses (NOT salon locations)", "Supplementary city search"),
        ("bookings", "Native app appointments [NOT INTEGRATED]", "Not wired to chatbot"),
        ("slots", "Vendor availability [NOT INTEGRATED]", "No availability check before booking"),
    ]
    for name, purpose, used in collections:
        pdf.h3(name)
        pdf.body(f"Purpose: {purpose}")
        pdf.body(f"Used by: {used}")

    pdf.h2("Key Relationships")
    pdf.mono(
        "users._id <- services.vendorId\n"
        "users._id <- reviews.vendorId\n"
        "categories._id <- services.categoryId\n"
        "users._id <- addresses.userId (customers only)"
    )

    # ── 7. Integrations ──────────────────────────────────────────────────────
    pdf.add_page()
    pdf.h1("7. External Integrations & Environment Variables")
    env_vars = [
        ("OPENAI_API_KEY", "Required for LLM + RAG"),
        ("OPENAI_MODEL", "gpt-4o-mini"),
        ("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
        ("MONGODB_URI", "Atlas connection string"),
        ("MONGODB_DB_NAME", "bookly"),
        ("CATEGORIES_API_URL", "http://localhost:4006/user/allCategories"),
        ("SALON_INFO_API_URL", "https://admin.bookly.ae:2053/user/viewVendor (unused)"),
        ("RAG_PERSIST_DIRECTORY", ".chroma"),
        ("RAG_COLLECTION_NAME", "bookly_knowledge"),
        ("TOP_K_RETRIEVAL", "8"),
        ("CATEGORIES_CACHE_TTL_SECONDS", "3600"),
        ("HOST / PORT", "127.0.0.1 / 8000"),
    ]
    pdf.table_row(["Variable", "Description"], bold=True)
    for k, v in env_vars:
        pdf.table_row([k, v])

    pdf.h2("Integration Summary")
    for name, flow in [
        ("OpenAI GPT-4o-mini", "IntentAgent structured output + FaqAgent synthesis"),
        ("OpenAI Embeddings", "RagStore -> ChromaDB upsert/query (top_k=8)"),
        ("MongoDB Atlas", "SalonRepository 4-query batched O(1) fetch; UserService profile load"),
        ("ChromaDB", "Local .chroma/ vector store for FAQ + policy docs"),
        ("Categories API", "GET /allCategories, TTL 1h, 8-category fallback"),
    ]:
        pdf.h3(name)
        pdf.body(flow)

    # ── 8. AI Agents ─────────────────────────────────────────────────────────
    pdf.add_page()
    pdf.h1("8. AI Agent Analysis")
    agents = [
        ("IntentAgent", "intent_agent.py", "Classify into 9 intents. Heuristic + GPT structured output.",
         "IntentAnalysis { intent, service, category, location }"),
        ("CategoryAgent", "category_agent.py", "Map service -> category via keyword match.",
         "string | null"),
        ("FaqAgent", "faq_agent.py", "RAG FAQ/policy answers from Bookly knowledge base only.",
         "string (answer)"),
        ("LocationAgent", "location_agent.py", "Normalise location + search radius (UAE 10km, else 15km).",
         "LocationAnalysis"),
        ("SalonDiscoveryAgent", "salon_discovery_agent.py", "Bridge to SalonService.discover() -> MongoDB.",
         "list[Salon]"),
        ("SalonRankingAgent", "salon_ranking_agent.py", "Score: 40% service, 30% distance, 20% rating, 10% avail.",
         "list[SalonRecommendation] top 5"),
        ("BookingAgent", "booking_agent.py", "Extract date/time from free-text. No name/phone requested.",
         "BookingPayload"),
    ]
    for name, file, role, output in agents:
        pdf.h3(f"{name} ({file})")
        pdf.body(role)
        pdf.mono(f"Output: {output}")

    pdf.h2("Intent Routing Matrix")
    pdf.table_row(["Intent", "Node", "Action"], bold=True)
    routing = [
        ("faq / policy", "faq_policy", "FaqAgent -> ChromaDB -> OpenAI"),
        ("salon_search", "service_prepare -> discover", "Location-only MongoDB query"),
        ("service_search", "service_prepare -> location -> discover", "Service+category+location"),
        ("appointment_booking", "booking", "Extract date/time, confirm"),
        ("appointment_cancellation", "faq_policy", "Policy explanation via RAG"),
        ("general_conversation", "general", "Personalised or generic greeting"),
    ]
    for intent, node, action in routing:
        pdf.table_row([intent, node, action])

    # ── 9. TypeScript Interfaces ─────────────────────────────────────────────
    pdf.add_page()
    pdf.h1("9. TypeScript Interface Contracts")
    pdf.body("Paste into types/bookly.d.ts or equivalent.")
    ts = """
interface ChatRequest { session_id: string; message: string; user_id?: string; }
interface SessionStartRequest { session_id: string; user_id?: string; }

interface ChatResponse {
  session_id: string; reply: string; intent: IntentType;
  structured: { intent, category, service, location, booking_payload, user_context };
  recommendations: SalonRecommendation[];
}

type IntentType = "faq"|"policy"|"salon_search"|"location_search"|"service_search"|
  "salon_discovery"|"appointment_booking"|"appointment_cancellation"|"general_conversation";

interface SalonCard {
  salonId: string; salonName: string; rating: number|null;
  distance: string|null; location: string|null;
  services: string[]; reason: string|null; redirectUrl: string|null;
}

interface BookingPayload {
  salon?: string; salon_id?: string; service?: string; category?: string;
  date?: string; time?: string; user_id?: string;
}

interface SessionContext {
  user_id, full_name, email, phone_number, gender, nationality, business_location;
}

// Socket: UserMessageEvent (C->S), BotResponseEvent (S->C),
//         SalonCardsEvent (S->C), TypingEvent (S->C)
"""
    pdf.mono(ts.strip())

    # ── 10. Testing Checklist ────────────────────────────────────────────────
    pdf.add_page()
    pdf.h1("10. Integration Testing Checklist")
    tests = [
        ("P0", "Backend", "GET /health returns status ok, rag_ready, categories_cached"),
        ("P0", "Backend", "POST /chat returns 200 with reply and intent"),
        ("P0", "Backend", "Show salons in Noida -> salon_search + recommendations"),
        ("P0", "Backend", "Hair Smoothing in Noida -> service, category, cards"),
        ("P0", "Backend", "What is Bookly? -> faq RAG answer"),
        ("P0", "Backend", "Full booking flow -> booking_id in structured"),
        ("P0", "Socket", "connect emits bot_response with welcome"),
        ("P0", "Socket", "user_message emits salon_cards when recommendations exist"),
        ("P0", "MongoDB", "GET /debug/salons?location=Noida count > 0"),
        ("P0", "Categories", "GET /categories returns >= 8 items"),
        ("P0", "Frontend", "salon_cards populates card UI with salonName, rating, redirectUrl"),
        ("P1", "Backend", "POST /session/start with user_id returns greeting with fullName"),
        ("P1", "Socket", "typing_start before bot_response; typing_end after"),
        ("P1", "RAG", "POST /debug-rag cancellation policy returns chunks"),
        ("P2", "Frontend", "localStorage persists conversation on refresh"),
    ]
    pdf.table_row(["Priority", "Area", "Test"], bold=True)
    for p, area, item in tests:
        pdf.table_row([p, area, item[:80]])

    # ── Frontend Integration Guide ───────────────────────────────────────────
    pdf.add_page()
    pdf.h1("11. Frontend Integration Guide")
    pdf.h2("Chat Screen (ChatPanel.tsx)")
    pdf.body("Primary integration: REST POST /chat (not Socket in current Next.js UI)")
    pdf.mono(
        "POST /chat\n"
        "Body: { session_id: uuid, message: string, user_id?: string }\n"
        "Response: { reply, intent, structured, recommendations[] }"
    )
    pdf.body("Loading: set loading=true before fetch, false after response.")
    pdf.body("Success: display reply; if recommendations.length > 0 render salon cards.")
    pdf.body("Error: catch HTTP 503 or network error; show user-friendly message.")

    pdf.h2("Socket Integration (index.html / production)")
    pdf.mono(
        "Connect: io('http://localhost:8000')\n"
        "Emit: socket.emit('user_message', { session_id, message, user_id })\n"
        "Listen: bot_response, salon_cards, typing_start, typing_end"
    )

    pdf.h2("Session Start (optional)")
    pdf.mono(
        "POST /session/start\n"
        "Body: { session_id, user_id }\n"
        "Response: { greeting, context: { full_name, email, ... } }"
    )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(OUT))
    print(f"PDF written: {OUT}")


if __name__ == "__main__":
    build()
