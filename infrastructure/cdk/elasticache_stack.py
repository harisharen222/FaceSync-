"""
elasticache_stack.py — Redis ElastiCache cluster for token blacklisting and challenge cache.
"""
import aws_cdk as cdk
from aws_cdk import aws_ec2 as ec2, aws_elasticache as elasticache
from constructs import Construct


class NHAIElastiCacheStack(cdk.Stack):
    def __init__(
        self, scope: Construct, id: str, env_name: str,
        vpc: ec2.Vpc, redis_sg: ec2.SecurityGroup, **kwargs
    ):
        super().__init__(scope, id, **kwargs)

        # ── Subnet Group ──────────────────────────────────────────────────────
        isolated_subnets = [s.subnet_id for s in vpc.isolated_subnets]

        subnet_group = elasticache.CfnSubnetGroup(
            self, "NHAIRedisSubnetGroup",
            cache_subnet_group_name=f"nhai-{env_name}-redis-subnets",
            description="NHAI Redis isolated subnet group",
            subnet_ids=isolated_subnets,
        )

        # ── Redis Cluster ──────────────────────────────────────────────────────
        is_prod = env_name == "production"

        self.redis_cluster = elasticache.CfnReplicationGroup(
            self, "NHAIRedis",
            replication_group_id=f"nhai-{env_name}-redis",
            replication_group_description="NHAI Auth Service token blacklist + challenge cache",
            engine="redis",
            engine_version="7.1",
            cache_node_type="cache.t3.micro" if not is_prod else "cache.t3.small",
            num_cache_clusters=2 if is_prod else 1,  # 2 nodes for HA in prod
            automatic_failover_enabled=is_prod,
            multi_az_enabled=is_prod,
            at_rest_encryption_enabled=True,
            transit_encryption_enabled=True,          # TLS in-transit
            cache_subnet_group_name=subnet_group.cache_subnet_group_name,
            security_group_ids=[redis_sg.security_group_id],
            # Eviction policy: allkeys-lru so blacklist entries auto-expire under memory pressure
            cache_parameter_group_name="default.redis7",
            snapshot_retention_limit=0,              # no persistence (blacklist is rebuilt from DB)
        )
        self.redis_cluster.add_dependency(subnet_group)

        self.redis_endpoint = self.redis_cluster.attr_primary_end_point_address

        cdk.CfnOutput(self, "RedisEndpoint", value=self.redis_endpoint)
