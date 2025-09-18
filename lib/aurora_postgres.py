import pulumi
import pulumi_aws as aws
import pulumi_random as random
from typing import Optional, Dict, Any


class AuroraPostgres(pulumi.ComponentResource):
    def __init__(self, name: str, args: Dict[str, Any], opts: Optional[pulumi.ResourceOptions] = None):
        super().__init__("huckstream:aws:postgres", name, {}, opts)

        # Set context details
        self.namespace = args["namespace"]
        self.environment = args["environment"]
        self.name = args["name"]

        self.base_name = f"{self.namespace}-{self.environment}-{self.name}-psql".lower()

        # Set tags
        base_tags = {
            "Namespace": self.namespace,
            "Environment": self.environment,
            "Name": self.base_name
        }

        # Configure vpc info
        vpc_id = args["vpc_id"]
        vpc_cidr = args["vpc_cidr"]
        subnet_ids = args["subnet_ids"]

        # Configure engine version
        self.engine_version = args["version"]
        self.major_engine_version = self.engine_version.split(".")[0]

        # Configure port
        self.port = args.get("port", 5432)

        # Create a KMS Key
        kms_key = aws.kms.Key(f"{self.base_name}-kms-key",
            description=f"KMS key for Aurora PostgreSQL encryption of database {self.base_name}",
            deletion_window_in_days=14,
            tags=base_tags,
            opts=pulumi.ResourceOptions(parent=self)
        )

        # Create a KMS Alias
        kms_alias = aws.kms.Alias(self.base_name,
            name=f"alias/{self.base_name}",
            target_key_id=kms_key.key_id,
            opts=pulumi.ResourceOptions(parent=self)
        )

        self.kms_key_id = kms_key.id
        self.kms_key_arn = kms_key.arn
        self.kms_alias_arn = kms_alias.arn

        # Create a DB subnet group
        subnet_group_name = f"{self.base_name}-subnet-group"
        subnet_group = aws.rds.SubnetGroup(subnet_group_name,
            name=subnet_group_name,
            description=f"Subnet group for Aurora Postgres cluster {self.base_name}",
            subnet_ids=subnet_ids,
            tags={
                **base_tags,
                "Name": subnet_group_name
            },
            opts=pulumi.ResourceOptions(parent=self)
        )

        # Create a security group
        sg_name = f"{self.base_name}-sg"
        sg = aws.ec2.SecurityGroup(sg_name,
            name=sg_name,
            description=f"Network permissions for Aurora Postgres cluster {self.base_name}",
            vpc_id=vpc_id,
            ingress=[
                aws.ec2.SecurityGroupIngressArgs(
                    description="Allow private local ingress",
                    protocol="tcp",
                    from_port=self.port,
                    to_port=self.port,
                    cidr_blocks=[vpc_cidr],  # Allow all Postgres traffic on local private subnets
                ),
            ],
            egress=[
                aws.ec2.SecurityGroupEgressArgs(
                    description="Allow private local egress",
                    protocol="-1",
                    from_port=0,
                    to_port=0,
                    cidr_blocks=[vpc_cidr],  # Allow all Postgres traffic on local private subnets
                ),
            ],
            tags={
                **base_tags,
                "Name": sg_name
            },
            opts=pulumi.ResourceOptions(parent=self)
        )

        # Create a cluster parameter group
        cluster_parameter_group_name = f"{self.base_name}-cpg"
        cluster_parameter_group = aws.rds.ClusterParameterGroup(cluster_parameter_group_name,
            name=cluster_parameter_group_name,
            family=f"aurora-postgresql{self.major_engine_version}",
            description=f"Cluster parameter group for {self.base_name}",
            parameters=[
                # Override Aurora Postgres Default cluster db parameters here
            ],
            tags={
                **base_tags,
                "Name": cluster_parameter_group_name
            },
            opts=pulumi.ResourceOptions(parent=self)
        )

        # Create a DB parameter group
        parameter_group_name = f"{self.base_name}-pg"
        parameter_group = aws.rds.ParameterGroup(parameter_group_name,
            name=parameter_group_name,
            family=f"aurora-postgresql{self.major_engine_version}",
            description=f"Cluster instance parameter group for {self.base_name}",
            parameters=[
                # Override Aurora Postgres default cluster instance db parameters here
            ],
            tags={
                **base_tags,
                "Name": parameter_group_name
            },
            opts=pulumi.ResourceOptions(parent=self)
        )

        # Generate admin creds
        db_password = random.RandomPassword(f"{self.base_name}-pwd",
            length=32,
            special=False,
            numeric=True,
            upper=True,
            lower=True,
            min_lower=1,
            min_upper=1,
            min_special=0,
            min_numeric=1,
            opts=pulumi.ResourceOptions(parent=self)
        )

        db_user = f"{self.namespace}admin".lower().replace("-", "")

        # Create an Aurora PostgreSQL cluster
        self.cluster = aws.rds.Cluster(f"{self.base_name}-cluster",
            # Cluster name
            cluster_identifier=self.base_name,

            # Engine config
            engine="aurora-postgresql",
            engine_version=self.engine_version,
            db_cluster_parameter_group_name=cluster_parameter_group.name,

            # Admin password
            master_username=db_user,
            master_password=db_password.result,

            # Encryption
            storage_encrypted=True,
            kms_key_id=kms_key.arn,

            # Configuration management
            apply_immediately=False,
            preferred_maintenance_window="Mon:00:00-Mon:03:00",
            allow_major_version_upgrade=False,

            # Backups
            backup_retention_period=14,
            preferred_backup_window="07:00-09:00",
            copy_tags_to_snapshot=True,
            final_snapshot_identifier=f"{self.base_name}-final",

            # Networking
            port=self.port,
            network_type="IPV4",
            db_subnet_group_name=subnet_group.name,
            vpc_security_group_ids=[sg.id],

            # Set tags
            tags=base_tags,
            opts=pulumi.ResourceOptions(parent=self)
        )

        self.cluster_name = pulumi.Output.from_input(self.base_name)
        self.cluster_arn = self.cluster.arn
        self.cluster_port = self.cluster.port
        self.cluster_endpoint = self.cluster.endpoint

        self.admin_user = pulumi.Output.secret(db_user)
        self.admin_password = pulumi.Output.secret(db_password.result)

        # Create Aurora PostgreSQL instances
        self.instances = []
        # Create two instances for HA
        for i in range(2):
            instance_name = f"{self.base_name}-instance-{i}"
            instance = aws.rds.ClusterInstance(instance_name,
                # Instance name
                identifier=instance_name,

                # Cluster membership
                cluster_identifier=self.cluster.id,

                # Engine config
                engine="aurora-postgresql",
                engine_version=self.engine_version,

                # Change management
                apply_immediately=False,
                auto_minor_version_upgrade=False,
                instance_class=args["db_instance_class"],

                # Backups
                copy_tags_to_snapshot=True,

                # Networking
                publicly_accessible=False,

                # Set tags
                tags=base_tags,
                opts=pulumi.ResourceOptions(parent=self)
            )
            self.instances.append(instance)

        # Register the outputs
        self.register_outputs({
            "kms_key_id": self.kms_key_id,
            "kms_key_arn": self.kms_key_arn,
            "kms_alias_arn": self.kms_alias_arn,
            "cluster_name": self.cluster_name,
            "cluster_port": self.cluster_port,
            "cluster_endpoint": self.cluster_endpoint,
            "admin_user": self.admin_user,
            "admin_password": self.admin_password,
        })