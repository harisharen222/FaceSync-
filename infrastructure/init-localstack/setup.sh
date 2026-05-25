#!/bin/bash
echo "Initializing LocalStack resources for NHAI Platform..."

# Create SQS Queues
awslocal sqs create-queue --queue-name nhai-attendance-queue
awslocal sqs create-queue --queue-name nhai-audit-queue
awslocal sqs create-queue --queue-name nhai-notification-queue
awslocal sqs create-queue --queue-name nhai-reporting-queue

# Create EventBridge Bus
awslocal events create-event-bus --name nhai-event-bus

# Create EventBridge Rule for Audit (All nhai.* events)
awslocal events put-rule --name audit-rule --event-bus-name nhai-event-bus --event-pattern '{"source": [{"prefix": "nhai."}]}'
awslocal events put-targets --rule audit-rule --event-bus-name nhai-event-bus --targets "Id"="1","Arn"="arn:aws:sqs:ap-south-1:000000000000:nhai-audit-queue"

# Create EventBridge Rule for Notifications (Specific events)
awslocal events put-rule --name notification-rule --event-bus-name nhai-event-bus --event-pattern '{"source": [{"prefix": "nhai."}], "detail-type": ["SpoofingDetected", "AdminLoginFailed", "WorkerEnrolled"]}'
awslocal events put-targets --rule notification-rule --event-bus-name nhai-event-bus --targets "Id"="1","Arn"="arn:aws:sqs:ap-south-1:000000000000:nhai-notification-queue"

# Create EventBridge Rule for Reporting (Attendance and Enrollments)
awslocal events put-rule --name reporting-rule --event-bus-name nhai-event-bus --event-pattern '{"source": [{"prefix": "nhai."}], "detail-type": ["AttendanceVerified", "WorkerEnrolled"]}'
awslocal events put-targets --rule reporting-rule --event-bus-name nhai-event-bus --targets "Id"="1","Arn"="arn:aws:sqs:ap-south-1:000000000000:nhai-reporting-queue"

# Create S3 Bucket for models
awslocal s3 mb s3://nhai-models-local

echo "LocalStack initialization complete!"
