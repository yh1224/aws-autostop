import json
import os
from datetime import datetime

import boto3
import requests

# Start on sunday 2am
START_ON_WEEKDAY = 5
START_ON_HOUR = 17

# Stop at 3am everyday
STOP_ON_HOUR = 18

TOPIC_ARN = os.environ.get('NOTIFY_ARN')
SLACK_WEBHOOK_URL = os.environ.get('SLACK_WEBHOOK_URL')


def lambda_handler(event, context):
    rds_client = boto3.client('rds')
    response = rds_client.describe_db_clusters()
    messages = []
    for cluster in response['DBClusters']:
        status = cluster['Status']  # stopped, starting, available, stopping
        cluster_identifier = cluster['DBClusterIdentifier']
        print(cluster_identifier + ': ' + status)

        dt_now = datetime.now()
        if dt_now.weekday() == START_ON_WEEKDAY and dt_now.hour == START_ON_HOUR and status == 'stopped':
            # Start cluster on sunday
            messages.append('Starting {}'.format(cluster_identifier))
            rds_client.start_db_cluster(DBClusterIdentifier=cluster_identifier)
        if dt_now.hour != STOP_ON_HOUR and status == 'available':
            # Stop cluster at 0 am
            messages.append('Stopping {}'.format(cluster_identifier))
            rds_client.stop_db_cluster(DBClusterIdentifier=cluster_identifier)
    if len(messages) > 0:
        notify('Check RDS', '\n'.join(messages))


def notify(title, message):
    print(title)
    print(message)
    if TOPIC_ARN is not None and TOPIC_ARN != 'Topic':
        notify_sns(TOPIC_ARN, title, message)
    if SLACK_WEBHOOK_URL is not None and SLACK_WEBHOOK_URL != 'SlackWebhookUrl':
        notify_slack(SLACK_WEBHOOK_URL, title, message)


def notify_slack(url, title, message):
    requests.post(url, data=json.dumps({
        'attachments': [
            {
                'color': '#36a64f',
                'pretext': title,
                'text': message
            }
        ]
    }))


def notify_sns(topic, title, message):
    sns_client = boto3.client('sns')
    sns_client.publish(
        TopicArn=topic,
        Subject=title,
        Message=message
    )
