"""How replies from OpenAI are read."""

from app.ai.transport import json_part


def test_a_sentence_before_the_json_is_dropped():
    assert json_part('{"a": 1}') == '{"a": 1}'
    assert json_part('Note: the image clashes.\n\n{"a": {"b": "}"}}\nthanks') == '{"a": {"b": "}"}}'
    assert json_part("no json here") == "no json here"
