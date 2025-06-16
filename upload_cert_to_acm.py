import boto3
import logging
from datetime import datetime, timedelta, timezone
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from botocore.exceptions import ClientError
import os

# Configure logging
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# Set working directory to the script location
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CERT_DIR = SCRIPT_DIR  # Store certs in ca-cert directory where script is

CERT_FILE = os.path.join(CERT_DIR, "alb.crt")
KEY_FILE = os.path.join(CERT_DIR, "alb.key")

def generate_self_signed_cert(cert_path, key_path, days_valid=365):
    logger.info("Generating private key and self-signed certificate...")

    key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "PH"),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Metro Manila"),
        x509.NameAttribute(NameOID.LOCALITY_NAME, "Taguig"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "SaaS"),
        x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, "Cloud"),
        x509.NameAttribute(NameOID.COMMON_NAME, "internal.saas.local"),
    ])

    cert = x509.CertificateBuilder() \
        .subject_name(subject) \
        .issuer_name(issuer) \
        .public_key(key.public_key()) \
        .serial_number(x509.random_serial_number()) \
        .not_valid_before(datetime.now(timezone.utc)) \
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=days_valid)) \
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True) \
        .sign(key, hashes.SHA256())

    with open(cert_path, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    logger.info(f"Certificate saved to: {cert_path}")

    with open(key_path, "wb") as f:
        f.write(key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        ))
    logger.info(f"Private key saved to: {key_path}")

def upload_cert_to_acm(cert_path, key_path):
    acm = boto3.client("acm")

    with open(cert_path, "rb") as f:
        cert_body = f.read()
    with open(key_path, "rb") as f:
        private_key = f.read()

    logger.info("Uploading certificate to ACM...")

    try:
        response = acm.import_certificate(
            Certificate=cert_body,
            PrivateKey=private_key
        )
        logger.info(f"Certificate successfully uploaded to ACM: {response['CertificateArn']}")
        return response['CertificateArn']
    except ClientError as e:
        logger.error(f"Failed to upload certificate: {e}")
        return None

if __name__ == "__main__":
    generate_self_signed_cert(CERT_FILE, KEY_FILE)
    upload_cert_to_acm(CERT_FILE, KEY_FILE)
