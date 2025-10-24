import Foundation
import SwiftUI

@MainActor
final class PluginsViewModel: ObservableObject {
    @Published var plugins: [PluginManifestView] = []
    @Published var errorMessage: String?

    private let client: AutomationClient

    init(client: AutomationClient) {
        self.client = client
    }

    func refresh() async {
        do {
            plugins = try await client.plugins()
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
