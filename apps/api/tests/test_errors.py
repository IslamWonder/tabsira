from __future__ import annotations

import logging

import pytest
from fastapi import HTTPException
from pydantic import BaseModel
from starlette.requests import Request

from src import errors
from src.errors import AppError, ErrorCode, error_response
from src.main import create_app
from tests.helpers import client_for


class Payload(BaseModel):
    count: int


@pytest.fixture
async def error_client(make_settings):
    """A client of an application with routes that fail in each way."""
    application = create_app(make_settings())

    @application.get("/_app-error")
    async def app_error() -> None:
        raise AppError(
            ErrorCode.CONFLICT,
            "Already exists.",
            status_code=409,
            headers={"Retry-After": "5"},
        )

    @application.get("/_app-error-default")
    async def app_error_default() -> None:
        raise AppError(ErrorCode.BAD_REQUEST, "Nope.")

    @application.get("/_http/{status}")
    async def http_error(status: int) -> None:
        raise HTTPException(status_code=status, detail="because", headers={"X-Why": "test"})

    @application.get("/_http-detail-object")
    async def http_error_object() -> None:
        raise HTTPException(status_code=400, detail={"a": 1})

    @application.get("/_add")
    async def add(count: int, name: str) -> dict[str, int]:
        return {"count": count}

    @application.post("/_body")
    async def body(payload: Payload) -> Payload:
        return payload

    @application.get("/_boom")
    async def boom() -> None:
        message = "database password is hunter2"
        raise RuntimeError(message)

    async with client_for(application) as http:
        yield http


async def test_unknown_path_is_a_json_not_found_with_the_request_id(error_client):
    response = await error_client.get("/nowhere")

    assert response.status_code == 404
    assert response.json() == {"error": "NOT_FOUND", "detail": "Not Found"}
    assert response.headers["content-type"] == "application/json"
    assert len(response.headers["x-request-id"]) == 32


async def test_wrong_method_is_a_json_method_not_allowed(error_client):
    response = await error_client.post("/health")

    assert response.status_code == 405
    assert response.json()["error"] == "METHOD_NOT_ALLOWED"
    assert "GET" in response.headers["allow"]


async def test_app_error_carries_its_code_status_and_headers(error_client):
    response = await error_client.get("/_app-error")

    assert response.status_code == 409
    assert response.json() == {"error": "CONFLICT", "detail": "Already exists."}
    assert response.headers["retry-after"] == "5"
    assert "x-request-id" in response.headers


async def test_app_error_defaults_to_bad_request(error_client):
    response = await error_client.get("/_app-error-default")

    assert response.status_code == 400
    assert response.json() == {"error": "BAD_REQUEST", "detail": "Nope."}


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (400, "BAD_REQUEST"),
        (401, "UNAUTHORIZED"),
        (403, "FORBIDDEN"),
        (404, "NOT_FOUND"),
        (409, "CONFLICT"),
        (422, "VALIDATION_ERROR"),
        (429, "RATE_LIMITED"),
        (500, "INTERNAL_ERROR"),
        (503, "SERVICE_UNAVAILABLE"),
        (418, "HTTP_ERROR"),
        (413, "HTTP_ERROR"),
    ],
)
async def test_http_exceptions_map_to_stable_codes_and_keep_their_headers(
    error_client, status, code
):
    response = await error_client.get(f"/_http/{status}")

    assert response.status_code == status
    assert response.json() == {"error": code, "detail": "because"}
    assert response.headers["x-why"] == "test"


async def test_a_non_text_detail_is_turned_into_text(error_client):
    response = await error_client.get("/_http-detail-object")

    assert response.json() == {"error": "BAD_REQUEST", "detail": "{'a': 1}"}


async def test_validation_errors_list_fields_without_the_rejected_values(error_client):
    response = await error_client.get("/_add", params={"count": "secret-not-an-int"})

    body = response.json()
    assert response.status_code == 422
    assert body["error"] == "VALIDATION_ERROR"
    assert body["detail"] == "The request does not match the expected format."
    assert {(tuple(f["loc"]), f["type"]) for f in body["fields"]} == {
        (("query", "count"), "int_parsing"),
        (("query", "name"), "missing"),
    }
    assert "secret-not-an-int" not in response.text


async def test_a_malformed_body_is_a_validation_error(error_client):
    response = await error_client.post("/_body", json={"count": "x"})

    assert response.status_code == 422
    assert response.json()["fields"][0]["loc"] == ["body", "count"]


async def test_an_unexpected_failure_is_a_500_that_reveals_nothing(error_client, caplog):
    with caplog.at_level(logging.ERROR, logger="tabsira.errors"):
        response = await error_client.get("/_boom")

    assert response.status_code == 500
    assert response.json() == {"error": "INTERNAL_ERROR", "detail": "Internal server error."}
    assert "hunter2" not in response.text
    request_id = response.headers["x-request-id"]
    assert len(request_id) == 32
    # The log has what the response hides: the request id and the traceback.
    record = caplog.records[0]
    assert request_id in record.getMessage()
    assert "GET /_boom" in record.getMessage()
    assert record.exc_info is not None
    assert "hunter2" in str(record.exc_info[1])


async def test_error_codes_are_unique_and_match_their_names():
    assert all(code.value == code.name for code in ErrorCode)
    assert len({code.value for code in ErrorCode}) == len(ErrorCode)


async def test_a_response_built_without_the_request_id_middleware_has_no_id_header():
    bare = Request({"type": "http", "method": "GET", "path": "/", "headers": []})

    response = error_response(bare, 400, ErrorCode.BAD_REQUEST, "x", headers={"X-A": "1"})

    assert "x-request-id" not in response.headers
    assert response.headers["x-a"] == "1"


@pytest.mark.parametrize(
    ("handler", "expected"),
    [
        (errors.handle_app_error, "AppError"),
        (errors.handle_http_exception, "HTTPException"),
        (errors.handle_validation_error, "RequestValidationError"),
    ],
)
async def test_a_handler_given_the_wrong_kind_of_exception_raises_instead_of_answering(
    handler, expected
):
    bare = Request({"type": "http", "method": "GET", "path": "/", "headers": []})

    with pytest.raises(TypeError, match=f"RuntimeError was routed to the handler of {expected}"):
        await handler(bare, RuntimeError("not mine"))
