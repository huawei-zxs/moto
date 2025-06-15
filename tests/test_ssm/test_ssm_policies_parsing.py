"""
Tests for SSM Parameter Store policies JSON parsing.

These tests validate that the Policies field in SSM parameters is correctly
parsed from its JSON representation. The bug being tested is: iterating over
the raw JSON string (self.policies) instead of the parsed list (policy_list),
which causes character-by-character iteration and produces corrupted PolicyText
and PolicyType values.

To reproduce the bug:
    Apply bug_patch.diff to moto/ssm/models.py

Expected behavior (without the bug):
    - A single policy "Expiration" produces one correct policy entry
    - Multiple policies produce correct entries in order
    - Invalid JSON is silently ignored (no Policies key in output)
"""

import json
from datetime import datetime

import boto3
import pytest
from moto import mock_aws


SSM_REGION = "us-east-1"
ACCOUNT_ID = "123456789012"


@mock_aws
def test_put_parameter_single_policy_returns_correct_values():
    """
    Test that a single policy string in a JSON array is correctly parsed.
    
    AWS SSM expects the Policies parameter to be a JSON-encoded array of strings.
    The correct behavior: each element in the parsed JSON array becomes a policy
    entry with PolicyText and PolicyType set to that string value.
    
    Bug behavior: if the code iterates over the raw JSON string instead of the
    parsed list, the output would contain 14 policy entries with single-character
    values like '[', '"', 'E', 'x', etc. instead of one entry with 'Expiration'.
    """
    name = "test-single-policy"
    client = boto3.client("ssm", region_name=SSM_REGION)
    
    client.put_parameter(
        Name=name,
        Description="Test parameter with single policy",
        Value="test-value",
        Type="String",
        Policies='["Expiration"]',
    )

    response = client.describe_parameters(
        ParameterFilters=[{"Key": "Name", "Option": "Equals", "Values": [name]}]
    )
    
    assert len(response["Parameters"]) == 1
    param = response["Parameters"][0]
    
    # Verify Policies field exists and has exactly one entry
    assert "Policies" in param
    policies = param["Policies"]
    assert len(policies) == 1, (
        f"Expected exactly 1 policy, got {len(policies)}. "
        f"Bug: iterating over raw JSON string character by character."
    )
    
    # Verify the single policy entry has correct values
    expected_policy = {
        "PolicyText": "Expiration",
        "PolicyType": "Expiration",
        "PolicyStatus": "Finished",
    }
    assert policies[0] == expected_policy, (
        f"Expected policy {expected_policy}, got {policies[0]}. "
        f"Bug: PolicyText/PolicyType contain individual characters from raw JSON string."
    )


@mock_aws
def test_put_parameter_multiple_policies_parsed_correctly():
    """
    Test that multiple policy strings in a JSON array are correctly parsed
    and preserved in the original order.
    
    AWS SSM preserves the order of policies as provided in the JSON array.
    The correct behavior: each element produces a corresponding policy entry
    in the same order as the input array.
    
    Bug behavior: if iterating over the raw JSON string, the output would be
    28+ single-character entries instead of 4 properly named policy entries,
    or the order would be wrong (based on character positions in the JSON string
    rather than array positions).
    """
    name = "test-multi-policy"
    client = boto3.client("ssm", region_name=SSM_REGION)
    
    policy_names = [
        "Expiration",
        "NoChangeNotification",
        "ExpirationNotification",
        "TagPolicy",
    ]
    policies_json = json.dumps(policy_names)
    
    client.put_parameter(
        Name=name,
        Description="Test parameter with multiple policies",
        Value="test-value",
        Type="String",
        Policies=policies_json,
    )

    response = client.describe_parameters(
        ParameterFilters=[{"Key": "Name", "Option": "Equals", "Values": [name]}]
    )
    
    assert len(response["Parameters"]) == 1
    param = response["Parameters"][0]
    
    assert "Policies" in param
    policies = param["Policies"]
    
    # Verify we have the correct number of policies
    assert len(policies) == len(policy_names), (
        f"Expected {len(policy_names)} policies, got {len(policies)}. "
        f"Bug: iterating over raw JSON string produces character-level entries."
    )
    
    # Verify each policy has correct values in the expected order
    for i, (actual, expected_name) in enumerate(zip(policies, policy_names)):
        expected_entry = {
            "PolicyText": expected_name,
            "PolicyType": expected_name,
            "PolicyStatus": "Finished",
        }
        assert actual == expected_entry, (
            f"Policy at index {i}: expected {expected_entry}, got {actual}. "
            f"Bug: PolicyText/PolicyType are wrong due to string-level iteration."
        )
    
    # Additional check: verify the names match the input order
    returned_names = [p["PolicyText"] for p in policies]
    assert returned_names == policy_names, (
        f"Policy order mismatch: expected {policy_names}, got {returned_names}. "
        f"Bug: JSON array order is not preserved."
    )


