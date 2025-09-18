import pulumi
import pulumi_aws as aws
import pulumi_awsx as awsx
from typing import Optional, List, Dict, Any


class VpcArgs:
    def __init__(self,
                 namespace: str,
                 environment: str,
                 name: str,
                 region: str,
                 cidr: str,
                 open_vpn_vpc_id: Optional[pulumi.Input[str]] = None,
                 open_vpn_vpc_cidr: Optional[pulumi.Input[str]] = None,
                 open_vpn_vpc_rtbls: Optional[pulumi.Output[List[aws.ec2.RouteTable]]] = None,
                 public_subnets: Optional[bool] = None,
                 private_app_subnets: Optional[bool] = None,
                 private_data_subnets: Optional[bool] = None,
                 isolated_data_subnets: Optional[bool] = None,
                 interface_endpoints: Optional[List[str]] = None):
        self.namespace = namespace
        self.environment = environment
        self.name = name
        self.region = region
        self.cidr = cidr
        self.open_vpn_vpc_id = open_vpn_vpc_id
        self.open_vpn_vpc_cidr = open_vpn_vpc_cidr
        self.open_vpn_vpc_rtbls = open_vpn_vpc_rtbls
        self.public_subnets = public_subnets
        self.private_app_subnets = private_app_subnets
        self.private_data_subnets = private_data_subnets
        self.isolated_data_subnets = isolated_data_subnets
        self.interface_endpoints = interface_endpoints or []


