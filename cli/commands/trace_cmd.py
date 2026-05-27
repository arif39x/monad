from __future__ import annotations

from cli.context import CliContext


async def execute(context: CliContext, *, trace_id: str) -> dict[str, object]:
    events = await context.engine.events_for_trace(trace_id)
    event_list = [event.model_dump(mode="json") for event in events]

    intents = [e["payload"].get("intent", "") for e in event_list if e["event_type"] == "intent_classified"]
    providers_used = set()
    for e in event_list:
        if e["event_type"] in ("provider_requested", "provider_responded"):
            p = e["payload"].get("provider", "")
            if p:
                providers_used.add(p)

    knowledge_count = sum(1 for e in event_list if e["event_type"] == "knowledge_retrieved")
    memory_events = sum(1 for e in event_list if e["event_type"] == "memory_summarized")

    return {
        "status": "ok",
        "trace_id": trace_id,
        "event_count": len(event_list),
        "providers_used": sorted(providers_used),
        "intents": intents,
        "knowledge_retrievals": knowledge_count,
        "memory_summaries": memory_events,
        "events": event_list,
    }
