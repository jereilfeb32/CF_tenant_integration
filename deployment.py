import boto3
import sys
import os
import logging
import argparse
from botocore.exceptions import ClientError

# --- Logging setup ---
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# --- AWS clients ---
cf = boto3.client('cloudformation')
ec2 = boto3.client('ec2')

# --- Constants ---
TEMPLATE_DIR = "templates"

# --- Argument parsing ---
parser = argparse.ArgumentParser()
parser.add_argument('--force', action='store_true', help='Force update stacks even if already completed.')
args = parser.parse_args()

# --- Stack deployment definitions ---
stack_definitions = [
    {
        "name": "LZvpcStack",
        "template": "vpc.yaml",
        "parameters": [
            {"ParameterKey": "ProjectName", "ParameterValue": "SaaS"},
            {"ParameterKey": "Owner", "ParameterValue": "YourName"},
            {"ParameterKey": "BusinessUnit", "ParameterValue": "Cloud"},
            {"ParameterKey": "VpcCidr", "ParameterValue": "10.10.0.0/16"},
            {"ParameterKey": "Region", "ParameterValue": "ap-southeast-1"},
            {"ParameterKey": "AvailabilityZones", "ParameterValue": "ap-southeast-1a,ap-southeast-1b,ap-southeast-1c"},
            {"ParameterKey": "PublicSubnetCidrs", "ParameterValue": "10.10.1.0/24,10.10.2.0/24,10.10.3.0/24"},
            {"ParameterKey": "PrivateSubnetCidrs", "ParameterValue": "10.10.4.0/24,10.10.5.0/24,10.10.6.0/24"},
            {"ParameterKey": "ALBSubnetCidrs", "ParameterValue": "10.10.7.0/24,10.10.8.0/24,10.10.9.0/24"},
            {"ParameterKey": "GWLBSubnetCidrs", "ParameterValue": "10.10.10.0/24,10.10.11.0/24,10.10.12.0/24"},
            {"ParameterKey": "SFTPSubnetCidrs", "ParameterValue": "10.10.13.0/24,10.10.14.0/24,10.10.15.0/24"},
            {"ParameterKey": "APIGWSubnetCidrs", "ParameterValue": "10.10.16.0/24,10.10.17.0/24,10.10.18.0/24"}
        ],
        "outputs": [
            "VpcId", "ALBSubnet1Id", "ALBSubnet2Id", "ALBSubnet3Id",
            "APIGWSubnet1Id", "APIGWSubnet2Id",
            "GWLBSubnet1Id", "GWLBSubnet2Id", "GWLBSubnet3Id",
            "SFTPSubnet1Id", "SFTPSubnet2Id", "SFTPSubnet3Id"
        ]
    },
    {
        "name": "LZwafStack",
        "template": "waf.yaml",
        "parameters": [{"ParameterKey": "ProjectName", "ParameterValue": "SaaS"}],
        "outputs": ["WebACLArn"]
    },
    {
        "name": "LZvgwStack",
        "template": "vgw.yaml",
        "parameters": [{"ParameterKey": "ProjectName", "ParameterValue": "SaaS"}],
        "parameters_from_outputs": [
            {"output_key": "VpcId", "parameter_key": "VpcId"}
        ]
    },
    {
        "name": "LZsgStack",
        "template": "security-groups.yaml",
        "parameters": [{"ParameterKey": "ProjectName", "ParameterValue": "SaaS"}],
        "parameters_from_outputs": [
            {"output_key": "VpcId", "parameter_key": "VpcId"}
        ],
        "outputs": [
            "ALBSecurityGroupId",
            "TargetGroupSecurityGroupId",
            "ApiGatewayEndpointSecurityGroupId",
            "SFTPSecurityGroupId"
        ]
    },
    {
    "name": "LZalbStack",
    "template": "alb.yaml",
    "parameters": [
        {"ParameterKey": "ProjectName", "ParameterValue": "SaaS"},
        {
            "ParameterKey": "ACMCertificateArn",
            "ParameterValue": "arn:aws:acm:ap-southeast-1:975050199901:certificate/054f77c3-aec0-488d-ab55-8a2b552c1c90"
        }
    ],
    "parameters_from_outputs": [
        {"output_key": "VpcId", "parameter_key": "VpcId"},
        {
            "output_keys": ["ALBSubnet1Id", "ALBSubnet2Id", "ALBSubnet3Id"],
            "parameter_key": "ALBSubnetIds"
        },
        {"output_key": "ALBSecurityGroupId", "parameter_key": "ALBSecurityGroupId"},
        {"output_key": "TargetGroupSecurityGroupId", "parameter_key": "TargetGroupSecurityGroupId"},
        {"output_key": "WebACLArn", "parameter_key": "WAFWebACLArn"}
    ],
    "outputs": [
        "ALBArn",
        "ALBTargetGroupArn"
    ]
    },

    {
        "name": "LZgwlbeStack",
        "template": "gwlb-endpoint.yaml",
        "parameters": [
            {"ParameterKey": "ProjectName", "ParameterValue": "SaaS"},
            {"ParameterKey": "ServiceName", "ParameterValue": "com.amazonaws.vpce.ap-southeast-1.vpce-svc-0dfb94683dffb962e"}
        ],
        "parameters_from_outputs": [
            {
                "output_keys": ["GWLBSubnet1Id", "GWLBSubnet2Id", "GWLBSubnet3Id"],
                "parameter_key": "SubnetIds"
            },
            {"output_key": "VpcId", "parameter_key": "VpcId"}
        ],
        "outputs": ["GWLBEId1", "GWLBEId2", "GWLBEId3"]
    },
    {
        "name": "LZsftpStack",
        "template": "sftp-endpoint.yaml",
        "parameters": [
            {"ParameterKey": "ProjectName", "ParameterValue": "SaaS"}
        ],
        "parameters_from_outputs": [
            {"output_key": "VpcId", "parameter_key": "VpcId"},
            {"output_key": "SFTPSubnetIds", "parameter_key": "SFTPSubnetIds"},
            {"output_key": "SFTPSecurityGroupId", "parameter_key": "SecurityGroupId"}
        ],
        "outputs": ["SFTPVpcEndpointId"]
    }
]

