import boto3
import logging
import time
from botocore.exceptions import ClientError

# --- Logging setup ---
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# --- AWS client ---
cf = boto3.client('cloudformation')

# --- Stack names in reverse order of deployment ---
STACK_NAMES = [
    "test-sftp-endpoint-stack",
    "test-gwlb-stack",
    "test-alb-stack",
    "test-security-groups-stack",
    "test-vgw-stack",
    "test-waf-stack",
    "test-vpc-stack"
]

def delete_stack(stack_name):
    logger.info(f"Initiating delete for stack: {stack_name}")
    try:
        cf.delete_stack(StackName=stack_name)
    except ClientError as e:
        logger.error(f"Failed to delete stack {stack_name}: {e}")
        return False
    return True

def wait_for_deletion(stack_name):
    logger.info(f"Waiting for stack deletion: {stack_name}")
    waiter = cf.get_waiter('stack_delete_complete')
    try:
        waiter.wait(StackName=stack_name)
        logger.info(f"Stack {stack_name} deleted successfully.")
    except ClientError as e:
        logger.error(f"Error waiting for deletion of stack {stack_name}: {e}")

def stack_exists(stack_name):
    try:
        cf.describe_stacks(StackName=stack_name)
        return True
    except ClientError as e:
        if "does not exist" in str(e):
            return False
        raise

def cleanup_stacks():
    for stack_name in STACK_NAMES:
        if not stack_exists(stack_name):
            logger.info(f"Stack {stack_name} does not exist. Skipping.")
            continue

        if delete_stack(stack_name):
            wait_for_deletion(stack_name)
        else:
            logger.error(f"Failed to initiate deletion for {stack_name}.")

if __name__ == "__main__":
    logger.info("Starting CloudFormation stack cleanup...")
    cleanup_stacks()
    logger.info("Cleanup complete.")
