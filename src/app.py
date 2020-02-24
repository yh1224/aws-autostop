import json
import os
import re
from datetime import datetime

import boto3
import requests
from pytz import timezone

NOTIFY_TOPIC_ARN = os.environ['NOTIFY_TOPIC_ARN']
SLACK_WEBHOOK_URL = os.environ['SLACK_WEBHOOK_URL']
TIMEZONE = timezone(os.environ['TIMEZONE'])

rds_client = boto3.client('rds')
ec2_client = boto3.client('ec2')
elbv2_client = boto3.client('elbv2')
asg_client = boto3.client('autoscaling')

START_TAGS = ['auto:start-at', 'Auto:StartAt']
STOP_TAGS = ['auto:stop-at', 'Auto:StopAt']


def lambda_handler(event, context):
    messages = []
    result = 0
    result += proc_asg(messages)
    result += proc_ec2(messages)
    result += proc_rds(messages)
    if result > 0:
        notify('AWS AutoStop', '\n'.join(messages))


def on_time(keys, tags):
    if tags is None:
        return False

    weekdays = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']
    dt_now = datetime.now(TIMEZONE)

    for tag_value in map(lambda x: x['Value'], filter(lambda x: x['Key'] in keys, tags)):
        for time in [i for i in re.split(r'[ ,]', tag_value) if i]:
            if ':' in time:
                (wd, time) = time.split(':')
                if '-' in wd:
                    (wd_start, wd_end) = wd.split('-')
                    try:
                        wd_start = weekdays.index(wd_start)
                        wd_end = weekdays.index(wd_end)
                    except ValueError:
                        continue
                    if wd_end < wd_start:
                        wd_end += len(weekdays)
                    if weekdays[dt_now.weekday()] not in (weekdays * 2)[wd_start:(wd_end + 1)]:
                        continue
                elif weekdays[dt_now.weekday()] != wd:
                    continue
            if '-' in time:
                (start, end) = time.split('-')
                try:
                    start = int(start)
                    end = int(end)
                except ValueError:
                    return False
                if not (start <= dt_now.hour <= end):
                    return False
            elif dt_now.hour != int(time):
                continue
            # matched
            return True
    # unmatched any
    return False


def proc_rds(messages):
    return proc_rds_clusters(messages) + proc_rds_instances(messages)


def proc_rds_instances(messages):
    actions = 0
    response = rds_client.describe_db_instances()
    # print(response)
    for instance in response['DBInstances']:
        status = instance['DBInstanceStatus']  # creating, modifying, available, stopping, stopped
        instance_identifier = instance['DBInstanceIdentifier']
        instance_arn = instance['DBInstanceArn']
        tags_response = rds_client.list_tags_for_resource(ResourceName=instance_arn)
        instance_tags = tags_response['TagList']
        message = f'- RDS instance: {instance_identifier} ({status})'

        action = False
        if on_time(STOP_TAGS, instance_tags) and status == 'available':
            # Stop RDS instances
            action = True
            message += ' => Stopping'
            try:
                rds_client.stop_db_instance(DBInstanceIdentifier=instance_identifier)
            except rds_client.exceptions.ClientError as e:
                message += ' ... FAILED: ' + str(e)
        elif on_time(START_TAGS, instance_tags) and status == 'stopped':
            # Start RDS instances
            action = True
            message += ' => Starting'
            try:
                rds_client.stop_db_instance(DBInstanceIdentifier=instance_identifier)
            except rds_client.exceptions.ClientError as e:
                message += ' ... FAILED: ' + str(e)

        print(message)
        if action:
            actions += 1
            messages.append(message)

    return actions


def proc_rds_clusters(messages):
    actions = 0
    response = rds_client.describe_db_clusters()
    for cluster in response['DBClusters']:
        status = cluster['Status']  # starting, available, stopping, stopped
        cluster_identifier = cluster['DBClusterIdentifier']
        cluster_arn = cluster['DBClusterArn']
        tags_response = rds_client.list_tags_for_resource(ResourceName=cluster_arn)
        cluster_tags = tags_response['TagList']
        message = f'- RDS cluster: {cluster_identifier} ({status})'

        action = False
        if on_time(STOP_TAGS, cluster_tags) and status == 'available':
            # Stop RDS clusters
            action = True
            message += ' => Stopping'
            try:
                rds_client.stop_db_cluster(DBClusterIdentifier=cluster_identifier)
            except rds_client.exceptions.ClientError as e:
                message += ' ... FAILED: ' + str(e)
        elif on_time(START_TAGS, cluster_tags) and status == 'stopped':
            # Start RDS clusters
            action = True
            message += ' => Starting'
            try:
                rds_client.start_db_cluster(DBClusterIdentifier=cluster_identifier)
            except rds_client.exceptions.ClientError as e:
                message += ' ... FAILED: ' + str(e)

        print(message)
        if action:
            actions += 1
            messages.append(message)

    return actions


def proc_ec2(messages):
    actions = 0
    response = ec2_client.describe_instances()
    for reservation in response['Reservations']:
        for instance in reservation['Instances']:
            instance_id = instance['InstanceId']
            instance_state = instance['State']['Name']
            if 'Tags' in instance:
                instance_tags = instance['Tags']
            else:
                instance_tags = []
            if 'aws:autoscaling:groupName' in map(lambda x: x['Key'], instance_tags):
                # Ignore instances for ASG
                print(f'- EC2 instance: {instance_id} ({instance_state}) for ASG')
                continue
            message = f'- EC2 instance: {instance_id} ({instance_state})'

            action = False
            if on_time(STOP_TAGS, instance_tags) and instance_state == 'running':
                # Stop EC2 instance
                action = True
                message += ' => Stopping'
                try:
                    ec2_client.stop_instances(InstanceIds=[instance_id])
                except ec2_client.exceptions.ClientError as e:
                    message += ' ... FAILED: ' + str(e)
            elif on_time(START_TAGS, instance_tags) and instance_state == 'stopped':
                # Start EC2 instance
                action = True
                message += ' => Starting'
                try:
                    ec2_client.start_instances(InstanceIds=[instance_id])
                except ec2_client.exceptions.ClientError as e:
                    message += ' ... FAILED: ' + str(e)

            print(message)
            if action:
                actions += 1
                messages.append(message)

    return actions


def proc_asg(messages):
    actions = 0
    response = asg_client.describe_auto_scaling_groups()
    for asg in response['AutoScalingGroups']:
        asg_name = asg['AutoScalingGroupName']
        instance_size = asg['MaxSize']
        asg_tags = asg['Tags']
        message = f'- ASG: {asg_name}'

        action = False
        new_value = None
        if on_time(STOP_TAGS, asg_tags) and instance_size > 0:
            new_value = 0
            message += ' => Stopping'
        elif on_time(START_TAGS, asg_tags) and instance_size == 0:
            new_value = 1
            message += ' => Starting'
        if new_value is not None:
            action = True
            try:
                asg_client.update_auto_scaling_group(
                    AutoScalingGroupName=asg_name,
                    MinSize=new_value,
                    MaxSize=new_value
                )
            except asg_client.exceptions.ClientError as e:
                message += ' ... FAILED: ' + str(e)

        print(message)
        if action:
            actions += 1
            messages.append(message)

    return actions


def notify(title, message):
    if len(NOTIFY_TOPIC_ARN) > 0:
        notify_sns(NOTIFY_TOPIC_ARN, title, message)
    if len(SLACK_WEBHOOK_URL) > 0:
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
