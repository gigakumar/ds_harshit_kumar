import Foundation

struct ConnectionStatus {
    enum Phase {
        case idle
        case checking
        case connected(AutomationHealth)
        case failed(String)
    }

    var phase: Phase
    var lastUpdated: Date?

    static var idle: ConnectionStatus { ConnectionStatus(phase: .idle, lastUpdated: nil) }
    static var checking: ConnectionStatus { ConnectionStatus(phase: .checking, lastUpdated: nil) }

    var health: AutomationHealth? {
        if case let .connected(health) = phase {
            return health
        }
        return nil
    }

    var errorMessage: String? {
        if case let .failed(message) = phase {
            return message
        }
        return nil
    }

    var isConnected: Bool {
        health != nil
    }

    var isChecking: Bool {
        if case .checking = phase { return true }
        return false
    }

    var stateTitle: String {
        switch phase {
        case .idle:
            return "Waiting for daemon"
        case .checking:
            return "Checking daemon connectivity"
        case .connected:
            return "Connected to automation daemon"
        case .failed:
            return "Daemon unreachable"
        }
    }

    var stateDetail: String {
        switch phase {
        case .idle:
            return "Trigger a refresh to verify the local automation daemon."
        case .checking:
            return "Contacting localhost services and validating health endpoints."
        case let .connected(health):
            let docs = health.documentCount
            if docs == 0 {
                return "No indexed knowledge yet — start by uploading documents."
            }
            return "Indexed knowledge: \(docs) document\(docs == 1 ? "" : "s")."
        case let .failed(message):
            return message
        }
    }
}
