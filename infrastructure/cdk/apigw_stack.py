"""
apigw_stack.py — AWS API Gateway HTTP API with VPC Link to internal ALB.

API Gateway sits at the internet edge and routes /auth/* → Auth Service ALB.
Future phases add routes for enrollment, attendance, models, etc.
"""
import aws_cdk as cdk
from aws_cdk import (
    aws_ec2 as ec2,
    aws_apigatewayv2 as apigwv2,
    aws_apigatewayv2_integrations as integrations,
    aws_elasticloadbalancingv2 as elbv2,
)
from constructs import Construct


class NHAIApiGatewayStack(cdk.Stack):
    def __init__(
        self, scope: Construct, id: str, env_name: str,
        vpc: ec2.Vpc,
        auth_alb_listener: elbv2.ApplicationListener,
        enroll_alb_listener: elbv2.ApplicationListener,
        att_alb_listener: elbv2.ApplicationListener,
        model_alb_listener: elbv2.ApplicationListener,
        audit_alb_listener: elbv2.ApplicationListener,
        reporting_alb_listener: elbv2.ApplicationListener,
        **kwargs,
    ):
        super().__init__(scope, id, **kwargs)

        # ── VPC Link ──────────────────────────────────────────────────────────
        # VPC Link allows API Gateway to route to private ALBs inside the VPC
        vpc_link = apigwv2.VpcLink(
            self, "NHAIVpcLink",
            vpc=vpc,
            vpc_link_name=f"nhai-{env_name}-vpc-link",
            subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
        )

        # ── Auth Service Integration ──────────────────────────────────────────
        auth_integration = integrations.HttpAlbIntegration(
            "AuthAlbIntegration",
            listener=auth_alb_listener,
            vpc_link=vpc_link,
            method=apigwv2.HttpMethod.ANY,
        )
        
        # ── Enrollment Service Integration ────────────────────────────────────
        enroll_integration = integrations.HttpAlbIntegration(
            "EnrollAlbIntegration",
            listener=enroll_alb_listener,
            vpc_link=vpc_link,
            method=apigwv2.HttpMethod.ANY,
        )
        
        # ── Attendance Sync Service Integration ───────────────────────────────
        att_integration = integrations.HttpAlbIntegration(
            "AttendanceAlbIntegration",
            listener=att_alb_listener,
            vpc_link=vpc_link,
            method=apigwv2.HttpMethod.ANY,
        )

        # ── Model Delivery Service Integration ────────────────────────────────
        model_integration = integrations.HttpAlbIntegration(
            "ModelAlbIntegration",
            listener=model_alb_listener,
            vpc_link=vpc_link,
            method=apigwv2.HttpMethod.ANY,
        )

        # ── Audit Service Integration ─────────────────────────────────────────
        audit_integration = integrations.HttpAlbIntegration(
            "AuditAlbIntegration",
            listener=audit_alb_listener,
            vpc_link=vpc_link,
            method=apigwv2.HttpMethod.ANY,
        )

        # ── Reporting Service Integration ─────────────────────────────────────
        reporting_integration = integrations.HttpAlbIntegration(
            "ReportingAlbIntegration",
            listener=reporting_alb_listener,
            vpc_link=vpc_link,
            method=apigwv2.HttpMethod.ANY,
        )

        # ── HTTP API ──────────────────────────────────────────────────────────
        self.api = apigwv2.HttpApi(
            self, "NHAIHttpApi",
            api_name=f"nhai-{env_name}-api",
            description="NHAI Biometric Attendance Platform — API Gateway",
            cors_preflight=apigwv2.CorsPreflightOptions(
                allow_origins=["*"] if env_name != "production" else [],
                allow_methods=[apigwv2.CorsHttpMethod.ANY],
                allow_headers=["Authorization", "Content-Type", "X-Internal-Api-Key"],
                max_age=cdk.Duration.hours(1),
            ),
            default_domain_mapping=None,  # Add custom domain in production
        )

        # ── Routes: /auth/* → Auth Service ───────────────────────────────────
        self.api.add_routes(
            path="/auth/{proxy+}",
            methods=[apigwv2.HttpMethod.ANY],
            integration=auth_integration,
        )

        # ── Routes: /enroll/* → Enrollment Service ───────────────────────────
        self.api.add_routes(
            path="/enroll/{proxy+}",
            methods=[apigwv2.HttpMethod.ANY],
            integration=enroll_integration,
        )

        # ── Routes: /attendance/* → Attendance Sync Service ──────────────────
        self.api.add_routes(
            path="/attendance/{proxy+}",
            methods=[apigwv2.HttpMethod.ANY],
            integration=att_integration,
        )

        # ── Routes: /models/* → Model Delivery Service ───────────────────────
        self.api.add_routes(
            path="/models/{proxy+}",
            methods=[apigwv2.HttpMethod.ANY],
            integration=model_integration,
        )

        # ── Routes: /audit/* → Audit Service ─────────────────────────────────
        self.api.add_routes(
            path="/audit/{proxy+}",
            methods=[apigwv2.HttpMethod.ANY],
            integration=audit_integration,
        )

        # ── Routes: /reports/* → Reporting Service ───────────────────────────
        self.api.add_routes(
            path="/reports/{proxy+}",
            methods=[apigwv2.HttpMethod.ANY],
            integration=reporting_integration,
        )

        # ── Health check passthrough ───────────────────────────────────────────
        # Note: In a real system, you'd likely map /health/auth, /health/enroll, etc.
        self.api.add_routes(
            path="/health",
            methods=[apigwv2.HttpMethod.GET],
            integration=auth_integration,
        )

        # ── JWKS endpoint passthrough (for other services to fetch public key) ─
        self.api.add_routes(
            path="/auth/token/jwks",
            methods=[apigwv2.HttpMethod.GET],
            integration=auth_integration,
        )

        # ── Outputs ───────────────────────────────────────────────────────────
        cdk.CfnOutput(
            self, "ApiGatewayUrl",
            value=self.api.api_endpoint,
            description="NHAI API Gateway base URL",
        )
        cdk.CfnOutput(self, "AuthEndpoint",
            value=f"{self.api.api_endpoint}/auth",
            description="Auth Service base URL via API Gateway",
        )