class Vpc(pulumi.ComponentResource):
    def __init__(self, name: str, args: Dict[str, Any], opts: Optional[pulumi.ResourceOptions] = None):
        super().__init__("huckstream:aws:vpc", name, {}, opts)

        # Set context details
        self.namespace = args["namespace"]
        self.environment = args["environment"]
        self.name = args["name"]

        self.base_name = f"{self.namespace}-{self.environment}-{self.name}"

        # Set tags
        base_tags = {
            "Namespace": self.namespace,
            "Environment": self.environment,
            "Name": self.base_name
        }

        # Create the subnet specs
        subnet_specs = []

        if args.get("public_subnets"):
            public_subnets = awsx.ec2.SubnetSpecArgs(
                type=awsx.ec2.SubnetType.PUBLIC,
                name="public"
            )
            subnet_specs.append(public_subnets)

        if args.get("private_app_subnets"):
            private_app_subnets = awsx.ec2.SubnetSpecArgs(
                type=awsx.ec2.SubnetType.PRIVATE,
                name="private-app",
                tags={
                    **base_tags,
                    "PrivateSubnetType": "App"
                }
            )
            subnet_specs.append(private_app_subnets)

        if args.get("private_data_subnets"):
            private_data_subnets = awsx.ec2.SubnetSpecArgs(
                type=awsx.ec2.SubnetType.PRIVATE,
                name="private-data",
                tags={
                    **base_tags,
                    "PrivateSubnetType": "Data"
                }
            )
            subnet_specs.append(private_data_subnets)

        if args.get("isolated_data_subnets"):
            isolated_data_subnets = awsx.ec2.SubnetSpecArgs(
                type=awsx.ec2.SubnetType.ISOLATED,
                name="isolated-data"
            )
            subnet_specs.append(isolated_data_subnets)

        # Set NAT Gateway strategy
        nat_gw_strategy = (awsx.ec2.NatGatewayStrategy.SINGLE
                          if args.get("public_subnets") and (args.get("private_app_subnets") or args.get("private_data_subnets"))
                          else awsx.ec2.NatGatewayStrategy.NONE)

        # Create the VPC
        vpc = awsx.ec2.Vpc(self.base_name,
            # IP Config
            cidr_block=args["cidr"],
            number_of_availability_zones=3,
            subnet_specs=subnet_specs,
            subnet_strategy=awsx.ec2.SubnetAllocationStrategy.AUTO,

            # NAT Gateway config
            nat_gateways=awsx.ec2.NatGatewayConfigurationArgs(
                strategy=nat_gw_strategy
            ),

            # DNS Config
            enable_dns_hostnames=True,
            enable_dns_support=True,

            # Tags
            tags=base_tags,
            opts=pulumi.ResourceOptions(parent=self)
        )

        self.vpc_id = vpc.vpc_id
        self.public_subnet_ids = vpc.public_subnet_ids
        self.private_subnet_ids = vpc.private_subnet_ids
        self.isolated_subnet_ids = vpc.isolated_subnet_ids
        self.route_tables = vpc.route_tables
        self.private_route_tables = vpc.route_tables.apply(
            lambda rtbls: pulumi.Output.all([
                rtbl.tags.apply(lambda tags: {"rtbl": rtbl, "tags": tags})
                for rtbl in rtbls
            ]).apply(
                lambda results: [
                    result["rtbl"] for result in results
                    if isinstance(result, dict) and isinstance(result.get("tags"), dict) and result["tags"].get("SubnetType") == "Private"
                ]
            )
        )

        # Gateway Endpoints
        # DynamoDB
        dynamodb_endpoint = aws.ec2.VpcEndpoint("dynamodb",
            vpc_id=vpc.vpc_id,
            service_name=f"com.amazonaws.{args['region']}.dynamodb",
            vpc_endpoint_type="Gateway",
            route_table_ids=vpc.route_tables.apply(lambda rtbls: [rtbl.id for rtbl in rtbls]),
            tags={
                **base_tags,
                "Name": f"{self.base_name}-dynamodb"
            },
            opts=pulumi.ResourceOptions(parent=self)
        )

        self.dynamodb_endpoint_id = dynamodb_endpoint.id

        # S3
        s3_endpoint = aws.ec2.VpcEndpoint("s3",
            vpc_id=vpc.vpc_id,
            service_name=f"com.amazonaws.{args['region']}.s3",
            vpc_endpoint_type="Gateway",
            route_table_ids=vpc.route_tables.apply(lambda rtbls: [rtbl.id for rtbl in rtbls]),
            tags={
                **base_tags,
                "Name": f"{self.base_name}-s3"
            },
            opts=pulumi.ResourceOptions(parent=self)
        )

        self.s3_endpoint_id = s3_endpoint.id

        # Interface Endpoints
        # Security group
        vpce_sg_name = f"{self.base_name}-vpce-sg"
        vpce_sg = aws.ec2.SecurityGroup("vpce-security-group",
            name=vpce_sg_name,
            vpc_id=self.vpc_id,
            description="Allow local traffic",
            ingress=[
                aws.ec2.SecurityGroupIngressArgs(
                    protocol="-1",
                    from_port=0,
                    to_port=0,
                    cidr_blocks=["0.0.0.0/0"],
                ),
            ],
            egress=[
                aws.ec2.SecurityGroupEgressArgs(
                    protocol="-1",
                    from_port=0,
                    to_port=0,
                    cidr_blocks=["0.0.0.0/0"],
                ),
            ],
            tags={
                **base_tags,
                "Name": vpce_sg_name
            },
            opts=pulumi.ResourceOptions(parent=self)
        )

        interface_endpoints = []
        for service in args.get("interface_endpoints", []):
            vpce = aws.ec2.VpcEndpoint(service,
                vpc_id=vpc.vpc_id,
                service_name=f"com.amazonaws.{args['region']}.{service}",
                vpc_endpoint_type="Interface",
                security_group_ids=[vpce_sg.id],
                subnet_ids=vpc.isolated_subnet_ids,
                private_dns_enabled=True,
                tags={
                    **base_tags,
                    "Name": f"{self.base_name}-{service}"
                },
                opts=pulumi.ResourceOptions(parent=self)
            )
            interface_endpoints.append(vpce)

        # Configure the VPC default route table
        default_route_table = aws.ec2.DefaultRouteTable("defaultRouteTable",
            default_route_table_id=vpc.vpc.default_route_table_id,
            routes=[],
            tags=base_tags,
            opts=pulumi.ResourceOptions(parent=self)
        )

        # Configure the VPC default security group
        default_security_group = aws.ec2.DefaultSecurityGroup("defaultSecurityGroup",
            vpc_id=self.vpc_id,
            ingress=[],
            egress=[],
            tags={
                **base_tags,
                "Name": f"{self.base_name}-default"
            },
            opts=pulumi.ResourceOptions(parent=self)
        )
        
        if args.get("open_vpn_vpc_id") is not None:
            # Create the peering
            open_vpn_vpc = aws.ec2.VpcPeeringConnection("openVpnVpc",
                peer_vpc_id=args["open_vpn_vpc_id"],
                vpc_id=vpc.vpc_id,
                auto_accept=True,
                tags={
                    **base_tags,
                    "Name": f"{self.base_name}-main"
                },
                opts=pulumi.ResourceOptions(parent=self)
            )

            # Configure local subnet routes
            def create_local_routes(route_tables):
                for i, route_table in enumerate(route_tables):
                    route_table.id.apply(
                        lambda route_table_id, i=i: aws.ec2.Route(
                            f"{args['name']}-{i}-main",
                            route_table_id=route_table_id,
                            destination_cidr_block=args["open_vpn_vpc_cidr"],
                            vpc_peering_connection_id=open_vpn_vpc.id,
                            opts=pulumi.ResourceOptions(parent=open_vpn_vpc)
                        )
                    )

            self.private_route_tables.apply(create_local_routes)

            # Configure main vpc subnet routes
            if args.get("open_vpn_vpc_rtbls"):
                def create_main_routes(route_tables):
                    for i, route_table in enumerate(route_tables):
                        if hasattr(route_table, 'id'):
                            route_table_id = route_table.id
                        elif isinstance(route_table, dict) and 'id' in route_table:
                            route_table_id = route_table['id']
                        else:
                            route_table_id = route_table

                        aws.ec2.Route(f"main-{i}-{args['name']}",
                            route_table_id=route_table_id,
                            destination_cidr_block=args["cidr"],
                            vpc_peering_connection_id=open_vpn_vpc.id,
                            opts=pulumi.ResourceOptions(parent=open_vpn_vpc)
                        )

                args["open_vpn_vpc_rtbls"].apply(create_main_routes)

        # Register outputs
        self.register_outputs({
            "vpc_id": self.vpc_id,
            "public_subnet_ids": self.public_subnet_ids,
            "private_subnet_ids": self.private_subnet_ids,
            "isolated_subnet_ids": self.isolated_subnet_ids,
            "route_tables": self.route_tables,
            "private_route_tables": self.private_route_tables,
            "dynamodb_endpoint_id": self.dynamodb_endpoint_id,
            "s3_endpoint_id": self.s3_endpoint_id,
        })