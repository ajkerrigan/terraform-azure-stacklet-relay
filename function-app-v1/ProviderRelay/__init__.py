import json
import logging
import os

import azure.functions as func

from azure.identity import DefaultAzureCredential

import boto3


def get_session(client_id, audience, role_arn):
    client = boto3.client("sts")
    creds = DefaultAzureCredential(managed_identity_client=client_id)
    token = creds.get_token(audience)
    try:
        res = client.assume_role_with_web_identity(
            WebIdentityToken=token.token,
            RoleArn=role_arn,
            RoleSessionName="ComingFromAzure",
        )
    except Exception as e:
        logging.error(f"unable to assume role:{e}")
        raise

    session = boto3.session.Session(
        aws_access_key_id=res["Credentials"]["AccessKeyId"],
        aws_secret_access_key=res["Credentials"]["SecretAccessKey"],
        aws_session_token=res["Credentials"]["SessionToken"],
    )
    logging.info("Got session")
    return session


def main(msg: func.QueueMessage):
    client_id = os.environ["AZURE_CLIENT_ID"]
    audience = os.environ["AZURE_AUDIENCE"]

    target_account = os.environ["AWS_TARGET_ACCOUNT"]
    region = os.environ["AWS_TARGET_REGION"]
    role_name = os.environ["AWS_TARGET_ROLE_NAME"]
    partition = os.environ["AWS_TARGET_PARTITION"]
    role_arn = f"arn:{partition}:iam::{target_account}:role/{role_name}"

    session = get_session(client_id, audience, role_arn)
    events_client = session.client("events", region_name=region)

    body_string = msg.get_body().decode("utf-8")
    body = json.loads(body_string)
    source = body["data"]["operationName"].split('/')[0]

    try:
        events_client.put_events(
            Entries=[
                {
                    "Time": msg.insertion_time,
                    "Source": source,
                    "DetailType": "CloudEvent/Azure System Topic Event",
                    "Detail": body_string,
                    "EventBusName": os.environ["AWS_TARGET_EVENT_BUS"],
                }
            ]
        )
    except Exception as e:
        logging.error(f"failed to put event:{e}")
        raise
