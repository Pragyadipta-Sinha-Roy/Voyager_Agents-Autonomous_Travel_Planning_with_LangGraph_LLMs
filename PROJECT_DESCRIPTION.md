# Voyager Agents — Project Description

## Elevator Pitch

Voyager Agents is a multi-agent AI travel planner. Instead of asking a single chatbot to "just figure it out," the user's request is handed off through a pipeline of specialized agents — one finds flights, one finds hotels, one drafts an itinerary, and one polishes the final, presentable travel plan. The result is a structured, end-to-end trip plan generated from a single sentence like *"Plan a 7 day Japan trip from Kolkata under 2 lakhs."*

## The Problem

Planning a trip usually means juggling multiple tabs: a flight search site, a hotel booking site, a handful of travel blogs for sightseeing ideas, and a spreadsheet or notes app to tie a budget together. Generic AI chatbots can *talk about* travel, but they don't reach out to live flight data, don't search the web for current hotel deals, and don't consistently return a usable, well-organized plan.

## The Solution

Voyager Agents breaks trip planning into discrete responsibilities and assigns each one to a dedicated agent inside a [LangGraph](https://www.langchain.com/langgraph) state graph:

1. **Flight Agent** — parses the request (origin, destination, dates/cities/countries) and queries the AviationStack API for live flight data.
2. **Hotel Agent** — searches the web (via Tavily) for current hotel recommendations near the destination.
3. **Itinerary Agent** — feeds the flight and hotel results into an LLM (Groq-hosted Llama 3.3 70B) to draft a day-by-day plan.
4. **Final Response Agent** — reformats everything into a clean, consistent six-section answer: Trip Summary, Flight Information, Hotel Suggestions, Day-by-Day Itinerary, Estimated Budget, and Final Recommendations.

Each agent only does one job, hands its output to the next, and the whole conversation state (including which flights/hotels were found) is checkpointed in PostgreSQL per conversation thread — so a user's trip-planning session can be resumed rather than starting from scratch.

## Key Features

- **Live, not hallucinated, flight data** — pulled from AviationStack rather than invented by the LLM.
- **Web-grounded hotel suggestions** — sourced from real search results, not static training data.
- **Multi-agent orchestration** — a LangGraph `StateGraph` coordinates four specialized agents instead of one large prompt.
- **Conversation memory** — a PostgreSQL-backed checkpointer persists state per `thread_id`.
- **Natural language input** — understands phrasing like "flights from Dhaka to Tokyo" or "Japan trip from Kolkata" and resolves cities/countries to airport codes automatically.
- **Usable output** — the frontend renders the answer as formatted Markdown, and lets the user copy it or export it directly to PDF.

## Who It's For

Anyone who wants a fast first draft of a trip plan — flights, hotels, a rough itinerary, and a ballpark budget — without manually cross-referencing multiple travel sites. It's also a practical reference implementation of a **multi-agent LangGraph application** with real external tool calls (as opposed to a single-prompt chatbot).

## What Makes It Different From "Just Asking ChatGPT"

| Generic chatbot | Voyager Agents |
|---|---|
| Answers from training data, which can be outdated or invented | Calls live APIs for flights and current web search results for hotels |
| One shot, one prompt | A pipeline of four specialized agents, each with a narrow job |
| No memory across requests unless you paste the whole history back | Conversation state persisted server-side per `thread_id` in PostgreSQL |
| Free-form, inconsistent output | Enforced six-section output structure for a predictable, shareable plan |

## Tech Highlights

- **Orchestration:** LangGraph (`StateGraph`) with a `PostgresSaver` checkpointer
- **LLM:** Groq-hosted `llama-3.3-70b-versatile` via `langchain-groq`
- **Tools:** AviationStack (flights), Tavily (web/hotel search)
- **Backend:** FastAPI
- **Frontend:** Jinja2-rendered HTML, vanilla JS, Markdown rendering (`marked.js`), client-side PDF export (`html2pdf.js`)
- **Deployment:** Dockerized, deployed on Render with a Render-managed PostgreSQL instance

## Future Scope

- Real ticket pricing (AviationStack provides live flight *status*, not fares — a pricing API such as Amadeus would close that gap)
- User accounts so trip threads persist across devices, not just `localStorage`
- Multi-city itineraries and return-trip planning
- Streaming responses so the user sees the itinerary being written in real time instead of waiting for the full pipeline to finish
