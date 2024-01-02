# AWS AutoStop

## Prerequisite

- [AWS SAM CLI](https://docs.aws.amazon.com/ja_jp/serverless-application-model/latest/developerguide/install-sam-cli.html)

## Deploy

```shell
sam build (--use-container)
sam deploy (--guided)
```

### Parameters

|Name|Default|Description|
|:--|:--|:--|
|Timezone|"`UTC`"|Timezone to evaluate time configuration. (example: `Asia/Tokyo`)|
|SlackWebhookUrl|(none)|Slack Webhook URL to notify. (can be ommitted)|
