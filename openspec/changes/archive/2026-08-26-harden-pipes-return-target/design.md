## Design

`cloud_connections._return_to()` returns one constant canonical URL. The
legacy environment variable remains readable for deployment compatibility but
cannot change the callback destination. This matches the existing WorkOS
Pipes connection design, which specifies a fixed return target under the
canonical MCP site.
