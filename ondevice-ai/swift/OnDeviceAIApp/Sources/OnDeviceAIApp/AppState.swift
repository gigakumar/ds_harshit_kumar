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
    @Published var themePreference: ThemePreference
    @Published private(set) var themeDescriptor: ThemeDescriptor
    @Published private(set) var preferences: UserPreferences

    private let defaults = UserDefaults.standard
    private static let themePreferenceKey = "ondevice.themePreference"
    private static let preferencesKey = "ondevice.userPreferences"
    private var systemColorScheme: ColorScheme = .dark

    init(client: AutomationClient = AutomationClient()) {
        self.client = client
        self.plannerViewModel = PlannerViewModel(client: client)
        self.knowledgeViewModel = KnowledgeViewModel(client: client)
        self.automationDashboard = AutomationDashboardViewModel(client: client)
        self.pluginsViewModel = PluginsViewModel(client: client)
        self.settingsViewModel = SettingsViewModel(client: client)
        self.connectionStatus = .checking
        self.backendLaunchState = .stopped
    self.themePreference = Self.loadThemePreference(from: UserDefaults.standard)
    self.preferences = Self.loadUserPreferences(from: UserDefaults.standard)
        self.themeDescriptor = ThemeDescriptor.midnight
        self.themeDescriptor = descriptor(for: themePreference, scheme: systemColorScheme)
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

    private static func loadThemePreference(from defaults: UserDefaults) -> ThemePreference {
        if let stored = defaults.string(forKey: themePreferenceKey), let preference = ThemePreference(rawValue: stored) {
            return preference
        }
        return .system
    }

    private static func loadUserPreferences(from defaults: UserDefaults) -> UserPreferences {
        guard let data = defaults.data(forKey: preferencesKey) else { return .defaults }
        let decoder = JSONDecoder()
        if let preferences = try? decoder.decode(UserPreferences.self, from: data) {
            return preferences
        }
        return .defaults
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

    func applyTheme(_ preference: ThemePreference, colorScheme: ColorScheme? = nil) {
        themePreference = preference
    defaults.set(preference.rawValue, forKey: Self.themePreferenceKey)
        let scheme = colorScheme ?? systemColorScheme
        themeDescriptor = descriptor(for: preference, scheme: scheme)
    }

    func updateSystemColorScheme(_ scheme: ColorScheme) {
        systemColorScheme = scheme
        if themePreference == .system {
            themeDescriptor = descriptor(for: themePreference, scheme: scheme)
        }
    }

    func descriptor(for colorScheme: ColorScheme) -> ThemeDescriptor {
        descriptor(for: themePreference, scheme: colorScheme)
    }

    private func descriptor(for preference: ThemePreference, scheme: ColorScheme) -> ThemeDescriptor {
        switch preference {
        case .system:
            return scheme == .light ? .lightBlue : .midnight
        case .midnight:
            return .midnight
        case .lightBlue:
            return .lightBlue
        case .sunset:
            return .sunset
        }
    }

    func updatePreferences(_ transform: (inout UserPreferences) -> Void) {
        var updated = preferences
        transform(&updated)
        preferences = updated
        persistPreferences(updated)
    }

    private func persistPreferences(_ preferences: UserPreferences) {
        let encoder = JSONEncoder()
        if let data = try? encoder.encode(preferences) {
            defaults.set(data, forKey: Self.preferencesKey)
        }
    }
}
