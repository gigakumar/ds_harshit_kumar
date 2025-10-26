from core.runtime_gateway import GatewayToken, RuntimeEndpoint, RuntimeGateway


def test_register_and_retrieve_endpoints() -> None:
    gateway = RuntimeGateway()
    http_endpoint = RuntimeEndpoint(name="mlx", protocol="http", address="http://127.0.0.1:9000")
    grpc_endpoint = RuntimeEndpoint(name="assistant", protocol="grpc", address="127.0.0.1:50051")

    gateway.register(http_endpoint)
    gateway.register(grpc_endpoint)

    assert gateway.find("http", "mlx") == http_endpoint
    assert gateway.find("grpc", "assistant") == grpc_endpoint
    assert len(gateway.endpoints()) == 2


def test_issue_and_authenticate_token() -> None:
    gateway = RuntimeGateway()
    token = gateway.issue_token(scopes=["query", "index"])

    assert isinstance(token, GatewayToken)
    assert gateway.authenticate(token.value)
    assert gateway.authenticate(token.value, required_scope="query")
    assert not gateway.authenticate(token.value, required_scope="admin")

    assert gateway.revoke_token(token.value)
    assert not gateway.authenticate(token.value)


def test_snapshot_structure() -> None:
    gateway = RuntimeGateway()
    gateway.register(RuntimeEndpoint(name="mlx", protocol="http", address="http://127.0.0.1:9000"))
    gateway.issue_token(scopes=["query"])

    snap = gateway.snapshot()
    assert "endpoints" in snap and "http" in snap["endpoints"]
    assert len(snap["endpoints"]["http"]) == 1
    assert "tokens" in snap and len(snap["tokens"]) == 1