def wait_for_completion(stack_name, operation):
    waiter_name = 'stack_create_complete' if operation == 'create_stack' else 'stack_update_complete'
    waiter = cf.get_waiter(waiter_name)
    logger.info(f"Waiting for {stack_name} to {operation.replace('_', ' ')}...")
    try:
        waiter.wait(StackName=stack_name)
        logger.info(f"{stack_name} {operation.replace('_', ' ')} completed successfully.")
    except Exception as e:
        logger.error(f"Error during stack wait: {e}")

def get_stack_status(stack_name):
    try:
        response = cf.describe_stacks(StackName=stack_name)
        return response['Stacks'][0]['StackStatus']
    except ClientError as e:
        if 'does not exist' in str(e):
            return None
        logger.error(f"Failed to get status of stack {stack_name}: {e}")
        return None

def deploy_stack(stack_def, collected_outputs):
    stack_name = stack_def["name"]
    template_path = os.path.join(TEMPLATE_DIR, stack_def["template"])

    if not os.path.isfile(template_path):
        logger.error(f"Template file not found: {template_path}")
        return False

    with open(template_path, 'r') as f:
        template_body = f.read()

    try:
        cf.validate_template(TemplateBody=template_body)
    except ClientError as e:
        logger.error(f"Template validation failed: {e}")
        return False

    parameters = list(stack_def.get("parameters", []))

    for p in stack_def.get("parameters_from_outputs", []):
        if "output_key" in p:
            key = p["output_key"]
            if key not in collected_outputs:
                logger.error(f"Missing required output '{key}' for stack {stack_name}")
                return False
            parameters.append({
                "ParameterKey": p["parameter_key"],
                "ParameterValue": collected_outputs[key]
            })
        elif "output_keys" in p:
            values = [collected_outputs.get(k) for k in p["output_keys"]]
            if None in values:
                missing = [k for k, v in zip(p["output_keys"], values) if v is None]
                logger.error(f"Missing required output(s) {', '.join(missing)} for stack {stack_name}")
                return False
            parameters.append({
                "ParameterKey": p["parameter_key"],
                "ParameterValue": ",".join(values)
            })
        else:
            logger.error(f"Invalid parameter mapping in stack {stack_name}: {p}")
            return False



    stack_status = get_stack_status(stack_name)
    try:
        if not stack_status:
            response = cf.create_stack(
                StackName=stack_name,
                TemplateBody=template_body,
                Parameters=parameters,
                Capabilities=['CAPABILITY_NAMED_IAM'],
                DisableRollback=True
            )
            logger.info(f"Creating stack: {response['StackId']}")
            wait_for_completion(stack_name, 'create_stack')
        elif stack_status in ["CREATE_COMPLETE", "UPDATE_COMPLETE"]:
            if not args.force:
                logger.info(f"Stack {stack_name} already exists. Skipping (use --force to override).")
                return True
            cf.update_stack(
                StackName=stack_name,
                TemplateBody=template_body,
                Parameters=parameters,
                Capabilities=['CAPABILITY_NAMED_IAM']
            )
            logger.info(f"Updating stack {stack_name}")
            wait_for_completion(stack_name, 'update_stack')
        else:
            logger.error(f"Stack {stack_name} is in unexpected state: {stack_status}")
            return False
        return True
    except ClientError as e:
        if "No updates are to be performed" in str(e):
            logger.info(f"No updates needed for stack {stack_name}.")
            return True
        logger.error(f"Error deploying stack {stack_name}: {e}")
        return False

