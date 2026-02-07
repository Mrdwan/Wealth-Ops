#!/usr/bin/env python3
"""AWS CDK App entrypoint for Wealth-Ops infrastructure."""

import aws_cdk as cdk

from stacks.foundation_stack import FoundationStack

app = cdk.App()

foundation = FoundationStack(
    app,
    "WealthOpsFoundationDev",
    env=cdk.Environment(
        account=app.node.try_get_context("account"),
        region=app.node.try_get_context("region") or "us-east-1",
    ),
    tags={"Project": "Wealth-Ops", "Environment": "dev"},
)

from stacks.compute_stack import ComputeStack

ComputeStack(
    app,
    "WealthOpsComputeDev",
    foundation_stack=foundation,
    env=cdk.Environment(
        account=app.node.try_get_context("account"),
        region=app.node.try_get_context("region") or "us-east-1",
    ),
    tags={"Project": "Wealth-Ops", "Environment": "dev"},
)

app.synth()
