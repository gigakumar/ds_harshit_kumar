import SwiftUI

@main
struct OnDeviceAIApp: App {
    @StateObject private var appState = AppState()
    @Environment(\.scenePhase) private var scenePhase

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(appState)
                .frame(minWidth: 1024, minHeight: 680)
        }
        .defaultSize(width: 1180, height: 760)
        .onChange(of: scenePhase) { _, phase in
            guard phase == .background else { return }
            Task { await BackendProcessManager.shared.stopBackend() }
        }
        Settings {
            SettingsView()
                .environmentObject(appState)
                .frame(width: 520, height: 420)
        }
    }
}
