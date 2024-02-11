import * as path from "node:path";
import * as cdktf from "cdktf";
import {AwsProvider} from "@cdktf/provider-aws/lib/provider";
import {CloudwatchEventRule} from "@cdktf/provider-aws/lib/cloudwatch-event-rule";
import {CloudwatchEventTarget} from "@cdktf/provider-aws/lib/cloudwatch-event-target";
import {CloudwatchLogGroup} from "@cdktf/provider-aws/lib/cloudwatch-log-group";
import {IamRole} from "@cdktf/provider-aws/lib/iam-role";
import {LambdaFunction} from "@cdktf/provider-aws/lib/lambda-function";
import {LambdaPermission} from "@cdktf/provider-aws/lib/lambda-permission";
import {S3Bucket} from "@cdktf/provider-aws/lib/s3-bucket";
import {S3Object} from "@cdktf/provider-aws/lib/s3-object";
import {SnsTopic} from "@cdktf/provider-aws/lib/sns-topic";
import {RandomProvider} from "@cdktf/provider-random/lib/provider";
import {Id} from "@cdktf/provider-random/lib/id";
import {Construct} from "constructs";
import {Config} from "./config";

type AwsAutoStopStackProps = {
    config: Config;
};

export class AwsAutoStopStack extends cdktf.TerraformStack {
    constructor(scope: Construct, id: string, props: AwsAutoStopStackProps) {
        super(scope, id);

        const {config} = props;
        const timezone = config.timezone ?? "UTC";
        const slackWebhookUrl = config.slackWebhookUrl ?? "";

        new RandomProvider(this, "RandomProvider", {});
        const uniqueSuffix = new Id(this, "RandomId", {byteLength: 5});

        new AwsProvider(this, "AwsProvider", {
            defaultTags: [{
                tags: {
                    "cdktf:project": config.project,
                },
            }],
            region: config.env?.region,
        });
        if (config.backend?.startsWith("s3://")) {
            const paths = config.backend?.substring(5).split("/");
            const bucket = paths.shift()!;
            const key = path.join(paths.join("/"), "terraform.cdktf.tfstate");
            new cdktf.S3Backend(this, {
                bucket,
                key,
                region: config.env?.region,
            });
        }

        const autoStopTopic = new SnsTopic(this, "AutoStopTopic", {
            name: `${config.project}-AutoStopTopic-${uniqueSuffix.hex}`,
        });

        const autoStopRole = new IamRole(this, "AutoStopRole", {
            assumeRolePolicy: JSON.stringify({
                Version: "2012-10-17",
                Statement: [{
                    Action: "sts:AssumeRole",
                    Principal: {
                        Service: "lambda.amazonaws.com",
                    },
                    Effect: "Allow",
                }],
            }),
            managedPolicyArns: [
                "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole",
            ],
            name: `${config.project}-AutoStopRole-${uniqueSuffix.hex}`,
            inlinePolicy: [{
                name: "AutoStopPolicy",
                policy: JSON.stringify({
                    Version: "2012-10-17",
                    Statement: [
                        {
                            Action: [
                                "autoscaling:DescribeAutoScalingGroups",
                                "autoscaling:UpdateAutoScalingGroup",
                                "ec2:DescribeInstanceStatus",
                                "ec2:DescribeInstances",
                                "ec2:StartInstances",
                                "ec2:StopInstances",
                                "elasticbeanstalk:DescribeEnvironmentResources",
                                "elasticbeanstalk:DescribeEnvironments",
                                "elasticbeanstalk:ListTagsForResource",
                                "elasticbeanstalk:UpdateEnvironment",
                                "rds:DescribeDBClusters",
                                "rds:DescribeDBInstances",
                                "rds:ListTagsForResource",
                                "rds:StartDBCluster",
                                "rds:StartDBInstance",
                                "rds:StopDBCluster",
                                "rds:StopDBInstance"
                            ],
                            Effect: "Allow",
                            Resource: "*",
                        },
                        {
                            Action: "sns:Publish",
                            Effect: "Allow",
                            Resource: autoStopTopic.arn,
                        }
                    ]
                }),
            }],
        });

        const bucket = new S3Bucket(this, "AssetBucket", {
            bucket: `cdktf-${config.project.toLowerCase()}-assets-${uniqueSuffix.hex}`,
        });
        const functionAsset = new cdktf.TerraformAsset(this, "lambda-asset", {
            path: path.resolve(__dirname, "../../../src/lambdas/AutoStopFunction"),
            type: cdktf.AssetType.ARCHIVE,
        });
        const lambdaArchive = new S3Object(this, "FunctionAsset", {
            bucket: bucket.bucket,
            key: functionAsset.assetHash,
            source: functionAsset.path,
            sourceHash: functionAsset.assetHash,
        });
        const autoStopFunction = new LambdaFunction(this, "AutoStopFunction", {
            architectures: ["arm64"],
            environment: {
                variables: {
                    TIMEZONE: timezone,
                    NOTIFY_TOPIC_ARN: autoStopTopic.arn,
                    SLACK_WEBHOOK_URL: slackWebhookUrl,
                },
            },
            functionName: `${config.project}-AutoStopFunction-${uniqueSuffix.hex}`,
            handler: "index.lambda_handler",
            runtime: "python3.11",
            role: autoStopRole.arn,
            s3Bucket: bucket.bucket,
            s3Key: lambdaArchive.key,
            timeout: 10,
        });
        new CloudwatchLogGroup(this, "AutoStopLogGroup", {
            name: `/aws/lambda/${autoStopFunction.functionName}`,
            retentionInDays: 7,
        });

        const autoStopEventRule = new CloudwatchEventRule(this, "AutoStopRule", {
            name: `${config.project}-AutoStopRule-${uniqueSuffix.hex}`,
            scheduleExpression: "cron(0 * * * ? *)", // every hour
        });
        new CloudwatchEventTarget(this, "AutoStopTarget", {
            arn: autoStopFunction.arn,
            rule: autoStopEventRule.name,
        });
        new LambdaPermission(this, "AutoStopPermission", {
            action: "lambda:InvokeFunction",
            functionName: autoStopFunction.functionName,
            principal: "events.amazonaws.com",
            sourceArn: autoStopEventRule.arn,
        });
    }
}
