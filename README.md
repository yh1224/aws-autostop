# AWS AutoStop

Stop/start resources automatically depends on tag.

## Supported resources

- EC2 instance
- EC2 instance managed by AutoScaling Group
  - Control by scaling to 0 (when stop) or to 1 (when start).
- RDS cluster/instance

It might fail to start/stop resources in progress or invalid state.
