"""Deterministic progress replay."""

from ai_brain.stage2.progress.projection import project_progress


def replay_progress(store, learner_id: str):
    events = store.events(learner_id)
    projections = project_progress(learner_id, events)
    return {"status": "CURRENT", "event_count": len(events), "projections": projections}
