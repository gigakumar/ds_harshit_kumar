import SwiftUI

struct SettingsView: View {
    @EnvironmentObject private var appState: AppState

    var body: some View {
        GlassBackground {
            SettingsDockView(viewModel: appState.settingsViewModel)
                .padding(24)
        }
    }
}
