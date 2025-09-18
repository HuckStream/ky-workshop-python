import pulumi
import pulumi_aws as aws

from lib.vpc import Vpc
from lib.ping_instance import PingInstance
from lib.encrypted_bucket import EncryptedBucket
from lib.aurora_postgres import AuroraPostgres


def main():
    # Assemble resource name from context pieces
    config = pulumi.Config()
    namespace = config.require("namespace")
    environment = config.require("environment")
    name = config.require("name")
    base_name = f"{namespace}-{environment}-{name}"

    ######
    # Step 1
    #
    # Retrieve stack references and outputs for main VPC infrastructure deployment stack.
    ######

    # Get the VPC CIDR from config
    vpc_cidr = config.require("vpcCidr")

    # Get the current AWS region
    region = aws.get_region().name

    # Reference bootstrapping stack
    open_vpn_stack = pulumi.StackReference(config.require("openVpnStack"))

    # Get the peering info
    open_vpn_vpc_id = open_vpn_stack.get_output("vpcId")
    open_vpn_vpc_cidr = open_vpn_stack.get_output("vpcCidr")
    # Need to cast from Output[any] to Output[RouteTable[]]
    open_vpn_vpc_rtbls = open_vpn_stack.get_output("privateRouteTables").apply(
        lambda rtbls: rtbls
    )

    ######
    # Step 2
    #
    # Deploy isolated VPC to the current region, with endpoints for required services and peering to main VPC
    #
    # Also uncomment outputs labeled 'VPC Outputs' at the bottom
    ######

    # Create VPC
    vpc = Vpc("vpc", {
        # Context info
        "namespace": namespace,
        "environment": environment,
        "name": name,

        # Networking configurations
        "cidr": vpc_cidr,
        "private_app_subnets": True,
        "isolated_data_subnets": True,

        # OpenVPN VPC for peering configuration
        "open_vpn_vpc_id": open_vpn_vpc_id,
        "open_vpn_vpc_cidr": open_vpn_vpc_cidr,
        "open_vpn_vpc_rtbls": open_vpn_vpc_rtbls,

        # VPC interface endpoint configuration
        # AWS region (convenience for interface endpoint definitions)
        "region": region,

        # See https://docs.aws.amazon.com/vpc/latest/privatelink/aws-services-privatelink-support.html for supported services
        "interface_endpoints": [
            "kms",
            "lambda",
            "logs",
            "rds",
            "sts",
            "ec2messages",
            "ssm",
            "ssmmessages",
        ]
    })

    private_app_subnet_id = vpc.private_subnet_ids.apply(lambda ids: ids[0])
    isolated_data_subnet_id = vpc.isolated_subnet_ids.apply(lambda ids: ids[1])

    ######
    # Step 3
    #
    # Deploy ping instances to test network connectivity
    ######
    # Get the ping instance config
    ping_ami_id = open_vpn_stack.get_output("pingAmiId")
    ping_iam_role = open_vpn_stack.get_output("pingIamRole")

    # Create main ping instances
    private_app_ping = PingInstance("ping-private-app", {
        # Context
        "namespace": namespace,
        "environment": environment,
        "name": f"{name}-ping-private-app",

        # Networking
        "vpc_id": vpc.vpc_id,
        "subnet_id": private_app_subnet_id,

        # Instance config
        "ami_id": ping_ami_id,

        # IAM permissions
        "instance_profile": ping_iam_role,
    })

    private_data_ping = PingInstance("ping-isolated-data", {
        # Context
        "namespace": namespace,
        "environment": environment,
        "name": f"{name}-ping-isolated-data",

        # Networking
        "vpc_id": vpc.vpc_id,
        "subnet_id": isolated_data_subnet_id,

        # Instance config
        "ami_id": ping_ami_id,

        # IAM permissions
        "instance_profile": ping_iam_role,
    })

    ######
    # Step 4
    #
    # Deploy encrypted S3 bucket
    #
    # Also uncomment outputs labeled 'S3 Bucket Outputs' at the bottom
    ######
    # S3 Bucket
    s3_bucket = EncryptedBucket("encrypted-bucket", {
        "namespace": namespace,
        "environment": environment,
        "name": name,

        ######
        # Step 5
        #
        # Provide the S3 VPC gateway endpoint to lock the S3 bucket down to only the VPC
        #
        # Also uncomment outputs labeled 'S3 Bucket Outputs' at the bottom
        ######

        "vpce_id": vpc.s3_endpoint_id,
    })

    ######
    # Step 6
    #
    # Deploy Aurora Postgres DB Cluster
    #
    # Also uncomment outputs labeled 'RDS Outputs' at the bottom
    ######
    # RDS Cluster
    db = AuroraPostgres("postgres", {
        "namespace": namespace,
        "environment": environment,
        "name": name,

        "db_instance_class": "db.t4g.medium",
        "version": "16.4",

        "vpc_id": vpc.vpc_id,
        "vpc_cidr": vpc_cidr,
        "subnet_ids": vpc.isolated_subnet_ids
    })

    ######
    # Step 2
    #
    # VPC Outputs
    ######
    pulumi.export("vpc_id", vpc.vpc_id)
    pulumi.export("vpc_cidr", vpc_cidr)
    pulumi.export("public_subnet_ids", vpc.public_subnet_ids)
    pulumi.export("private_subnet_ids", vpc.private_subnet_ids)
    pulumi.export("isolated_subnet_ids", vpc.isolated_subnet_ids)

    ######
    # Step 4
    #
    # S3 Bucket Outputs
    ######
    pulumi.export("bucket_name", s3_bucket.bucket_name)
    pulumi.export("bucket_arn", s3_bucket.bucket_arn)

    ######
    # Step 6
    #
    # RDS Outputs
    ######
    pulumi.export("db_cluster_name", db.cluster_name)
    pulumi.export("db_cluster_port", db.cluster_port)
    pulumi.export("db_cluster_endpoint", db.cluster_endpoint)
    pulumi.export("db_admin_user", db.admin_user)
    pulumi.export("db_admin_password", db.admin_password)


if __name__ == "__main__":
    main()