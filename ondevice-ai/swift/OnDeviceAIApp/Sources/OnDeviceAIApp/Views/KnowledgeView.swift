import SwiftUI

struct KnowledgeView: View {
    @ObservedObject var viewModel: KnowledgeViewModel

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 28) {
                addDocumentSection
                searchSection
                documentsSection
                if let detail = viewModel.highlightedDoc {
                    detailSection(detail)
                }
                hitsSection
            }
            .padding(.bottom, 48)
        }
        .scrollIndicators(.hidden)
        .foregroundColor(.white)
    }

    private var addDocumentSection: some View {
        GlassContainer {
            VStack(alignment: .leading, spacing: 16) {
                GlassSectionHeader(title: "Add knowledge", systemImage: "tray.and.arrow.down")
                Text("Drop raw notes or transcripts to seed the knowledge graph without leaving the app.")
                    .font(.system(.callout, design: .rounded))
                    .foregroundColor(.white.opacity(0.75))
                TextEditor(text: $viewModel.newDocumentText)
                    .frame(minHeight: 120)
                    .padding(12)
                    .background(Color.white.opacity(0.08), in: RoundedRectangle(cornerRadius: 18, style: .continuous))
                    .foregroundColor(.white)
                HStack(spacing: 12) {
                    TextField("Source tag", text: $viewModel.newDocumentSource)
                        .textFieldStyle(.plain)
                        .padding(12)
                        .background(Color.white.opacity(0.08), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                        .foregroundColor(.white)
                        .frame(maxWidth: 180)
                    Button {
                        viewModel.indexSnippet()
                    } label: {
                        Label("Index snippet", systemImage: "square.and.arrow.down.on.square")
                            .font(.system(.headline, design: .rounded))
                    }
                    .buttonStyle(GlassToolbarButtonStyle())
                    .disabled(viewModel.isIndexing)

                    if viewModel.isIndexing {
                        ProgressView()
                            .progressViewStyle(.circular)
                            .tint(.white)
                    }

                    Spacer()
                }
            }
        }
    }

    private var searchSection: some View {
        GlassContainer {
            VStack(alignment: .leading, spacing: 14) {
                GlassSectionHeader(title: "Semantic search", systemImage: "magnifyingglass")
                HStack(spacing: 12) {
                    TextField("Search indexed memory", text: $viewModel.searchTerm)
                        .textFieldStyle(.plain)
                        .padding(14)
                        .background(Color.white.opacity(0.08), in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                        .foregroundColor(.white)
                        .onSubmit(viewModel.performSearch)
                        .onChange(of: viewModel.searchTerm) { _, newValue in
                            if newValue.isEmpty {
                                viewModel.performSearch()
                            }
                        }

                    Button(action: viewModel.performSearch) {
                        Label("Search", systemImage: "arrow.forward.circle")
                            .font(.system(.headline, design: .rounded))
                    }
                    .buttonStyle(GlassToolbarButtonStyle())
                }

                if let error = viewModel.errorMessage {
                    HStack(spacing: 10) {
                        Image(systemName: "exclamationmark.triangle.fill")
                            .foregroundColor(.yellow)
                        Text(error)
                            .font(.footnote)
                            .foregroundColor(.white.opacity(0.85))
                    }
                }
            }
        }
    }

    private var documentsSection: some View {
        GlassContainer {
            VStack(alignment: .leading, spacing: 18) {
                GlassSectionHeader(title: "Documents", systemImage: "doc.richtext")
                if viewModel.isLoading {
                    ProgressView()
                        .progressViewStyle(.circular)
                        .tint(.white)
                }
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 220), spacing: 18)], spacing: 18) {
                    ForEach(viewModel.documents) { document in
                        Button {
                            viewModel.loadDocumentDetail(id: document.id)
                        } label: {
                            VStack(alignment: .leading, spacing: 6) {
                                HStack {
                                    Text(document.source.capitalized)
                                        .font(.system(.headline, design: .rounded))
                                    Spacer()
                                    Text(document.timestamp, style: .relative)
                                        .font(.caption)
                                        .foregroundColor(.white.opacity(0.6))
                                }
                                Text(document.preview)
                                    .font(.system(.callout, design: .rounded))
                                    .foregroundColor(.white.opacity(0.86))
                                    .lineLimit(3)
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(16)
                            .background(Color.white.opacity(0.05), in: RoundedRectangle(cornerRadius: 20, style: .continuous))
                        }
                        .buttonStyle(.plain)
                    }
                }
                if viewModel.documents.isEmpty {
                    Text("No documents indexed yet. Use the CLI or automation flows to add context.")
                        .font(.footnote)
                        .foregroundColor(.white.opacity(0.75))
                }
            }
        }
    }

    private func detailSection(_ detail: KnowledgeDocumentDetail) -> some View {
        GlassContainer {
            VStack(alignment: .leading, spacing: 14) {
                GlassSectionHeader(title: "Selected document", systemImage: "doc.text")
                HStack {
                    Text(detail.source.capitalized)
                        .font(.system(.headline, design: .rounded))
                    Spacer()
                    Text(detail.timestamp, style: .relative)
                        .font(.caption)
                        .foregroundColor(.white.opacity(0.6))
                }
                ScrollView {
                    Text(detail.text)
                        .font(.system(.body, design: .rounded))
                        .foregroundColor(.white.opacity(0.9))
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding()
                        .background(Color.white.opacity(0.05), in: RoundedRectangle(cornerRadius: 22, style: .continuous))
                }
                .frame(maxHeight: 260)
            }
        }
    }

    private var hitsSection: some View {
        Group {
            if viewModel.semanticHits.isEmpty == false {
                GlassContainer {
                    VStack(alignment: .leading, spacing: 16) {
                        GlassSectionHeader(title: "Top matches", systemImage: "sparkle")
                        ForEach(viewModel.semanticHits) { hit in
                            VStack(alignment: .leading, spacing: 6) {
                                Text(hit.preview.isEmpty ? hit.text : hit.preview)
                                    .font(.system(.callout, design: .rounded))
                                    .foregroundColor(.white.opacity(0.86))
                                HStack(spacing: 12) {
                                    GlassTag(text: String(format: "%.2f", hit.score), tint: Color.green.opacity(0.35))
                                    Text(hit.docID)
                                        .font(.caption2)
                                        .foregroundColor(.white.opacity(0.55))
                                    Spacer()
                                }
                            }
                            .padding(14)
                            .background(Color.white.opacity(0.05), in: RoundedRectangle(cornerRadius: 18, style: .continuous))
                        }
                    }
                }
            }
        }
    }
}
