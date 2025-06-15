import boto3
import pytest
from botocore.exceptions import ClientError

from moto import mock_aws


@mock_aws
def test_add_instance_as_cluster_member():
    # When creating a rds instance with DBClusterIdentifier provided,
    # the instance is included as a ClusterMember in the describe_db_clusters call
    client = boto3.client("rds", "us-east-1")

    _ = client.create_db_cluster(
        DBClusterIdentifier="dbci",
        Engine="mysql",
        MasterUsername="masterusername",
        MasterUserPassword="hunter2_",
    )["DBCluster"]
    client.create_db_instance(
        DBInstanceIdentifier="dbi",
        DBClusterIdentifier="dbci",
        DBInstanceClass="db.r5.large",
        Engine="mysql",
    )

    cluster = client.describe_db_clusters()["DBClusters"][0]
    assert "DBClusterMembers" in cluster

    members = cluster["DBClusterMembers"]
    assert len(members) == 1
    assert members[0] == {
        "DBInstanceIdentifier": "dbi",
        "IsClusterWriter": True,
        "DBClusterParameterGroupStatus": "in-sync",
        "PromotionTier": 1,
    }


@mock_aws
def test_remove_instance_from_cluster():
    # When creating a rds instance with DBClusterIdentifier provided,
    # the instance is included as a ClusterMember in the describe_db_clusters call
    client = boto3.client("rds", "us-east-1")

    _ = client.create_db_cluster(
        DBClusterIdentifier="dbci",
        Engine="mysql",
        MasterUsername="masterusername",
        MasterUserPassword="hunter2_",
    )["DBCluster"]
    client.create_db_instance(
        DBInstanceIdentifier="dbi",
        DBClusterIdentifier="dbci",
        DBInstanceClass="db.r5.large",
        Engine="mysql",
    )

    client.delete_db_instance(
        DBInstanceIdentifier="dbi",
        SkipFinalSnapshot=True,
    )

    cluster = client.describe_db_clusters()["DBClusters"][0]
    assert "DBClusterMembers" in cluster

    members = cluster["DBClusterMembers"]
    assert len(members) == 0


@mock_aws
def test_add_instance_to_serverless_cluster():
    client = boto3.client("rds", "us-east-1")

    _ = client.create_db_cluster(
        DBClusterIdentifier="dbci",
        Engine="aurora-postgresql",
        EngineMode="serverless",
        MasterUsername="masterusername",
        MasterUserPassword="hunter2_",
    )["DBCluster"]
    with pytest.raises(ClientError) as exc:
        client.create_db_instance(
            DBInstanceIdentifier="dbi",
            DBClusterIdentifier="dbci",
            DBInstanceClass="db.r5.large",
            Engine="aurora-postgresql",
        )
    err = exc.value.response["Error"]
    assert err["Code"] == "InvalidParameterValue"
    assert err["Message"] == "Instances cannot be added to Aurora Serverless clusters."


@mock_aws
def test_delete_db_cluster_fails_if_cluster_contains_db_instances():
    cluster_identifier = "test-cluster"
    instance_identifier = "test-instance"
    client = boto3.client("rds", "us-east-1")
    client.create_db_cluster(
        DBClusterIdentifier=cluster_identifier,
        Engine="aurora-postgresql",
        MasterUsername="test-user",
        MasterUserPassword="password",
    )
    client.create_db_instance(
        DBClusterIdentifier=cluster_identifier,
        Engine="aurora-postgresql",
        DBInstanceIdentifier=instance_identifier,
        DBInstanceClass="db.t4g.medium",
    )
    with pytest.raises(ClientError) as exc:
        client.delete_db_cluster(
            DBClusterIdentifier=cluster_identifier,
            SkipFinalSnapshot=True,
        )
    err = exc.value.response["Error"]
    assert err["Code"] == "InvalidDBClusterStateFault"
    assert (
        err["Message"]
        == "Cluster cannot be deleted, it still contains DB instances in non-deleting state."
    )
    client.delete_db_instance(
        DBInstanceIdentifier=instance_identifier,
        SkipFinalSnapshot=True,
    )
    cluster = client.delete_db_cluster(
        DBClusterIdentifier=cluster_identifier,
        SkipFinalSnapshot=True,
    )["DBCluster"]
    assert cluster["DBClusterIdentifier"] == cluster_identifier


@mock_aws
def test_create_instance_with_non_existent_cluster_raises_error():
    client = boto3.client("rds", "us-east-1")
    cluster_identifier = "non-existent-cluster-id"
    with pytest.raises(ClientError) as exc:
        client.create_db_instance(
            DBClusterIdentifier=cluster_identifier,
            Engine="aurora-postgresql",
            DBInstanceIdentifier="test-instance",
            DBInstanceClass="db.t4g.medium",
        )
    err = exc.value.response["Error"]
    assert err["Code"] == "DBClusterNotFoundFault"
    assert cluster_identifier in err["Message"]
    assert "could not be found" in err["Message"]


@mock_aws
def test_rename_db_cluster_preserves_members():
    """Renaming a DB cluster should preserve its member instances."""
    client = boto3.client("rds", "us-east-1")

    # Create a cluster with two instances
    client.create_db_cluster(
        DBClusterIdentifier="old-cluster-id",
        Engine="aurora-postgresql",
        MasterUsername="root",
        MasterUserPassword="hunter2000",
    )
    client.create_db_instance(
        DBInstanceIdentifier="instance-1",
        DBClusterIdentifier="old-cluster-id",
        Engine="aurora-postgresql",
        DBInstanceClass="db.r5.large",
    )
    client.create_db_instance(
        DBInstanceIdentifier="instance-2",
        DBClusterIdentifier="old-cluster-id",
        Engine="aurora-postgresql",
        DBInstanceClass="db.r5.large",
    )

    # Verify members exist before rename
    before = client.describe_db_clusters(
        DBClusterIdentifier="old-cluster-id"
    )["DBClusters"][0]
    assert len(before["DBClusterMembers"]) == 2

    # Rename the cluster
    client.modify_db_cluster(
        DBClusterIdentifier="old-cluster-id",
        NewDBClusterIdentifier="new-cluster-id",
    )

    # After rename, the cluster should still have 2 members
    after = client.describe_db_clusters(
        DBClusterIdentifier="new-cluster-id"
    )["DBClusters"][0]
    assert after["DBClusterIdentifier"] == "new-cluster-id"
    assert len(after["DBClusterMembers"]) == 2, (
        f"Expected 2 members after rename, got {len(after['DBClusterMembers'])}"
    )
