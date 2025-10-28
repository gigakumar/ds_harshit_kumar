import SwiftUI

struct ControlCenterSheet: View {
    enum Tab: String, CaseIterable, Identifiable {
        case status
        case logs
        case tools

        var id: String { rawValue }

        var title: String {
            switch self {
            case .status: return "Status"
            case .logs: return "Logs"
            case .tools: return "Tools"
            }
        }

        var icon: String {
            switch self {
            case .status: return "waveform.path.ecg"
            case .logs: return "clock.arrow.circlepath"
            case .tools: return "wrench.and.screwdriver"
            }
        }
    }

    @EnvironmentObject private var appState: AppState
    @Environment(\.themeDescriptor) private var theme
    @ObservedObject var dashboardViewModel: AutomationDashboardViewModel
    let openSettings: () -> Void

    @State private var selectedTab: Tab

    init(selectedTab: Tab, dashboardViewModel: AutomationDashboardViewModel, openSettings: @escaping () -> Void) {
        _selectedTab = State(initialValue: selectedTab)
        self.dashboardViewModel = dashboardViewModel
        self.openSettings = openSettings
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            Capsule()
                .fill(theme.secondaryText.opacity(0.35))
                .frame(width: 42, height: 5)
                .frame(maxWidth: .infinity)
                .padding(.top, 4)

            Picker("Focus", selection: $selectedTab) {
                ForEach(Tab.allCases) { tab in
                    Label(tab.title, systemImage: tab.icon)
                        .tag(tab)
                }
            }
            .pickerStyle(.segmented)

            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    switch selectedTab {
                    case .status:
                        statusView
                    case .logs:
                        logsView
                    case .tools:
                        toolsView
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .padding(24)
        .frame(minWidth: 560, minHeight: 480)
        .task {
            await ensureData(for: selectedTab)
        }
        .onChange(of: selectedTab) { _, tab in
            Task { @MainActor in
                await ensureData(for: tab)
            }
        }
    }

    @MainActor
    private func ensureData(for tab: Tab) async {
        switch tab {
        case .status:
            await appState.refreshConnectionStatus(force: true)
        case .logs:
            await dashboardViewModel.refreshLogsOnly()
        case .tools:
            break
        }
    }

    private var statusView: some View {
        VStack(alignment: .leading, spacing: 16) {
            GlassSectionHeader(title: "System status", systemImage: "waveform")
            ConnectionStatusHero(
                status: appState.connectionStatus,
                backendState: appState.backendLaunchState,
                refreshAction: {
                    Task { await appState.refreshConnectionStatus(force: true) }
                },
                openSettings: openSettings
            )
        }
    }

    private var logsView: some View {
        VStack(alignment: .leading, spacing: 16) {
            GlassSectionHeader(title: "Automation log", systemImage: "clock.arrow.circlepath")
            AutomationLogListView(events: dashboardViewModel.automationLog)
        }
    }

    private var toolsView: some View {
        VStack(alignment: .leading, spacing: 18) {
            GlassSectionHeader(title: "Quick tools", systemImage: "wrench.and.screwdriver")

            GlassContainer {
                VStack(alignment: .leading, spacing: 14) {
                    Text("Themes")
                        .font(.system(.subheadline, design: .rounded, weight: .medium))
                        .foregroundColor(theme.secondaryText)
                    HStack(spacing: 12) {
                        ForEach(ThemePreference.allCases) { preference in
                            Button {
                                appState.applyTheme(preference)
                            } label: {
                                HStack(spacing: 8) {
                                    Image(systemName: preference.iconName)
                                    Text(preference.title)
                                }
                                .padding(.vertical, 8)
                                .padding(.horizontal, 14)
                                .background(theme.quickActionBackground, in: Capsule())
                                .overlay(
                                    Capsule().stroke(preference == appState.themePreference ? theme.accent.opacity(0.6) : theme.cardStroke, lineWidth: preference == appState.themePreference ? 2 : 1)
                                )
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }
            }

            GlassContainer {
                VStack(alignment: .leading, spacing: 14) {
                    Text("Maintenance")
                        .font(.system(.subheadline, design: .rounded, weight: .medium))
                        .foregroundColor(theme.secondaryText)
                    HStack(spacing: 12) {
                        Button {
                            Task { await appState.refreshAll() }
                        } label: {
                            Label("Refresh", systemImage: "arrow.clockwise")
                        }
                        .buttonStyle(GlassToolbarButtonStyle())

                        Button {
                            openSettings()
                        } label: {
                            Label("Settings", systemImage: "gearshape")
                        }
                        .buttonStyle(GlassToolbarButtonStyle())

                        Spacer()
                    }
                }
            }
        }
    }
}
