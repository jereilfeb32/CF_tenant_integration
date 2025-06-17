import boto3
import logging
import sys
from botocore.exceptions import ClientError

# --- Logging setup ---
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# --- AWS client ---
cf = boto3.client('cloudformation')

# --- Stack Deletion Order (reverse of creation order) ---
stack_names = [
    "LZs3VpcEndpointStack",
    "LZsftpStack",
    "LZgwlbeStack",
    "LZalbStack",
    "LZsgStack",
    "LZvgwStack",
    "LZwafStack",
    "LZvpcStack"
]

def get_stack_status(stack_name):
    """Check if the stack exists and return its status."""
    try:
        response = cf.describe_stacks(StackName=stack_name)
        return response['Stacks'][0]['StackStatus']
    except ClientError as e:
        if 'does not exist' in str(e):
            return None
        logger.error(f"Error checking stack {stack_name}: {e}")
        return None

def wait_for_deletion(stack_name):
    """Wait until the stack is deleted."""
    logger.info(f"Waiting for stack {stack_name} to be deleted...")
    waiter = cf.get_waiter('stack_delete_complete')
    try:
        waiter.wait(StackName=stack_name)
        logger.info(f"Stack {stack_name} deleted successfully.")
    except Exception as e:
        logger.error(f"Error waiting for deletion of stack {stack_name}: {e}")
        sys.exit(1)

def delete_stack(stack_name):
    """Delete the specified CloudFormation stack."""
    status = get_stack_status(stack_name)
    if not status:
        logger.info(f"Stack {stack_name} does not exist. Skipping.")
        return
    if status.endswith("_IN_PROGRESS"):
        logger.warning(f"Stack {stack_name} is in progress state ({status}). Skipping.")
        return

    try:
        cf.delete_stack(StackName=stack_name)
        logger.info(f"Delete initiated for stack {stack_name}")
        wait_for_deletion(stack_name)
    except ClientError as e:
        logger.error(f"Failed to delete stack {stack_name}: {e}")
        sys.exit(1)

if __name__ == "__main__":
    for stack in stack_names:
        delete_stack(stack)

    logger.info("✅ Cleanup complete.")
