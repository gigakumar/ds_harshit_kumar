import Foundation

enum AutomationClientError: LocalizedError {
    case invalidURL
    case requestFailed(status: Int)
    case decodingFailed
    case daemonUnavailable

    var errorDescription: String? {
        switch self {
        case .invalidURL:
            return "The automation daemon URL is invalid."
        case let .requestFailed(status):
            return "Automation daemon responded with status code \(status)."
        case .decodingFailed:
            return "Failed to decode automation daemon response."
        case .daemonUnavailable:
            return "Automation daemon is not reachable."
        }
    }
}

actor AutomationClient {
    private var baseURL: URL
    private let session: URLSession
    private let decoder: JSONDecoder
    private let encoder: JSONEncoder
    private var prefersAPINamespace: Bool = false

    init(baseURL: URL = URL(string: "http://127.0.0.1:9000")!, session: URLSession = .shared) {
        self.baseURL = baseURL
        self.session = session

        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .secondsSince1970
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        self.decoder = decoder

        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .secondsSince1970
        encoder.keyEncodingStrategy = .convertToSnakeCase
        self.encoder = encoder
    }

    func updateBaseURL(_ string: String) throws {
        guard let url = URL(string: string) else {
            throw AutomationClientError.invalidURL
        }
        baseURL = url
        prefersAPINamespace = false
    }

    // MARK: - Networking helpers

    private func makeURL(_ path: String) throws -> URL {
        guard let url = URL(string: path, relativeTo: baseURL) else {
            throw AutomationClientError.invalidURL
        }
        return url
    }

    private func dataRequest(_ path: String, method: String = "GET", body: Data? = nil) async throws -> Data {
        let normalizedPath = normalize(path)
        let primaryPath = prefersAPINamespace ? apiPrefixed(normalizedPath) : normalizedPath
        do {
            return try await performRequest(primaryPath, method: method, body: body)
        } catch AutomationClientError.requestFailed(status: 404) {
            let fallbackPath = prefersAPINamespace ? normalizedPath : apiPrefixed(normalizedPath)
            guard fallbackPath != primaryPath else { throw AutomationClientError.requestFailed(status: 404) }
            let data = try await performRequest(fallbackPath, method: method, body: body)
            prefersAPINamespace.toggle()
            return data
        }
    }

    private func performRequest(_ path: String, method: String, body: Data?) async throws -> Data {
        let url = try makeURL(path)
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.timeoutInterval = 25
        if let body {
            request.httpBody = body
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }

        do {
            let (data, response) = try await session.data(for: request)
            guard let httpResponse = response as? HTTPURLResponse else {
                throw AutomationClientError.daemonUnavailable
            }
            guard (200..<300).contains(httpResponse.statusCode) else {
                throw AutomationClientError.requestFailed(status: httpResponse.statusCode)
            }
            return data
        } catch let error as AutomationClientError {
            throw error
        } catch {
            throw AutomationClientError.daemonUnavailable
        }
    }

    private func get<T: Decodable>(_ path: String) async throws -> T {
        let data = try await dataRequest(path)
        do {
            return try decoder.decode(T.self, from: data)
        } catch {
            throw AutomationClientError.decodingFailed
        }
    }

    private func post<T: Decodable, Body: Encodable>(_ path: String, body: Body) async throws -> T {
        let payload: Data
        do {
            payload = try encoder.encode(body)
        } catch {
            throw AutomationClientError.decodingFailed
        }
        let data = try await dataRequest(path, method: "POST", body: payload)
        do {
            return try decoder.decode(T.self, from: data)
        } catch {
            throw AutomationClientError.decodingFailed
        }
    }

    private func postEmpty<Body: Encodable>(_ path: String, body: Body) async throws {
        let _: EmptyResponse = try await post(path, body: body)
    }

    private struct EmptyResponse: Decodable { }

    private func normalize(_ path: String) -> String {
        guard path.isEmpty == false else { return "/" }
        if path.hasPrefix("/") { return path }
        return "/" + path
    }

    private func apiPrefixed(_ path: String) -> String {
        if path == "/" {
            return "/api"
        }
        if path.hasPrefix("/api/") {
            return path
        }
        if path == "/api" {
            return path
        }
        return "/api" + (path.hasPrefix("/") ? path : "/" + path)
    }

    // MARK: - API surface

    func health() async throws -> AutomationHealth {
        struct HealthResponse: Decodable {
            let status: String
            let documents: Int?
        }
        let response: HealthResponse = try await get("/health")
        return AutomationHealth(ok: response.status.lowercased() == "ok", documentCount: response.documents ?? 0)
    }

    func permissions() async throws -> AutomationPermissions {
        struct PermissionsEnvelope: Decodable { let permissions: AutomationPermissions }
        let response: PermissionsEnvelope = try await get("/permissions")
        return response.permissions
    }

    func update(permissions: AutomationPermissions) async throws -> AutomationPermissions {
        struct UpdateBody: Encodable { let permissions: AutomationPermissions }
        struct UpdateEnvelope: Decodable { let permissions: AutomationPermissions }
        let response: UpdateEnvelope = try await post("/permissions", body: UpdateBody(permissions: permissions))
        return response.permissions
    }

    func modelConfiguration() async throws -> ModelConfiguration {
        let response: ModelConfiguration = try await get("/model")
        return response
    }

    func updateModelConfiguration(profileID: String, runtimeURL: String? = nil, backend: String? = nil) async throws -> ModelConfiguration {
        struct Body: Encodable {
            let profile: String
            let runtime_url: String?
            let backend: String?
        }
        let body = Body(profile: profileID, runtime_url: runtimeURL, backend: backend)
        let response: ModelConfiguration = try await post("/model", body: body)
        return response
    }

    func index(text: String, source: String = "ui") async throws -> String {
        struct IndexBody: Encodable { let text: String; let source: String }
        struct IndexResponse: Decodable { let id: String }
        let response: IndexResponse = try await post("/index", body: IndexBody(text: text, source: source))
        return response.id
    }

    func query(_ query: String, limit: Int = 5) async throws -> [QueryHit] {
        struct QueryBody: Encodable { let query: String; let limit: Int }
        struct QueryResponse: Decodable { let hits: [QueryHit] }
        let response: QueryResponse = try await post("/query", body: QueryBody(query: query, limit: limit))
        return response.hits
    }

    func plan(goal: String, params: PlanParameters? = nil) async throws -> [PlanAction] {
        struct PlanBody: Encodable {
            let goal: String
            let params: PlanParameters?
        }
        struct PlanResponse: Decodable { let actions: [PlanAction] }
        let response: PlanResponse = try await post("/plan", body: PlanBody(goal: goal, params: params))
        return response.actions
    }

    func listDocuments(limit: Int = 40) async throws -> [KnowledgeDocument] {
        struct DocsResponse: Decodable { let documents: [KnowledgeDocument] }
        let response: DocsResponse = try await get("/documents")
        return Array(response.documents.prefix(limit))
    }

    func fetchDocument(id: String) async throws -> KnowledgeDocumentDetail {
        struct DocResponse: Decodable {
            let id: String
            let source: String?
            let ts: TimeInterval?
            let text: String
        }
        let response: DocResponse = try await get("/documents/\(id)")
        return KnowledgeDocumentDetail(
            id: response.id,
            source: response.source ?? "unknown",
            timestamp: Date(timeIntervalSince1970: response.ts ?? 0),
            text: response.text
        )
    }

    func logs(limit: Int = 50) async throws -> [AutomationLogEvent] {
        struct AuditResponse: Decodable { let events: [AutomationLogEvent] }
        let response: AuditResponse = try await get("/audit")
        if response.events.count <= limit {
            return response.events
        }
        return Array(response.events.prefix(limit))
    }

    func appendLog(_ event: AutomationLogEventPayload) async throws {
        struct Payload: Encodable {
            let type: String
            let payload: [String: String]
            let ts: TimeInterval
        }
        let body = Payload(type: event.type, payload: event.payload, ts: event.timestamp.timeIntervalSince1970)
        try await postEmpty("/audit", body: body)
    }

    func execute(action: PlanAction) async throws -> Bool {
        let payload = AutomationLogEventPayload(
            type: "action_execute",
            payload: [
                "name": action.name,
                "payload": action.payload,
                "sensitive": String(action.sensitive),
                "preview_required": String(action.previewRequired)
            ],
            timestamp: Date()
        )
        do {
            try await appendLog(payload)
            return true
        } catch {
            return false
        }
    }

    func plugins() async throws -> [PluginManifestView] {
        struct PluginResponse: Decodable { let plugins: [PluginManifestView] }
        let response: PluginResponse = try await get("/plugins")
        return response.plugins
    }
}