@mock_aws
def test_put_parameter_invalid_policies_json_silently_ignored():
    """
    Test that invalid JSON in the Policies field is silently ignored.
    
    AWS SSM ignores policies that are not valid JSON, and does not include
    a Policies key in the returned parameter description.
    
    This validates the existing behavior (should work with or without the bug,
    since the JSONDecodeError is caught separately from the iteration logic).
    """
    name = "test-invalid-policy-json"
    client = boto3.client("ssm", region_name=SSM_REGION)
    
    client.put_parameter(
        Name=name,
        Description="Test parameter with invalid policies JSON",
        Value="test-value",
        Type="String",
        Policies="this is not valid json at all",
    )

    param = client.describe_parameters(
        ParameterFilters=[{"Key": "Name", "Option": "Equals", "Values": [name]}]
    )["Parameters"][0]
    
    # Invalid JSON should result in no Policies key in the output
    assert "Policies" not in param, (
        "Invalid JSON policies should not produce a Policies field in the output."
    )


@mock_aws
def test_put_parameter_empty_policies_array():
    """
    Test that an empty JSON array in the Policies field is handled correctly.
    
    AWS SSM accepts an empty array and returns it as an empty list.
    """
    name = "test-empty-policies"
    client = boto3.client("ssm", region_name=SSM_REGION)
    
    client.put_parameter(
        Name=name,
        Description="Test parameter with empty policies array",
        Value="test-value",
        Type="String",
        Policies="[]",
    )

    param = client.describe_parameters(
        ParameterFilters=[{"Key": "Name", "Option": "Equals", "Values": [name]}]
    )["Parameters"][0]
    
    assert "Policies" in param
    policies = param["Policies"]
    assert policies == [], (
        f"Expected empty list for empty policies array, got {policies}"
    )


@mock_aws
def test_put_parameter_policies_persist_after_overwrite():
    """
    Test that when a parameter is overwritten without specifying new policies,
    the existing policies are preserved correctly.
    
    This is a regression test: the existing test for overwrite preservation
    uses a single-policy array, which with the bug would produce corrupted
    results. This test explicitly validates with multiple policies.
    """
    name = "test-policies-overwrite"
    client = boto3.client("ssm", region_name=SSM_REGION)
    
    policy_names = ["Expiration", "BackupPolicy"]
    policies_json = json.dumps(policy_names)
    
    # Create parameter with policies
    client.put_parameter(
        Name=name,
        Description="Original description",
        Value="original-value",
        Type="String",
        Policies=policies_json,
    )
    
    # Overwrite just the value (no policies specified)
    client.put_parameter(
        Name=name,
        Value="updated-value",
        Overwrite=True,
    )
    
    response = client.describe_parameters(
        ParameterFilters=[{"Key": "Name", "Option": "Equals", "Values": [name]}]
    )
    
    param = response["Parameters"][0]
    
    # Verify description is preserved
    assert param["Description"] == "Original description"
    
    # Verify policies are preserved correctly after overwrite
    assert "Policies" in param
    policies = param["Policies"]
    assert len(policies) == 2, (
        f"After overwrite, expected 2 preserved policies, got {len(policies)}"
    )
    
    returned_names = [p["PolicyText"] for p in policies]
    assert returned_names == policy_names, (
        f"After overwrite, expected {policy_names}, got {returned_names}"
    )
