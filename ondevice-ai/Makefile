.PHONY: proto run daemon test cli-index cli-query
proto:
	python -m grpc_tools.protoc -I=proto --python_out=core --grpc_python_out=core proto/assistant.proto

run:
	python automation_daemon.py

daemon:
	python automation_daemon.py $(ARGS)

cli-index:
	python -m cli.index index "$(text)"

cli-query:
	python -m cli.index query "$(text)"

test:
	pytest -q
