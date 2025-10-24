import SwiftUI

struct PluginsView: View {
    @ObservedObject var viewModel: PluginsViewModel

    private let columns = [
        GridItem(.flexible(minimum: 220), spacing: 20),
        GridItem(.flexible(minimum: 220), spacing: 20)
    ]

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 28) {
                pluginSummary
                pluginGrid
            }
            .padding(.bottom, 48)
        }
        .scrollIndicators(.hidden)
        .foregroundColor(.white)
        .task {
            if viewModel.plugins.isEmpty {
                await viewModel.refresh()
            }
        }
    }

    private var pluginSummary: some View {
        GlassContainer {
            VStack(alignment: .leading, spacing: 16) {
                GlassSectionHeader(title: "Installed plugins", systemImage: "puzzlepiece")
                if let error = viewModel.errorMessage {
                    HStack(spacing: 10) {
                        Image(systemName: "exclamationmark.triangle.fill")
                            .foregroundColor(.yellow)
                        Text(error)
                            .font(.footnote)
                            .foregroundColor(.white.opacity(0.85))
                    }
                }
                Text(summaryText)
                    .font(.system(.callout, design: .rounded))
                    .foregroundColor(.white.opacity(0.82))
            }
        }
    }

    private var pluginGrid: some View {
        GlassContainer {
            VStack(alignment: .leading, spacing: 18) {
                if viewModel.plugins.isEmpty {
                    Text("No plugins registered yet. Drop manifest bundles into the backend plugins folder and refresh.")
                        .font(.footnote)
                        .foregroundColor(.white.opacity(0.75))
                        .frame(maxWidth: .infinity, alignment: .leading)
                } else {
                    LazyVGrid(columns: columns, spacing: 18) {
                        ForEach(viewModel.plugins) { plugin in
                            pluginCard(plugin)
                        }
                    }
                }
            }
        }
    }

    private func pluginCard(_ plugin: PluginManifestView) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 6) {
                    Text(plugin.name)
                        .font(.system(.title3, design: .rounded))
                        .fontWeight(.semibold)
                    Text("v\(plugin.version)")
                        .font(.system(.footnote, design: .rounded))
                        .foregroundColor(.white.opacity(0.68))
                }
                Spacer()
                Image(systemName: plugin.signatureValid ? "checkmark.seal.fill" : "exclamationmark.triangle.fill")
                    .font(.title3)
                    .foregroundStyle(plugin.signatureValid ? Color.green.opacity(0.8) : Color.orange.opacity(0.9))
            }

            if plugin.scopes.isEmpty == false {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 8) {
                        ForEach(plugin.scopes, id: \.self) { scope in
                            GlassTag(text: scope.uppercased(), tint: Color.blue.opacity(0.35))
                        }
                    }
                }
            }

            VStack(alignment: .leading, spacing: 8) {
                Text("API Endpoint")
                    .font(.system(.caption, design: .rounded))
                    .foregroundColor(.white.opacity(0.6))
                Text(plugin.api)
                    .font(.system(.footnote, design: .monospaced))
                    .foregroundColor(.white.opacity(0.86))
                    .lineLimit(2)
            }

            if plugin.capabilities.isEmpty == false {
                VStack(alignment: .leading, spacing: 6) {
                    Text("Capabilities")
                        .font(.system(.caption, design: .rounded))
                        .foregroundColor(.white.opacity(0.6))
                    ForEach(plugin.capabilities, id: \.self) { capability in
                        Text("• \(capability)")
                            .font(.system(.footnote, design: .rounded))
                            .foregroundColor(.white.opacity(0.82))
                    }
                }
            }

            Text("Requires core \(plugin.minCoreVersion)")
                .font(.system(.caption2, design: .rounded))
                .foregroundColor(.white.opacity(0.6))
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(18)
        .background(Color.white.opacity(0.05), in: RoundedRectangle(cornerRadius: 24, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 24, style: .continuous)
                .stroke(Color.white.opacity(0.12), lineWidth: 1)
        )
    }

    private var summaryText: String {
        if viewModel.plugins.isEmpty {
            return "Connect the automation daemon to load plugin manifests."
        }
        let count = viewModel.plugins.count
        return count == 1 ? "1 plugin ready to use." : "\(count) plugins ready to use."
    }
}
