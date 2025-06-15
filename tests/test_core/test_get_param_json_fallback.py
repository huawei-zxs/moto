"""Test for _get_param JSON body fallback behavior.

This test verifies that _get_param correctly falls through to path params
and if_none default when a parameter is missing from the JSON body.
"""
import json
from typing import Any, Dict

import pytest
from botocore.awsrequest import AWSPreparedRequest, HTTPHeaders

from moto.core.responses import BaseResponse


def _make_response_with_json_body(body_obj: Dict[str, Any]) -> BaseResponse:
    """Helper to create a BaseResponse with a JSON body."""
    body = json.dumps(body_obj).encode("utf-8")
    headers = HTTPHeaders()
    headers["Content-Type"] = "application/json"
    request = AWSPreparedRequest("POST", "http://test.example.com/", headers, body, False)
    response = BaseResponse()
    response.setup_class(request, request.url, request.headers)
    return response


class TestGetParamJsonFallback:
    """Tests for _get_param JSON body fallback.

    The BUG being tested: _get_param's JSON body fallback uses .get()
    instead of [param_name]. When a key is missing from the JSON body,
    .get() returns None immediately, short-circuiting the fallback chain
    (path params -> if_none default). The correct behavior is to use
    [param_name] with KeyError handling, which falls through to if_none.
    """

    def test_param_found_in_json_body(self):
        """When param exists in JSON body, it should be returned."""
        response = _make_response_with_json_body({"Region": "us-east-1", "MaxItems": 10})

        result = response._get_param("Region")
        assert result == "us-east-1", f"Expected 'us-east-1', got {result!r}"

        result = response._get_param("MaxItems")
        assert result == 10, f"Expected 10, got {result!r}"

    def test_param_missing_from_json_body_returns_if_none(self):
        """
        When param is missing from JSON body AND querystring, _get_param
        MUST return the if_none default value, NOT None.

        This is the core bug: body_json.get(param_name) returns None
        for missing keys, which is NOT the same as falling through to
        the if_none default. This causes silent data corruption where
        callers receive None instead of their expected default value.
        """
        response = _make_response_with_json_body({"ExistingKey": "some_value"})

        # "MissingKey" is NOT in the JSON body.
        # BUG: body_json.get("MissingKey") returns None, bypassing the
        # path-params fallback and the if_none default
        result = response._get_param("MissingKey", if_none="my_default")
        assert result == "my_default", (
            f"Expected 'my_default' (if_none fallback), but got {result!r}. "
            f"BUG: The JSON body .get() is short-circuiting "
            f"the fallback chain with None."
        )

    def test_param_missing_with_non_none_default(self):
        """Verify if_none with various non-None defaults is preserved."""
        response = _make_response_with_json_body({"Name": "test"})

        # List default
        default_list = [1, 2, 3]
        result = response._get_param("Tags", if_none=default_list)
        assert result == default_list, (
            f"Expected {default_list!r}, but got {result!r}"
        )

        # Int default
        result = response._get_param("MaxResults", if_none=50)
        assert result == 50, f"Expected 50, but got {result!r}"

        # Dict default
        default_dict = {"Key": "Value"}
        result = response._get_param("Config", if_none=default_dict)
        assert result == default_dict, f"Expected {default_dict!r}, but got {result!r}"

    def test_param_missing_with_none_default(self):
        """
        When if_none is None (default), both correct and buggy behavior
        return None. This makes the bug extremely hard to detect.
        """
        response = _make_response_with_json_body({"ExistingKey": "value"})

        # With default if_none=None, behavior is identical in both cases
        result = response._get_param("MissingKey")  # if_none defaults to None
        assert result is None

    def test_param_found_via_querystring_ignores_json(self):
        """When param is in querystring, JSON body should not be consulted."""
        body = json.dumps({"Name": "json_value"}).encode("utf-8")
        headers = HTTPHeaders()
        headers["Content-Type"] = "application/json"
        request = AWSPreparedRequest("POST", "http://test/", headers, body, False)
        response = BaseResponse()
        response.setup_class(request, request.url, request.headers)

        # Manually set querystring to override JSON body
        response.querystring["Name"] = ["querystring_value"]

        result = response._get_param("Name")
        assert result == "querystring_value", (
            f"Querystring should take priority, got {result!r}"
        )

    def test_known_param_name_not_in_body_or_querystring(self):
        """
        Test with a realistic AWS parameter name that's commonly missing.
        For example, 'MaxResults' is an optional parameter in many AWS
        list APIs. When not provided, the service should use its if_none
        default (e.g., 100).
        """
        response = _make_response_with_json_body({"ResourceArns": ["arn:aws:s3:::bucket"]})

        # Simulate a typical AWS list API call without MaxResults
        result = response._get_param("MaxResults", if_none=100)
        assert result == 100, (
            f"Expected if_none default 100, but got {result!r}. "
            f"BUG: .get() returned None instead of falling through."
        )
