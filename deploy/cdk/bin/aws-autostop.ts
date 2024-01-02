#!/usr/bin/env node
import "source-map-support/register";
import * as cdk from "aws-cdk-lib";
import {AwsAutoStopStack} from "../lib/aws-autostop-stack";
import {createConfig} from "../lib/config";

const app = new cdk.App();
const config = createConfig(app.node.tryGetContext("env") || process.env.ENV);

new AwsAutoStopStack(app, "AwsAutoStopStack", {
    env: config.env,
    stackName: config.stackName,
    config,
});
