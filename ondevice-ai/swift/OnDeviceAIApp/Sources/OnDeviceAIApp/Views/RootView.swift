import SwiftUI

enum AppSection: String, CaseIterable, Identifiable {
    case planner
    case knowledge
    case automation
    case plugins
    case settings

    var id: String { rawValue }

    var title: String {
        switch self {
        case .planner: return "Planner"
        case .knowledge: return "Knowledge"
        case .automation: return "Automation"
        case .plugins: return "Plugins"
        case .settings: return "Settings"
        }
    }

    var icon: String {
        switch self {
        case .planner: return "list.bullet.rectangle"
        case .knowledge: return "books.vertical"
        case .automation: return "bolt.circle"
        case .plugins: return "puzzlepiece.extension"
        case .settings: return "gearshape"
        }
    }
}

struct RootView: View {
    @EnvironmentObject private var appState: AppState
    @State private var selection: AppSection? = .planner

    var body: some View {
        GlassBackground {
            NavigationSplitView {
                sidebar
            } detail: {
                detail
                    .padding(.horizontal, 32)
                    .padding(.vertical, 28)
            }
            .navigationSplitViewStyle(.balanced)
        }
        .task {
            await reload()
        }
    }

    private var sidebar: some View {
        List(AppSection.allCases, selection: $selection) { section in
            Label(section.title, systemImage: section.icon)
                .padding(.vertical, 6)
                .foregroundStyle(.white)
        }
        .listStyle(.sidebar)
        .scrollContentBackground(.hidden)
        .background(.ultraThinMaterial)
        .frame(minWidth: 220)
    }

    @ViewBuilder
    private var detail: some View {
        switch selection ?? .planner {
        case .planner:
            PlannerView(viewModel: appState.plannerViewModel)
        case .knowledge:
            KnowledgeView(viewModel: appState.knowledgeViewModel)
        case .automation:
            AutomationDashboardView(viewModel: appState.automationDashboard)
        case .plugins:
            PluginsView(viewModel: appState.pluginsViewModel)
        case .settings:
            SettingsDockView(viewModel: appState.settingsViewModel)
        }
    }

    private func reload() async {
        await appState.settingsViewModel.refreshHealth()
        await appState.knowledgeViewModel.refresh()
        await appState.pluginsViewModel.refresh()
        await appState.automationDashboard.refresh()
    }
}
