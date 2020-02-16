# AWS AutoStop

Stop/start resources automatically depends on tag.

## Supported resources

- EC2 instance
- EC2 instance managed by AutoScaling Group
  - Control by scaling to 0 (when stop) or to 1 (when start).
- RDS cluster/instance

It might fail to start/stop resources in progress or invalid state.

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
|`Auto:StartAt` or `auto:start-at`|`[<dayOfWeek>:]<startHour>[-<endHour>]`|Time configuration to start resource|
|`Auto:StopAt` or `auto:stop-at`|`[<dayOfWeek>:]<startHour>[-<endHour>]`|Time configuration to stop resource|

### Example

|Exmample|Description|
|:--|:--|
|`21`|21:00|
|`0-23`|evenry hours|
|`sun:0-2`|0:00, 1:00 and 2:00 on sunday|
|`6 12 18`|6:00, 12:00, 18:00|
