# OnDeviceAIApp (SwiftUI)

Native macOS shell for the MahiLLM automation daemon.

## Getting started

1. Install Xcode 16 or newer and the Swift gRPC plugin:
   ```bash
   brew install swift-protobuf
   brew install grpc-swift
   ```
2. Generate the Swift gRPC stubs (optional – the app defaults to the JSON HTTP API, but gRPC clients can be enabled):
   ```bash
   cd ../../proto
   protoc \
     --swift_out=../swift/OnDeviceAIApp/Sources/OnDeviceAIApp/Generated \
     --grpc-swift_out=../swift/OnDeviceAIApp/Sources/OnDeviceAIApp/Generated \
     assistant.proto
   ```
   The app ships with an HTTP client by default, so this step can be skipped.
3. Open the package in Xcode:
   ```bash
   open Package.swift
   ```
4. Set the scheme to **OnDeviceAIApp (My Mac)** and run. The app expects the automation daemon to be running locally (see repository README).

## Features

- Planner view with contextual knowledge and multi-step plans.
- Knowledge browser with recency timeline, semantic search, and quick actions.
- Automations dashboard for saved runbooks and execution history.
- Persistent connection header that surfaces daemon uptime, indexed document totals, and one-tap refresh or troubleshooting shortcuts.
- Plugin manifest inspector with signature status.
- Settings panel with daemon health indicators, permission checklist, and model controls.

## Integrated backend

The SwiftUI app now bundles and controls the Python automation daemon directly:

- On launch the UI checks local health, starts the Python backend when needed, and waits for it to report healthy before unblocking interactions.
- Backend stdout/stderr is piped into the macOS unified logging system (visible via Console.app) for quick debugging.
- When the app is backgrounded or exited, the embedded daemon is terminated cleanly to avoid orphaned processes.

You can override the Python interpreter via the `MAHI_PYTHON_EXEC` environment variable if you need to target a custom virtual environment. By default the app resolves `automation_daemon.py` from the repository root and runs it with `python3`.

The UI is fully SwiftUI-based, uses SF Symbols, vibrant materials, and adapts to both light/dark modes automatically.
