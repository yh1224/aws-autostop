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

## How to use

Add tags below to resources.

|Key|Format|Description|
|:--|:--|:--|
|`Auto:StartAt` or `auto:start-at`|`[<dayOfWeeks>:]<hours>`|Time configuration to start resource|
|`Auto:StopAt` or `auto:stop-at`|`[<dayOfWeeks>:]<hours>`|Time configuration to stop resource|

### Example

|Example|Description|
|:--|:--|
|`21`|21:00|
|`0-23`|every hours|
|`sun:0-2`|0:00, 1:00 and 2:00 on sunday|
|`6 12 18`|6:00, 12:00 and 18:00 everyday|
