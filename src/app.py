import json
import os
import re
from datetime import datetime

import boto3
import requests

NOTIFY_TOPIC_ARN = os.environ['NOTIFY_TOPIC_ARN']
SLACK_WEBHOOK_URL = os.environ['SLACK_WEBHOOK_URL']

rds_client = boto3.client('rds')
eb_client = boto3.client('elasticbeanstalk')
ec2_client = boto3.client('ec2')
elbv2_client = boto3.client('elbv2')
asg_client = boto3.client('autoscaling')

START_TAGS = ['auto:start-at', 'Auto:StartAt']
STOP_TAGS = ['auto:stop-at', 'Auto:StopAt']


def lambda_handler(event, context):
    messages = []
    # result = proc_eb(messages)
    result = proc_asg(messages)
    result += proc_ec2(messages)
    result += proc_rds(messages)
    if result > 0:
        notify('AWS AutoStop', '\n'.join(messages))


def on_time(keys, tags):
    if tags is None:
        return False

    weekdays = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']
    dt_now = datetime.now()

    for tag_value in map(lambda x: x['Value'], filter(lambda x: x['Key'] in keys, tags)):
        for time in [i for i in re.split(r'[ ,]', tag_value) if i]:
            if ':' in time:
                (weekday, time) = time.split(':')
                if weekdays[dt_now.weekday()] != weekday:
                    continue
            if '-' in time:
                (start, end) = time.split('-')
                try:
                    if not (int(start) <= dt_now.hour <= int(end)):
                        continue
                except ValueError:
                    continue
            elif dt_now.hour != int(time):
                continue
            # matched
            return True
    # unmatched any
    return False


def proc_rds(messages):
    actions = 0
    response = rds_client.describe_db_clusters()
    for cluster in response['DBClusters']:
        status = cluster['Status']  # stopped, starting, available, stopping
        cluster_identifier = cluster['DBClusterIdentifier']
        cluster_arn = cluster['DBClusterArn']
        tags_response = rds_client.list_tags_for_resource(ResourceName=cluster_arn)
        cluster_tags = tags_response['TagList']
        message = f'- RDS: {cluster_identifier} ({status})'

        if on_time(STOP_TAGS, cluster_tags) and status == 'available':
            # Stop RDS clusters
            actions += 1
            message += ' => Stopping'
            try:
                rds_client.stop_db_cluster(DBClusterIdentifier=cluster_identifier)
            except rds_client.exceptions.ClientError as e:
                message += ' ... FAILED: ' + str(e)
        elif on_time(START_TAGS, cluster_tags) and status == 'stopped':
            # Start RDS clusters
            actions += 1
            message += ' => Starting'
            try:
                rds_client.start_db_cluster(DBClusterIdentifier=cluster_identifier)
            except rds_client.exceptions.ClientError as e:
                message += ' ... FAILED: ' + str(e)

        messages.append(message)

    return actions


def proc_ec2(messages):
    actions = 0
    response = ec2_client.describe_instances()
    for reservation in response['Reservations']:
        for instance in reservation['Instances']:
            instance_id = instance['InstanceId']
            instance_state = instance['State']['Name']
            instance_tags = instance['Tags']
            if 'aws:autoscaling:groupName' in map(lambda x: x['Key'], instance_tags):
                # Ignore instances for ASG
                messages.append(f'- EC2: {instance_id} ({instance_state}) for ASG')
                continue
            message = f'- EC2: {instance_id} ({instance_state})'

            if on_time(STOP_TAGS, instance_tags) and instance_state == 'running':
                # Stop EC2 instance
                actions += 1
                message += ' => Stopping'
                try:
                    ec2_client.stop_instances(InstanceIds=[instance_id])
                except ec2_client.exceptions.ClientError as e:
                    message += ' ... FAILED: ' + str(e)
            elif on_time(START_TAGS, instance_tags) and instance_state == 'stopped':
                # Start EC2 instance
                actions += 1
                message += ' => Starting'
                try:
                    ec2_client.start_instances(InstanceIds=[instance_id])
                except ec2_client.exceptions.ClientError as e:
                    message += ' ... FAILED: ' + str(e)

            messages.append(message)

    return actions


def proc_eb(messages):
    actions = 0
    response = eb_client.describe_environments()
    for environment in response['Environments']:
        application_name = environment['ApplicationName']
        environment_id = environment['EnvironmentId']
        environment_arn = environment['EnvironmentArn']
        environment_name = environment['EnvironmentName']
        settings_response = eb_client.describe_configuration_settings(
            ApplicationName=application_name, EnvironmentName=environment_name)
        instance_size = next(map(lambda x: int(x['Value']), filter(
            lambda x: x['ResourceName'] == 'AWSEBAutoScalingGroup' and x['Namespace'] == 'aws:autoscaling:asg' and
                      x['OptionName'] == 'MaxSize', settings_response['ConfigurationSettings'][0]['OptionSettings']
        )), None)
        resources_response = eb_client.describe_environment_resources(EnvironmentId=environment_id)
        resources = resources_response['EnvironmentResources']
        tags_response = eb_client.list_tags_for_resource(ResourceArn=environment_arn)
        environment_tags = tags_response['ResourceTags']
        message = f'- EB: {application_name} {environment_id} {environment_name}'

        for load_balancer in resources['LoadBalancers']:
            load_balancer_name = load_balancer['Name']
            try:
                lb_response = elbv2_client.describe_load_balancers(Names=[load_balancer_name])
                lb_state = lb_response['LoadBalancers'][0]['State']['Code']
                message += f'\n  - LB: {load_balancer_name} ({lb_state})'
            except elbv2_client.exceptions.LoadBalancerNotFoundException:
                # probably Classic Load Balancer
                message += f'\n  - LB: {load_balancer_name}'

        new_value = None
        if on_time(STOP_TAGS, environment_tags) and instance_size > 0:
            new_value = 0
            message += ' => Stopping'
        elif on_time(START_TAGS, environment_tags) and instance_size == 0:
            new_value = 1
            message += ' => Starting'
        if new_value is not None:
            actions += 1
            try:
                eb_client.update_environment(
                    EnvironmentId=environment_id,
                    OptionSettings=[
                        {
                            'ResourceName': 'AWSEBAutoScalingGroup',
                            'Namespace': 'aws:autoscaling:asg',
                            'OptionName': 'MinSize',
                            'Value': str(new_value)
                        },
                        {
                            'ResourceName': 'AWSEBAutoScalingGroup',
                            'Namespace': 'aws:autoscaling:asg',
                            'OptionName': 'MaxSize',
                            'Value': str(new_value)
                        },
                    ])
            except eb_client.exceptions.ClientError as e:
                message += ' ... FAILED: ' + str(e)

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

        new_value = None
        if on_time(STOP_TAGS, asg_tags) and instance_size > 0:
            new_value = 0
            message += ' => Stopping'
        elif on_time(START_TAGS, asg_tags) and instance_size == 0:
            new_value = 1
            message += ' => Starting'
        if new_value is not None:
            actions += 1
            try:
                asg_client.update_auto_scaling_group(
                    AutoScalingGroupName=asg_name,
                    MinSize=new_value,
                    MaxSize=new_value
                )
            except eb_client.exceptions.ClientError as e:
                message += ' ... FAILED: ' + str(e)

        messages.append(message)

    return actions


def notify(title, message):
    print(title)
    print(message)
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
