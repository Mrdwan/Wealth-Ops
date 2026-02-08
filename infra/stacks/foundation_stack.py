"""Foundation Stack: Core AWS infrastructure for Wealth-Ops.

This stack creates the foundational resources that all other phases build upon:
- S3 bucket for data storage (raw, processed, models, artifacts)
- ECR repository for Docker images
- IAM roles for Lambda and Fargate execution
- DynamoDB tables for state management
"""
from typing import Any

from aws_cdk import Duration, RemovalPolicy, Stack, Tags
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_ecr as ecr
from aws_cdk import aws_iam as iam
from aws_cdk import aws_s3 as s3
from constructs import Construct


class FoundationStack(Stack):
    """Foundation infrastructure stack for Wealth-Ops."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        tags: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the Foundation Stack.

        Args:
            scope: The CDK app scope.
            construct_id: Unique identifier for this stack.
            tags: Optional tags to apply to all resources.
            **kwargs: Additional stack options.
        """
        super().__init__(scope, construct_id, **kwargs)

        # Apply tags to all resources in this stack
        if tags:
            for key, value in tags.items():
                Tags.of(self).add(key, value)

        # Create core resources
        self._data_bucket = self._create_data_bucket()
        self._ecr_repo = self._create_ecr_repository()
        self._lambda_role = self._create_lambda_execution_role()
        self._fargate_role = self._create_fargate_task_role()

        # Create DynamoDB tables
        self._config_table = self._create_config_table()
        self._ledger_table = self._create_ledger_table()
        self._portfolio_table = self._create_portfolio_table()
        self._system_table = self._create_system_table()

        # Grant table access to roles
        self._grant_table_permissions()

    def _create_data_bucket(self) -> s3.Bucket:
        """Create the S3 bucket for market data and artifacts.

        Bucket structure:
            - raw/: Raw market data from providers
            - processed/: Cleaned, gap-filled data
            - models/: Trained XGBoost models
            - artifacts/: Backtest results, logs

        Returns:
            The created S3 bucket.
        """
        return s3.Bucket(
            self,
            "DataBucket",
            bucket_name="wealth-ops-data-dev",
            versioned=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.RETAIN,
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="ExpireOldVersions",
                    noncurrent_version_expiration=Duration.days(30),
                    enabled=True,
                ),
            ],
        )

    def _create_ecr_repository(self) -> ecr.Repository:
        """Create the ECR repository for Lambda/Fargate Docker images.

        Returns:
            The created ECR repository.
        """
        return ecr.Repository(
            self,
            "EcrRepository",
            repository_name="wealth-ops-ecr-dev",
            removal_policy=RemovalPolicy.RETAIN,
            lifecycle_rules=[
                ecr.LifecycleRule(
                    max_image_count=10,
                    description="Keep only 10 most recent images",
                ),
            ],
        )

    def _create_lambda_execution_role(self) -> iam.Role:
        """Create the shared IAM role for Lambda functions.

        Permissions:
            - S3: GetObject, PutObject on data bucket
            - DynamoDB: Full access (for future phases)
            - CloudWatch Logs: Write access

        Returns:
            The created IAM role.
        """
        role = iam.Role(
            self,
            "LambdaExecutionRole",
            role_name="wealth-ops-lambda-role-dev",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            description="Execution role for Wealth-Ops Lambda functions",
        )

        # S3 permissions
        self._data_bucket.grant_read_write(role)

        # DynamoDB permissions (for future phases)
        role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "dynamodb:GetItem",
                    "dynamodb:PutItem",
                    "dynamodb:UpdateItem",
                    "dynamodb:DeleteItem",
                    "dynamodb:Query",
                    "dynamodb:Scan",
                ],
                resources=[f"arn:aws:dynamodb:{self.region}:{self.account}:table/wealth-ops-*"],
            )
        )

        # CloudWatch Logs permissions
        role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name(
                "service-role/AWSLambdaBasicExecutionRole"
            )
        )

        return role

    def _create_fargate_task_role(self) -> iam.Role:
        """Create the IAM role for Fargate training tasks.

        Permissions:
            - All Lambda role permissions
            - ECR: Pull images
            - CloudWatch Logs: Create and write

        Returns:
            The created IAM role.
        """
        role = iam.Role(
            self,
            "FargateTaskRole",
            role_name="wealth-ops-fargate-role-dev",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            description="Task role for Wealth-Ops Fargate tasks",
        )

        # S3 permissions
        self._data_bucket.grant_read_write(role)

        # ECR permissions
        self._ecr_repo.grant_pull(role)

        # DynamoDB permissions (same as Lambda)
        role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "dynamodb:GetItem",
                    "dynamodb:PutItem",
                    "dynamodb:UpdateItem",
                    "dynamodb:DeleteItem",
                    "dynamodb:Query",
                    "dynamodb:Scan",
                ],
                resources=[f"arn:aws:dynamodb:{self.region}:{self.account}:table/wealth-ops-*"],
            )
        )

        # CloudWatch Logs permissions
        role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                ],
                resources=["*"],
            )
        )

        return role

    def _create_config_table(self) -> dynamodb.Table:
        """Create the Config table for asset configuration.

        Schema:
            - ticker (PK): Stock symbol (e.g., 'AAPL')
            - last_updated_date: Last data fetch date
            - sector: Asset sector for correlation limits
            - enabled: Whether to trade this asset

        Returns:
            The created DynamoDB table.
        """
        return dynamodb.Table(
            self,
            "ConfigTable",
            table_name="wealth-ops-config-dev",
            partition_key=dynamodb.Attribute(
                name="ticker",
                type=dynamodb.AttributeType.STRING,
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.RETAIN,
            point_in_time_recovery=True,
        )

    def _create_ledger_table(self) -> dynamodb.Table:
        """Create the Ledger table for trade history.

        Schema:
            - ticker (PK): Stock symbol
            - date (SK): Trade date (YYYY-MM-DD)
            - action: BUY/SELL
            - quantity: Number of shares
            - price: Execution price

        Returns:
            The created DynamoDB table.
        """
        return dynamodb.Table(
            self,
            "LedgerTable",
            table_name="wealth-ops-ledger-dev",
            partition_key=dynamodb.Attribute(
                name="ticker",
                type=dynamodb.AttributeType.STRING,
            ),
            sort_key=dynamodb.Attribute(
                name="date",
                type=dynamodb.AttributeType.STRING,
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.RETAIN,
            point_in_time_recovery=True,
        )

    def _create_portfolio_table(self) -> dynamodb.Table:
        """Create the Portfolio table for current positions.

        Schema:
            - asset_type (PK): 'CASH' or 'STOCK'
            - ticker (SK): Symbol or 'EUR' for cash
            - quantity: Shares or cash amount
            - avg_cost: Average purchase price

        Returns:
            The created DynamoDB table.
        """
        return dynamodb.Table(
            self,
            "PortfolioTable",
            table_name="wealth-ops-portfolio-dev",
            partition_key=dynamodb.Attribute(
                name="asset_type",
                type=dynamodb.AttributeType.STRING,
            ),
            sort_key=dynamodb.Attribute(
                name="ticker",
                type=dynamodb.AttributeType.STRING,
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.RETAIN,
            point_in_time_recovery=True,
        )

    def _create_system_table(self) -> dynamodb.Table:
        """Create the System table for global state.

        Schema:
            - key (PK): State key (e.g., 'market_status', 'last_run')
            - value: State value
            - updated_at: Timestamp of last update

        Returns:
            The created DynamoDB table.
        """
        return dynamodb.Table(
            self,
            "SystemTable",
            table_name="wealth-ops-system-dev",
            partition_key=dynamodb.Attribute(
                name="key",
                type=dynamodb.AttributeType.STRING,
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.RETAIN,
            point_in_time_recovery=True,
        )

    def _grant_table_permissions(self) -> None:
        """Grant read/write access to all tables for Lambda and Fargate roles."""
        tables = [
            self._config_table,
            self._ledger_table,
            self._portfolio_table,
            self._system_table,
        ]
        for table in tables:
            table.grant_read_write_data(self._lambda_role)
            table.grant_read_write_data(self._fargate_role)

    @property
    def data_bucket(self) -> s3.Bucket:
        """Get the data S3 bucket."""
        return self._data_bucket

    @property
    def ecr_repo(self) -> ecr.Repository:
        """Get the ECR repository."""
        return self._ecr_repo

    @property
    def lambda_role(self) -> iam.Role:
        """Get the Lambda execution role."""
        return self._lambda_role

    @property
    def fargate_role(self) -> iam.Role:
        """Get the Fargate task role."""
        return self._fargate_role

    @property
    def config_table(self) -> dynamodb.Table:
        """Get the Config DynamoDB table."""
        return self._config_table

    @property
    def ledger_table(self) -> dynamodb.Table:
        """Get the Ledger DynamoDB table."""
        return self._ledger_table

    @property
    def portfolio_table(self) -> dynamodb.Table:
        """Get the Portfolio DynamoDB table."""
        return self._portfolio_table

    @property
    def system_table(self) -> dynamodb.Table:
        """Get the System DynamoDB table."""
        return self._system_table
