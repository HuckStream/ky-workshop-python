import pulumi
import pulumi_aws as aws
import json
from typing import Optional, Dict, Any


class EncryptedBucket(pulumi.ComponentResource):
    def __init__(self, name: str, args: Dict[str, Any], opts: Optional[pulumi.ResourceOptions] = None):
        super().__init__("huckstream:aws:encrypted-bucket", name, {}, opts)

        # Set context details
        self.namespace = args["namespace"]
        self.environment = args["environment"]
        self.name = args["name"]

        self.base_name = f"{self.namespace}-{self.environment}-{self.name}".lower()

        # Set tags
        base_tags = {
            "Namespace": self.namespace,
            "Environment": self.environment,
            "Name": self.base_name
        }

        # Create a KMS Key
        kms_key = aws.kms.Key(self.base_name,
            description=f"KMS key for encrypting S3 bucket {self.base_name}",
            deletion_window_in_days=14,
            tags=base_tags,
            opts=pulumi.ResourceOptions(parent=self)
        )

        kms_alias = aws.kms.Alias(self.base_name,
            name=f"alias/{self.base_name}",
            target_key_id=kms_key.key_id,
            opts=pulumi.ResourceOptions(parent=self)
        )

        self.kms_key_id = kms_key.id
        self.kms_key_arn = kms_key.arn
        self.kms_alias_arn = kms_alias.arn

        # Create an S3 Bucket encrypted with the KMS Key
        bucket = aws.s3.Bucket(self.base_name,
            bucket=self.base_name,
            versioning=aws.s3.BucketVersioningArgs(
                enabled=True
            ),
            server_side_encryption_configuration=aws.s3.BucketServerSideEncryptionConfigurationArgs(
                rule=aws.s3.BucketServerSideEncryptionConfigurationRuleArgs(
                    apply_server_side_encryption_by_default=aws.s3.BucketServerSideEncryptionConfigurationRuleApplyServerSideEncryptionByDefaultArgs(
                        sse_algorithm="aws:kms",
                        kms_master_key_id=kms_key.arn,
                    ),
                ),
            ),
            tags=base_tags,
            opts=pulumi.ResourceOptions(parent=self)
        )

        # If the VPC endpoint has been passed, set the bucket policy to restrict S3 actions to only
        if args.get("vpce_id"):
            def create_bucket_policy(bucket_arn_and_vpc_endpoint):
                bucket_arn, vpc_endpoint_id = bucket_arn_and_vpc_endpoint
                return json.dumps({
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Sid": "Restrict-Access-to-Specific-VPCE",
                            "Effect": "Deny",
                            "Principal": "*",
                            "Action": [
                                "s3:PutObject",
                                "s3:GetObject",
                                "s3:DeleteObject",
                                "s3:DeleteObjectVersion"
                            ],
                            "Resource": [
                                bucket_arn,
                                f"{bucket_arn}/*"
                            ],
                            "Condition": {
                                "StringNotEquals": {
                                    "aws:sourceVpce": vpc_endpoint_id,
                                },
                            },
                        },
                    ],
                })

            bucket_policy = aws.s3.BucketPolicy(self.base_name,
                bucket=bucket.bucket,
                policy=pulumi.Output.all(bucket.arn, args["vpce_id"]).apply(create_bucket_policy),
                opts=pulumi.ResourceOptions(parent=self)
            )

        self.bucket_name = pulumi.Output.from_input(self.base_name)
        self.bucket_arn = bucket.arn

        # Register outputs
        self.register_outputs({
            "kms_key_id": self.kms_key_id,
            "kms_key_arn": self.kms_key_arn,
            "kms_alias_arn": self.kms_alias_arn,
            "bucket_name": self.bucket_name,
            "bucket_arn": self.bucket_arn,
        })