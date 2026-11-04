"""A campaign's stages, in order. A stage can't be skipped, and nothing is written before approval.

brief -> asking (only when there are questions) -> plan_ready -> approved -> writing -> done

At done, assets are edited by chat or by hand; that never moves the stage back.
"""

BRIEF = "brief"
"""Waiting for the brief to be pasted."""
ASKING = "asking"
"""Questions are being asked, one at a time."""
PLAN_READY = "plan_ready"
"""A plan is proposed; the user can change it by chat or on the cards, then approve it."""
APPROVED = "approved"
WRITING = "writing"
"""Assets are being written, a few at a time."""
DONE = "done"


class WrongStage(Exception):
    """The action isn't allowed at the campaign's current stage."""


def require(stage: str, *allowed: str, action: str) -> None:
    if stage not in allowed:
        raise WrongStage(f"Can't {action} now: the campaign is at the {stage.replace('_', ' ')} stage.")
