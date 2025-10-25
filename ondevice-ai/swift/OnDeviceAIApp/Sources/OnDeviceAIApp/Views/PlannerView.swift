import SwiftUI

struct PlannerView: View {
    @ObservedObject var viewModel: PlannerViewModel
    @FocusState private var goalFieldFocused: Bool

    private struct GoalTemplate: Identifiable {
        let id = UUID()
        let title: String
        let subtitle: String
        let icon: String
        let prompt: String
    }

    private let templates: [GoalTemplate] = [
        GoalTemplate(title: "Team standup", subtitle: "Summarize updates and blockers", icon: "person.2.wave.2", prompt: "Compile a standup summary from today's meeting notes and highlight blockers."),
        GoalTemplate(title: "Launch checklist", subtitle: "Review QA and docs", icon: "checkmark.seal", prompt: "Create a launch readiness checklist including QA, documentation, and marketing steps."),
        GoalTemplate(title: "Research brief", subtitle: "Gather top resources", icon: "brain.head.profile", prompt: "Research the latest trends in personal AI assistants and draft a 5-point brief."),
        GoalTemplate(title: "Inbox triage", subtitle: "Group and prioritize email", icon: "envelope.open", prompt: "Plan how to triage the inbox by grouping related emails and suggesting next actions."),
        GoalTemplate(title: "Sprint retro", subtitle: "Capture wins and deltas", icon: "chart.line.flattrend.xaxis", prompt: "Summarize sprint wins, issues, and concrete improvements for the next sprint."),
    ]

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

                GlassContainer {
                    VStack(alignment: .leading, spacing: 18) {
                        GlassSectionHeader(title: "Planning preferences", systemImage: "slider.horizontal.3")
                        ViewThatFits {
                            HStack(spacing: 24) {
                                preferenceControls
                            }
                            VStack(alignment: .leading, spacing: 18) {
                                preferenceControls
                            }
                        }
                    }
                }

                if templates.isEmpty == false {
                    GlassContainer {
                        VStack(alignment: .leading, spacing: 14) {
                            GlassSectionHeader(title: "Goal templates", systemImage: "sparkles")
                            ScrollView(.horizontal, showsIndicators: false) {
                                HStack(spacing: 16) {
                                    ForEach(templates) { template in
                                        Button {
                                            viewModel.goal = template.prompt
                                            goalFieldFocused = false
                                        } label: {
                                            VStack(alignment: .leading, spacing: 10) {
                                                HStack {
                                                    Image(systemName: template.icon)
                                                        .font(.system(size: 22, weight: .semibold))
                                                    Spacer()
                                                    Image(systemName: "arrow.right")
                                                        .font(.caption)
                                                        .foregroundColor(.white.opacity(0.7))
                                                }
                                                Text(template.title)
                                                    .font(.system(.headline, design: .rounded))
                                                    .foregroundColor(.white)
                                                Text(template.subtitle)
                                                    .font(.system(.caption, design: .rounded))
                                                    .foregroundColor(.white.opacity(0.7))
                                                    .multilineTextAlignment(.leading)
                                            }
                                            .padding(16)
                                            .frame(width: 220, alignment: .leading)
                                            .background(Color.white.opacity(0.06), in: RoundedRectangle(cornerRadius: 20, style: .continuous))
                                        }
                                        .buttonStyle(.plain)
                                    }
                                }
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

    private var preferenceControls: some View {
        Group {
            VStack(alignment: .leading, spacing: 10) {
                Label("Temperature", systemImage: "thermometer.medium")
                    .font(.system(.subheadline, design: .rounded))
                    .foregroundColor(.white.opacity(0.75))
                Slider(value: $viewModel.temperature, in: 0...1, step: 0.05)
                Text(String(format: "%.2f", viewModel.temperature))
                    .font(.system(.caption, design: .monospaced))
                    .foregroundColor(.white.opacity(0.65))
            }

            VStack(alignment: .leading, spacing: 10) {
                Label("Max tokens", systemImage: "number")
                    .font(.system(.subheadline, design: .rounded))
                    .foregroundColor(.white.opacity(0.75))
                Slider(value: $viewModel.maxTokens, in: 64...768, step: 32)
                Text("\(Int(viewModel.maxTokens)) tokens")
                    .font(.system(.caption, design: .monospaced))
                    .foregroundColor(.white.opacity(0.65))
            }

            Toggle(isOn: $viewModel.includeKnowledge) {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Use indexed knowledge")
                        .font(.system(.body, design: .rounded))
                    Text("Fetch vectors to ground your plan.")
                        .font(.system(.caption, design: .rounded))
                        .foregroundColor(.white.opacity(0.68))
                }
            }
            .toggleStyle(.switch)
        }
    }
}
