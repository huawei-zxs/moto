"""Tests for Step Functions intrinsic JSON manipulation functions."""
from unittest.mock import MagicMock

from moto.stepfunctions.parser.asl.component.intrinsic.argument.function_argument import (
    FunctionArgument,
)
from moto.stepfunctions.parser.asl.component.intrinsic.argument.function_argument_list import (
    FunctionArgumentList,
)
from moto.stepfunctions.parser.asl.component.intrinsic.function.statesfunction.json_manipulation.string_to_json import (
    StringToJson,
)


def _create_string_to_json(value):
    """Helper: create a StringToJson instance with a single literal argument."""
    arg = FunctionArgument(value=value)
    arg_list = FunctionArgumentList(arg_list=[arg])
    return StringToJson(arg_list=arg_list)


def _execute(fn):
    """Execute StringToJson via the public eval() method with a mock env."""
    env = MagicMock()
    env.stack = []  # Real list, so stack operations work correctly
    fn.eval(env)
    assert len(env.stack) == 1, f"Expected 1 result on stack, got {env.stack}"
    return env.stack[0]


# ==================== FAIL_TO_PASS ====================
# These tests CURRENTLY FAIL (crash with json.JSONDecodeError)
# and WILL PASS after the fix is applied

def test_string_to_json_with_empty_string():
    """
    States.StringToJson("") should handle empty string gracefully
    (return null) rather than crashing with an unhandled JSONDecodeError.
    """
    fn = _create_string_to_json("")
    result = _execute(fn)
    assert result is None


def test_string_to_json_with_whitespace_string():
    """
    States.StringToJson("   ") should handle whitespace-only string
    gracefully (return null) rather than crashing.
    """
    fn = _create_string_to_json("   ")
    result = _execute(fn)
    assert result is None


# ==================== PASS_TO_PASS ====================
# These tests PASS both before and after the fix

def test_string_to_json_with_valid_json_object():
    """Valid JSON object string should be parsed correctly."""
    fn = _create_string_to_json('{"key": "value"}')
    result = _execute(fn)
    assert result == {"key": "value"}


def test_string_to_json_with_valid_json_array():
    """Valid JSON array string should be parsed correctly."""
    fn = _create_string_to_json('[1, 2, 3]')
    result = _execute(fn)
    assert result == [1, 2, 3]


def test_string_to_json_with_none_input():
    """None input (no argument) should return None."""
    fn = _create_string_to_json(None)
    result = _execute(fn)
    assert result is None


def test_string_to_json_with_json_string_primitive():
    """Valid JSON string primitive should be parsed correctly."""
    fn = _create_string_to_json('"hello world"')
    result = _execute(fn)
    assert result == "hello world"


def test_string_to_json_with_json_number():
    """Valid JSON number should be parsed correctly."""
    fn = _create_string_to_json("42")
    result = _execute(fn)
    assert result == 42


def test_string_to_json_with_json_null():
    """Valid JSON null literal should be parsed to Python None."""
    fn = _create_string_to_json("null")
    result = _execute(fn)
    assert result is None


def test_string_to_json_with_json_boolean():
    """Valid JSON boolean should be parsed correctly."""
    fn = _create_string_to_json("true")
    result = _execute(fn)
    assert result is True
