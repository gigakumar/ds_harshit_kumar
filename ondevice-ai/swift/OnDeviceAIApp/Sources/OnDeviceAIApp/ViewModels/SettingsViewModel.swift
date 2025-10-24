import Foundation
import SwiftUI

@MainActor
final class SettingsViewModel: ObservableObject {
    @Published var baseURL: String = "http://127.0.0.1:9000"
    @Published var health: AutomationHealth?
    @Published var errorMessage: String?
    @Published var isRefreshing: Bool = false

    private let client: AutomationClient

    init(client: AutomationClient) {
        self.client = client
    }

    func applyBaseURL() async -> Bool {
        do {
            try await client.updateBaseURL(baseURL)
            errorMessage = nil
            health = nil
            return true
        } catch {
            errorMessage = error.localizedDescription
            return false
        }
    }

    func refreshHealth() async {
        isRefreshing = true
        defer { isRefreshing = false }
        do {
            health = try await client.health()
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
