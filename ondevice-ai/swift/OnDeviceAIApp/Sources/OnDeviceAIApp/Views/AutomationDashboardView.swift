import SwiftUI

struct AutomationDashboardView: View {
    @ObservedObject var viewModel: AutomationDashboardViewModel

    private let gridColumns = [
        GridItem(.flexible(minimum: 220), spacing: 20),
        GridItem(.flexible(minimum: 220), spacing: 20)
    ]

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 28) {
                quickActions
                logSection
            }
            .padding(.bottom, 48)
        }
        .scrollIndicators(.hidden)
        .foregroundColor(.white)
        .task {
            await viewModel.refresh()
        }
    }

    private var quickActions: some View {
        GlassContainer {
            VStack(alignment: .leading, spacing: 20) {
                HStack {
                    GlassSectionHeader(title: "Quick automations", systemImage: "bolt.fill")
                    Spacer()
                    if viewModel.isRunningQuickAction {
                        ProgressView()
                            .progressViewStyle(.circular)
                            .tint(.white)
                    }
                }

                LazyVGrid(columns: gridColumns, spacing: 20) {
                    ForEach(viewModel.quickActions) { action in
                        Button {
                            viewModel.trigger(action: action)
                        } label: {
                            VStack(alignment: .leading, spacing: 10) {
                                HStack {
                                    Image(systemName: action.icon)
                                        .font(.system(size: 24, weight: .semibold))
                                        .symbolRenderingMode(.palette)
                                        .foregroundStyle(.white, Color.white.opacity(0.4))
                                    Spacer()
                                    Image(systemName: "arrow.forward.circle.fill")
                                        .font(.title3)
                                        .foregroundColor(.white.opacity(0.75))
                                }
                                Text(action.title)
                                    .font(.system(.title3, design: .rounded, weight: .semibold))
                                    .foregroundColor(.white)
                                Text(action.subtitle)
                                    .font(.system(.footnote, design: .rounded))
                                    .foregroundColor(.white.opacity(0.75))
                                    .multilineTextAlignment(.leading)
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(18)
                            .background(Color.white.opacity(0.05), in: RoundedRectangle(cornerRadius: 24, style: .continuous))
                            .overlay(
                                RoundedRectangle(cornerRadius: 24, style: .continuous)
                                    .stroke(Color.white.opacity(0.12), lineWidth: 1)
                            )
                        }
                        .buttonStyle(.plain)
                        .disabled(viewModel.isRunningQuickAction)
                    }
                }

                if let status = viewModel.statusMessage {
                    Text(status)
                        .font(.footnote)
                        .foregroundColor(.white.opacity(0.8))
                }
            }
        }
    }

    private var logSection: some View {
        GlassContainer {
            VStack(alignment: .leading, spacing: 18) {
                GlassSectionHeader(title: "Automation log", systemImage: "clock.arrow.circlepath")
                if viewModel.automationLog.isEmpty {
                    Text("No automation events captured yet.")
                        .font(.footnote)
                        .foregroundColor(.white.opacity(0.75))
                } else {
                    ForEach(viewModel.automationLog) { event in
                        VStack(alignment: .leading, spacing: 6) {
                            HStack {
                                Text(event.type.capitalized)
                                    .font(.system(.headline, design: .rounded))
                                Spacer()
                                Text(event.ts, style: .time)
                                    .font(.caption)
                                    .foregroundColor(.white.opacity(0.58))
                            }
                            if event.payload.isEmpty == false {
                                Text(event.payload.map { "\($0.key): \($0.value)" }.sorted().joined(separator: ", "))
                                    .font(.system(.caption, design: .monospaced))
                                    .foregroundColor(.white.opacity(0.78))
                                    .lineLimit(3)
                            }
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(14)
                        .background(Color.white.opacity(0.05), in: RoundedRectangle(cornerRadius: 18, style: .continuous))
                    }
                }
            }
        }
    }
}
