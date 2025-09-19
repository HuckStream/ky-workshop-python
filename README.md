# ky-workshop-python

Workshop example deploying an VPC, S3 Bucket, RDS Aurora PostgreSQL, and EC2 instances to AWS using Python

## Step 0 - Setup

### Pulumi Cloud

Accept invite to Pulumi Cloud organization and login to dashboard

### AWS SSO

Log into AWS SSO via the start URL and verify access to account

### Stack Configuration

- Find your username and CIDR, i.e. `bcenter` and `10.x.0.0/16`

- Set required configuration:

  ```bash
  pulumi config set aws:region us-east-1
  pulumi config set namespace your-namespace
  pulumi config set name your-username
  pulumi config set openVpnStack your-openvpn-stack-reference
  pulumi config set vpcCidr "10.x.0.0/16"
  ```

- Create stack

  ```bash
  pulumi stack init your-username
  ```

- Select stack
  ```bash
  pulumi stack select your-username
  ```

## Step 1 - Using Stack References & Outputs

- Uncomment code related to Step 1 in `__main__.py`

- Run update

  ```bash
  pulumi up
  ```

- Verify update successful in Pulumi Cloud

## Step 2 - Deploy VPC

- Uncomment code related to Step 2 in `__main__.py`

- Run update

  ```bash
  pulumi up
  ```

- Compare resource graph in Pulumi Cloud to AWS Console

## Step 3 - Deploy Ping Instances

- Uncomment code related to Step 3 in `__main__.py`

- Run update

  ```bash
  pulumi up
  ```

- Connect to main vpc private ping instance using SSM connect
- Verify network connectivity between instances

## Step 4 - Deploy Encrypted S3 Bucket

- Uncomment code related to Step 4 in `__main__.py`

- Run update
  ```bash
  pulumi up
  ```
- Connect to main vpc private ping instance using SSM connect

- Create a test file

  ```bash
  echo "your-username" > test.txt

  aws s3 cp \
    test.txt \
    s3://huckstream-wksp-your-username/test.txt \
    --sse aws:kms \
    --sse-kms-key-id alias/huckstream-wksp-your-username
  ```

- Get version ID from AWS console e.g. `86BPXBR7RHyN7ZlgSGF3sesAZlPSEwxO`

- Delete test file
  ```bash
  aws s3api delete-object \
    --bucket huckstream-wksp-your-username \
    --key test.txt \
    --version-id 86BPXBR7RHyN7ZlgSGF3sesAZlPSEwxO
  ```

## Step 5 - Restrict S3 Bucket to VPC

- Uncomment code related to Step 5 in `__main__.py` (vpce_id parameter)

- Run update

  ```bash
  pulumi up
  ```

- Connect to main vpc private ping instance using SSM connect

- Create a test file

  ```bash
  echo "your-username" > test.txt

  aws s3 cp \
    test.txt \
    s3://huckstream-wksp-your-username/test.txt \
    --sse aws:kms \
    --sse-kms-key-id alias/huckstream-wksp-your-username
  ```

- Get version ID from AWS console e.g. `86BPXBR7RHyN7ZlgSGF3sesAZlPSEwxO`

- Delete test file
  ```bash
  aws s3api delete-object \
    --bucket huckstream-wksp-your-username \
    --key test.txt \
    --version-id 86BPXBR7RHyN7ZlgSGF3sesAZlPSEwxO
  ```

## Step 6 - Deploy Aurora PostgreSQL Cluster

- Uncomment code related to Step 6 in `__main__.py`

- Run update
  ```bash
  pulumi up
  ```

## Step 7 - Verify Cluster Access Restriction

- Connect to isolated vpc private instance using SSM connect

- Install Postgres 16 client

  ```bash
  sudo dnf install postgresql16
  ```

- Attempt successful connection to database

  ```bash
  psql -U huckstremadmin -p 5432 -h huckstream-wksp-your-username-psql.cluster-xxxxx.us-east-1.rds.amazonaws.com
  ```

- Connect to main vpc private instance using SSM connect

- Install Postgres 16 client

  ```bash
  sudo dnf install postgresql16
  ```

- Attempt failed connection to database
  ```bash
  psql -U huckstremadmin -p 5432 -h huckstream-wksp-your-username-psql.cluster-xxxxx.us-east-1.rds.amazonaws.com
  ```
