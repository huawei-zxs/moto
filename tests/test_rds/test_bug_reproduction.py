import boto3
import pytest
from moto import mock_aws

DEFAULT_REGION = "us-east-1"


@mock_aws
def test_modify_stopped_db_instance_keeps_stopped_status():
    """After modifying a stopped DB instance, its status should remain 'stopped'."""
    client = boto3.client("rds", region_name=DEFAULT_REGION)
    
    # Create a DB instance
    client.create_db_instance(
        DBInstanceIdentifier="test-db-1",
        DBInstanceClass="db.m1.small",
        Engine="mysql",
        MasterUsername="root",
        MasterUserPassword="password",
        AllocatedStorage=10,
    )
    
    # Verify initial state
    instance = client.describe_db_instances(DBInstanceIdentifier="test-db-1")["DBInstances"][0]
    assert instance["DBInstanceStatus"] == "available"
    
    # Stop the instance
    client.stop_db_instance(DBInstanceIdentifier="test-db-1")
    instance = client.describe_db_instances(DBInstanceIdentifier="test-db-1")["DBInstances"][0]
    assert instance["DBInstanceStatus"] == "stopped"
    
    # Modify the stopped instance
    client.modify_db_instance(
        DBInstanceIdentifier="test-db-1",
        BackupRetentionPeriod=7,
        ApplyImmediately=True,
    )
    
    # BUG: status should still be "stopped", but bug makes it "available"
    instance = client.describe_db_instances(DBInstanceIdentifier="test-db-1")["DBInstances"][0]
    assert instance["DBInstanceStatus"] == "stopped", (
        f"Expected status 'stopped' after modifying a stopped instance, "
        f"but got '{instance['DBInstanceStatus']}'"
    )
    assert instance["BackupRetentionPeriod"] == 7
