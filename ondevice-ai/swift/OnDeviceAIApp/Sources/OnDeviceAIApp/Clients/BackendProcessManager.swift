import Combine
import Foundation
#if canImport(AppKit)
import AppKit
#endif

@MainActor
final class BackendProcessManager: ObservableObject {
    enum LaunchState: Equatable {
        case stopped
        case launching
        case running
        case failed(String)

        static func == (lhs: LaunchState, rhs: LaunchState) -> Bool {
            switch (lhs, rhs) {
            case (.stopped, .stopped), (.launching, .launching), (.running, .running):
                return true
            case let (.failed(a), .failed(b)):
                return a == b
            default:
                return false
            }
        }
    }

    enum BackendProcessError: LocalizedError {
        case daemonNotFound(String)
        case launchFailed(String)

        var errorDescription: String? {
            switch self {
            case let .daemonNotFound(path):
                return "Could not locate automation daemon at \(path)."
            case let .launchFailed(message):
                return "Failed to launch automation daemon: \(message)"
            }
        }
    }

    static let shared = BackendProcessManager()

    @Published private(set) var launchState: LaunchState = .stopped

    private var process: Process?
    private var stdoutPipe: Pipe?
    private var stderrPipe: Pipe?
    private let pipelineQueue = DispatchQueue(label: "ai.mahi.backend.pipeline")
    private var lastLaunchAttempt: Date?
#if canImport(AppKit)
    private var terminationObserver: Any?
#endif

    private init() {
#if canImport(AppKit)
        terminationObserver = NotificationCenter.default.addObserver(
            forName: NSApplication.willTerminateNotification,
            object: nil,
            queue: nil
        ) { [weak self] _ in
            Task { await self?.stopBackend() }
        }
#endif
    }

    deinit {
#if canImport(AppKit)
        if let terminationObserver {
            NotificationCenter.default.removeObserver(terminationObserver)
        }
#endif
    }

    func ensureBackendRunning(client: AutomationClient, gracePeriod: TimeInterval = 1.4) async -> Bool {
        if await isHealthy(client: client) {
            launchState = .running
            return true
        }

        do {
            try startBackend()
        } catch {
            launchState = .failed(error.localizedDescription)
            return false
        }

        do {
            try await Task.sleep(nanoseconds: UInt64(gracePeriod * 1_000_000_000))
        } catch {}

        if await isHealthy(client: client) {
            launchState = .running
            return true
        }

        launchState = .failed("Daemon failed to report healthy after launch.")
        return false
    }

    func stopBackend() async {
        guard let process else { return }
        if process.isRunning {
            process.terminate()
            try? await Task.sleep(nanoseconds: 200_000_000)
            if process.isRunning {
                process.interrupt()
            }
        }
        cleanupProcess()
        launchState = .stopped
    }

    private func isHealthy(client: AutomationClient) async -> Bool {
        do {
            _ = try await client.health()
            return true
        } catch {
            return false
        }
    }

    private func startBackend() throws {
        if let process, process.isRunning {
            launchState = .running
            return
        }
        if let lastLaunchAttempt, Date().timeIntervalSince(lastLaunchAttempt) < 2.0 {
            return
        }
        lastLaunchAttempt = Date()

        let launchConfiguration = try resolveLaunchConfiguration()
        let process = Process()
        process.executableURL = launchConfiguration.executable
        process.arguments = launchConfiguration.arguments
        process.currentDirectoryURL = launchConfiguration.workingDirectory
        var environment = ProcessInfo.processInfo.environment
        environment["PYTHONUNBUFFERED"] = "1"
        if let existingPythonPath = environment["PYTHONPATH"], existingPythonPath.isEmpty == false {
            environment["PYTHONPATH"] = launchConfiguration.pythonPath + ":" + existingPythonPath
        } else {
            environment["PYTHONPATH"] = launchConfiguration.pythonPath
        }
        process.environment = environment

        let stdoutPipe = Pipe()
        let stderrPipe = Pipe()
        process.standardOutput = stdoutPipe
        process.standardError = stderrPipe
        capture(pipe: stdoutPipe, label: "STDOUT")
        capture(pipe: stderrPipe, label: "STDERR")

        launchState = .launching
        do {
            try process.run()
        } catch {
            cleanupProcess()
            throw BackendProcessError.launchFailed(error.localizedDescription)
        }
        process.terminationHandler = { [weak self] proc in
            Task { @MainActor [weak self] in
                guard let self else { return }
                if proc.terminationStatus == 0 {
                    self.launchState = .stopped
                } else {
                    self.launchState = .failed("Daemon exited with status \(proc.terminationStatus)")
                }
                self.cleanupProcess()
            }
        }

        self.process = process
        self.stdoutPipe = stdoutPipe
        self.stderrPipe = stderrPipe
    }

