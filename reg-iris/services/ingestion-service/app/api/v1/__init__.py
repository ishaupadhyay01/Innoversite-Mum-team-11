from app.api.v1 import alerts, documents, internal, versions

public_routers = [documents.router, versions.router, alerts.router]
internal_routers = [internal.router]
