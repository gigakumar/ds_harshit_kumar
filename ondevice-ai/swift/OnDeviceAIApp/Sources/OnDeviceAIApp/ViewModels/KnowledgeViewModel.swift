import Foundation
import SwiftUI

@MainActor
final class KnowledgeViewModel: ObservableObject {
    @Published var documents: [KnowledgeDocument] = []
    @Published var highlightedDoc: KnowledgeDocumentDetail?
    @Published var searchTerm: String = ""
    @Published var semanticHits: [QueryHit] = []
    @Published var errorMessage: String?
    @Published var isLoading: Bool = false
    @Published var newDocumentText: String = ""
    @Published var newDocumentSource: String = "sandbox"
    @Published var isIndexing: Bool = false

    private let client: AutomationClient

    init(client: AutomationClient) {
        self.client = client
    }

    func refresh() async {
        isLoading = true
        defer { isLoading = false }
        do {
            documents = try await client.listDocuments()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func performSearch() {
        let trimmed = searchTerm.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmed.isEmpty == false else {
            semanticHits = []
            return
        }
        Task {
            do {
                semanticHits = try await client.query(trimmed, limit: 5)
            } catch {
                errorMessage = error.localizedDescription
            }
        }
    }

    func loadDocumentDetail(id: String) {
        Task {
            do {
                highlightedDoc = try await client.fetchDocument(id: id)
            } catch {
                errorMessage = error.localizedDescription
            }
        }
    }

    func indexSnippet() {
        let trimmed = newDocumentText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmed.isEmpty == false else {
            errorMessage = "Enter some text before indexing."
            return
        }
        isIndexing = true
        Task {
            do {
                _ = try await client.index(text: trimmed, source: newDocumentSource.isEmpty ? "manual" : newDocumentSource)
                await MainActor {
                    newDocumentText = ""
                    errorMessage = nil
                }
                await refresh()
            } catch {
                await MainActor {
                    errorMessage = error.localizedDescription
                }
            }
            await MainActor {
                isIndexing = false
            }
        }
    }
}
