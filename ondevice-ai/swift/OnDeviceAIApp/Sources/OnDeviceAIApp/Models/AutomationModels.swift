import Foundation

struct PlanAction: Identifiable, Codable, Hashable {
    let id: UUID
    let name: String
    let payload: String
    let sensitive: Bool
    let previewRequired: Bool

    enum CodingKeys: String, CodingKey {
        case name
        case payload
        case sensitive
        case previewRequired = "preview_required"
    }

    init(id: UUID = UUID(), name: String, payload: String, sensitive: Bool, previewRequired: Bool) {
        self.id = id
        self.name = name
        self.payload = payload
        self.sensitive = sensitive
        self.previewRequired = previewRequired
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.id = UUID()
        self.name = try container.decodeIfPresent(String.self, forKey: .name) ?? ""
        if let payloadString = try container.decodeIfPresent(String.self, forKey: .payload) {
            self.payload = payloadString
        } else if let payloadDict = try? container.decodeIfPresent([String: String].self, forKey: .payload) {
            self.payload = (try? String(data: JSONSerialization.data(withJSONObject: payloadDict, options: [.prettyPrinted]), encoding: .utf8)) ?? ""
        } else {
            self.payload = ""
        }
        self.sensitive = try container.decodeIfPresent(Bool.self, forKey: .sensitive) ?? false
        self.previewRequired = try container.decodeIfPresent(Bool.self, forKey: .previewRequired) ?? false
    }
}

struct QueryHit: Identifiable, Codable, Hashable {
    let id: UUID
    let docID: String
    let score: Double
    let text: String
    let preview: String

    enum CodingKeys: String, CodingKey {
        case docID = "doc_id"
        case score
        case text
        case preview
    }

    init(docID: String, score: Double, text: String, preview: String) {
        self.id = UUID()
        self.docID = docID
        self.score = score
        self.text = text
        self.preview = preview
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.id = UUID()
        self.docID = try container.decodeIfPresent(String.self, forKey: .docID) ?? ""
        self.score = try container.decodeIfPresent(Double.self, forKey: .score) ?? 0
        self.text = try container.decodeIfPresent(String.self, forKey: .text) ?? ""
        self.preview = try container.decodeIfPresent(String.self, forKey: .preview) ?? ""
    }
}

struct KnowledgeDocument: Identifiable, Codable, Hashable {
    let id: String
    let source: String
    let timestamp: Date
    let preview: String

    enum CodingKeys: String, CodingKey {
        case id
        case source
        case timestamp = "ts"
        case preview
    }

    init(id: String, source: String, timestamp: Date, preview: String) {
        self.id = id
        self.source = source
        self.timestamp = timestamp
        self.preview = preview
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.id = try container.decode(String.self, forKey: .id)
        self.source = try container.decodeIfPresent(String.self, forKey: .source) ?? "unknown"
        let ts = try container.decodeIfPresent(TimeInterval.self, forKey: .timestamp) ?? 0
        self.timestamp = Date(timeIntervalSince1970: ts)
        self.preview = try container.decodeIfPresent(String.self, forKey: .preview) ?? ""
    }
}

struct KnowledgeDocumentDetail: Identifiable, Hashable {
    let id: String
    let source: String
    let timestamp: Date
    let text: String
}

struct AutomationLogEvent: Identifiable, Codable, Hashable {
    let id: UUID
    let type: String
    let payload: [String: String]
    let ts: Date

    init(type: String, payload: [String: String], ts: Date) {
        self.id = UUID()
        self.type = type
        self.payload = payload
        self.ts = ts
    }

    enum CodingKeys: String, CodingKey {
        case type
        case payload
        case ts
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.id = UUID()
        self.type = try container.decodeIfPresent(String.self, forKey: .type) ?? ""

        if let directPayload = try? container.decodeIfPresent([String: String].self, forKey: .payload) {
            self.payload = directPayload
        } else if let genericPayload = try? container.decodeIfPresent([String: AnyCodable].self, forKey: .payload) {
            var converted: [String: String] = [:]
            for (key, value) in genericPayload {
                converted[key] = value.description
            }
            self.payload = converted
        } else {
            self.payload = [:]
        }

        let tsValue = try container.decodeIfPresent(TimeInterval.self, forKey: .ts) ?? 0
        self.ts = Date(timeIntervalSince1970: tsValue)
    }
}

struct AutomationLogEventPayload {
    let type: String
    let payload: [String: String]
    let timestamp: Date
}

struct PluginManifestView: Identifiable, Hashable, Decodable {
    private let manifestID: String
    let name: String
    let version: String
    let scopes: [String]
    let api: String
    let signature: String
    let minCoreVersion: String
    let capabilities: [String]

    enum CodingKeys: String, CodingKey {
        case id
        case name
        case version
        case scopes
        case api
        case signature
        case minCoreVersion = "min_core_version"
        case capabilities
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.manifestID = try container.decodeIfPresent(String.self, forKey: .id) ?? UUID().uuidString
        self.name = try container.decodeIfPresent(String.self, forKey: .name) ?? "Unnamed Plugin"
        self.version = try container.decodeIfPresent(String.self, forKey: .version) ?? "0.0.0"
        self.scopes = try container.decodeIfPresent([String].self, forKey: .scopes) ?? []
        self.api = try container.decodeIfPresent(String.self, forKey: .api) ?? ""
        self.signature = try container.decodeIfPresent(String.self, forKey: .signature) ?? ""
        self.minCoreVersion = try container.decodeIfPresent(String.self, forKey: .minCoreVersion) ?? ""
        self.capabilities = try container.decodeIfPresent([String].self, forKey: .capabilities) ?? []
    }

    var id: String { manifestID }

    var signatureValid: Bool {
        signature.lowercased().hasPrefix("ed25519:")
    }
}

struct AutomationHealth: Codable {
    let ok: Bool
    let documentCount: Int
}

struct AutomationPermissions: Codable, Equatable {
    var fileAccess: Bool
    var calendarAccess: Bool
    var mailAccess: Bool

    static let defaults = AutomationPermissions(fileAccess: false, calendarAccess: false, mailAccess: false)
}

struct ModelRequirement: Codable, Hashable {
    let environment: [String]?
}

struct ModelProfile: Identifiable, Codable, Hashable {
    let id: String
    let label: String
    let backend: String
    let description: String
    let capabilities: [String]
    let requires: ModelRequirement?
    let settings: [String: [String: String]]?
    let selected: Bool?

    var isSelected: Bool { selected ?? false }
}

struct ModelConfiguration: Codable, Hashable {
    let profile: String
    let backend: String
    let runtimeURL: String?
    let profiles: [ModelProfile]

    enum CodingKeys: String, CodingKey {
        case profile
        case backend
        case runtimeURL = "runtime_url"
        case profiles
    }
}

struct PlanParameters: Codable, Hashable {
    let temperature: Double
    let maxTokens: Int

    enum CodingKeys: String, CodingKey {
        case temperature
        case maxTokens = "max_tokens"
    }
}
