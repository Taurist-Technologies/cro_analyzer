"""Structural checks on the structured-output schema."""

from analyzer.pdp.schema import PDP_ANALYSIS_SCHEMA


def _walk_objects(node, path="$"):
    if isinstance(node, dict):
        if node.get("type") == "object":
            yield path, node
        for key, value in node.items():
            yield from _walk_objects(value, f"{path}.{key}")
    elif isinstance(node, list):
        for i, item in enumerate(node):
            yield from _walk_objects(item, f"{path}[{i}]")


def test_every_object_disallows_additional_properties():
    for path, obj in _walk_objects(PDP_ANALYSIS_SCHEMA):
        assert obj.get("additionalProperties") is False, f"{path} missing additionalProperties: false"


def test_every_object_requires_all_its_properties():
    # Structured outputs require the full property list in `required`
    for path, obj in _walk_objects(PDP_ANALYSIS_SCHEMA):
        props = set(obj.get("properties", {}).keys())
        required = set(obj.get("required", []))
        assert props == required, f"{path}: properties {props ^ required} not in required"


def test_no_unsupported_constraints():
    # Structured outputs reject these keywords
    banned = {"minItems", "maxItems", "minimum", "maximum", "minLength", "maxLength", "multipleOf"}

    def walk(node):
        if isinstance(node, dict):
            assert not banned & set(node.keys()), f"unsupported constraint in {node.keys()}"
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(PDP_ANALYSIS_SCHEMA)


def test_scorecards_cover_pdp_dimensions():
    scorecards = PDP_ANALYSIS_SCHEMA["properties"]["scorecards"]["properties"]
    assert set(scorecards) == {"buy_box", "product_content", "social_proof", "mobile_experience", "page_speed"}
