.PHONY: all
all: build

.PHONY: build
build:
	sam build --use-container

env.json: env.json.example
	if [ ! -e env.json ]; then cp env.json.example env.json; fi

.PHONY: local-invoke
local-invoke: build env.json
	sam local invoke --env-vars env.json

.PHONY:
deploy: build
	sam deploy
