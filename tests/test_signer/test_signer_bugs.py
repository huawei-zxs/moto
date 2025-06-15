import boto3
import pytest

from moto import mock_aws


@mock_aws
def test_get_signing_profile__nonexistent_profile():
    """
    Test that getting a non-existent signing profile raises an error
    that is NOT an AttributeError (which would indicate a null-value bug).
    """
    client = boto3.client("signer", region_name="eu-west-1")

    # Create a valid profile to ensure the backend is working
    client.put_signing_profile(
        profileName="existing_prof",
        platformId="AWSLambda-SHA384-ECDSA",
    )

    # Attempt to retrieve a profile that does not exist.
    # With the null bug, this raises AttributeError on None.to_dict().
    # Without the bug, this should raise a lookup error (KeyError) instead.
    with pytest.raises(Exception) as exc_info:
        client.get_signing_profile(profileName="no_such_profile")

    # The key assertion: the error must NOT be an AttributeError,
    # because AttributeError indicates a null-value dereference bug
    # (calling .to_dict() on None returned by dict.get()).
    assert not isinstance(exc_info.value, AttributeError), (
        f"Got AttributeError: {exc_info.value}. "
        "This indicates a null-value bug: get_signing_profile returned None "
        "and the caller tried to call .to_dict() on it."
    )
