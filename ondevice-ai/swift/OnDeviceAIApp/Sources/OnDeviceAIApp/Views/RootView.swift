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
    @Environment(\.scenePhase) private var scenePhase
    @State private var selection: AppSection? = .planner

    var body: some View {
        GlassBackground {
            NavigationSplitView {
                sidebar
            } detail: {
                detail
                    .padding(.horizontal, 32)
                    .padding(.top, 16)
                    .padding(.bottom, 28)
                    .safeAreaInset(edge: .top, spacing: 0) {
                        ConnectionStatusHero(
                            status: appState.connectionStatus,
                            backendState: appState.backendLaunchState,
                            refreshAction: {
                                Task { await appState.refreshConnectionStatus(force: true) }
                            },
                            openSettings: {
                                selection = .settings
                            }
                        )
                        .padding(.horizontal, 32)
                        .padding(.top, 24)
                    }
            }
            .navigationSplitViewStyle(.balanced)
        }
        .task {
            await reload()
        }
        .onChange(of: scenePhase) { _, phase in
            guard phase == .active else { return }
            Task { await appState.refreshConnectionStatus(force: true) }
        }
    }

    private var sidebar: some View {
        List(AppSection.allCases, selection: $selection) { section in
            sidebarRow(for: section)
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
        await appState.settingsViewModel.refresh()
        await appState.knowledgeViewModel.refresh()
        await appState.pluginsViewModel.refresh()
        await appState.automationDashboard.refresh()
        await appState.refreshConnectionStatus(force: false)
    }

    @ViewBuilder
    private func sidebarRow(for section: AppSection) -> some View {
        HStack(spacing: 14) {
            Label(section.title, systemImage: section.icon)
                .labelStyle(.titleAndIcon)
                .foregroundStyle(.white)
            Spacer(minLength: 8)
            if section == .knowledge, let documents = appState.connectionStatus.health?.documentCount {
                sidebarBadge(text: "\(documents)")
            }
            if section == .automation {
                statusDot
            }
        }
        .padding(.vertical, 8)
        .contentShape(Rectangle())
    }

    private func sidebarBadge(text: String) -> some View {
        Text(text)
            .font(.system(.caption, design: .rounded, weight: .medium))
            .foregroundColor(.white)
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(
                Capsule(style: .continuous)
                    .fill(Color.white.opacity(0.18))
            )
    }

    private var statusDot: some View {
        let color: Color
        if appState.connectionStatus.isChecking {
            color = .blue.opacity(0.9)
        } else if appState.connectionStatus.isConnected {
            color = .green.opacity(0.85)
        } else {
            color = .red.opacity(0.85)
        }
        return Circle()
            .fill(color)
            .frame(width: 10, height: 10)
            .overlay(
                Circle()
                    .stroke(Color.white.opacity(0.4), lineWidth: 1)
            )
    }
}
