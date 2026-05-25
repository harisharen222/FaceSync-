"""
secrets_stack.py — AWS Secrets Manager entries for the NHAI platform.

Secrets created here:
  1. nhai/rs256-keypair       : RS256 private + public key PEM (for Auth Service JWT signing)
  2. nhai/internal-api-key    : Shared API key for service-to-service calls
  3. nhai/aes256-embedding-key: AES-256-GCM key for face embedding encryption (Enrollment Service)

NOTE: The actual secret VALUES are NOT set by CDK (that would be a security risk —
secrets would appear in CloudFormation templates). CDK creates the Secret resources
as placeholders. You populate them manually ONCE after first deploy:

  aws secretsmanager put-secret-value \
    --secret-id nhai/rs256-keypair \
    --secret-string '{"private_key": "-----BEGIN RSA...", "public_key": "-----BEGIN PUBLIC..."}'
"""
import aws_cdk as cdk
from aws_cdk import aws_secretsmanager as sm
from aws_cdk import aws_iam as iam
from constructs import Construct


class NHAISecretsStack(cdk.Stack):
    def __init__(self, scope: Construct, id: str, env_name: str, **kwargs):
        super().__init__(scope, id, **kwargs)

        # ── RS256 Keypair ─────────────────────────────────────────────────────
        self.rs256_secret = sm.Secret(
            self, "Rs256Secret",
            secret_name=f"nhai/{env_name}/rs256-keypair",
            description="RS256 private/public keypair for NHAI Auth Service JWT signing",
            # Placeholder — populate manually after first deploy
            secret_string_value=cdk.SecretValue.unsafe_plain_text(
                '{"private_key": "REPLACE_ME", "public_key": "REPLACE_ME"}'
            ),
        )

        # ── Internal Service API Key ───────────────────────────────────────────
        # Shared between all microservices for internal REST calls
        self.internal_api_key_secret = sm.Secret(
            self, "InternalApiKeySecret",
            secret_name=f"nhai/{env_name}/internal-api-key",
            description="Shared API key for NHAI microservice-to-microservice calls",
            generate_secret_string=sm.SecretStringGenerator(
                secret_string_template='{"api_key": "REPLACE_ME"}',
                generate_string_key="api_key",
                password_length=64,
                exclude_punctuation=True,
            ),
        )

        # ── AES-256 Embedding Encryption Key ──────────────────────────────────
        # Used by Enrollment Service to encrypt 128-D face embeddings
        self.aes_embedding_secret = sm.Secret(
            self, "AesEmbeddingSecret",
            secret_name=f"nhai/{env_name}/aes256-embedding-key",
            description="AES-256-GCM key for face embedding encryption (Enrollment Service)",
            generate_secret_string=sm.SecretStringGenerator(
                secret_string_template='{"key_hex": "REPLACE_ME"}',
                generate_string_key="key_hex",
                password_length=64,
                exclude_punctuation=True,
            ),
        )

        # ── Outputs ───────────────────────────────────────────────────────────
        cdk.CfnOutput(self, "Rs256SecretArn", value=self.rs256_secret.secret_arn)
        cdk.CfnOutput(self, "InternalApiKeySecretArn", value=self.internal_api_key_secret.secret_arn)
        cdk.CfnOutput(self, "AesEmbeddingSecretArn", value=self.aes_embedding_secret.secret_arn)
