"""
rds_stack.py — PostgreSQL RDS instance for NHAI (multi-AZ for production).

Single RDS cluster with one database. Each microservice uses its own schema
(database-per-service pattern within a single cluster to save cost).
"""
import aws_cdk as cdk
from aws_cdk import aws_ec2 as ec2, aws_rds as rds
from constructs import Construct


class NHAIRdsStack(cdk.Stack):
    def __init__(
        self, scope: Construct, id: str, env_name: str,
        vpc: ec2.Vpc, rds_sg: ec2.SecurityGroup, **kwargs
    ):
        super().__init__(scope, id, **kwargs)

        is_prod = env_name == "production"

        # ── DB Credentials ────────────────────────────────────────────────────
        self.db_secret = rds.DatabaseSecret(
            self, "NHAIDbSecret",
            secret_name=f"nhai/{env_name}/rds-credentials",
            username="nhai",
        )

        # ── Subnet Group ──────────────────────────────────────────────────────
        subnet_group = rds.SubnetGroup(
            self, "NHAIDbSubnetGroup",
            description="NHAI RDS isolated subnet group",
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED),
        )

        # ── RDS PostgreSQL Instance ───────────────────────────────────────────
        self.db_instance = rds.DatabaseInstance(
            self, "NHAIPostgres",
            engine=rds.DatabaseInstanceEngine.postgres(
                version=rds.PostgresEngineVersion.VER_16
            ),
            instance_identifier=f"nhai-{env_name}-postgres",
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.T3,
                ec2.InstanceSize.MEDIUM if is_prod else ec2.InstanceSize.MICRO,
            ),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED),
            subnet_group=subnet_group,
            security_groups=[rds_sg],
            credentials=rds.Credentials.from_secret(self.db_secret),
            database_name="nhai_auth",
            multi_az=is_prod,                    # HA in production
            storage_encrypted=True,              # AES-256 at rest
            deletion_protection=is_prod,
            backup_retention=cdk.Duration.days(7 if is_prod else 1),
            enable_performance_insights=is_prod,
            cloudwatch_logs_exports=["postgresql"],
            auto_minor_version_upgrade=True,
            publicly_accessible=False,           # NEVER public
            allocated_storage=20,
            max_allocated_storage=100,           # auto-scaling storage up to 100 GB
        )

        self.db_endpoint = self.db_instance.db_instance_endpoint_address

        # ── Outputs ───────────────────────────────────────────────────────────
        cdk.CfnOutput(self, "DbEndpoint", value=self.db_endpoint)
        cdk.CfnOutput(self, "DbSecretArn", value=self.db_secret.secret_arn)
