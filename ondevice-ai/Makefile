.PHONY: proto run daemon test cli-index cli-query bundle-models package package-with-models clean-artifacts
proto:
	python3 -m grpc_tools.protoc -I=proto --python_out=core --grpc_python_out=core proto/assistant.proto

run:
	python3 automation_daemon.py

daemon:
	python3 automation_daemon.py $(ARGS)

cli-index:
	python3 -m cli.index index "$(text)"

cli-query:
	python3 -m cli.index query "$(text)"

bundle-models:
	python3 -m tools.fetch_models

package:
	pyinstaller packaging/OnDeviceAI.spec --noconfirm

package-with-models:
	$(MAKE) bundle-models
	$(MAKE) package

test:
	python3 -m pytest -q

clean-artifacts:
	rm -rf build dist OnDeviceAI.spec __pycache__ *.egg-info .pytest_cache
