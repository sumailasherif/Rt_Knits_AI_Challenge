RT Knits Agentic CMMS
CBBR-NATEC Innovation Cup — Technical Report
1. Executive Summary & The Value Proposition
Factory maintenance in a textile manufacturing environment like RT Knits runs on a fragile chain of manual handoffs: a machine breaks, a worker has to find a supervisor, the supervisor has to remember to log it somewhere, someone has to figure out which technician is free, and by the time a repair actually starts, production has already bled minutes or hours of downtime. Every step in that chain is a place where information gets lost, delayed, or never recorded at all — which means the data needed to actually improve the maintenance operation never gets captured in the first place.
RT Knits Agentic CMMS replaces that chain with a single, frictionless entry point: WhatsApp. A factory floor worker sends a text, a voice note, or a photo of the broken equipment — in English, French/Creole, Hindi, or Bengali — and a coordinated swarm of seven specialized AI agents takes it from there. Within seconds, the fault is transcribed or visually analyzed, translated, classified by urgency, matched against historical repair knowledge, assigned to the best-available technician, and tracked end-to-end until the job is confirmed complete and rated.
The result is a maintenance system that requires zero training for factory workers (everyone already knows how to send a WhatsApp message), zero manual triage effort for supervisors, and produces a continuously growing structured dataset of equipment health, technician performance, and repair patterns — the exact enterprise-grade insight layer that manual, paper-based, or spreadsheet-based CMMS systems can never produce.
2. System Architecture & Technical Deep Dive
The system is built as five distinct layers, each chosen deliberately for the constraints of a real factory floor environment rather than a lab demo.
Layer 1 — Entry Point: WhatsApp Cloud API (Meta Graph v19)
Factory floor workers and technicians are not going to install a new app, remember a login, or learn a new interface — but every one of them already has WhatsApp open all day. By building directly on Meta's Graph API (rather than a third-party wrapper), the system eliminates every point of adoption friction: reporting a fault is as natural as texting a coworker. This is the difference between a CMMS that gets used and one that gets abandoned within a week.
Layer 2 — API Gateway: FastAPI + Uvicorn
FastAPI was chosen specifically because WhatsApp's Cloud API expects webhook responses within a tight time window — a synchronous, blocking framework would risk timeouts and dropped messages under real load. FastAPI's async-native design lets the gateway acknowledge Meta's webhook instantly (returning 200 OK) while the actual agent processing continues in the background, alongside full CRUD endpoints for work orders, technicians, planning, and analytics. Every inbound webhook is authenticated via HMAC-SHA256 signature verification (X-Hub-Signature-256) before a single byte of the payload is trusted — closing the door on spoofed or tampered requests.
Layer 3 & 4 — Orchestrator & Agent Swarm
At the heart of the system is a LangGraph StateGraph — not a loose collection of independently-prompted LLM calls, but a compiled, directed graph with explicit nodes and conditional edges: rating_gate → intake → knowledge → triage → dispatch → send_reply. This is a deliberate architectural choice: unstructured multi-agent systems tend to degrade into unpredictable, hard-to-debug chains of LLM-to-LLM handoffs. By contrast, a StateGraph gives every transition a named, inspectable route — the system can be reasoned about, tested, and extended node-by-node, and a single Pydantic-typed state object (OrchestratorState) flows through the entire pipeline, so there's never ambiguity about what any given agent knows at any given point.
Seven specialized agents sit inside and around this graph, each running on GPT-4o:
#
Agent
Role
1
Intake Agent
Whisper transcription, GPT-4o Vision fault analysis, 4-language translation, structured fault extraction
2
Triage Agent
Rule-based + LLM priority classification (P0/P1/P2)
3
Dispatch Agent
SQL-driven technician matching and assignment
4
Orchestrator (Maintenance Supervisor)
Graph-level routing and state control
5
Knowledge Agent
ChromaDB vector search over SOPs/manuals
6
Planning Agent
Nightly bin-packing shift scheduling
7
Analytics Agent
KPI aggregation and reporting

