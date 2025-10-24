import SwiftUI

@MainActor
final class AppState: ObservableObject {
    let client: AutomationClient

    @Published var plannerViewModel: PlannerViewModel
    @Published var knowledgeViewModel: KnowledgeViewModel
    @Published var automationDashboard: AutomationDashboardViewModel
    @Published var pluginsViewModel: PluginsViewModel
    @Published var settingsViewModel: SettingsViewModel

    init(client: AutomationClient = AutomationClient()) {
        self.client = client
        self.plannerViewModel = PlannerViewModel(client: client)
        self.knowledgeViewModel = KnowledgeViewModel(client: client)
        self.automationDashboard = AutomationDashboardViewModel(client: client)
        self.pluginsViewModel = PluginsViewModel(client: client)
        self.settingsViewModel = SettingsViewModel(client: client)
    }

    func refreshAll() {
        Task {
            await settingsViewModel.refreshHealth()
            await knowledgeViewModel.refresh()
            await automationDashboard.refresh()
            await pluginsViewModel.refresh()
        }
    }
}
