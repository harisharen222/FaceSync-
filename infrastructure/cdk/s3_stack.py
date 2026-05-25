"""
s3_stack.py — S3 bucket for storing TFLite/ONNX models + CloudFront OAC.
"""
import aws_cdk as cdk
from aws_cdk import (
    aws_s3 as s3,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    aws_iam as iam,
)
from constructs import Construct

class NHAIS3Stack(cdk.Stack):
    def __init__(self, scope: Construct, id: str, env_name: str, **kwargs):
        super().__init__(scope, id, **kwargs)

        # ── S3 Bucket ─────────────────────────────────────────────────────────
        self.model_bucket = s3.Bucket(
            self, "ModelBucket",
            bucket_name=f"nhai-{env_name}-models-{self.account}-{self.region}",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            versioned=True,
            removal_policy=cdk.RemovalPolicy.RETAIN,
        )

        # ── CloudFront Distribution (OAC) ─────────────────────────────────────
        # Only create CloudFront in production to save costs, or if specifically requested.
        # For simplicity in this demo, we create it but it's optional.
        
        self.oac = cloudfront.CfnOriginAccessControl(
            self, "ModelBucketOAC",
            origin_access_control_config=cloudfront.CfnOriginAccessControl.OriginAccessControlConfigProperty(
                name=f"nhai-{env_name}-model-oac",
                origin_access_control_origin_type="s3",
                signing_behavior="always",
                signing_protocol="sigv4"
            )
        )

        self.distribution = cloudfront.Distribution(
            self, "ModelDistribution",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3Origin(self.model_bucket),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
                # In a real setup, you might restrict by geo or use signed cookies here.
                # Since the S3 presigned URLs are verified by S3 itself (forwarded), 
                # we just pass the query strings.
                origin_request_policy=cloudfront.OriginRequestPolicy.CORS_S3_ORIGIN,
            ),
            price_class=cloudfront.PriceClass.PRICE_CLASS_200, # Covers India
        )

        # Allow CloudFront to read from the bucket via OAC
        self.model_bucket.add_to_resource_policy(
            iam.PolicyStatement(
                actions=["s3:GetObject"],
                resources=[self.model_bucket.arn_for_objects("*")],
                principals=[iam.ServicePrincipal("cloudfront.amazonaws.com")],
                conditions={
                    "StringEquals": {
                        "AWS:SourceArn": f"arn:aws:cloudfront::{self.account}:distribution/{self.distribution.distribution_id}"
                    }
                }
            )
        )

        cdk.CfnOutput(self, "ModelBucketName", value=self.model_bucket.bucket_name)
        cdk.CfnOutput(self, "CloudFrontDomain", value=self.distribution.distribution_domain_name)
