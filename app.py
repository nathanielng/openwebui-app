#!/usr/bin/env python3

import os
import aws_cdk as cdk

from openwebui_app.openwebui_app_stack import OpenwebuiAppStack


app = cdk.App()
OpenwebuiAppStack(app, "OpenwebuiAppStack",
    env=cdk.Environment(
        account=os.getenv('CDK_DEFAULT_ACCOUNT'),
        region=os.getenv('CDK_DEFAULT_REGION')
    ),
)
app.synth()
