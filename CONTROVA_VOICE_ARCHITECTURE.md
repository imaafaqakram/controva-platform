# Controva Voice — "AI Employee" Platform
### Architecture & Build Plan

> A unified inbound + outbound AI voice platform built on top of the existing
> Controva Intelligence Platform. One real-time voice pipeline powers two
> products: an **AI Receptionist** (inbound) and an **AI SDR** (outbound).

---

## 1. The Insight

The existing asset stack is, accidentally, a complete voice-AI stack:

| Asset | Role in the voice pipeline |
|---|---|
| **Deepgram** | Speech-to-text — the agent's *ears* |
| **nexos.ai** | LLM gateway — the agent's *brain* (any model) |
| **Cartesia** | Low-latency TTS (~90ms) — the agent's *mouth* |
| **Krisp** | Noise suppression — cleans caller audio |
| **Controva** | Lead generation engine — supplies who to call |
| **Replicate / Imagine.art** | Generates website mockups to sell to SMBs |

The moat: most voice-AI companies must make customers bring their own leads.
Controva **generates** them. We own the full loop: *find → call → close*.

---

## 2. Core Architecture — One Loop, Two Modes

```
                    PHONE CALL  (Twilio)
                          |
              Media Stream (WebSocket, mu-law 8kHz audio)
                          |
        +-----------------v-----------------+
        |   VOICE ORCHESTRATOR (your VPS)   |
        |                                   |
        |  Krisp --> Deepgram --> nexos.ai  |
        |  (clean)   (hear)       (think)   |
        |                          |        |
        |              Cartesia <--+        |
        |              (speak)              |
        +-----------------+-----------------+
                          |
              back to caller's ear (~700ms target)
                          |
                  Controva PostgreSQL
        (logs call, transcript, outcome, cost)
```

- **Inbound (AI Receptionist):** an SMB client's number rings → agent answers,
  books appointments, takes messages, answers FAQs.
- **Outbound (AI SDR):** Controva finds + scores a lead → agent dials it →
  pitches, qualifies, books a meeting → writes outcome back to the lead record.

Identical code path. The only differences are **call direction** and the
**playbook** (system prompt + goal).

---

## 3. Technical Requirements of the Real-Time Loop

To feel human, the full round-trip (caller stops talking → agent replies) must
stay under ~800ms. That forces a few design rules:

1. **Stream everything.** No waiting for full sentences. Use Deepgram streaming
   partials and Cartesia streaming output chunks.
2. **Barge-in / interruption.** When the human starts speaking, the agent must
   stop talking immediately. Requires Voice Activity Detection (VAD).
3. **Audio format bridging.** Twilio Media Streams deliver base64 mu-law 8kHz
   over WebSocket. Convert to/from the PCM formats Deepgram and Cartesia expect.
4. **Fast model on nexos.ai.** Use a low-latency model for the live conversation;
   reserve premium models for post-call summarization.
5. **Async orchestrator.** A single Python asyncio WebSocket server multiplexing
   the Twilio stream, Deepgram socket, and Cartesia socket per call.

---

## 4. Telephony Decision

| Provider | Verdict | Notes |
|---|---|---|
| **Twilio** | **Use first** | Media Streams is battle-tested for exactly this. Best docs = fastest build. ~$1/mo per number + ~$0.013/min (verify). |
| **Telnyx** | Add later | ~3-5x cheaper per minute, also supports media streaming. Swap in for margin at scale. |
| **AWS Connect** | Skip for now | Full contact-center, slow to wire up. Spend the $100 AWS credit on compute instead. |

Reuse Controva's existing provider-toggle pattern:
`telephony: twilio | telnyx`. Switching later is a config change, not a rewrite.

---

## 5. Data Model — Extends Controva, Doesn't Replace It

Existing tables (`leads`, `contacts`, `assets`, `outreach_log`, etc.) stay as-is.
Add four:

