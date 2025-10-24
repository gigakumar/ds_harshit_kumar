import SwiftUI

@main
struct OnDeviceAIApp: App {
    @StateObject private var appState = AppState()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(appState)
                .frame(minWidth: 1024, minHeight: 680)
        }
        .defaultSize(width: 1180, height: 760)
        Settings {
            SettingsView()
                .environmentObject(appState)
                .frame(width: 520, height: 420)
        }
    }
}
