# Runbook — Shopify CSM Agent

A linear, copy-pasteable guide to taking the agent from a fresh Hostinger /
GCP VPS to a working production deployment serving one or more client
stores.

## 1. Provision the VPS

Tested on Ubuntu 22.04 LTS, 1 vCPU / 2 GB RAM / 40 GB disk.

```bash
ssh root@<vps-ip>

# OS basics
apt update && apt -y upgrade
apt -y install git curl ufw fail2ban
useradd -m -s /bin/bash -G sudo eric
mkdir -p /home/eric/.ssh
cp ~/.ssh/authorized_keys /home/eric/.ssh/
chown -R eric:eric /home/eric/.ssh
chmod 700 /home/eric/.ssh && chmod 600 /home/eric/.ssh/authorized_keys

# Lock SSH
sed -i 's/^#PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
sed -i 's/^#PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
systemctl reload ssh

ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
```

## 2. Tailscale (admin plane)

```bash
curl -fsSL https://tailscale.com/install.sh | sh
tailscale up --ssh --hostname=csm-$(hostname)
# Bookmark the URL it prints to authorise the node in your tailnet.
```

After this, `ssh eric@csm-<host>` works from any of your tailnet machines
without exposing port 22 publicly. Long term, close port 22 in `ufw` and
rely on Tailscale SSH only.

## 3. Docker + Compose

```bash
curl -fsSL https://get.docker.com | sh
usermod -aG docker eric
```

## 4. App deploy

```bash
sudo -iu eric
git clone https://github.com/<your-handle>/shopify-csm-agent.git
cd shopify-csm-agent

cp .env.example .env
nano .env  # fill in tokens

# Tag the public host the Caddyfile expects
echo "PUBLIC_HOST=your-domain.com" >> .env

cd deploy
docker compose up -d --build
docker compose logs -f api
```

DNS: point `csm.your-domain.com` (and one CNAME per client subdomain) at
the VPS public IP. Caddy provisions Let's Encrypt certs automatically on
first request.

## 5. Hook up Shopify

In each client's Shopify admin → Settings → Notifications → Webhooks:

- Event: `Customer / contact request` (or whichever channel feeds you)
- Format: JSON
- URL: `https://csm.<client-subdomain>.your-domain.com/webhooks/shopify`

Copy the webhook signing secret into the corresponding row of the
`clients` table (or, for a single-tenant deploy, into `.env`).

## 6. Hook up Slack

1. Create a Slack app, enable Bots, install to your workspace.
2. Add scopes: `chat:write`, `chat:write.public`, `commands`.
3. Set Interactive Components request URL to
   `https://csm.your-domain.com/slack/callback`.
4. Copy the bot token + signing secret to `.env`.
5. Invite the bot to the review channel.

## 7. Smoke test

```bash
curl -X POST https://csm.your-domain.com/v1/messages \
     -H "Content-Type: application/json" \
     -d '{"customer_email":"sam@example.com",
          "body":"Where is order #1042?"}'
```

Expected response: `{"intent":"order_status","decision":"auto_send",...}`
or `escalate` if confidence is below threshold (with a Slack draft).

## 8. Day-2 ops

- **Logs.** `docker compose logs -f api worker`. Structured JSON; pipe
  to your log aggregator of choice.
- **Metrics.** `/admin/metrics` (Tailscale-only) exposes Prometheus
  counters: `csm_messages_total`, `csm_auto_sent_total`,
  `csm_escalated_total`, `csm_llm_tokens_total`.
- **Backups.** SQLite is mounted on the `csm-data` volume; nightly
  `litestream` replication to S3-compatible storage is recommended.
- **Updates.** `git pull && docker compose up -d --build`.
  Zero-downtime is not a goal — the worker drains in <5s.

## 9. Onboarding a new client

See `docs/client_onboarding.md` for the per-client steps (subdomain,
webhook secret, brand voice block, confidence threshold, Slack channel).
The whole thing is ~15 minutes per client once the platform is up.
