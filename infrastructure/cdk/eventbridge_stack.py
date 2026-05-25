"""
eventbridge_stack.py — Custom EventBridge bus and routing rules for microservices.
"""
import aws_cdk as cdk
from aws_cdk import (
    aws_events as events,
    aws_events_targets as targets,
    aws_sqs as sqs,
)
from constructs import Construct

class NHAIEventBridgeStack(cdk.Stack):
    def __init__(self, scope: Construct, id: str, env_name: str, audit_queue: sqs.Queue, notification_queue: sqs.Queue, reporting_queue: sqs.Queue, **kwargs):
        super().__init__(scope, id, **kwargs)

        # ── Custom Event Bus ──────────────────────────────────────────────────
        self.bus = events.EventBus(
            self, "NHAIEventBus",
            event_bus_name=f"nhai-{env_name}-event-bus"
        )
        
        # ── Audit Rule (All nhai.* events) ────────────────────────────────────
        self.audit_rule = events.Rule(
            self, "AuditRule",
            event_bus=self.bus,
            rule_name=f"nhai-{env_name}-audit-rule",
            event_pattern=events.EventPattern(
                source=events.Match.prefix("nhai.")
            )
        )
        self.audit_rule.add_target(targets.SqsQueue(audit_queue))

        # ── Notification Rule (Specific high-priority events) ──────────────────
        self.notification_rule = events.Rule(
            self, "NotificationRule",
            event_bus=self.bus,
            rule_name=f"nhai-{env_name}-notification-rule",
            event_pattern=events.EventPattern(
                source=events.Match.prefix("nhai."),
                detail_type=["SpoofingDetected", "AdminLoginFailed", "WorkerEnrolled"]
            )
        )
        self.notification_rule.add_target(targets.SqsQueue(notification_queue))

        # ── Reporting Rule ────────────────────────────────────────────────────
        self.reporting_rule = events.Rule(
            self, "ReportingRule",
            event_bus=self.bus,
            rule_name=f"nhai-{env_name}-reporting-rule",
            event_pattern=events.EventPattern(
                source=events.Match.prefix("nhai."),
                detail_type=["AttendanceVerified", "WorkerEnrolled"]
            )
        )
        self.reporting_rule.add_target(targets.SqsQueue(reporting_queue))

        cdk.CfnOutput(self, "EventBusName", value=self.bus.event_bus_name)
        cdk.CfnOutput(self, "EventBusArn", value=self.bus.event_bus_arn)
