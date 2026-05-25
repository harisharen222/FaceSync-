"""
infrastructure/cdk/app.py — AWS CDK application entry point.

Deploy with:
    cd infrastructure/cdk
    pip install -r requirements.txt
    cdk bootstrap aws://ACCOUNT/ap-south-1
    cdk deploy --all --context env=staging
"""
import aws_cdk as cdk
from network_stack import NHAINetworkStack
from secrets_stack import NHAISecretsStack
from rds_stack import NHAIRdsStack
from elasticache_stack import NHAIElastiCacheStack
from ecs_stack import NHAIEcsStack
from apigw_stack import NHAIApiGatewayStack
from sqs_stack import NHAISqsStack
from eventbridge_stack import NHAIEventBridgeStack
from s3_stack import NHAIS3Stack

app = cdk.App()

# ── Target environment ────────────────────────────────────────────────────────
env_name = app.node.try_get_context("env") or "staging"
ENV_NAME = env_name
env = cdk.Environment(
    account=app.node.try_get_context("account"),
    region="ap-south-1",    # Mumbai — closest to NHAI HQ
)
aws_env = env

# ── Core Infrastructure ─────────────────────────────────────────────────
network = NHAINetworkStack(app, f"NHAINetwork-{env_name}", env_name=ENV_NAME, env=env)

secrets = NHAISecretsStack(app, f"NHAISecrets-{env_name}", env_name=ENV_NAME, env=env)

rds = NHAIRdsStack(
    app, f"NHAIRds-{env_name}",
    env_name=ENV_NAME,
    vpc=network.vpc,
    rds_sg=network.rds_security_group,
    env=env,
)

redis = NHAIElastiCacheStack(
    app, f"NHAIRedis-{env_name}",
    env_name=ENV_NAME,
    vpc=network.vpc,
    redis_sg=network.redis_security_group,
    env=env,
)

# ── Event-Driven & Storage Infrastructure ───────────────────────────────
sqs_stack = NHAISqsStack(app, f"NHAISqs-{env_name}", env_name=ENV_NAME, env=env)
eb_stack = NHAIEventBridgeStack(
    app, f"NHAIEventBridge-{env_name}",
    env_name=ENV_NAME,
    audit_queue=sqs_stack.audit_queue,
    notification_queue=sqs_stack.notification_queue,
    reporting_queue=sqs_stack.reporting_queue,
    env=env
)
s3_stack = NHAIS3Stack(app, f"NHAIS3-{env_name}", env_name=ENV_NAME, env=env)

# ── Microservices (ECS Fargate) ──────────────────────────────────────────
ecs_stack = NHAIEcsStack(
    app, f"NHAIEcs-{env_name}",
    env_name=ENV_NAME,
    vpc=network.vpc,
    ecs_sg=network.ecs_security_group,
    db_secret=rds.db_secret,
    db_endpoint=rds.db_endpoint,
    redis_endpoint=redis.redis_endpoint,
    rs256_secret=secrets.rs256_secret,
    internal_api_key_secret=secrets.internal_api_key_secret,
    aes_embedding_secret=secrets.aes_embedding_secret,
    attendance_queue=sqs_stack.attendance_queue,
    audit_queue=sqs_stack.audit_queue,
    notification_queue=sqs_stack.notification_queue,
    reporting_queue=sqs_stack.reporting_queue,
    event_bus=eb_stack.bus,
    model_bucket=s3_stack.model_bucket,
    cloudfront_domain=s3_stack.distribution.distribution_domain_name,
    env=env,
)

# ── API Gateway ──────────────────────────────────────────────────────────
apigw = NHAIApiGatewayStack(
    app, f"NHAIApiGateway-{env_name}",
    env_name=ENV_NAME,
    vpc=network.vpc,
    auth_alb_listener=ecs_stack.auth_alb_listener,
    enroll_alb_listener=ecs_stack.enroll_alb_listener,
    att_alb_listener=ecs_stack.att_alb_listener,
    model_alb_listener=ecs_stack.model_alb_listener,
    audit_alb_listener=ecs_stack.audit_alb_listener,
    reporting_alb_listener=ecs_stack.reporting_alb_listener,
    env=env,
)

# Tag all resources for cost attribution
for stack in [network, secrets, rds, redis, ecs_stack, apigw, sqs_stack, eb_stack, s3_stack]:
    cdk.Tags.of(stack).add("Project", "NHAI-Biometric-Attendance")
    cdk.Tags.of(stack).add("Environment", env_name)
    cdk.Tags.of(stack).add("ManagedBy", "CDK")

app.synth()
