import Combine
import SwiftUI

@MainActor
final class AppState: ObservableObject {
    let client: AutomationClient

    @Published var plannerViewModel: PlannerViewModel
    @Published var knowledgeViewModel: KnowledgeViewModel
    @Published var automationDashboard: AutomationDashboardViewModel
    @Published var pluginsViewModel: PluginsViewModel
    @Published var settingsViewModel: SettingsViewModel
    @Published var connectionStatus: ConnectionStatus
    @Published var backendLaunchState: BackendProcessManager.LaunchState

    init(client: AutomationClient = AutomationClient()) {
        self.client = client
        self.plannerViewModel = PlannerViewModel(client: client)
        self.knowledgeViewModel = KnowledgeViewModel(client: client)
        self.automationDashboard = AutomationDashboardViewModel(client: client)
        self.pluginsViewModel = PluginsViewModel(client: client)
        self.settingsViewModel = SettingsViewModel(client: client)
        self.connectionStatus = .checking
        self.backendLaunchState = .stopped
        self.settingsViewModel.onProfileUpdated = { [weak self] in
            Task { await self?.automationDashboard.refresh() }
        }
        BackendProcessManager.shared.$launchState
            .receive(on: RunLoop.main)
            .assign(to: &$backendLaunchState)
        Task { [weak self] in
            guard let self else { return }
            _ = await BackendProcessManager.shared.ensureBackendRunning(client: client)
            await self.refreshConnectionStatus(force: true)
        }
    }

    func refreshAll() {
        Task {
            await settingsViewModel.refresh()
            await knowledgeViewModel.refresh()
            await automationDashboard.refresh()
            await pluginsViewModel.refresh()
            await refreshConnectionStatus(force: false)
        }
    }

    func refreshConnectionStatus(force: Bool) async {
        if force || connectionStatus.isChecking == false {
            connectionStatus = .checking
        }
        do {
            let health = try await client.health()
            connectionStatus = ConnectionStatus(phase: .connected(health), lastUpdated: Date())
        } catch {
            let _ = await BackendProcessManager.shared.ensureBackendRunning(client: client)
            do {
                let health = try await client.health()
                connectionStatus = ConnectionStatus(phase: .connected(health), lastUpdated: Date())
            } catch {
                let message = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
                connectionStatus = ConnectionStatus(phase: .failed(message), lastUpdated: Date())
            }
        }
    }
}
