import json
import os
from datetime import datetime

import boto3
import requests

# Stop on 8pm-6am JST everyday
STOP_ON_HOUR = range(11, 22)

# Wakeup RDS on sunday 6pm-7pm JST
WAKEUP_RDS_ON_WEEKDAY = 5
WAKEUP_RDS_ON_HOUR = range(9, 11)

TOPIC_ARN = os.environ.get('NOTIFY_ARN')
SLACK_WEBHOOK_URL = os.environ.get('SLACK_WEBHOOK_URL')

rds_client = boto3.client('rds')
eb_client = boto3.client('elasticbeanstalk')
ec2_client = boto3.client('ec2')
elbv2_client = boto3.client('elbv2')


def lambda_handler(event, context):
    dt_now = datetime.now()
    messages = []
    if dt_now.weekday() == WAKEUP_RDS_ON_WEEKDAY and dt_now.hour in WAKEUP_RDS_ON_HOUR:
        messages = wakeup_rds()
    if dt_now.hour in STOP_ON_HOUR:
        messages = stop_eb() + stop_ec2() + stop_rds()
    if len(messages) > 0:
        notify('AWS AutoStop', '\n'.join(messages))


def wakeup_rds():
    messages = []
    response = rds_client.describe_db_clusters()
    for cluster in response['DBClusters']:
        status = cluster['Status']  # stopped, starting, available, stopping
        cluster_identifier = cluster['DBClusterIdentifier']
        print(f'- RDS: {cluster_identifier} ({status})')
        if status == 'stopped':
            # Start cluster
            message = '- Waking up RDS cluster: {}'.format(cluster_identifier)
            try:
                rds_client.start_db_cluster(DBClusterIdentifier=cluster_identifier)
                messages.append(message)
            except rds_client.exceptions.ClientError:
                messages.append(f'{message} ... FAILED')
    return messages


def stop_rds():
    messages = []
    response = rds_client.describe_db_clusters()
    for cluster in response['DBClusters']:
        status = cluster['Status']  # stopped, starting, available, stopping
        cluster_identifier = cluster['DBClusterIdentifier']
        print(f'- RDS: {cluster_identifier} ({status})')
        if status == 'available':
            # Stop cluster
            message = '- Stopping RDS cluster: {}'.format(cluster_identifier)
            try:
                rds_client.stop_db_cluster(DBClusterIdentifier=cluster_identifier)
                messages.append(message)
            except rds_client.exceptions.ClientError:
                messages.append(f'{message} ... FAILED')
    return messages


def stop_eb():
    messages = []

    # EB
    response = eb_client.describe_environments()
    for environment in response['Environments']:
        application_name = environment['ApplicationName']
        environment_id = environment['EnvironmentId']
        environment_name = environment['EnvironmentName']
        print(f'- EB: {application_name} {environment_id} {environment_name}')
        resources_response = eb_client.describe_environment_resources(EnvironmentId=environment_id)
        resources = resources_response['EnvironmentResources']

        for load_balancer in resources['LoadBalancers']:
            load_balancer_name = load_balancer['Name']
            try:
                lb_response = elbv2_client.describe_load_balancers(Names=[load_balancer_name])
                lb_state = lb_response['LoadBalancers'][0]['State']['Code']
                print(f'  - LB: {load_balancer_name} ({lb_state})')
            except elbv2_client.exceptions.LoadBalancerNotFoundException:
                # probably Classic Load Balancer
                print(f'  - LB: {load_balancer_name}')

        running_instances = []
        for instance in resources['Instances']:
            instance_id = instance['Id']
            status_response = ec2_client.describe_instance_status(InstanceIds=[instance_id], IncludeAllInstances=True)
            instance_state = status_response['InstanceStatuses'][0]['InstanceState']['Name']
            print(f'  - EC2: {instance_id} ({instance_state})')
            if instance_state == 'running':
                running_instances.append(instance_id)

        if len(running_instances) > 0:
            # Terminate instances
            message = '- Terminating EC2 instances for EB: {}'.format(', '.join(running_instances))
            try:
                eb_client.update_environment(
                    EnvironmentId=environment_id,
                    OptionSettings=[
                        {
                            # 'ResourceName': 'string',
                            'Namespace': 'aws:autoscaling:asg',
                            'OptionName': 'MinSize',
                            'Value': '0'
                        },
                        {
                            # 'ResourceName': 'string',
                            'Namespace': 'aws:autoscaling:asg',
                            'OptionName': 'MaxSize',
                            'Value': '0'
                        },
                    ])
                messages.append(message)
            except eb_client.exceptions.ClientError:
                messages.append(f'{message} ... FAILED')

        return messages


def stop_ec2():
    messages = []

    # EC2
    response = ec2_client.describe_instances()
    for reservation in response['Reservations']:
        for instance in reservation['Instances']:
            instance_id = instance['InstanceId']
            instance_state = instance['State']['Name']
            instance_tags = instance['Tags']
            if 'elasticbeanstalk:environment-id' in map(lambda x: x['Key'], instance_tags):
                # Ignore instances for EB
                continue
            print(f'- EC2: {instance_id} ({instance_state})')
            if instance_state == 'running':
                # Stop instances
                message = '- Stopping EC2 instance: {}'.format(instance_id)
                try:
                    ec2_client.stop_instances(InstanceIds=[instance_id])
                    messages.append(message)
                except ec2_client.exceptions.ClientError:
                    messages.append(f'{message} ... FAILED')

    return messages


def notify(title, message):
    print(title)
    print(message)
    if TOPIC_ARN is not None and TOPIC_ARN != 'AutoStopTopic':
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
