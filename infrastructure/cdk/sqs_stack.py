"""
sqs_stack.py — Standard SQS queue for async attendance record ingestion.
"""
import aws_cdk as cdk
from aws_cdk import aws_sqs as sqs
from constructs import Construct

class NHAISqsStack(cdk.Stack):
    def __init__(self, scope: Construct, id: str, env_name: str, **kwargs):
        super().__init__(scope, id, **kwargs)

        # ── Dead Letter Queue (DLQ) ───────────────────────────────────────────
        self.dlq = sqs.Queue(
            self, "AttendanceSyncDLQ",
            queue_name=f"nhai-{env_name}-attendance-dlq",
            retention_period=cdk.Duration.days(14),  # Keep failed messages for 14 days
        )

        # ── Main Attendance Queue ─────────────────────────────────────────────
        self.attendance_queue = sqs.Queue(
            self, "AttendanceSyncQueue",
            queue_name=f"nhai-{env_name}-attendance-queue",
            visibility_timeout=cdk.Duration.seconds(30), # Must be > worker processing time
            retention_period=cdk.Duration.days(4),
            dead_letter_queue=sqs.DeadLetterQueue(
                max_receive_count=3, # Move to DLQ after 3 failed attempts
                queue=self.dlq
            ),
        )

        # ── Audit Queue ───────────────────────────────────────────────────────
        self.audit_dlq = sqs.Queue(
            self, "AuditDLQ",
            queue_name=f"nhai-{env_name}-audit-dlq",
            retention_period=cdk.Duration.days(14),
        )
        self.audit_queue = sqs.Queue(
            self, "AuditQueue",
            queue_name=f"nhai-{env_name}-audit-queue",
            visibility_timeout=cdk.Duration.seconds(30),
            dead_letter_queue=sqs.DeadLetterQueue(max_receive_count=3, queue=self.audit_dlq),
        )

        # ── Notification Queue ────────────────────────────────────────────────
        self.notification_dlq = sqs.Queue(
            self, "NotificationDLQ",
            queue_name=f"nhai-{env_name}-notification-dlq",
            retention_period=cdk.Duration.days(14),
        )
        self.notification_queue = sqs.Queue(
            self, "NotificationQueue",
            queue_name=f"nhai-{env_name}-notification-queue",
            visibility_timeout=cdk.Duration.seconds(30),
            dead_letter_queue=sqs.DeadLetterQueue(max_receive_count=3, queue=self.notification_dlq),
        )

        # ── Reporting Queue ───────────────────────────────────────────────────
        self.reporting_dlq = sqs.Queue(
            self, "ReportingDLQ",
            queue_name=f"nhai-{env_name}-reporting-dlq",
            retention_period=cdk.Duration.days(14),
        )
        self.reporting_queue = sqs.Queue(
            self, "ReportingQueue",
            queue_name=f"nhai-{env_name}-reporting-queue",
            visibility_timeout=cdk.Duration.seconds(30),
            dead_letter_queue=sqs.DeadLetterQueue(max_receive_count=3, queue=self.reporting_dlq),
        )

        cdk.CfnOutput(self, "AttendanceQueueUrl", value=self.attendance_queue.queue_url)
        cdk.CfnOutput(self, "AttendanceQueueArn", value=self.attendance_queue.queue_arn)
        cdk.CfnOutput(self, "AuditQueueUrl", value=self.audit_queue.queue_url)
        cdk.CfnOutput(self, "NotificationQueueUrl", value=self.notification_queue.queue_url)
        cdk.CfnOutput(self, "ReportingQueueUrl", value=self.reporting_queue.queue_url)
