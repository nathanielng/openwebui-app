from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    aws_elasticloadbalancingv2 as elbv2,
    CfnOutput,
)
from constructs import Construct

CUSTOM_HEADER_NAME="..."
CUSTOM_HEADER_VALUE="..."

class OpenwebuiAppStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # The code that defines your stack goes here
        prefix = "openwebui"

        # Networking
        vpc = ec2.Vpc(
            self,
            f"{prefix}AppVpc",
            ip_addresses=ec2.IpAddresses.cidr("10.0.0.0/16"),
            max_azs=2,
            vpc_name=f"{prefix}-vpc",
            nat_gateways=1,
        )

        # Security Groups
        ecs_security_group = ec2.SecurityGroup(
            self,
            f"{prefix}SecurityGroupECS",
            vpc=vpc,
            security_group_name=f"{prefix}-ecs-sg",
        )
        alb_security_group = ec2.SecurityGroup(
            self,
            f"{prefix}SecurityGroupALB",
            vpc=vpc,
            security_group_name=f"{prefix}-alb-sg",
        )
        ecs_security_group.add_ingress_rule(
            peer=alb_security_group,
            connection=ec2.Port.tcp(3000),
            description="ALB traffic",
        )

        # ECS cluster and service definition
        cluster = ecs.Cluster(
            self,
            f"{prefix}Cluster",
            enable_fargate_capacity_providers=True,
            vpc=vpc)

        # ALB to connect to ECS
        alb = elbv2.ApplicationLoadBalancer(
            self,
            f"{prefix}Alb",
            vpc=vpc,
            internet_facing=True,
            load_balancer_name=f"{prefix}-alb",
            security_group=alb_security_group,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PUBLIC
            ),
        )

        # Fargate Task
        fargate_task_definition = ecs.FargateTaskDefinition(
            self,
            f"{prefix}TaskDef",
            memory_limit_mib=512,
            cpu=256,
        )

        # Build Dockerfile from local folder and push to ECR
        # image = ecs.ContainerImage.from_asset('local_folder')
        # Get image from registry
        image = ecs.ContainerImage.from_registry("ghcr.io/open-webui/open-webui:main")

        fargate_task_definition.add_container(
            f"{prefix}WebContainer",
            image=image,
            port_mappings=[
                ecs.PortMapping(
                    container_port=3000,
                    protocol=ecs.Protocol.TCP)],
            logging=ecs.LogDrivers.aws_logs(stream_prefix="WebContainerLogs"),
        )

        service = ecs.FargateService(
            self,
            f"{prefix}FargateService",
            cluster=cluster,
            task_definition=fargate_task_definition,
            service_name=f"{prefix}-stl-front",
            security_groups=[ecs_security_group],
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
        )

        # Task Role & Policy
        # openwebui_policy = iam.Policy(
        #     self, f"{prefix}OpenWebUIPolicy",
        #     statements=[
        #         iam.PolicyStatement(
        #             actions=[
        #                 "bedrock:GetAsyncInvoke",
        #                 "bedrock:InvokeModel",
        #                 "dynamodb:GetItem",
        #                 "dynamodb:PutItem",
        #                 "dynamodb:Scan",
        #                 "s3:GetObject",
        #                 "s3:PutObject",
        #                 "ssm:GetParameter"
        #             ],
        #             resources=["*"]
        #         )
        #     ]
        # )
        # task_role = fargate_task_definition.task_role
        # task_role.attach_inline_policy(openwebui_policy)

        # Add ALB as CloudFront Origin
        origin = origins.LoadBalancerV2Origin(
            alb,
            custom_headers={CUSTOM_HEADER_NAME: CUSTOM_HEADER_VALUE},
            origin_shield_enabled=False,
            protocol_policy=cloudfront.OriginProtocolPolicy.HTTP_ONLY,
        )

        cloudfront_distribution = cloudfront.Distribution(
            self,
            f"{prefix}CfDist",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origin,
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                allowed_methods=cloudfront.AllowedMethods.ALLOW_ALL,
                cache_policy=cloudfront.CachePolicy.CACHING_DISABLED,
                origin_request_policy=cloudfront.OriginRequestPolicy.ALL_VIEWER,
            ),
        )

        # ALB Listener
        http_listener = alb.add_listener(
            f"{prefix}HttpListener",
            port=80,
            open=True,
        )

        http_listener.add_targets(
            f"{prefix}TargetGroup",
            target_group_name=f"{prefix}-tg",
            port=3000,
            priority=1,
            conditions=[
                elbv2.ListenerCondition.http_header(
                    CUSTOM_HEADER_NAME,
                    [CUSTOM_HEADER_VALUE]
                )
            ],
            protocol=elbv2.ApplicationProtocol.HTTP,
            targets=[service],
        )
        # add a default action to the listener that will deny all requests that
        # do not have the custom header
        http_listener.add_action(
            "default-action",
            action=elbv2.ListenerAction.fixed_response(
                status_code=403,
                content_type="text/plain",
                message_body="Access denied",
            ),
        )

        # Output CloudFront URL
        CfnOutput(self, "CloudFrontDistributionURL",
                  value=cloudfront_distribution.domain_name)
