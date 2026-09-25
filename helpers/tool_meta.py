from mcp.types import ToolAnnotations

# Every source lookup here is a read against a public government catalog:
# nothing in this server ever writes to or mutates the source itself.
READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=True)

# The two operator tools (audit_bce_catalog, compare_bce_sources) write
# local snapshot/report artifacts instead of only answering a lookup, so
# they get their own annotation rather than READ_ONLY -- see
# docs/MCP_ARCHITECTURE.md's public/maintenance profile split.
WRITES_LOCAL_ARTIFACTS = ToolAnnotations(
    read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=True
)