Layer 5 — Data Stores: PostgreSQL + pgvector + ChromaDB
Rather than juggling multiple database technologies for the sake of it, the system uses PostgreSQL as the single source of relational truth — ten tables covering assets, technicians, requesters, task requests, work orders, assignments, daily plans, feedback, departments, and knowledge documents — with pgvector support available natively for embedding-adjacent queries where relational and vector data need to sit close together. ChromaDB runs as a dedicated, lightweight vector store purpose-built for the Knowledge Agent's semantic search over SOPs and repair manuals, keeping that workload fast and isolated from transactional traffic. This hybrid isn't complexity for its own sake — it's the right tool for each job, without the operational overhead of forcing everything through one engine that isn't optimized for it.
3. Cognitive Algorithmic Flows (How It Works)
Task Intake & Validation
A worker sends a message — text, a voice note, or a photo of the fault — to the factory WhatsApp number. The Intake Agent routes it accordingly: voice notes are transcribed via the Whisper API, photos are analyzed with GPT-4o Vision (returning a structured description of the equipment, visible damage, and safety signals), and any non-English input (French/Creole, Hindi, or Bengali) is translated automatically. The agent then extracts a structured FaultDetail object — asset name, description, location, urgency signal — and makes a single explicit judgment call: is there enough information to act, or does it need to ask the worker one clarifying question before proceeding? This prevents the system from ever dispatching a technician on guesswork.
Intelligent Triage & Prioritization
Once intake is complete, the Knowledge Agent first pulls relevant SOP context from ChromaDB, which gets folded into the Triage Agent's decision. Triage combines rule-based signals (explicit danger words like “sparks,” “fire,” “flooding”) with LLM judgment to assign a priority tier — P0, P1, or P2 — each carrying its own SLA window. This is the moment unstructured floor chatter becomes a structured, trackable Work Order with a due date and required trade.
Smart Dispatching & Technician Assignment
The Dispatch Agent queries live technician state directly in SQL: who's currently on shift, who's already at capacity (via max_concurrent_jobs), and — among eligible candidates for the required trade — who has the fewest active jobs and the highest historical reward score. For P0 emergencies, the system will even pull in an off-shift technician if no on-shift match exists. Every dispatch triggers a WhatsApp notification with interactive buttons (Acknowledge → On Site → Done), and P0 assignments carry a built-in 5-minute escalation timer: if unacknowledged, the job automatically re-routes to the next available technician via APScheduler, with the cycle repeating until someone responds. Nothing critical is ever left silently waiting.
Predictive Planning
Every night, the Planning Agent runs a scheduled batch job (via APScheduler's cron trigger) that pulls all on-shift technicians and all open/queued work orders, sorted P0-first. It then applies a greedy best-fit-decreasing bin-packing algorithm: each job is assigned to the technician with the matching trade and the most remaining shift capacity (a fixed 420-minute/8-hour budget), maximizing utilization while respecting priority order. Technicians receive their full next-day plan as a WhatsApp message and can confirm it or flag a conflict — closing the loop between an automated schedule and the humans who have to execute it.
4. Database Selection Rationale (Why This Codebase Wins)
PostgreSQL + pgvector was chosen over a split multi-database architecture for a simple reason: operational simplicity without sacrificing capability. A single, battle-tested, ACID-compliant relational engine manages the ten core tables — work orders, assignments, technicians, assets, feedback, and more — while pgvector support means the system isn't locked out of native vector operations if hybrid relational-vector queries are ever needed. One database to back up, one database to monitor, one connection pool to manage — this is the kind of decision that separates a system built to actually run in production from one built to survive a demo.
ChromaDB is used specifically where a dedicated, lightweight, purpose-built vector engine outperforms a general-purpose one: semantic search over SOPs and repair manuals. This is what lets the Knowledge Agent instantly retrieve relevant step-by-step fix guidance and feed it into the Triage Agent's context — giving technicians (and the AI itself) grounded, document-backed answers rather than hallucinated repair advice, all served fast enough to keep up with a live WhatsApp conversation.
5. Why This Solution 
Feasibility & Production Readiness — Every data boundary in the system is enforced with Pydantic schemas, from inbound WhatsApp payloads to inter-agent state to outbound API responses. Configuration is fully isolated via environment variables (no hardcoded secrets), Alembic manages versioned schema migrations, and the whole stack is containerized with Docker and Docker Compose — this isn't a notebook full of API calls, it's a layered application with the separation of concerns you'd expect from an enterprise system.
Scalability — FastAPI's async request handling means the gateway doesn't block on one worker's request while another technician is trying to check in — and LangGraph's node-based execution model keeps each conversation's state cleanly isolated, so growing from a single production line to a multi-factory deployment doesn't require re-architecting the orchestration layer, just scaling out the same graph across more concurrent invocations.
Human-in-the-Loop & Safety — The Rating Gate is a deliberate friction point: a requester with unrated completed work orders is blocked from submitting new ones until they provide feedback, guaranteeing the analytics layer is fed real signal rather than being gamed by endless new requests. Combined with strict HMAC-SHA256 verification on every inbound webhook, the system is protected against both malicious injection at the network layer and silent data quality decay at the business logic layer.


technician matching is currently based on trade match, current workload, and reward  score.


GITHUB REPO ACCESS TO ALL CODES : https://github.com/sumailasherif/Rt_Knits_AI_Challenge	
	