def get_stack_outputs(stack_name):
    try:
        response = cf.describe_stacks(StackName=stack_name)
        return {o['OutputKey']: o['OutputValue'] for o in response['Stacks'][0].get('Outputs', [])}
    except ClientError as e:
        logger.error(f"Failed to get outputs for {stack_name}: {e}")
        return {}

def set_vpc_dns_attributes(vpc_id):
    try:
        ec2.modify_vpc_attribute(VpcId=vpc_id, EnableDnsSupport={'Value': True})
        ec2.modify_vpc_attribute(VpcId=vpc_id, EnableDnsHostnames={'Value': True})
        logger.info(f"Enabled DNS support and hostnames for VPC {vpc_id}")
    except ClientError as e:
        logger.error(f"Failed to modify VPC DNS attributes: {e}")
        sys.exit(1)

from datetime import datetime  # Add this at the top if not present

if __name__ == "__main__":
    collected_outputs = {}

    for stack in stack_definitions:
        success = deploy_stack(stack, collected_outputs)
        if not success:
            logger.error("Aborting pipeline due to failed stack.")
            sys.exit(1)

        outputs = get_stack_outputs(stack["name"])
        for key in stack.get("outputs", []):
            if key in outputs:
                collected_outputs[key] = outputs[key]
            else:
                logger.warning(f"Output '{key}' not found in {stack['name']}")

        # === DERIVED OUTPUTS after test-vpc-stack ===
        if stack["name"] == "test-vpc-stack":
            # Build ALBSubnetIds
            alb_required = ["ALBSubnet1Id", "ALBSubnet2Id", "ALBSubnet3Id"]
            if all(k in collected_outputs for k in alb_required):
                collected_outputs["ALBSubnetIds"] = ",".join(collected_outputs[k] for k in alb_required)
            else:
                missing = [k for k in alb_required if k not in collected_outputs]
                logger.error(f"Missing ALB subnet IDs: {', '.join(missing)}")
                sys.exit(1)

            # Build APIGW SubnetIds
            apigw_required = ["APIGWSubnet1Id", "APIGWSubnet2Id"]
            if all(k in collected_outputs for k in apigw_required):
                collected_outputs["APIGWSubnetIds"] = ",".join(collected_outputs[k] for k in apigw_required)
            else:
                missing = [k for k in apigw_required if k not in collected_outputs]
                logger.error(f"Missing API Gateway subnet IDs: {', '.join(missing)}")
                sys.exit(1)

            # Build SFTPSubnetIds
            sftp_required = ["SFTPSubnet1Id", "SFTPSubnet2Id", "SFTPSubnet3Id"]
            if all(k in collected_outputs for k in sftp_required):
                collected_outputs["SFTPSubnetIds"] = ",".join(collected_outputs[k] for k in sftp_required)
            else:
                missing = [k for k in sftp_required if k not in collected_outputs]
                logger.error(f"Missing SFTP subnet IDs: {', '.join(missing)}")
                sys.exit(1)

            # Build GWLBSubnetIds
            gwlb_required = ["GWLBSubnet1Id", "GWLBSubnet2Id", "GWLBSubnet3Id"]
            if all(k in collected_outputs for k in gwlb_required):
                collected_outputs["GWLBSubnetIds"] = ",".join(collected_outputs[k] for k in gwlb_required)
            else:
                missing = [k for k in gwlb_required if k not in collected_outputs]
                logger.error(f"Missing GWLB subnet IDs: {', '.join(missing)}")
                sys.exit(1)

            # Enable DNS attributes
            set_vpc_dns_attributes(collected_outputs["VpcId"])

            logger.info("\n--- Derived Outputs after test-vpc-stack ---")
            for k in ["ALBSubnetIds", "APIGWSubnetIds", "SFTPSubnetIds", "GWLBSubnetIds"]:
                logger.info(f"{k}: {collected_outputs[k]}")
