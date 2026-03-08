import * as cdk from "aws-cdk-lib";
import * as iam from "aws-cdk-lib/aws-iam";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as lambda_python from "@aws-cdk/aws-lambda-python-alpha";
import * as logs from "aws-cdk-lib/aws-logs";
import * as scheduler from "aws-cdk-lib/aws-scheduler";
import * as scheduler_targets from "aws-cdk-lib/aws-scheduler-targets";
import * as sns from "aws-cdk-lib/aws-sns";
import {Construct} from "constructs";
import {Config} from "./config";

type AwsAutoStopStackProps = cdk.StackProps & {
    readonly config: Config;
}

export class AwsAutoStopStack extends cdk.Stack {
    constructor(scope: Construct, id: string, props: AwsAutoStopStackProps) {
        super(scope, id, props);

        const {config} = props;
        const timezone = config.timezone ?? "UTC";
        const slackWebhookUrl = config.slackWebhookUrl ?? "";

        const autoStopTopic = new sns.Topic(this, "AutoStopTopic");

        const autoStopRole = new iam.Role(this, "AutoStopRole", {
            assumedBy: new iam.ServicePrincipal("lambda.amazonaws.com"),
            managedPolicies: [
                iam.ManagedPolicy.fromAwsManagedPolicyName("service-role/AWSLambdaBasicExecutionRole"),
            ],
            inlinePolicies: {
                "AutoStopPolicy": new iam.PolicyDocument({
                    statements: [
                        new iam.PolicyStatement({
                            actions: [
                                "autoscaling:DescribeAutoScalingGroups",
                                "autoscaling:UpdateAutoScalingGroup",
                                "ec2:DescribeInstances",
                                "ec2:DescribeInstanceStatus",
                                "ec2:StartInstances",
                                "ec2:StopInstances",
                                "elasticbeanstalk:DescribeEnvironments",
                                "elasticbeanstalk:DescribeEnvironmentResources",
                                "elasticbeanstalk:ListTagsForResource",
                                "elasticbeanstalk:UpdateEnvironment",
                                "rds:DescribeDBClusters",
                                "rds:DescribeDBInstances",
                                "rds:ListTagsForResource",
                                "rds:StartDBCluster",
                                "rds:StartDBInstance",
                                "rds:StopDBCluster",
                                "rds:StopDBInstance",
                            ],
                            effect: iam.Effect.ALLOW,
                            resources: ["*"],
                        }),
                        new iam.PolicyStatement({
                            actions: ["sns:Publish"],
                            effect: iam.Effect.ALLOW,
                            resources: [autoStopTopic.topicArn],
                        }),
                    ],
                }),
            },
        });

        const autoStopFunction = new lambda_python.PythonFunction(this, "AutoStopFunction", {
            architecture: lambda.Architecture.ARM_64,
            entry: "../../src/lambdas/AutoStopFunction",
            environment: {
                TIMEZONE: timezone,
                NOTIFY_TOPIC_ARN: autoStopTopic.topicArn,
                SLACK_WEBHOOK_URL: slackWebhookUrl,
            },
            handler: "lambda_handler",
            logGroup: new logs.LogGroup(this, "AutoStopFunctionLogGroup", {
                retention: logs.RetentionDays.ONE_WEEK,
            }),
            runtime: lambda.Runtime.PYTHON_3_14,
            role: autoStopRole,
            timeout: cdk.Duration.seconds(10),
        });
        // run every hour
        new scheduler.Schedule(this, "Schedule", {
            schedule: scheduler.ScheduleExpression.cron({minute: "0", timeZone: cdk.TimeZone.of(timezone)}),
            target: new scheduler_targets.LambdaInvoke(autoStopFunction),
        });
    }
}
