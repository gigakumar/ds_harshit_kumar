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
}
