"""Top-level schemas package.

Each subpackage re-exports the Pydantic models that back one domain's
request/response surface. Many domain services keep their Pydantic
models alongside the service implementation; the ``app.schemas``
namespace exists so route handlers can pull typed response shapes from
a single import site.
"""
