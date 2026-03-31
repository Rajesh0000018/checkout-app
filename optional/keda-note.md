# KEDA note for the current application

Your current gateway handles `/api/quote` by proxying to the quote service internally.

For HTTP scale-to-zero with the KEDA HTTP add-on, the public HTTP path must be routed through the KEDA interceptor. With the current app, you have two clean options:

1. **Direct quote ingress path**
   - expose quote directly via ingress, for example `/quote-direct`
   - route that path through the KEDA interceptor/HTTPScaledObject
   - use that path for cold/warm latency measurement

2. **Gateway change**
   - keep `/api/quote` on the gateway
   - change the gateway's `QUOTE_URL` to target the KEDA HTTP interceptor instead of `quote-svc`
   - this requires careful interceptor URL wiring

For the coursework, deploy the base app first, validate it, then add KEDA as a second phase.
