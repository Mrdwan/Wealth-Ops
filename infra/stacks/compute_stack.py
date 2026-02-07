"""Compute Stack: Lambda functions and scheduling.

This stack defines the compute resources:
- Data Ingestion Lambda (Daily at 23:00 UTC)
- Market Pulse Lambda (Daily at 09:00 UTC)
"""

from aws_cdk import Duration, Stack, Tags
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as targets
from aws_cdk import aws_lambda as _lambda
from constructs import Construct

from stacks.foundation_stack import FoundationStack


class ComputeStack(Stack):
    """Compute infrastructure stack for Wealth-Ops."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        foundation_stack: FoundationStack,
        tags: dict[str, str] | None = None,
        **kwargs: object,
    ) -> None:
        """Initialize the Compute Stack.

        Args:
            scope: The CDK app scope.
            construct_id: Unique identifier for this stack.
            foundation_stack: Reference to the foundation stack for dependencies.
            tags: Optional tags to apply to all resources.
            **kwargs: Additional stack options.
        """
        super().__init__(scope, construct_id, **kwargs)

        self._foundation = foundation_stack

        # Apply tags
        if tags:
            for key, value in tags.items():
                Tags.of(self).add(key, value)

        # Create Lambdas
        self._create_data_ingestion_lambda()
        self._create_market_pulse_lambda()

    def _create_data_ingestion_lambda(self) -> None:
        """Create the Data Ingestion Lambda function."""
        fn = _lambda.DockerImageFunction(
            self,
            "DataIngestionFunction",
            code=_lambda.DockerImageCode.from_image_asset(
                directory="..",  # Root of the repo (where Dockerfile.lambda is)
                file="Dockerfile.lambda",
                cmd=["src.lambdas.data_ingestion.handler"],
            ),
            timeout=Duration.minutes(15),  # Long timeout for ingestion
            memory_size=1024,
            role=self._foundation.lambda_role,
            environment={
                "S3_BUCKET": self._foundation.data_bucket.bucket_name,
                "CONFIG_TABLE": self._foundation.config_table.table_name,
                "SYSTEM_TABLE": self._foundation.system_table.table_name,
                # Secrets should ideally be injected via Secrets Manager, 
                # but for this phase we expect them in environment or .env locally
                # We'll map them from the build environment (if using GitHub Actions / .env)
                # For CDK, we usually pass them from context or secrets.
                # Assuming they are present in the Lambda execution env via other means 
                # or we just rely on `dotenv` which we don't use in prod lambda usually.
                # EDIT: We need to pass them. For now, let's assume they are set in the
                # console or passed via some config mechanism. 
                # For the sake of this file, we won't hardcode keys.
            },
            description="Ingests market data daily using provider failover",
        )

        # Schedule: 23:00 UTC daily
        rule = events.Rule(
            self,
            "DataIngestionSchedule",
            schedule=events.Schedule.cron(minute="0", hour="23"),
            description="Trigger data ingestion daily at 23:00 UTC",
        )
        rule.add_target(targets.LambdaFunction(fn))

    def _create_market_pulse_lambda(self) -> None:
        """Create the Market Pulse Lambda function."""
        fn = _lambda.DockerImageFunction(
            self,
            "MarketPulseFunction",
            code=_lambda.DockerImageCode.from_image_asset(
                directory="..",
                file="Dockerfile.lambda",
                cmd=["src.lambdas.market_pulse.handler"],
            ),
            timeout=Duration.minutes(5),
            memory_size=512,
            role=self._foundation.lambda_role,
            environment={
                "SYSTEM_TABLE": self._foundation.system_table.table_name,
                "PORTFOLIO_TABLE": self._foundation.portfolio_table.table_name,
            },
            description="Checks market regime and sends daily pulse",
        )

        # Schedule: 09:00 UTC daily
        rule = events.Rule(
            self,
            "MarketPulseSchedule",
            schedule=events.Schedule.cron(minute="0", hour="9"),
            description="Trigger market pulse daily at 09:00 UTC",
        )
        rule.add_target(targets.LambdaFunction(fn))
