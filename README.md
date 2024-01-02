# AWS AutoStop

Stop/start resources automatically depends on tag.

## Supported resources

- EC2 instance
- EC2 instance managed by AutoScaling Group
  - Control by scaling to 0 (when stop) or to 1 (when start).
- RDS cluster/instance

It might fail to start/stop resources in progress or invalid state.

## Deploy

You will need one of the following tools to deploy

- [AWS SAM CLI](deploy/sam/README.md)
- [AWS CDK](deploy/cdk/README.md)
- [CDK for Terraform](deploy/cdktf/README.md)

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
