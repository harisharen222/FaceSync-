"""
network_stack.py — VPC, subnets, NAT Gateway, and Security Groups for all NHAI services.

Architecture:
  - 2 Availability Zones (ap-south-1a, ap-south-1b) for HA
  - Public subnets:  ALBs only (internet-facing)
  - Private subnets: ECS Fargate tasks (no direct internet access)
  - Isolated subnets: RDS + ElastiCache (no internet, no NAT)
  - NAT Gateway in each public subnet for outbound-only private subnet access
"""
import aws_cdk as cdk
from aws_cdk import aws_ec2 as ec2
from constructs import Construct


class NHAINetworkStack(cdk.Stack):
    def __init__(self, scope: Construct, id: str, env_name: str, **kwargs):
        super().__init__(scope, id, **kwargs)

        # ── VPC ───────────────────────────────────────────────────────────────
        self.vpc = ec2.Vpc(
            self, "NHAIVpc",
            vpc_name=f"nhai-{env_name}-vpc",
            max_azs=2,
            ip_addresses=ec2.IpAddresses.cidr("10.0.0.0/16"),
            nat_gateways=1,      # single NAT for cost savings in non-prod
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(
                    name="Private",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(
                    name="Isolated",
                    subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
                    cidr_mask=24,
                ),
            ],
        )

        # ── Security Groups ───────────────────────────────────────────────────

        # ALB Security Group: accepts HTTPS from internet
        self.alb_security_group = ec2.SecurityGroup(
            self, "AlbSg",
            vpc=self.vpc,
            security_group_name=f"nhai-{env_name}-alb-sg",
            description="NHAI ALB — accepts HTTPS from internet",
            allow_all_outbound=True,
        )
        self.alb_security_group.add_ingress_rule(
            ec2.Peer.any_ipv4(), ec2.Port.tcp(443), "HTTPS from internet"
        )
        self.alb_security_group.add_ingress_rule(
            ec2.Peer.any_ipv4(), ec2.Port.tcp(80), "HTTP redirect from internet"
        )

        # ECS Security Group: accepts traffic from ALB only
        self.ecs_security_group = ec2.SecurityGroup(
            self, "EcsSg",
            vpc=self.vpc,
            security_group_name=f"nhai-{env_name}-ecs-sg",
            description="NHAI ECS Fargate tasks — accepts from ALB only",
            allow_all_outbound=True,
        )
        self.ecs_security_group.add_ingress_rule(
            self.alb_security_group, ec2.Port.tcp(8000),
            "Fargate app port from ALB"
        )

        # RDS Security Group: accepts PostgreSQL from ECS only
        self.rds_security_group = ec2.SecurityGroup(
            self, "RdsSg",
            vpc=self.vpc,
            security_group_name=f"nhai-{env_name}-rds-sg",
            description="NHAI RDS PostgreSQL — accepts from ECS tasks only",
            allow_all_outbound=False,
        )
        self.rds_security_group.add_ingress_rule(
            self.ecs_security_group, ec2.Port.tcp(5432),
            "PostgreSQL from ECS Fargate"
        )

        # Redis Security Group: accepts from ECS only
        self.redis_security_group = ec2.SecurityGroup(
            self, "RedisSg",
            vpc=self.vpc,
            security_group_name=f"nhai-{env_name}-redis-sg",
            description="NHAI Redis — accepts from ECS tasks only",
            allow_all_outbound=False,
        )
        self.redis_security_group.add_ingress_rule(
            self.ecs_security_group, ec2.Port.tcp(6379),
            "Redis from ECS Fargate"
        )

        # ── Outputs ───────────────────────────────────────────────────────────
        cdk.CfnOutput(self, "VpcId", value=self.vpc.vpc_id)
        cdk.CfnOutput(self, "PrivateSubnetIds",
            value=",".join([s.subnet_id for s in self.vpc.private_subnets]))
        cdk.CfnOutput(self, "IsolatedSubnetIds",
            value=",".join([s.subnet_id for s in self.vpc.isolated_subnets]))
