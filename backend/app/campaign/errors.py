"""What a campaign chat refuses, and why. The chat routes turn each into an HTTP answer."""

from app.campaign import stages


class NoBrand(Exception):
    pass


class UnknownQuestion(ValueError):
    pass


class BadPlan(ValueError):
    pass


class UnknownAsset(ValueError):
    pass


class BadContent(ValueError):
    """Typed-in asset content of the wrong shape (a list where text goes, say)."""


class QuestionExpired(stages.WrongStage):
    """The question was asked at an earlier stage (before the plan was approved, say), so it no longer applies."""


class PlanChanged(stages.WrongStage):
    """The plan or its research changed since this was started (or since the user last saw it)."""
