![License](https://img.shields.io/badge/license-MIT-blue)
![GenLayer](https://img.shields.io/badge/GenLayer-genlayer--js-6c5ce7)

# Crude Consensus — an OilPriceOracle dApp

A minimal, no-build-step web frontend for [OilPriceOracle](https://github.com/Mary1270/Genlayer-oilpriceoracle-v3), the multi-source, provenance-checked crude-oil price settlement Intelligent Contract on GenLayer. This is the **app layer** — real frontend logic that connects to a real, deployed GenLayer Intelligent Contract — as distinct from the contract submission itself.

**The contract source is included in this repository** (`contract.py`, plus its full offline test suite under `tests/`) alongside the frontend, so the client-side method mapping, source fetching, domain/endpoint checks, price comparison, validator-consensus pattern, and resolution guards this dApp calls into can all be reviewed together, in one place, as a single project — rather than requiring a separate repository lookup to see what `create_agreement`/`resolve_agreement`/`get_agreement` actually do server-side. It is identical to the version at [Genlayer-oilpriceoracle-v3](https://github.com/Mary1270/Genlayer-oilpriceoracle-v3), copied here for review convenience, not forked or modified.

**Live contract:** `0xe86C81d32530FCB2e18ba394a69169a79B3768d6` on GenLayer Studio
**Explorer:** https://explorer-studio.genlayer.com/address/0xe86C81d32530FCB2e18ba394a69169a79B3768d6
**Contract source (canonical repo):** https://github.com/Mary1270/Genlayer-oilpriceoracle-v3

---

## Repository layout

```
index.html      the entire frontend (this project) - HTML/CSS/JS, no build step
contract.py     the Intelligent Contract this frontend calls (included for review)
tests/          contract.py's offline test suite (135/135 passing) - see below
README.md
LICENSE
```

`create_agreement`/`resolve_agreement`/`get_agreement` in `index.html` map 1:1 onto the public methods defined in `contract.py`. To review what actually happens when this page's write calls trigger `resolve_agreement` server-side — the fetch → LLM-extraction pipeline, domain/endpoint allowlist checks, deterministic price comparison, and the `prompt_comparative` validator-consensus pattern — see `contract.py` directly, or its full design writeup in the [canonical OilPriceOracle repository](https://github.com/Mary1270/Genlayer-oilpriceoracle-v3)'s README.

```bash
python3 -m unittest discover -s tests -p "test_*.py" -v
```

---

## What this is

A single static page (`index.html`, no build step, no framework) that lets a person:

1. **Create an agreement** — fill in party names, oil type, threshold price, comparison direction, and (optionally) a committed source-domain policy, and submit `create_agreement` as a signed transaction.
2. **Resolve an agreement** — submit 3–6 candidate source URLs and call `resolve_agreement`, which triggers the contract's real fetch → LLM-extraction → validator-consensus pipeline on GenLayer Studio.
3. **Read an agreement** — call the read-only `get_agreement` method and see the full evidence trail (per-source domain, fetch status, quality flag, comparison) rendered as a readable list, plus the final verdict and winner.

All three actions call the deployed contract directly through [`genlayer-js`](https://github.com/genlayerlabs/genlayer-js), the official GenLayer JavaScript SDK — there is no backend server in between. The read call (`get_agreement`) uses an unauthenticated read client, since it doesn't need signing. For write calls (`create_agreement`, `resolve_agreement`), there are two ways to connect:

- **MetaMask** — click "connect MetaMask." Requires MetaMask (or another injected-provider wallet) installed and the GenLayer Studio network already added to it.
- **Test session** — click "start test session" instead. This generates a fresh, throwaway keypair in the browser using `genlayer-js`'s own `createAccount()`, with no external wallet or network configuration required at all. It holds no real value, isn't saved anywhere, and resets on page reload — useful for quickly trying the app (especially on mobile, where adding a custom network to a wallet app is more friction) without any wallet setup. If a transaction fails with an insufficient-funds error, that generated address needs test funds from GenLayer Studio's faucet first.

## Why a real GenLayer Portal "Project," not just an "Intelligent Contract" submission

The Portal's Intelligent Contracts category is for the contract primitive itself — which OilPriceOracle already was, and was accepted as, twice. This repository is the separate "app layer" the Projects category asks for: a real frontend with real app logic that actually calls a deployed Intelligent Contract's read and write methods, not a mockup or a demo screenshot.

## Design notes

The visual language is built around the subject: a crude-oil trading terminal. The signature element is the **consensus tape** — a horizontal, auto-scrolling ticker along the top of the page that renders each source's domain, its deterministic comparison (▲ Above / ▼ Below / ＝ Equal), and its extracted price, in the style of a market data tape, populated live from whatever agreement was last read. Typography pairs a slab-serif display face (industrial, technical) with a monospace face for all data, addresses, and the tape itself, and a plain sans for body copy — deliberately avoiding a generic "AI dashboard" look.

## Running it

No build step. Two options:

**Just open it:**
```bash
open index.html
```
(Some browsers restrict ES module imports from `file://` — if the page loads blank, use a static server instead.)

**Serve it locally:**
```bash
python3 -m http.server 8000
# then open http://localhost:8000
```

You'll need, for write actions, **one of**:
- A browser with [MetaMask](https://metamask.io) (or another injected-provider wallet) installed and the GenLayer Studio network configured, **or**
- Nothing at all — click "start test session" to generate a throwaway in-browser keypair instead (see "How it talks to GenLayer" below).

No wallet or session is required just to **read** an existing agreement by ID.

## How it talks to GenLayer

```js
import { createClient } from "genlayer-js";
import { studionet } from "genlayer-js/chains";

// Read-only (no wallet needed)
const readClient = createClient({ chain: studionet });
const agreement = await readClient.readContract({
  address: CONTRACT_ADDRESS,
  functionName: "get_agreement",
  args: [agreementId],
});

// Write, via MetaMask
const accounts = await window.ethereum.request({ method: "eth_requestAccounts" });
const client = createClient({ chain: studionet, account: accounts[0] });

// Write, via a throwaway in-browser test account (no wallet needed)
import { createAccount } from "genlayer-js";
const testAccount = createAccount();
const client = createClient({ chain: studionet, account: testAccount });

const txHash = await client.writeContract({
  address: CONTRACT_ADDRESS,
  functionName: "create_agreement",
  args: [partyA, partyB, oilType, threshold, comparison, description, requiredDomains],
});
await client.waitForTransactionReceipt({ hash: txHash, status: "FINALIZED" });
```

This page loads `genlayer-js` from a CDN (`esm.sh`) as an ES module, so it needs no `npm install` or bundler to run. For a production app, installing it via `npm install genlayer-js` and bundling normally is the recommended path — see the [GenLayerJS SDK reference](https://docs.genlayer.com/api-references/genlayer-js).

## What this dApp does NOT do

- It does not move funds. Neither this frontend nor the underlying contract implements escrow or payment — `create_agreement`/`resolve_agreement` only produce and record an adjudication decision. See OilPriceOracle's README for the full disclosure.
- It does not run its own backend, database, or indexer. Every read comes straight from `get_agreement` on-chain; there is no caching layer, so repeated reads are repeated contract calls.
- It does not manage wallets or private keys. It only requests `eth_requestAccounts` from whatever provider (e.g. MetaMask) is already injected into the browser.

## License

MIT — see `LICENSE`.
