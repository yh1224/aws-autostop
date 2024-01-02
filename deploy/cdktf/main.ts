import * as cdktf from "cdktf";
import {AwsAutoStopStack} from "./lib/aws-autostop-stack";
import {createConfig} from "./lib/config";

const app = new cdktf.App();
const config = createConfig(process.env.ENV);

new AwsAutoStopStack(app, "cdktf", {config});
app.synth();
