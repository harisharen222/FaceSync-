"""
ecs_stack.py — ECS Fargate cluster + Auth Service task definition + internal ALB.
"""
import aws_cdk as cdk
from aws_cdk import (
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_ecr as ecr,
    aws_iam as iam,
    aws_logs as logs,
    aws_secretsmanager as sm,
    aws_elasticloadbalancingv2 as elbv2,
    aws_sqs as sqs,
    aws_events as events,
    aws_s3 as s3,
)
from constructs import Construct


class NHAIEcsStack(cdk.Stack):
    def __init__(
        self, scope: Construct, id: str, env_name: str,
        vpc: ec2.Vpc,
        ecs_sg: ec2.SecurityGroup,
        db_secret: sm.Secret,
        db_endpoint: str,
        redis_endpoint: str,
        rs256_secret: sm.Secret,
        internal_api_key_secret: sm.Secret,
        aes_embedding_secret: sm.Secret,
        attendance_queue: sqs.Queue,
        audit_queue: sqs.Queue,
        notification_queue: sqs.Queue,
        reporting_queue: sqs.Queue,
        event_bus: events.EventBus,
        model_bucket: s3.Bucket,
        cloudfront_domain: str,
        **kwargs,
    ):
        super().__init__(scope, id, **kwargs)

        # ── ECS Cluster ───────────────────────────────────────────────────────
        self.cluster = ecs.Cluster(
            self, "NHAICluster",
            cluster_name=f"nhai-{env_name}",
            vpc=vpc,
            container_insights=True,    # CloudWatch Container Insights
        )

        # ── ECR Repository ────────────────────────────────────────────────────
        auth_repo = ecr.Repository(
            self, "AuthServiceRepo",
            repository_name=f"nhai-{env_name}/auth-service",
            image_scan_on_push=True,    # Automated vulnerability scanning
            removal_policy=cdk.RemovalPolicy.RETAIN,
        )

        # ── CloudWatch Log Group ──────────────────────────────────────────────
        log_group = logs.LogGroup(
            self, "AuthServiceLogs",
            log_group_name=f"/nhai/{env_name}/auth-service",
            retention=logs.RetentionDays.ONE_MONTH,
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )

        # ── IAM Task Role ─────────────────────────────────────────────────────
        task_role = iam.Role(
            self, "AuthServiceTaskRole",
            role_name=f"nhai-{env_name}-auth-task-role",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            description="NHAI Auth Service — least-privilege ECS task role",
        )
        # Allow reading ONLY the secrets this service needs
        rs256_secret.grant_read(task_role)
        internal_api_key_secret.grant_read(task_role)
        db_secret.grant_read(task_role)

        # ── Task Definition ───────────────────────────────────────────────────
        task_def = ecs.FargateTaskDefinition(
            self, "AuthServiceTask",
            family=f"nhai-{env_name}-auth-service",
            cpu=256,           # 0.25 vCPU
            memory_limit_mib=512,
            task_role=task_role,
        )

        # ── Container Definition ──────────────────────────────────────────────
        container = task_def.add_container(
            "AuthServiceContainer",
            container_name="auth-service",
            image=ecs.ContainerImage.from_ecr_repository(auth_repo, tag="latest"),
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix="auth-service",
                log_group=log_group,
            ),
            environment={
                "ENV": env_name,
                "DEBUG": "false",
                "AWS_REGION": "ap-south-1",
                "USE_AWS_SECRETS": "true",
                "AWS_SECRET_NAME_RS256": rs256_secret.secret_name,
                "DB_ENDPOINT": db_endpoint,
                "REDIS_URL": f"rediss://{redis_endpoint}:6379/0",  # rediss:// = TLS
            },
            secrets={
                # Injected from Secrets Manager at task startup
                "DB_PASSWORD": ecs.Secret.from_secrets_manager(db_secret, "password"),
                "INTERNAL_API_KEY": ecs.Secret.from_secrets_manager(
                    internal_api_key_secret, "api_key"
                ),
            },
            health_check=ecs.HealthCheck(
                command=["CMD-SHELL",
                    "python -c \"import urllib.request; urllib.request.urlopen('http://localhost:8000/health')\""],
                interval=cdk.Duration.seconds(30),
                timeout=cdk.Duration.seconds(5),
                retries=3,
                start_period=cdk.Duration.seconds(15),
            ),
            port_mappings=[ecs.PortMapping(container_port=8000)],
        )

        # ── Internal ALB + Fargate Service ────────────────────────────────────
        # INTERNAL ALB — not internet-facing. API Gateway connects to it via VPC Link.
        alb = elbv2.ApplicationLoadBalancer(
            self, "AuthServiceAlb",
            vpc=vpc,
            internet_facing=False,      # INTERNAL only
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            load_balancer_name=f"nhai-{env_name}-auth-alb",
        )

        self.auth_alb_listener = alb.add_listener(
            "AuthListener",
            port=80,
            open=False,
        )

        service = ecs.FargateService(
            self, "AuthService",
            service_name=f"nhai-{env_name}-auth-service",
            cluster=self.cluster,
            task_definition=task_def,
            desired_count=2 if env_name == "production" else 1,
            security_groups=[ecs_sg],
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            assign_public_ip=False,
            enable_execute_command=env_name != "production",  # ECS Exec for debugging
        )

        self.auth_alb_listener.add_targets(
            "AuthTarget",
            port=8000,
            protocol=elbv2.ApplicationProtocol.HTTP,
            targets=[service],
            health_check=elbv2.HealthCheck(
                path="/health",
                healthy_http_codes="200",
                interval=cdk.Duration.seconds(30),
            ),
            deregistration_delay=cdk.Duration.seconds(30),
        )

        # ── Auto Scaling ──────────────────────────────────────────────────────
        scaling = service.auto_scale_task_count(min_capacity=1, max_capacity=5)
        scaling.scale_on_cpu_utilization(
            "AuthCpuScaling",
            target_utilization_percent=70,
            scale_in_cooldown=cdk.Duration.seconds(120),
            scale_out_cooldown=cdk.Duration.seconds(60),
        )

        # ==============================================================================
        # ── ENROLLMENT SERVICE ────────────────────────────────────────────────────────
        # ==============================================================================
        enrollment_repo = ecr.Repository(self, "EnrollmentRepo", repository_name=f"nhai-{env_name}/enrollment-service", removal_policy=cdk.RemovalPolicy.RETAIN)
        enroll_log_group = logs.LogGroup(self, "EnrollmentLogs", log_group_name=f"/nhai/{env_name}/enrollment-service", removal_policy=cdk.RemovalPolicy.DESTROY)
        
        enroll_task_role = iam.Role(
            self, "EnrollTaskRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
        )
        rs256_secret.grant_read(enroll_task_role)
        internal_api_key_secret.grant_read(enroll_task_role)
        aes_embedding_secret.grant_read(enroll_task_role)
        db_secret.grant_read(enroll_task_role)

        enroll_task_def = ecs.FargateTaskDefinition(self, "EnrollTask", family=f"nhai-{env_name}-enrollment", cpu=1024, memory_limit_mib=2048, task_role=enroll_task_role)
        
        enroll_task_def.add_container(
            "EnrollContainer",
            container_name="enrollment-service",
            image=ecs.ContainerImage.from_ecr_repository(enrollment_repo, tag="latest"),
            logging=ecs.LogDrivers.aws_logs(stream_prefix="enroll", log_group=enroll_log_group),
            environment={
                "ENV": env_name, "AWS_REGION": "ap-south-1", "USE_AWS_SECRETS": "true",
                "AUTH_JWKS_URL": f"http://{alb.load_balancer_dns_name}/auth/token/jwks",
                "AUTH_SERVICE_URL": f"http://{alb.load_balancer_dns_name}",
                "AWS_SECRET_NAME_AES": aes_embedding_secret.secret_name,
                "DB_ENDPOINT": db_endpoint,
            },
            secrets={
                "DB_PASSWORD": ecs.Secret.from_secrets_manager(db_secret, "password"),
                "INTERNAL_API_KEY": ecs.Secret.from_secrets_manager(internal_api_key_secret, "api_key"),
            },
            port_mappings=[ecs.PortMapping(container_port=8000)],
        )

        enroll_service = ecs.FargateService(
            self, "EnrollService",
            service_name=f"nhai-{env_name}-enrollment-service",
            cluster=self.cluster, task_definition=enroll_task_def,
            desired_count=1, security_groups=[ecs_sg],
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
        )

        self.enroll_alb_listener = alb.add_listener("EnrollListener", port=8002, open=False)
        self.enroll_alb_listener.add_targets("EnrollTarget", port=8000, targets=[enroll_service])

        # ==============================================================================
        # ── ATTENDANCE SYNC SERVICE ───────────────────────────────────────────────────
        # ==============================================================================
        attendance_repo = ecr.Repository(self, "AttendanceRepo", repository_name=f"nhai-{env_name}/attendance-service", removal_policy=cdk.RemovalPolicy.RETAIN)
        att_log_group = logs.LogGroup(self, "AttendanceLogs", log_group_name=f"/nhai/{env_name}/attendance-service", removal_policy=cdk.RemovalPolicy.DESTROY)
        
        att_task_role = iam.Role(
            self, "AttendanceTaskRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
        )
        rs256_secret.grant_read(att_task_role)
        internal_api_key_secret.grant_read(att_task_role)
        db_secret.grant_read(att_task_role)
        attendance_queue.grant_send_messages(att_task_role)
        event_bus.grant_put_events_to(att_task_role)

        att_task_def = ecs.FargateTaskDefinition(self, "AttendanceTask", family=f"nhai-{env_name}-attendance", cpu=512, memory_limit_mib=1024, task_role=att_task_role)
        
        att_task_def.add_container(
            "AttendanceContainer",
            container_name="attendance-service",
            image=ecs.ContainerImage.from_ecr_repository(attendance_repo, tag="latest"),
            logging=ecs.LogDrivers.aws_logs(stream_prefix="attendance", log_group=att_log_group),
            environment={
                "ENV": env_name, "AWS_REGION": "ap-south-1",
                "AUTH_JWKS_URL": f"http://{alb.load_balancer_dns_name}/auth/token/jwks",
                "AUTH_SERVICE_URL": f"http://{alb.load_balancer_dns_name}",
                "SQS_QUEUE_URL": attendance_queue.queue_url,
                "EVENT_BUS_NAME": event_bus.event_bus_name,
                "DB_ENDPOINT": db_endpoint,
            },
            secrets={
                "DB_PASSWORD": ecs.Secret.from_secrets_manager(db_secret, "password"),
                "INTERNAL_API_KEY": ecs.Secret.from_secrets_manager(internal_api_key_secret, "api_key"),
            },
            port_mappings=[ecs.PortMapping(container_port=8000)],
        )

        att_service = ecs.FargateService(
            self, "AttendanceService",
            service_name=f"nhai-{env_name}-attendance-service",
            cluster=self.cluster, task_definition=att_task_def,
            desired_count=2 if env_name == "production" else 1, security_groups=[ecs_sg],
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
        )

        self.att_alb_listener = alb.add_listener("AttendanceListener", port=8003, open=False)
        self.att_alb_listener.add_targets("AttendanceTarget", port=8000, targets=[att_service])

        # ==============================================================================
        # ── MODEL DELIVERY SERVICE ────────────────────────────────────────────────────
        # ==============================================================================
        model_repo = ecr.Repository(self, "ModelRepo", repository_name=f"nhai-{env_name}/model-service", removal_policy=cdk.RemovalPolicy.RETAIN)
        model_log_group = logs.LogGroup(self, "ModelLogs", log_group_name=f"/nhai/{env_name}/model-service", removal_policy=cdk.RemovalPolicy.DESTROY)
        
        model_task_role = iam.Role(
            self, "ModelTaskRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
        )
        rs256_secret.grant_read(model_task_role)
        db_secret.grant_read(model_task_role)
        model_bucket.grant_read_write(model_task_role)

        model_task_def = ecs.FargateTaskDefinition(self, "ModelTask", family=f"nhai-{env_name}-model", cpu=512, memory_limit_mib=1024, task_role=model_task_role)
        
        model_task_def.add_container(
            "ModelContainer",
            container_name="model-service",
            image=ecs.ContainerImage.from_ecr_repository(model_repo, tag="latest"),
            logging=ecs.LogDrivers.aws_logs(stream_prefix="model", log_group=model_log_group),
            environment={
                "ENV": env_name, "AWS_REGION": "ap-south-1",
                "AUTH_JWKS_URL": f"http://{alb.load_balancer_dns_name}/auth/token/jwks",
                "DB_ENDPOINT": db_endpoint,
                "MODEL_BUCKET_NAME": model_bucket.bucket_name,
                "CLOUDFRONT_DOMAIN": cloudfront_domain,
            },
            secrets={
                "DB_PASSWORD": ecs.Secret.from_secrets_manager(db_secret, "password"),
            },
            port_mappings=[ecs.PortMapping(container_port=8000)],
        )

        model_service = ecs.FargateService(
            self, "ModelService",
            service_name=f"nhai-{env_name}-model-service",
            cluster=self.cluster, task_definition=model_task_def,
            desired_count=1, security_groups=[ecs_sg],
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
        )

        self.model_alb_listener = alb.add_listener("ModelListener", port=8004, open=False)
        self.model_alb_listener.add_targets("ModelTarget", port=8000, targets=[model_service])

        # ==============================================================================
        # ── AUDIT & SECURITY SERVICE ──────────────────────────────────────────────────
        # ==============================================================================
        audit_repo = ecr.Repository(self, "AuditRepo", repository_name=f"nhai-{env_name}/audit-service", removal_policy=cdk.RemovalPolicy.RETAIN)
        audit_log_group = logs.LogGroup(self, "AuditLogs", log_group_name=f"/nhai/{env_name}/audit-service", removal_policy=cdk.RemovalPolicy.DESTROY)
        
        audit_task_role = iam.Role(
            self, "AuditTaskRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
        )
        rs256_secret.grant_read(audit_task_role)
        db_secret.grant_read(audit_task_role)
        audit_queue.grant_consume_messages(audit_task_role)

        audit_task_def = ecs.FargateTaskDefinition(self, "AuditTask", family=f"nhai-{env_name}-audit", cpu=256, memory_limit_mib=512, task_role=audit_task_role)
        
        audit_task_def.add_container(
            "AuditContainer",
            container_name="audit-service",
            image=ecs.ContainerImage.from_ecr_repository(audit_repo, tag="latest"),
            logging=ecs.LogDrivers.aws_logs(stream_prefix="audit", log_group=audit_log_group),
            environment={
                "ENV": env_name, "AWS_REGION": "ap-south-1",
                "AUTH_JWKS_URL": f"http://{alb.load_balancer_dns_name}/auth/token/jwks",
                "SQS_QUEUE_URL": audit_queue.queue_url,
                "DB_ENDPOINT": db_endpoint,
            },
            secrets={
                "DB_PASSWORD": ecs.Secret.from_secrets_manager(db_secret, "password"),
            },
            port_mappings=[ecs.PortMapping(container_port=8000)],
        )

        audit_service = ecs.FargateService(
            self, "AuditService",
            service_name=f"nhai-{env_name}-audit-service",
            cluster=self.cluster, task_definition=audit_task_def,
            desired_count=1, security_groups=[ecs_sg],
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
        )

        self.audit_alb_listener = alb.add_listener("AuditListener", port=8005, open=False)
        self.audit_alb_listener.add_targets("AuditTarget", port=8000, targets=[audit_service])

        # ==============================================================================
        # ── NOTIFICATION SERVICE (Background Worker Only) ─────────────────────────────
        # ==============================================================================
        notif_repo = ecr.Repository(self, "NotifRepo", repository_name=f"nhai-{env_name}/notification-service", removal_policy=cdk.RemovalPolicy.RETAIN)
        notif_log_group = logs.LogGroup(self, "NotifLogs", log_group_name=f"/nhai/{env_name}/notification-service", removal_policy=cdk.RemovalPolicy.DESTROY)
        
        notif_task_role = iam.Role(
            self, "NotifTaskRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
        )
        notification_queue.grant_consume_messages(notif_task_role)

        notif_task_def = ecs.FargateTaskDefinition(self, "NotifTask", family=f"nhai-{env_name}-notification", cpu=256, memory_limit_mib=512, task_role=notif_task_role)
        
        notif_task_def.add_container(
            "NotifContainer",
            container_name="notification-service",
            image=ecs.ContainerImage.from_ecr_repository(notif_repo, tag="latest"),
            logging=ecs.LogDrivers.aws_logs(stream_prefix="notif", log_group=notif_log_group),
            environment={
                "ENV": env_name, "AWS_REGION": "ap-south-1",
                "SQS_QUEUE_URL": notification_queue.queue_url,
            },
        )

        notif_service = ecs.FargateService(
            self, "NotifService",
            service_name=f"nhai-{env_name}-notification-service",
            cluster=self.cluster, task_definition=notif_task_def,
            desired_count=1, security_groups=[ecs_sg],
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
        )

        # ==============================================================================
        # ── REPORTING SERVICE ─────────────────────────────────────────────────────────
        # ==============================================================================
        reporting_repo = ecr.Repository(self, "ReportingRepo", repository_name=f"nhai-{env_name}/reporting-service", removal_policy=cdk.RemovalPolicy.RETAIN)
        reporting_log_group = logs.LogGroup(self, "ReportingLogs", log_group_name=f"/nhai/{env_name}/reporting-service", removal_policy=cdk.RemovalPolicy.DESTROY)
        
        reporting_task_role = iam.Role(
            self, "ReportingTaskRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
        )
        rs256_secret.grant_read(reporting_task_role)
        db_secret.grant_read(reporting_task_role)
        reporting_queue.grant_consume_messages(reporting_task_role)

        reporting_task_def = ecs.FargateTaskDefinition(self, "ReportingTask", family=f"nhai-{env_name}-reporting", cpu=256, memory_limit_mib=512, task_role=reporting_task_role)
        
        reporting_task_def.add_container(
            "ReportingContainer",
            container_name="reporting-service",
            image=ecs.ContainerImage.from_ecr_repository(reporting_repo, tag="latest"),
            logging=ecs.LogDrivers.aws_logs(stream_prefix="reporting", log_group=reporting_log_group),
            environment={
                "ENV": env_name, "AWS_REGION": "ap-south-1",
                "AUTH_JWKS_URL": f"http://{alb.load_balancer_dns_name}/auth/token/jwks",
                "SQS_QUEUE_URL": reporting_queue.queue_url,
                "DB_ENDPOINT": db_endpoint,
            },
            secrets={
                "DB_PASSWORD": ecs.Secret.from_secrets_manager(db_secret, "password"),
            },
            port_mappings=[ecs.PortMapping(container_port=8000)],
        )

        reporting_service = ecs.FargateService(
            self, "ReportingService",
            service_name=f"nhai-{env_name}-reporting-service",
            cluster=self.cluster, task_definition=reporting_task_def,
            desired_count=1, security_groups=[ecs_sg],
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
        )

        self.reporting_alb_listener = alb.add_listener("ReportingListener", port=8006, open=False)
        self.reporting_alb_listener.add_targets("ReportingTarget", port=8000, targets=[reporting_service])

        # ── Outputs ───────────────────────────────────────────────────────────
        cdk.CfnOutput(self, "AuthServiceAlbDns", value=alb.load_balancer_dns_name)
        cdk.CfnOutput(self, "EcsClusterArn", value=self.cluster.cluster_arn)
        cdk.CfnOutput(self, "AuthEcrRepoUri", value=auth_repo.repository_uri)
