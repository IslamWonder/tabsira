"""
Strict JSON schemas for structured output, generated from Pydantic models.

OpenAI's strict mode (and OVH's guided decoding, which reads the same
`response_format`) needs every object closed (`additionalProperties: false`)
with every property required, and refuses some keywords. The Pydantic model
stays the single definition: the schema sent to the model is derived from it,
and the answer is validated against the model again on our side, so a keyword
removed here (a length limit, a default) is still enforced.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

# Keywords strict mode does not accept; Pydantic enforces them after the call.
DROPPED_KEYWORDS = frozenset(
    {"default", "title", "minLength", "maxLength", "examples", "discriminator"}
)
# Keywords whose value maps names to schemas; the names are not keywords.
NAMED_SCHEMAS = frozenset({"properties", "$defs"})


def strict_json_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Return the strict JSON schema of `model`, ready for `response_format`."""
    schema = model.model_json_schema()
    if schema.get("type") != "object":
        message = f"{model.__name__} must be an object to be used as structured output"
        raise ValueError(message)
    definitions = schema.get("$defs", {})
    result = _strict(schema, definitions)
    assert isinstance(result, dict)
    return result


def response_format(model: type[BaseModel]) -> dict[str, Any]:
    """Return the `response_format` value that asks for `model` as strict JSON."""
    return {
        "type": "json_schema",
        "json_schema": {
            "name": model.__name__,
            "strict": True,
            "schema": strict_json_schema(model),
        },
    }


def _strict(node: Any, definitions: dict[str, Any]) -> Any:
    if isinstance(node, list):
        return [_strict(item, definitions) for item in node]
    if not isinstance(node, dict):
        return node
    if "$ref" in node and len(node) > 1:
        # Strict mode refuses keywords beside a $ref: inline the definition instead.
        siblings = {key: value for key, value in node.items() if key != "$ref"}
        node = {**_definition(node["$ref"], definitions), **siblings}

    result: dict[str, Any] = {}
    for key, value in node.items():
        if key in DROPPED_KEYWORDS:
            continue
        if key in NAMED_SCHEMAS:
            result[key] = {name: _strict(sub, definitions) for name, sub in value.items()}
        elif key == "const":
            result["enum"] = [value]
        else:
            result[key] = _strict(value, definitions)

    if result.get("type") == "object":
        if "properties" not in result:
            message = "strict structured output cannot hold a free-form object"
            raise ValueError(message)
        result["additionalProperties"] = False
        result["required"] = list(result["properties"])
    return result


def _definition(reference: str, definitions: dict[str, Any]) -> dict[str, Any]:
    name = reference.removeprefix("#/$defs/")
    definition = definitions.get(name)
    if not isinstance(definition, dict):
        message = f"unresolvable schema reference {reference}"
        raise ValueError(message)  # noqa: TRY004
    return definition
