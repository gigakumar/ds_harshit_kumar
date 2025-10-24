import SwiftUI

struct PlannerView: View {
    @ObservedObject var viewModel: PlannerViewModel
    @FocusState private var goalFieldFocused: Bool

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 28) {
                GlassContainer {
                    VStack(alignment: .leading, spacing: 18) {
                        GlassSectionHeader(title: "Automation Goal", systemImage: "target")
                        TextField("Describe what you need to accomplish", text: $viewModel.goal, axis: .vertical)
                            .textFieldStyle(.plain)
                            .focused($goalFieldFocused)
                            .padding(14)
                            .background(.white.opacity(0.08), in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                            .foregroundColor(.white)

                        HStack(spacing: 12) {
                            Button(action: viewModel.runPlanning) {
                                Label("Generate Plan", systemImage: "sparkles")
                                    .font(.system(.headline, design: .rounded))
                            }
                            .buttonStyle(GlassToolbarButtonStyle())
                            .disabled(viewModel.isPlanning)

                            if viewModel.isPlanning {
                                ProgressView()
                                    .progressViewStyle(.circular)
                                    .tint(.white)
                            }

                            Spacer()

                            if let executionStatus = viewModel.executionStatus {
                                Text(executionStatus)
                                    .font(.footnote)
                                    .foregroundStyle(.white.opacity(0.75))
                            }
                        }
                    }
                }

                if let planError = viewModel.planError {
                    GlassContainer {
                        HStack(spacing: 12) {
                            Image(systemName: "exclamationmark.triangle.fill")
                                .foregroundColor(.yellow)
                            Text(planError)
                                .font(.footnote)
                                .foregroundColor(.white.opacity(0.9))
                        }
                    }
                }

                if viewModel.actions.isEmpty == false {
                    GlassContainer {
                        VStack(alignment: .leading, spacing: 16) {
                            GlassSectionHeader(title: "Proposed actions", systemImage: "checkmark.circle")
                            ForEach(viewModel.actions) { action in
                                VStack(alignment: .leading, spacing: 8) {
                                    HStack {
                                        Text(action.name.capitalized)
                                            .font(.system(.headline, design: .rounded))
                                            .foregroundColor(.white)
                                        Spacer()
                                        if action.sensitive {
                                            GlassTag(text: "Sensitive", tint: Color.red.opacity(0.35))
                                        }
                                        if action.previewRequired {
                                            GlassTag(text: "Preview", tint: Color.blue.opacity(0.35))
                                        }
                                    }
                                    if action.payload.isEmpty == false {
                                        Text(action.payload)
                                            .font(.system(.callout, design: .monospaced))
                                            .foregroundColor(.white.opacity(0.85))
                                            .padding(12)
                                            .background(Color.white.opacity(0.06), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                                    }
                                    Button {
                                        viewModel.execute(action: action)
                                    } label: {
                                        Label("Dispatch", systemImage: "paperplane")
                                            .font(.system(.callout, design: .rounded))
                                    }
                                    .buttonStyle(GlassToolbarButtonStyle())
                                }
                                .padding(.vertical, 8)
                                if viewModel.actions.last?.id != action.id {
                                    Divider().blendMode(.plusLighter)
                                }
                            }
                        }
                    }
                }

                if viewModel.contextHits.isEmpty == false {
                    GlassContainer {
                        VStack(alignment: .leading, spacing: 16) {
                            GlassSectionHeader(title: "Knowledge snippets", systemImage: "doc.text.magnifyingglass")
                            ForEach(viewModel.contextHits) { hit in
                                VStack(alignment: .leading, spacing: 6) {
                                    Text(hit.preview.isEmpty ? hit.text : hit.preview)
                                        .font(.system(.callout, design: .rounded))
                                        .foregroundColor(.white.opacity(0.85))
                                    HStack {
                                        GlassTag(text: String(format: "%.2f", hit.score), tint: Color.green.opacity(0.35))
                                        Text(hit.docID)
                                            .font(.caption2)
                                            .foregroundColor(.white.opacity(0.55))
                                    }
                                }
                                .padding(12)
                                .background(Color.white.opacity(0.05), in: RoundedRectangle(cornerRadius: 18, style: .continuous))
                            }
                        }
                    }
                }
            }
            .padding(.bottom, 40)
        }
        .scrollIndicators(.hidden)
        .foregroundColor(.white)
        .onAppear {
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.6) {
                goalFieldFocused = viewModel.goal.isEmpty
            }
        }
    }
}
