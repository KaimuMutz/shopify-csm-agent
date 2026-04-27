# Client Onboarding — 15-minute checklist

For a new client store on an already-running deployment.

1. **Subdomain.** Add a CNAME for `csm.<client>.your-domain.com` pointing
   at the VPS. Caddy will issue the cert on first request.
2. **Shopify creds.** Create a custom app in the client's Shopify admin
   with `read_orders, read_customers, read_products` scopes. Save the
   Admin API access token.
3. **Webhook.** In Shopify → Settings → Notifications → Webhooks, add a
   webhook for the inbound channel (Customer contact request, Inbox,
   etc.) pointing to `https://csm.<client>.your-domain.com/webhooks/shopify`.
   Save the signing secret.
4. **Slack channel.** Create or pick an existing review channel. Invite
   the CSM bot.
5. **Brand voice block.** One paragraph describing the store's tone
   ("warm, slightly playful, never overly formal, sign off with 'Cheers,
   the <store> team'"). Goes into the `clients.brand_voice` column.
6. **Policy.** Confidence threshold (default 0.78), escalate-refunds
   (default true), escalate-address-changes (default true), daily token
   budget.
7. **Insert row.** `python scripts/add_client.py --slug <client> --token
   <shopify_token> --webhook-secret <secret> --slack-channel <#chan>
   --brand-voice "<voice>"`.
8. **Smoke test.** Send a test customer message via the Shopify contact
   form. Confirm the bot drafts a reply in the review channel.
9. **Handoff.** Share the `/admin/conversations/<client>` link (over
   Tailscale) with the client lead so they can audit decisions.