```sql
-- The playbooks: each agent is a persona + goal + voice
voice_agents (
  id UUID, name TEXT, mode TEXT,           -- 'inbound' | 'outbound'
  system_prompt TEXT, goal TEXT,
  voice_id TEXT,                            -- Cartesia voice
  model TEXT,                               -- nexos.ai model id
  client_id UUID NULL,                      -- owning client (inbound)
  created_at TIMESTAMPTZ
)

-- Twilio/Telnyx numbers mapped to an agent or client
phone_numbers (
  id UUID, e164 TEXT, provider TEXT,        -- 'twilio' | 'telnyx'
  agent_id UUID, client_id UUID NULL,
  created_at TIMESTAMPTZ
)

-- Every call, inbound or outbound
calls (
  id UUID, agent_id UUID,
  lead_id UUID NULL,                        -- set for outbound
  client_id UUID NULL,                      -- set for inbound
  direction TEXT, from_e164 TEXT, to_e164 TEXT,
  status TEXT,                              -- ringing|in_progress|completed|failed|no_answer
  duration_sec INT, recording_url TEXT,
  transcript JSONB,                         -- turn-by-turn
  outcome TEXT, summary TEXT,               -- AI post-call summary
  cost_usd NUMERIC, created_at TIMESTAMPTZ
)

-- The SMBs paying for receptionist service (SaaS side)
clients (
  id UUID, business_name TEXT, contact_email TEXT,
  plan TEXT, status TEXT, created_at TIMESTAMPTZ
)
```

Linkage: outbound call -> `lead_id`; inbound call -> `client_id`.
Outbound outcomes also flow back into `outreach_log` and update `leads.status`.

---

## 6. Dashboard Additions

The existing React/Tailwind dashboard gets four new tabs:

- **Agents** — build/configure playbooks (prompt, voice, goal, model).
- **Numbers** — provision and map phone numbers.
- **Calls** — live call monitor + transcripts + recordings + outcomes + cost.
- **Clients** — manage receptionist customers (the SaaS side).

OpenClaw (self-hosted chat UI) becomes the internal "ask anything" console over
the whole database: *"How many demos did the SDR book this week?"*

---

## 7. Build Phasing

| Phase | Deliverable | Why this order |
|---|---|---|
| **0** | **Browser voice test** — talk to the agent via mic (WebRTC), no phone | Proves the Deepgram->nexos->Cartesia loop with **zero telephony cost** |
| **1** | **Inbound AI Receptionist** — 1 Twilio number, 1 agent, logs calls | First real calls; dogfood as Controva's own line |
| **2** | **Outbound AI SDR** — call Controva's scored leads, write back outcomes | Closes the find->call->close loop |
| **3** | **Multi-tenant SaaS** — many clients/numbers + usage billing | Becomes sellable recurring revenue |

---

## 8. Economics (rough — verify current pricing)

Per minute of conversation, approximate:

| Component | ~Cost/min |
|---|---|
| Twilio voice | ~$0.013 |
| Deepgram STT (streaming) | ~$0.004 |
| Cartesia TTS | ~$0.02-0.04 |
| nexos.ai (fast model) | ~$0.01-0.03 |
| **All-in** | **~$0.07-0.12 / min** |

Sell receptionist plans at **$100-300/mo** per SMB. With typical SMB call
volumes, gross margins are very healthy. Outbound SDR cost is justified by even
a low meeting-booking rate given Controva's lead targeting.

---

## 9. The Self-Funding Loop

Controva specializes in finding **SMBs with weak/no online presence** — exactly
the businesses that:
- miss inbound calls (need an **AI Receptionist**), and
- have no website (need the **mockups** Controva already generates).

So the go-to-market is self-referential:
1. Controva **finds** SMBs with no web presence.
2. The **AI SDR calls** them automatically.
3. What it **sells** is an AI Receptionist + a website.

The product finds, calls, and closes its own customers.

---

## 10. Open Questions / Next Decisions

- **Brand:** "Controva Voice" module vs standalone product name.
- **Compliance:** outbound calling requires consent/DNC handling (TCPA in US,
  similar elsewhere). Must design call-time-window + opt-out from day one.
- **Recording consent:** two-party-consent states require a disclosure prompt.
- **Concurrency target:** how many simultaneous calls in Phase 1? Drives VPS sizing.
- **First vertical:** which SMB niche to target first (e.g., salons, dental,
  trades) — narrower = better playbook + higher conversion.
