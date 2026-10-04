from __future__ import annotations

from typing import Annotated, Literal

import pytest
from pydantic import BaseModel, Field, RootModel

from src.ai.strict_schema import _strict, response_format, strict_json_schema


class Box(BaseModel):
    """A box."""

    x: int


class Item(BaseModel):
    title: Annotated[str, Field(min_length=1, max_length=40)]
    default: int = 3
    kind: Literal["thing"]
    box: Annotated[Box, Field(description="where it is")]
    maybe: Box | None = None
    tags: Annotated[list[str], Field(min_length=1, max_length=4)]


class Answer(BaseModel):
    items: list[Item]
    note: str | None = None


def walk(node):
    """Yield every dict of a schema."""
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from walk(value)


def test_every_object_is_closed_and_requires_all_its_properties():
    schema = strict_json_schema(Answer)

    objects = [node for node in walk(schema) if node.get("type") == "object"]
    assert objects
    for node in objects:
        assert node["additionalProperties"] is False
        assert node["required"] == list(node["properties"])


def test_keywords_strict_mode_refuses_are_dropped_but_property_names_are_kept():
    schema = strict_json_schema(Answer)

    item = schema["$defs"]["Item"]
    assert set(item["properties"]) == {"title", "default", "kind", "box", "maybe", "tags"}
    for node in walk(schema):
        if node is item["properties"] or node is schema["$defs"]:
            continue
        assert not {"default", "title", "minLength", "maxLength"} & set(node)
    # Array limits are supported by strict mode and kept.
    assert item["properties"]["tags"]["minItems"] == 1


def test_a_reference_with_siblings_is_inlined_and_const_becomes_an_enum():
    item = strict_json_schema(Answer)["$defs"]["Item"]

    assert item["properties"]["box"]["description"] == "where it is"
    assert item["properties"]["box"]["properties"] == {"x": {"type": "integer"}}
    assert "$ref" not in item["properties"]["box"]
    assert item["properties"]["kind"] == {"enum": ["thing"], "type": "string"}


def test_response_format_names_the_model_and_asks_for_strict_mode():
    value = response_format(Box)

    assert value == {
        "type": "json_schema",
        "json_schema": {
            "name": "Box",
            "strict": True,
            "schema": {
                "description": "A box.",
                "type": "object",
                "properties": {"x": {"type": "integer"}},
                "additionalProperties": False,
                "required": ["x"],
            },
        },
    }


class Free(BaseModel):
    data: dict[str, int]


def test_a_free_form_object_is_refused():
    with pytest.raises(ValueError, match="free-form object"):
        strict_json_schema(Free)


class Root(RootModel[list[int]]):
    pass


def test_the_root_must_be_an_object():
    with pytest.raises(ValueError, match="must be an object"):
        strict_json_schema(Root)


def test_an_unresolvable_reference_is_refused():
    with pytest.raises(ValueError, match="unresolvable"):
        _strict({"$ref": "#/$defs/Missing", "description": "x"}, {})
