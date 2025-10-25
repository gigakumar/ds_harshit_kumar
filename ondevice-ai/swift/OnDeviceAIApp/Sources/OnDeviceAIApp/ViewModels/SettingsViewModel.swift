import Foundation
import SwiftUI

@MainActor
final class SettingsViewModel: ObservableObject {
    @Published var baseURL: String = "http://127.0.0.1:9000"
    @Published var health: AutomationHealth?
    @Published var errorMessage: String?
    @Published var isRefreshing: Bool = false
    @Published var permissions: AutomationPermissions = .defaults
    @Published var modelConfiguration: ModelConfiguration?
    @Published var isUpdatingModel: Bool = false

    var onProfileUpdated: (() -> Void)?

    private let client: AutomationClient

    init(client: AutomationClient) {
        self.client = client
    }

    func applyBaseURL() async -> Bool {
        do {
            try await client.updateBaseURL(baseURL)
            errorMessage = nil
            health = nil
            permissions = .defaults
            modelConfiguration = nil
            return true
        } catch {
            errorMessage = error.localizedDescription
            return false
        }
    }

    func refresh() async {
        isRefreshing = true
        defer { isRefreshing = false }
        do {
            async let healthTask = client.health()
            async let permissionsTask = client.permissions()
            async let modelTask = client.modelConfiguration()
            let (fetchedHealth, fetchedPermissions, fetchedModel) = try await (healthTask, permissionsTask, modelTask)
            health = fetchedHealth
            permissions = fetchedPermissions
            modelConfiguration = fetchedModel
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func updatePermission(_ keyPath: WritableKeyPath<AutomationPermissions, Bool>, to newValue: Bool) {
        let previous = permissions
        permissions[keyPath: keyPath] = newValue
        Task {
            do {
                let updated = try await client.update(permissions: permissions)
                await MainActor {
                    self.permissions = updated
                    self.errorMessage = nil
                }
            } catch {
                await MainActor {
                    self.permissions = previous
                    self.errorMessage = error.localizedDescription
                }
            }
        }
    }

    func selectModel(profileID: String) {
        guard isUpdatingModel == false else { return }
        isUpdatingModel = true
        Task {
            do {
                let updated = try await client.updateModelConfiguration(profileID: profileID)
                await MainActor {
                    self.modelConfiguration = updated
                    self.errorMessage = nil
                    self.onProfileUpdated?()
                }
            } catch {
                await MainActor {
                    self.errorMessage = error.localizedDescription
                }
            }
            await MainActor { self.isUpdatingModel = false }
        }
    }
}