    private func cleanupProcess() {
        process = nil
        stdoutPipe = nil
        stderrPipe = nil
    }

    private func capture(pipe: Pipe, label: String) {
        pipe.fileHandleForReading.readabilityHandler = { handle in
            let data = handle.availableData
            guard data.isEmpty == false else { return }
            let text = String(decoding: data, as: UTF8.self)
            self.pipelineQueue.async {
                let formatted = text.trimmingCharacters(in: .whitespacesAndNewlines)
                guard formatted.isEmpty == false else { return }
                NSLog("[Backend] \(label): \(formatted)")
            }
        }
    }

    private struct LaunchConfiguration {
        let executable: URL
        let arguments: [String]
        let workingDirectory: URL
        let pythonPath: String
    }

    private func resolveLaunchConfiguration() throws -> LaunchConfiguration {
        if let packagedBinary = locatePackagedBinary() {
            let workingDirectory = packagedBinary.deletingLastPathComponent()
            return LaunchConfiguration(
                executable: packagedBinary,
                arguments: [],
                workingDirectory: workingDirectory,
                pythonPath: workingDirectory.path
            )
        }

        let repoRoot = locateRepositoryRoot()
        let daemonPath = repoRoot.appendingPathComponent("automation_daemon.py")
        guard FileManager.default.fileExists(atPath: daemonPath.path) else {
            throw BackendProcessError.daemonNotFound(daemonPath.path)
        }

        let overrideExec = ProcessInfo.processInfo.environment["MAHI_PYTHON_EXEC"]
        if let overrideExec, overrideExec.isEmpty == false {
            return LaunchConfiguration(
                executable: URL(fileURLWithPath: overrideExec),
                arguments: [daemonPath.path],
                workingDirectory: repoRoot,
                pythonPath: repoRoot.path
            )
        }

        let executable = URL(fileURLWithPath: "/usr/bin/env")
        return LaunchConfiguration(
            executable: executable,
            arguments: ["python3", daemonPath.path],
            workingDirectory: repoRoot,
            pythonPath: repoRoot.path
        )
    }

    private func locatePackagedBinary() -> URL? {
        let fileManager = FileManager.default

        var candidates: [URL] = []

        let bundleURL = Bundle.main.bundleURL
        let backendRoot = bundleURL.appendingPathComponent("Contents/Resources/backend", isDirectory: true)
        candidates.append(backendRoot.appendingPathComponent("mahi_backend"))
        candidates.append(backendRoot.appendingPathComponent("OnDeviceAI"))

        if let resourceURL = Bundle.main.resourceURL {
            let resourceBackend = resourceURL.appendingPathComponent("backend", isDirectory: true)
            candidates.append(resourceBackend.appendingPathComponent("mahi_backend"))
            candidates.append(resourceBackend.appendingPathComponent("OnDeviceAI"))
        }

        let repoRoot = locateRepositoryRoot()
        candidates.append(repoRoot.appendingPathComponent("build/backend/mahi_backend"))
        candidates.append(repoRoot.appendingPathComponent("build/mahi_backend/mahi_backend"))
        candidates.append(repoRoot.appendingPathComponent("build/OnDeviceAI/OnDeviceAI"))

        for candidate in candidates {
            if fileManager.isExecutableFile(atPath: candidate.path) {
                return candidate
            }
        }

        return nil
    }

    private func locateRepositoryRoot() -> URL {
        var url = URL(fileURLWithPath: #filePath)
        for _ in 0..<6 {
            url.deleteLastPathComponent()
        }
        return url
    }

}
